"""Bounded BHASHINI/ULCA OCR adapter for document crops.

The published ULCA model registry documents the ``tryMe`` multipart contract
(``file`` + ``modelId``) and ``output[].source`` response used here. The older
authenticated Dhruva pipeline OCR payload could not be confirmed, so secret
values are deliberately never attached to this request.
"""

from __future__ import annotations

import hashlib
import io
import json
import threading
import time
import urllib.error
import urllib.request
import uuid
from typing import Any

from PIL import Image

from config import BHASHINI_INFERENCE_KEY, BHASHINI_UDYAT_KEY


ULCA_OCR_ENDPOINT = "https://meity-auth.ulcacontrib.org/ulca/apis/v0/model/tryMe"
BHASHINI_MODEL_IDS = {
    "handwritten": "6384a69cff7cd87a3f7e1013",
    "printed": "63846bb986369150cb004335",
}
# OCR remains useful with BHASHINI unavailable.  A short bounded probe and a
# longer circuit prevent a failing provider from adding repeated latency to one
# officer's extraction queue.
BHASHINI_TIMEOUT_SECONDS = 3
BHASHINI_CIRCUIT_SECONDS = 300

_state_lock = threading.RLock()
_circuit_open_until = 0.0


def credential_status() -> dict[str, str]:
    """Expose configuration state without ever returning credential values."""

    return {
        "udyat_key": "SET" if BHASHINI_UDYAT_KEY else "MISSING",
        "inference_key": "SET" if BHASHINI_INFERENCE_KEY else "MISSING",
    }


def provider_runtime_status() -> str:
    """Return a non-secret readiness value suitable for routing decisions."""
    if not BHASHINI_UDYAT_KEY or not BHASHINI_INFERENCE_KEY:
        return "missing_configuration"
    with _state_lock:
        return "circuit_open" if time.monotonic() < _circuit_open_until else "ready"


def _empty(status: str, reason: str, *, model_id: str | None = None) -> dict[str, Any]:
    return {
        "text": "",
        "confidence": None,
        "confidence_type": "unavailable",
        "status": status,
        "reason": reason,
        "provider": "BHASHINI",
        "model_id": model_id,
        "api_contract": "ulca_published_try_me_multipart_v0",
    }


def _encode_png(image: Image.Image) -> bytes:
    output = io.BytesIO()
    image.convert("RGB").save(output, format="PNG", optimize=True)
    return output.getvalue()


def _multipart(image_bytes: bytes, model_id: str) -> tuple[bytes, str]:
    boundary = f"----landsight-{uuid.uuid4().hex}"
    chunks: list[bytes] = []

    def add(name: str, value: bytes, filename: str | None = None, content_type: str | None = None) -> None:
        disposition = f'Content-Disposition: form-data; name="{name}"'
        if filename:
            disposition += f'; filename="{filename}"'
        headers = [f"--{boundary}", disposition]
        if content_type:
            headers.append(f"Content-Type: {content_type}")
        chunks.append(("\r\n".join(headers) + "\r\n\r\n").encode("ascii"))
        chunks.append(value)
        chunks.append(b"\r\n")

    add("file", image_bytes, "crop.png", "image/png")
    add("modelId", model_id.encode("ascii"))
    chunks.append(f"--{boundary}--\r\n".encode("ascii"))
    return b"".join(chunks), boundary


def _parse_response(payload: Any, model_id: str) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return _empty("malformed_response", "response_is_not_an_object", model_id=model_id)
    output = payload.get("output")
    if not isinstance(output, list) or not output or not isinstance(output[0], dict):
        return _empty("malformed_response", "output_array_missing", model_id=model_id)
    source = output[0].get("source")
    if not isinstance(source, str):
        return _empty("malformed_response", "source_text_missing", model_id=model_id)
    return {
        "text": source.strip(),
        "raw_text": source,
        "confidence": None,
        "confidence_type": "provider_did_not_return_confidence",
        "status": "ready",
        "provider": "BHASHINI",
        "model_id": model_id,
        "api_contract": "ulca_published_try_me_multipart_v0",
    }


def recognize_crop(
    image: Image.Image,
    *,
    handwritten: bool,
    cache: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Recognize one crop without allowing provider failure to escape."""

    global _circuit_open_until

    # Requiring both configured keys makes external OCR an explicit deployment
    # opt-in. They are not sent because this published endpoint documents no
    # auth header and the Dhruva OCR auth contract was not confirmed.
    if not BHASHINI_UDYAT_KEY or not BHASHINI_INFERENCE_KEY:
        return _empty("missing_configuration", "bhashini_keys_missing")

    model_id = BHASHINI_MODEL_IDS["handwritten" if handwritten else "printed"]
    image_bytes = _encode_png(image)
    cache_key = hashlib.sha256(model_id.encode("ascii") + image_bytes).hexdigest()
    if cache is not None and cache_key in cache:
        return {**cache[cache_key], "cache_hit": True}

    with _state_lock:
        if time.monotonic() < _circuit_open_until:
            return _empty("skipped", "provider_circuit_open", model_id=model_id)

    body, boundary = _multipart(image_bytes, model_id)
    request = urllib.request.Request(
        ULCA_OCR_ENDPOINT,
        data=body,
        headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Accept": "application/json",
            "User-Agent": "LANDSiGHT-Server/1.0",
        },
        method="POST",
    )
    holder: dict[str, dict[str, Any]] = {}

    def perform_request() -> None:
        try:
            with urllib.request.urlopen(request, timeout=BHASHINI_TIMEOUT_SECONDS) as response:
                payload = json.loads(response.read())
            holder["result"] = _parse_response(payload, model_id)
        except urllib.error.HTTPError as exc:
            reason = "rate_limited" if exc.code == 429 else (
                "authentication_rejected" if exc.code in {401, 403} else f"http_{exc.code}"
            )
            holder["result"] = _empty("failed", reason, model_id=model_id)
        except (TimeoutError, urllib.error.URLError):
            holder["result"] = _empty("failed", "network_or_timeout", model_id=model_id)
        except (json.JSONDecodeError, UnicodeDecodeError):
            holder["result"] = _empty("malformed_response", "invalid_json", model_id=model_id)
        except Exception as exc:
            holder["result"] = _empty("failed", type(exc).__name__, model_id=model_id)

    # DNS/TLS setup can exceed urllib's socket timeout. A daemon worker gives
    # the request path a strict wall-clock bound without blocking extraction.
    worker = threading.Thread(target=perform_request, daemon=True)
    worker.start()
    worker.join(BHASHINI_TIMEOUT_SECONDS)
    result = holder.get("result") or _empty("failed", "network_or_timeout", model_id=model_id)

    if result["status"] in {"failed", "malformed_response"}:
        with _state_lock:
            _circuit_open_until = time.monotonic() + BHASHINI_CIRCUIT_SECONDS
    if cache is not None:
        cache[cache_key] = result
    return result
