"""Field-aware Khatauni OCR helpers.

The constants here describe layout and schema only. Values always come from
real recognition engines run on uploaded document crops.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
import hashlib
import math
import os
import re
import threading
import time
import unicodedata
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import pytesseract
from PIL import Image, ImageOps

from config import TESSERACT_LANGUAGES, TESSERACT_CMD
from khatauni_schema import HEADER_FIELDS, TABLE_COLUMNS


HTR_MODEL_ID = os.getenv("KHATAUNI_HTR_MODEL", "aayushpuri01/TrOCR-Devanagari")
ENABLE_LOCAL_HTR = os.getenv("KHATAUNI_ENABLE_HTR", "1").lower() not in {"0", "false", "no", "off"}
try:
    HTR_MAX_CROPS = max(0, int(os.getenv("KHATAUNI_HTR_MAX_CROPS", "4")))
except ValueError:
    HTR_MAX_CROPS = 4
DEVANAGARI_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")


@dataclass(frozen=True)
class Region:
    key: str
    box: tuple[float, float, float, float]
    kind: str = "text"


HEADER_REGIONS = [
    # These are value-side regions, not generic header strips.  The small
    # vertical margin preserves a handwritten shirorekha/matra without
    # reaching the adjacent labelled line on the standard Khatauni layout.
    Region("village_name", (0.15, 0.057, 0.41, 0.086), "handwritten"),
    Region("tehsil", (0.16, 0.096, 0.41, 0.145), "handwritten"),
    Region("district", (0.47, 0.100, 0.74, 0.145), "handwritten"),
    Region("crop_year", (0.17, 0.130, 0.42, 0.170), "numeric"),
    Region("khata_number", (0.83, 0.116, 0.97, 0.139), "numeric"),
    Region("holder_name", (0.25, 0.155, 0.54, 0.197), "handwritten"),
    Region("guardian_name", (0.25, 0.183, 0.57, 0.222), "handwritten"),
]


TABLE_KEY_BY_TEMPLATE = {
    "plot_number": (0, 1, "numeric"),
    "area": (1, 4, "numeric"),
    "land_type": (4, 5, "text"),
    "irrigation_source": (5, 6, "text"),
    "revenue": (8, 9, "numeric"),
    "holder_name": (9, 10, "handwritten"),
    "order_remarks": (10, 11, "text"),
}


_htr_cache: dict[str, Any] = {"state": "not_loaded"}
_htr_lock = threading.RLock()
HTR_CACHE_DIR = str(Path(__file__).resolve().parent / "models")


def _clean_text(value: str, numeric: bool = False) -> str:
    value = (value or "").translate(DEVANAGARI_DIGITS)
    value = value.replace("\n", " ").replace("|", " ")
    value = re.sub(r"\s+", " ", value).strip(" _.,:;~-—'\"")
    if numeric:
        kept = re.findall(r"[0-9]+(?:[./-][0-9]+)*", value)
        return " ".join(kept).strip()
    return value


def _devanagari_score(value: str) -> float:
    letters = re.findall(r"[\w\u0900-\u097f]", value, flags=re.UNICODE)
    if not letters:
        return 0.0
    indic = re.findall(r"[\u0900-\u097f]", value)
    return len(indic) / len(letters)


def _suspicious_hindi_candidate(value: str, kind: str) -> bool:
    """Reject obvious Latin/mixed-script OCR noise for Hindi value regions.

    This does not substitute or transliterate text.  It only prevents a
    visibly implausible candidate from winning over an unresolved value or a
    real alternate recognizer result.
    """
    if kind == "numeric" or not value:
        return False
    devanagari = len(re.findall(r"[\u0900-\u097f]", value))
    latin = len(re.findall(r"[A-Za-z]", value))
    letters = devanagari + latin
    return bool(latin and (not devanagari or devanagari / max(letters, 1) < 0.60))


def _confidence_level(value: float | None) -> str:
    if value is None:
        return "UNAVAILABLE"
    if value >= 90:
        return "HIGH"
    if value >= 70:
        return "MEDIUM"
    return "LOW"


def _empty_htr(status: str, reason: str | None = None) -> dict[str, Any]:
    payload = {"text": "", "model_score": None, "status": status}
    if reason:
        payload["reason"] = reason
    return payload


def _should_try_htr(tesseract: dict[str, Any], kind: str) -> tuple[bool, str]:
    if kind != "handwritten":
        return False, "not_handwritten"
    if not ENABLE_LOCAL_HTR:
        return False, "disabled"
    text = tesseract.get("text") or ""
    confidence = tesseract.get("confidence")
    if not text:
        return True, "no_tesseract_text"
    if (confidence or 0) < 55:
        return True, "low_tesseract_confidence"
    if _devanagari_score(text) < 0.45:
        return True, "weak_devanagari_candidate"
    if (confidence or 0) < 75 and tesseract.get("pass_agreement", 0) < 0.35:
        return True, "low_candidate_agreement"
    return False, "tesseract_candidate_sufficient"


def _crop_key(crop: Image.Image, prefix: str) -> str:
    gray = crop.convert("L")
    digest = hashlib.sha256(gray.tobytes()).hexdigest()
    return f"{prefix}:{gray.width}x{gray.height}:{digest}"


def _maybe_htr(
    crop: Image.Image,
    tesseract: dict[str, Any],
    kind: str,
    budget: dict[str, int] | None,
    cache: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    # A failed local model load is process-wide.  Do not consume the bounded
    # crop budget repeatedly once its runtime is known unavailable.
    if _htr_cache.get("state") == "unavailable":
        if budget is not None:
            budget["skipped"] = budget.get("skipped", 0) + 1
        return _empty_htr("skipped", "local_htr_unavailable")
    should, reason = _should_try_htr(tesseract, kind)
    if not should:
        if budget is not None:
            budget["skipped"] = budget.get("skipped", 0) + 1
        return _empty_htr("skipped", reason)
    cache_key = _crop_key(crop, "htr")
    if cache is not None and cache_key in cache:
        return {**cache[cache_key], "cache_hit": True}
    if budget is not None:
        if budget.get("remaining", 0) <= 0:
            budget["skipped"] = budget.get("skipped", 0) + 1
            return _empty_htr("skipped", "htr_budget_exhausted")
        budget["remaining"] = budget.get("remaining", 0) - 1
        budget["attempted"] = budget.get("attempted", 0) + 1
    result = _htr_candidate(crop)
    if cache is not None:
        cache[cache_key] = result
    return result


def _numeric_variants(tesseract: dict[str, Any]) -> set[str]:
    return {
        str(candidate.get("text") or "")
        for candidate in tesseract.get("passes", [])
        if candidate.get("text")
    }


def _crop(image: Image.Image, box: tuple[float, float, float, float]) -> Image.Image:
    width, height = image.size
    left, top, right, bottom = box
    # ROI definitions are deliberately value-side and tight.  A few pixels of
    # adaptive padding protects first/last digits and Devanagari matras while
    # retaining the label/value separation.
    pad_x = max(2, round(width * .0025))
    pad_y = max(2, round(height * .0025))
    return image.crop((max(0, int(left * width) - pad_x), max(0, int(top * height) - pad_y),
                       min(width, int(right * width) + pad_x), min(height, int(bottom * height) + pad_y)))


def _prepare_crop(crop: Image.Image, scale: int = 3) -> Image.Image:
    gray = ImageOps.grayscale(crop)
    gray = ImageOps.autocontrast(gray)
    if scale > 1:
        gray = gray.resize((gray.width * scale, gray.height * scale), Image.Resampling.LANCZOS)
    return gray


def _clean_crop(crop: Image.Image, remove_slanted: bool = False) -> Image.Image:
    """An alternate crop, with only long lower ruling removed.

    Never erode/open the handwriting itself. Keep all original crop evidence
    in the other pass. Trim the surrounding paper using component geometry;
    retain dots/matras inside the resulting text rectangle.
    """
    gray = np.asarray(crop.convert("L"))
    mask = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
    lines = cv2.morphologyEx(mask, cv2.MORPH_OPEN,
        cv2.getStructuringElement(cv2.MORPH_RECT, (max(30, int(crop.width * .30)), 1)))
    lines[:int(crop.height * .55)] = 0
    segments = cv2.HoughLinesP(mask, 1, np.pi/180, threshold=25,
        minLineLength=max(35, int(crop.width*.3)), maxLineGap=8)
    if remove_slanted and segments is not None:
        for x1,y1,x2,y2 in segments[:,0]:
            if min(y1,y2) > crop.height*.55 and abs(y2-y1) <= max(2, abs(x2-x1)*.035):
                cv2.line(lines, (x1,y1), (x2,y2), 255, 2)
    mask[lines > 0] = 0
    count, labels, stats, _ = cv2.connectedComponentsWithStats(mask)
    boxes = [(x,y,w,h) for x,y,w,h,area in stats[1:] if h >= 4 and w >= 2 and area >= 6]
    if not boxes:
        return Image.fromarray(255-mask)
    left = max(0, min(x for x,y,w,h in boxes)-2)
    top = max(0, min(y for x,y,w,h in boxes)-2)
    right = min(crop.width, max(x+w for x,y,w,h in boxes)+2)
    bottom = min(crop.height, max(y+h for x,y,w,h in boxes)+2)
    return ImageOps.expand(Image.fromarray(255-mask[top:bottom,left:right]), border=5, fill=255)


def _tesseract_candidate(
    crop: Image.Image,
    kind: str,
    *,
    cache: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Run one primary field OCR pass and at most one evidence-based retry."""
    numeric = kind == "numeric"
    cache_key = _crop_key(crop, f"tesseract:{kind}")
    if cache is not None and cache_key in cache:
        return {**cache[cache_key], "cache_hit": True}

    passes: list[dict[str, Any]] = []
    pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD

    def run_pass(variant: str, prepared: Image.Image, config: str, languages: str) -> dict[str, Any]:
        try:
            data = pytesseract.image_to_data(
                prepared,
                lang=languages,
                config=config,
                output_type=pytesseract.Output.DICT,
                timeout=20,
            )
        except Exception as exc:
            return {"text": "", "confidence": None, "variant": variant, "config": config,
                    "languages": languages, "error": f"{type(exc).__name__}: {exc}"}
        tokens = [{"text": text, "confidence": float(data["conf"][i]),
                   "bbox": {key: int(data[key][i]) for key in ("left", "top", "width", "height")}}
                  for i, text in enumerate(data["text"]) if text.strip()]
        raw_text = " ".join(token["text"] for token in tokens)
        confidences = [token["confidence"] for token in tokens if token["confidence"] >= 0]
        text = _clean_text(raw_text, numeric=numeric)
        confidence = sum(confidences) / len(confidences) if confidences else None
        valid = bool(re.fullmatch(r"[0-9]+(?:[./ -][0-9]+)*", _clean_text(raw_text))) if numeric else bool(text)
        return {"text": text, "raw_text": raw_text, "confidence": confidence, "config": config,
                "variant": variant, "languages": languages, "tokens": tokens, "format_valid": valid}

    # A line-oriented Hindi+English pass is the default for value crops.  For
    # numbers the isolated-word PSM keeps adjacent ruling and labels from
    # becoming digits.  Numeric-only OCR is deliberately limited to numbers.
    primary_config = "--psm 8" if numeric else "--psm 7"
    primary = run_pass("grayscale", _prepare_crop(crop, 4), primary_config, TESSERACT_LANGUAGES)
    passes.append(primary)
    weak_primary = (
        not primary.get("text")
        or (primary.get("confidence") or 0) < 65
        or (numeric and not primary.get("format_valid"))
        or _suspicious_hindi_candidate(primary.get("text") or "", kind)
    )
    if weak_primary:
        retry_config = "--psm 8 -c tessedit_char_whitelist=0123456789./-" if numeric else "--psm 7"
        retry_language = "eng" if numeric else TESSERACT_LANGUAGES
        passes.append(run_pass("line_clean", _prepare_crop(_clean_crop(crop), 4), retry_config, retry_language))
    usable = [p for p in passes if p["text"]]
    if not usable:
        result = {"text": "", "confidence": None, "passes": passes}
        if cache is not None:
            cache[cache_key] = result
        return result
    def rank(p):
        agreement = sum(q["text"] == p["text"] for q in usable) / len(usable)
        return ((1 if numeric and p.get("format_valid") else 0), float(p["confidence"] or 0) + agreement * 12
                + (15 if numeric and p.get("format_valid") else 0)
                + (_devanagari_score(p["text"]) * 10 if kind != "numeric" else 0)
                - (25 if _suspicious_hindi_candidate(p["text"], kind) else 0))
    best = max(usable, key=rank)
    result = {**best, "pass_agreement": sum(p["text"] == best["text"] for p in usable) / len(usable), "passes": passes}
    if cache is not None:
        cache[cache_key] = result
    return result


def _load_htr() -> dict[str, Any]:
    with _htr_lock:
        return _load_htr_locked()


def _load_htr_locked() -> dict[str, Any]:
    if _htr_cache.get("state") != "not_loaded":
        return _htr_cache
    try:
        import torch
        from transformers import ViTImageProcessor, RobertaTokenizer, TrOCRProcessor, VisionEncoderDecoderModel
        from huggingface_hub import snapshot_download

        # Model acquisition is a separate explicit setup step. Requests never
        # transmit images or attempt a model download during extraction.
        path = HTR_MODEL_ID if os.path.isdir(HTR_MODEL_ID) else snapshot_download(
            HTR_MODEL_ID, cache_dir=HTR_CACHE_DIR, local_files_only=True,
            allow_patterns=["*.json", "*.txt", "*.safetensors"])
        processor = TrOCRProcessor(
            image_processor=ViTImageProcessor.from_pretrained(path, local_files_only=True),
            tokenizer=RobertaTokenizer.from_pretrained(path, local_files_only=True))
        model = VisionEncoderDecoderModel.from_pretrained(path, local_files_only=True)
        device = "cuda" if torch.cuda.is_available() else "cpu"
        if device == "cpu":
            torch.set_num_threads(max(1, min(4, os.cpu_count() or 1)))
        model.to(device)
        model.eval()
        _htr_cache.update(state="ready", processor=processor, model=model, torch=torch, device=device, cache=path)
    except Exception as exc:
        _htr_cache.update(state="unavailable", error=f"{type(exc).__name__}: {exc}", model_id=HTR_MODEL_ID)
    return _htr_cache


def _htr_single(crop: Image.Image) -> dict[str, Any]:
    state = _load_htr()
    if state.get("state") != "ready":
        return {"text": "", "model_score": None, "status": state.get("state"), "error": state.get("error")}
    try:
        image = _prepare_crop(crop, 1).convert("RGB")
        # The model author's preprocessing preserves aspect ratio and pads to
        # 224 square. Direct ViT resizing stretches thin lines into tall glyphs.
        size = state["processor"].image_processor.size
        image = ImageOps.pad(image, (size["width"],size["height"]), color="white")
        inputs = state["processor"](images=image, return_tensors="pt")
        pixel_values = inputs.pixel_values.to(state["device"])
        with _htr_lock, state["torch"].inference_mode():
            generated = state["model"].generate(pixel_values, max_length=48, num_beams=1,
                do_sample=False, return_dict_in_generate=True, output_scores=True)
        text = state["processor"].batch_decode(generated.sequences, skip_special_tokens=True, clean_up_tokenization_spaces=False)[0]
        text = _clean_text(text)
        ids = generated.sequences[0, -len(generated.scores):].tolist() if generated.scores else []
        special = set(state["processor"].tokenizer.all_special_ids)
        logs = [float(logits[0].log_softmax(-1)[token].item())
                for token, logits in zip(ids, generated.scores) if token not in special]
        score = math.exp(sum(logs) / len(logs)) if logs and text else None
        return {"text": text, "model_score": score, "score_type": "uncalibrated_token_probability_geometric_mean",
                "token_log_probabilities": logs, "truncated": bool(ids and ids[-1] not in special and len(ids) >= 40),
                "status": "ready", "model": HTR_MODEL_ID, "device": state["device"]}
    except Exception as exc:
        return {"text": "", "model_score": None, "status": "failed", "error": f"{type(exc).__name__}: {exc}", "model": HTR_MODEL_ID}


def _htr_candidate(crop: Image.Image) -> dict[str, Any]:
    line = _htr_single(crop)
    if line.get("status") != "ready":
        return line
    clean = _clean_crop(crop, remove_slanted=True)
    occupied = np.any(np.asarray(clean) < 128, axis=0)
    spans, start = [], None
    for x, used in enumerate([*occupied, False]):
        if used and start is None:
            start = x
        if not used and start is not None:
            if spans and start-spans[-1][1] < max(6, clean.height*.20):
                spans[-1] = (spans[-1][0], x)
            else:
                spans.append((start,x))
            start = None
    spans = [(left,right) for left,right in spans if right-left >= 5]
    if not 2 <= len(spans) <= 6:
        return line
    words = [_htr_single(ImageOps.expand(clean.crop((left,0,right,clean.height)), border=5, fill=255))
             for left,right in spans]
    if not all(word.get("text") for word in words):
        return {**line, "word_candidates": words}
    logs = [value for word in words for value in word.get("token_log_probabilities", [])]
    score = math.exp(sum(logs)/len(logs)) if logs else 0
    if score <= (line.get("model_score") or 0):
        return {**line, "word_candidates": words}
    return {**line, "text": " ".join(word["text"] for word in words), "model_score": score,
            "token_log_probabilities": logs, "segmentation": "word_gaps_in_line_crop",
            "word_candidates": words, "line_candidate": line,
            "truncated": any(word.get("truncated") for word in words)}


def _comparison_text(value: str, kind: str) -> str:
    value = unicodedata.normalize("NFKC", value or "").translate(DEVANAGARI_DIGITS)
    value = re.sub(r"\s+", " ", value).strip()
    if kind == "numeric":
        return re.sub(r"\s+", "", value)
    return value.casefold().strip(" .,:;|_-'\"")


def _candidate_similarity(left: str, right: str, kind: str) -> float:
    left_value, right_value = _comparison_text(left, kind), _comparison_text(right, kind)
    if not left_value or not right_value:
        return 0.0
    if kind == "numeric":
        return 1.0 if left_value == right_value else 0.0
    from rapidfuzz.fuzz import ratio

    return ratio(left_value, right_value) / 100


def _calculate_evidence_confidence(
    selected_text: str,
    selected_engine: str | None,
    tesseract: dict[str, Any],
    htr: dict[str, Any],
    kind: str,
    agreements: dict[str, float],
    supporting_engines: list[str],
    warnings: list[str],
) -> tuple[float | None, str, dict[str, Any]]:
    """Derive a bounded evidence-strength score from existing recognition data.

    This post-selection helper does not invoke recognizers or alter candidate
    choice. Its output is an explainable evidence score, not a probability.
    """
    raw_tesseract_confidence = tesseract.get("confidence")
    raw_htr_model_score = htr.get("model_score")
    agreement_similarity = agreements.get("tesseract_htr")
    pass_agreement = tesseract.get("pass_agreement")
    breakdown: dict[str, Any] = {
        "selected_engine": selected_engine,
        "engine_base": None,
        "raw_tesseract_confidence": raw_tesseract_confidence,
        "raw_htr_model_score": raw_htr_model_score,
        "agreement_similarity": agreement_similarity,
        "agreement_bonus": 0,
        "pass_agreement": pass_agreement,
        "stability_bonus": 0,
        "validation_bonus": 0,
        "penalties": [],
        "applied_caps": [],
        "final_score": None,
    }
    method = "bhumiai_evidence_score_v1_uncalibrated"
    if not selected_text or selected_engine is None:
        return None, method, breakdown

    if selected_engine == "TESSERACT":
        if raw_tesseract_confidence is None:
            return None, method, breakdown
        try:
            engine_base = max(0.0, min(100.0, float(raw_tesseract_confidence)))
        except (TypeError, ValueError):
            return None, method, breakdown
    elif selected_engine == "HTR":
        # TrOCR's geometric mean token score is retained as raw evidence but
        # deliberately is not scaled into a percentage.
        engine_base = 50.0
    else:
        return None, method, breakdown
    breakdown["engine_base"] = engine_base

    # Agreements are populated only when both local candidates passed their
    # existing usability checks, so this cannot double-count OCR pass stability.
    if agreement_similarity is not None:
        if agreement_similarity >= 0.95:
            breakdown["agreement_bonus"] = 15
        elif agreement_similarity >= 0.90:
            breakdown["agreement_bonus"] = 10
        elif agreement_similarity >= 0.80:
            breakdown["agreement_bonus"] = 5

    if selected_engine == "TESSERACT" and pass_agreement is not None:
        if pass_agreement >= 0.95:
            breakdown["stability_bonus"] = 5
        elif pass_agreement >= 0.50:
            breakdown["stability_bonus"] = 2

    numeric_valid = bool(re.fullmatch(r"[0-9]+(?:[./ -][0-9]+)*", selected_text))
    if kind == "numeric":
        if numeric_valid:
            breakdown["validation_bonus"] = 5
    elif _devanagari_score(selected_text) >= 0.90:
        breakdown["validation_bonus"] = 5

    penalty_total = 0
    caps: list[tuple[str, float]] = []
    if "engine_disagreement" in warnings:
        breakdown["penalties"].append({"reason": "engine_disagreement", "value": -15})
        penalty_total += 15
        caps.append(("engine_disagreement", 59))
    if "tesseract_digit_disagreement" in warnings:
        breakdown["penalties"].append({"reason": "tesseract_digit_disagreement", "value": -15})
        penalty_total += 15
        caps.append(("tesseract_digit_disagreement", 49))
    if kind == "numeric" and not numeric_valid:
        caps.append(("invalid_numeric_format", 35))
    if "mixed_script_review" in warnings:
        caps.append(("mixed_script_review", 39))
    if selected_engine == "HTR" and htr.get("truncated") is True:
        caps.append(("truncated_htr", 39))

    score = (
        engine_base
        + breakdown["agreement_bonus"]
        + breakdown["stability_bonus"]
        + breakdown["validation_bonus"]
        - penalty_total
    )
    for reason, maximum in caps:
        breakdown["applied_caps"].append({"reason": reason, "max_score": maximum})
        score = min(score, maximum)
    score = round(max(0.0, min(100.0, score)), 2)
    breakdown["final_score"] = score
    return score, method, breakdown


def _select(
    tesseract: dict[str, Any],
    htr: dict[str, Any],
    kind: str,
) -> dict[str, Any]:
    t_text = tesseract.get("text") or ""
    h_text = htr.get("text") or ""
    t_conf = tesseract.get("confidence")
    h_score = htr.get("model_score")

    t_usable = bool(t_text and not _suspicious_hindi_candidate(t_text, kind))
    h_usable = bool(h_text and _devanagari_score(h_text) >= 0.55 and not htr.get("truncated"))
    usable = {
        **({"TESSERACT": t_text} if t_usable else {}),
        **({"HTR": h_text} if h_usable else {}),
    }
    agreements: dict[str, float] = {}
    names = list(usable)
    for index, left in enumerate(names):
        for right in names[index + 1:]:
            agreements[f"{left.lower()}_{right.lower()}"] = round(
                _candidate_similarity(usable[left], usable[right], kind), 3
            )
    support = {name: [name] for name in names}
    for pair, score in agreements.items():
        if score < 0.9:
            continue
        left, right = pair.upper().split("_", 1)
        support[left].append(right)
        support[right].append(left)

    strong_t = bool(
        t_usable
        and (
            (t_conf or 0) >= 75 and tesseract.get("pass_agreement", 0) >= 0.5
            or _devanagari_score(t_text) >= 0.95 and len(t_text) >= 4 and (t_conf or 0) >= 45
        )
    )
    best_supported = max(support, key=lambda name: (len(set(support[name])), name == "TESSERACT"), default=None)
    warnings: list[str] = []
    supporting_engines: list[str] = []

    if best_supported and len(set(support[best_supported])) >= 2:
        supporting_engines = sorted(set(support[best_supported]))
        if kind == "handwritten" and "HTR" in supporting_engines and not strong_t:
            engine = "HTR"
        elif "TESSERACT" in supporting_engines:
            engine = "TESSERACT"
        else:
            engine = best_supported
        selected_text = usable[engine]
        reason = "selected candidate supported by independent recognizer agreement"
    elif kind == "numeric":
        if t_usable:
            selected_text, engine = t_text, "TESSERACT"
            reason = "numeric Tesseract candidate retained without independent agreement"
        else:
            selected_text, engine = "", None
            reason = "no format-valid numeric candidate"
    elif h_usable and not strong_t and (not t_text or (h_score or 0) >= 0.25):
        selected_text, engine = h_text, "HTR"
        reason = "usable Devanagari HTR candidate with no stable Tesseract candidate"
    elif t_usable:
        selected_text, engine = t_text, "TESSERACT"
        reason = "strongest local Tesseract candidate retained"
    elif h_usable:
        selected_text, engine = h_text, "HTR"
        reason = "only usable local HTR candidate; officer review required"
    else:
        selected_text, engine = "", None
        reason = "no recognizer produced a trustworthy candidate"

    if len(usable) >= 2 and not supporting_engines:
        warnings.append("engine_disagreement")
    if kind == "numeric" and len(_numeric_variants(tesseract)) > 1:
        warnings.append("tesseract_digit_disagreement")
    if t_text and not t_usable:
        warnings.append("mixed_script_review")

    confidence, confidence_method, confidence_breakdown = _calculate_evidence_confidence(
        selected_text,
        engine,
        tesseract,
        htr,
        kind,
        agreements,
        supporting_engines,
        warnings,
    )

    compact_candidates = {
        "tesseract": {
            "raw_text": tesseract.get("raw_text"),
            "normalized_text": _comparison_text(t_text, kind) or None,
            "confidence": t_conf,
            "confidence_type": "tesseract_token_mean",
            "status": "ready" if t_text else "unresolved",
        },
        "local_htr": {
            "raw_text": h_text or None,
            "normalized_text": _comparison_text(h_text, kind) or None,
            "confidence": h_score,
            "confidence_type": htr.get("score_type", "unavailable"),
            "status": htr.get("status"),
        },
    }
    return {
        "selected_text": selected_text,
        "selected_engine": engine,
        "supporting_engines": supporting_engines,
        "confidence": confidence,
        "confidence_level": _confidence_level(confidence),
        "tesseract": tesseract,
        "htr": htr,
        "candidates": compact_candidates,
        "agreement": agreements.get("tesseract_htr"),
        "agreements": agreements,
        "warnings": warnings,
        "selection_reason": reason,
        "confidence_method": confidence_method,
        "confidence_breakdown": confidence_breakdown,
    }


def _recognition_context() -> dict[str, Any]:
    return {
        "htr_budget": {"remaining": HTR_MAX_CROPS, "attempted": 0, "skipped": 0},
        "htr_cache": {},
        "tesseract_cache": {},
        "metrics": {"tesseract_calls": 0, "tesseract_cache_hits": 0},
    }


def _recognize_crop(crop: Image.Image, kind: str, context: dict[str, Any]) -> dict[str, Any]:
    tesseract = _tesseract_candidate(crop, kind, cache=context.get("tesseract_cache"))
    metrics = context.get("metrics")
    if metrics is not None:
        metrics["tesseract_cache_hits" if tesseract.get("cache_hit") else "tesseract_calls"] += 1
    htr = _maybe_htr(
        crop,
        tesseract,
        kind,
        context.get("htr_budget"),
        context.get("htr_cache"),
    )
    return _select(tesseract, htr, kind)


def recognize_header_fields(
    original_path: str,
    anchors: dict[str, Any] | None = None,
    context: dict[str, Any] | None = None,
) -> dict[str, dict[str, Any]]:
    image = Image.open(original_path).convert("RGB")
    context = context or _recognition_context()
    results: dict[str, dict[str, Any]] = {}
    for region in HEADER_REGIONS:
        crop = _crop(image, region.box)
        tesseract = _tesseract_candidate(crop, region.kind, cache=context.get("tesseract_cache"))
        metrics = context.get("metrics")
        if metrics is not None:
            metrics["tesseract_cache_hits" if tesseract.get("cache_hit") else "tesseract_calls"] += 1
        anchor = (anchors or {}).get(region.key, {})
        value = anchor.get("ocr_value", "")
        if (anchor.get("audit_metadata") or {}).get("source") == "inline_printed_anchor" and value:
            valid = bool(re.fullmatch(r"[0-9]+(?:[./ -][0-9]+)*", value)) if region.kind == "numeric" else (
                _devanagari_score(value) >= .95 and len(value.split()) <= 5)
            if valid and (anchor.get("ocr_confidence") or 0) > (tesseract.get("confidence") or 0):
                tesseract = {"text": value, "confidence": anchor.get("ocr_confidence"),
                    "variant": "inline_printed_anchor", "format_valid": True, "pass_agreement": 0,
                    "source_token_ids": anchor.get("source_token_ids", []),
                    "bounding_box": anchor.get("bounding_box"), "crop_candidate": tesseract}
        htr = _maybe_htr(crop, tesseract, region.kind, context.get("htr_budget"), context.get("htr_cache"))
        selected = _select(tesseract, htr, region.kind)
        if region.key == "crop_year" and selected.get("selected_text") and (selected.get("confidence") or 0) <= 0:
            # A single zero-confidence year reading is especially prone to a
            # changed digit.  Preserve it in candidates, but require officer
            # review instead of publishing an apparently precise false date.
            selected = {
                **selected,
                "selected_text": "",
                "selected_engine": None,
                "confidence": None,
                "confidence_level": "UNAVAILABLE",
                "warnings": [*selected.get("warnings", []), "critical_numeric_unresolved"],
                "selection_reason": "zero-confidence critical year retained only as recognition evidence",
            }
        results[region.key] = {**selected, "roi": region.box, "recognizer": "relative_khatauni_header_roi"}
    return results


def _line_positions(mask: np.ndarray, horizontal: bool) -> list[int]:
    kernel_shape = (40, 1) if horizontal else (1, 40)
    opened = cv2.morphologyEx(mask, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, kernel_shape))
    contours, _ = cv2.findContours(opened, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    positions: list[int] = []
    for contour in contours:
        x, y, width, height = cv2.boundingRect(contour)
        if horizontal and width > mask.shape[1] * 0.45:
            positions.append(y)
        if not horizontal and height > mask.shape[0] * 0.25:
            positions.append(x)
    positions = sorted(positions)
    deduped: list[int] = []
    for position in positions:
        if not deduped or position - deduped[-1] > 3:
            deduped.append(position)
    return deduped


def _repair_template_columns(positions: list[int], expected: int = 12) -> list[int]:
    """Repair at most two broken grid lines using only neighboring geometry."""

    repaired = list(positions)
    while len(repaired) < expected and len(repaired) >= expected - 2:
        gaps = [right - left for left, right in zip(repaired, repaired[1:])]
        if not gaps:
            break
        typical = float(np.median(sorted(gaps)[: max(2, len(gaps) - 2)]))
        widest = max(range(len(gaps)), key=gaps.__getitem__)
        if gaps[widest] < typical * 1.55:
            break
        pieces = max(2, round(gaps[widest] / max(typical, 1)))
        repaired.insert(widest + 1, round(repaired[widest] + gaps[widest] / pieces))
    while len(repaired) > expected and len(repaired) <= expected + 2:
        candidates = []
        for index in range(1, len(repaired) - 1):
            left_gap = repaired[index] - repaired[index - 1]
            right_gap = repaired[index + 1] - repaired[index]
            candidates.append((min(left_gap, right_gap), index))
        if not candidates:
            break
        _, remove_index = min(candidates)
        repaired.pop(remove_index)
    return repaired


def _ink_line_spans(crop: Image.Image) -> list[tuple[int, int]]:
    """Return clearly separated text-line bands inside one ruled cell."""

    gray = np.asarray(crop.convert("L"))
    mask = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
    line_mask = cv2.morphologyEx(
        mask,
        cv2.MORPH_OPEN,
        cv2.getStructuringElement(cv2.MORPH_RECT, (max(20, crop.width // 3), 1)),
    )
    mask[line_mask > 0] = 0
    joined = cv2.morphologyEx(
        mask,
        cv2.MORPH_CLOSE,
        cv2.getStructuringElement(cv2.MORPH_RECT, (max(3, crop.width // 35), 3)),
    )
    active = np.count_nonzero(joined, axis=1) >= max(3, crop.width // 120)
    spans: list[tuple[int, int]] = []
    start = None
    for y, used in enumerate([*active.tolist(), False]):
        if used and start is None:
            start = y
        if not used and start is not None:
            if spans and start - spans[-1][1] <= max(4, crop.height // 14):
                spans[-1] = (spans[-1][0], y)
            else:
                spans.append((start, y))
            start = None
    minimum_height = max(6, crop.height // 10)
    spans = [(top, bottom) for top, bottom in spans if bottom - top >= minimum_height]
    return spans if 2 <= len(spans) <= 5 else []


def _table_grid(original_path: str) -> tuple[tuple[int, int], list[int], list[int], Image.Image] | None:
    image = cv2.imread(original_path)
    if image is None:
        return None
    height, width = image.shape[:2]
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    mask = cv2.adaptiveThreshold(~gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY, 31, -2)
    horizontal = cv2.morphologyEx(mask,cv2.MORPH_OPEN,cv2.getStructuringElement(cv2.MORPH_RECT,(max(40,width//18),1)))
    vertical = cv2.morphologyEx(mask,cv2.MORPH_OPEN,cv2.getStructuringElement(cv2.MORPH_RECT,(1,max(40,height//24))))
    joined = cv2.morphologyEx(horizontal|vertical,cv2.MORPH_CLOSE,cv2.getStructuringElement(cv2.MORPH_RECT,(5,5)))
    contours,_ = cv2.findContours(joined,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
    boxes = sorted((cv2.boundingRect(c) for c in contours),key=lambda b:b[2]*b[3],reverse=True)
    for left,top,w,h in boxes:
        if w < width*.5 or h < height*.12:
            continue
        local = mask[top:top+h,left:left+w]
        xs = _repair_template_columns(_line_positions(local,horizontal=False))
        ys = _line_positions(local,horizontal=True)
        if len(xs)==12 and len(ys)>=3:
            # First band contains this template's merged printed headings.
            # Remaining row count and bottom edge come from actual grid lines.
            return (left,top),xs,ys[1:],Image.open(original_path).convert("RGB")
    return None


def recognize_table_rows(
    original_path: str,
    context: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    grid = _table_grid(original_path)
    if not grid:
        return []
    (origin_x, origin_y), xs, ys, image = grid
    context = context or _recognition_context()
    rows: list[dict[str, Any]] = []
    row_bands = [(ys[index], ys[index + 1]) for index in range(len(ys) - 1)]
    for source_row_index, (row_top, row_bottom) in enumerate(row_bands):
        if row_bottom - row_top < 22:
            continue
        cells = []
        holder_lines: list[dict[str, Any]] = []
        first_cell_text = ""
        for target_index, column in enumerate(TABLE_COLUMNS):
            mapping = TABLE_KEY_BY_TEMPLATE.get(column["key"])
            if not mapping:
                cells.append({"column_index": target_index, "raw_ocr_value": "", "ai_value": "", "ai_confidence": None, "confidence_source": "unavailable", "audit_metadata": {"source": "khatauni_table_roi", "status": "no_template_column"}})
                continue
            start, end, kind = mapping
            if end >= len(xs):
                continue
            padding = 4
            box = (origin_x + xs[start] + padding, origin_y + row_top + padding, origin_x + xs[end] - padding, origin_y + row_bottom - padding)
            crop = image.crop(box)
            metrics = context.get("metrics")
            # Multi-line holder cells are recognized from their individual
            # physical bands.  OCRing the enclosing cell first is duplicate
            # work and can merge two people into one candidate.
            line_spans = _ink_line_spans(crop) if column["key"] == "holder_name" else []
            tesseract = None
            if not line_spans:
                tesseract = _tesseract_candidate(crop, kind, cache=context.get("tesseract_cache"))
                if metrics is not None:
                    metrics["tesseract_cache_hits" if tesseract.get("cache_hit") else "tesseract_calls"] += 1
            if tesseract and kind == "numeric" and end-start > 1:
                # A multi-unit area occupies distinct ruled subcells. Keep
                # them separate during recognition, then preserve their order
                # as space-separated components; never invent a decimal/unit.
                parts = []
                for sub in range(start,end):
                    subbox = (origin_x+xs[sub]+padding,box[1],origin_x+xs[sub+1]-padding,box[3])
                    part = _tesseract_candidate(image.crop(subbox), kind, cache=context.get("tesseract_cache"))
                    if metrics is not None:
                        metrics["tesseract_cache_hits" if part.get("cache_hit") else "tesseract_calls"] += 1
                    parts.append({**part, "roi": subbox})
                if all(part.get("text") for part in parts):
                    tesseract = {"text": " ".join(part["text"] for part in parts),
                        "confidence": min(part.get("confidence") or 0 for part in parts),
                        "format_valid": all(part.get("format_valid") for part in parts),
                        "pass_agreement": min(part.get("pass_agreement",0) for part in parts),
                        "components": parts, "whole_cell_candidate": tesseract,
                        "representation": "source_subcells_left_to_right_no_unit_conversion"}
            if tesseract and column["key"] == "plot_number":
                # Inspect raw OCR before numeric cleaning removes the label.
                raw_candidates = " ".join(p.get("raw_text", "") for p in tesseract.get("passes", []))
                if re.search(r"योग|कुल|total", raw_candidates, re.IGNORECASE):
                    cells = []
                    break
            if line_spans:
                recognized_lines = []
                for line_top, line_bottom in line_spans:
                    line_box = (
                        box[0], box[1] + line_top, box[2], box[1] + line_bottom,
                    )
                    line_crop = image.crop(line_box)
                    line_result = _recognize_crop(line_crop, kind, context)
                    if line_result.get("selected_text"):
                        recognized_lines.append({"box": line_box, "recognition": line_result})
                if len(recognized_lines) >= 2:
                    holder_lines = recognized_lines
                    selected = recognized_lines[0]["recognition"]
                    box = recognized_lines[0]["box"]
                else:
                    # Keep the normal whole-cell result only when its bands
                    # did not provide independently usable holder values.
                    selected = _recognize_crop(crop, kind, context)
            else:
                assert tesseract is not None
                htr = _maybe_htr(
                    crop, tesseract, kind,
                    context.get("htr_budget"), context.get("htr_cache"),
                )
                selected = _select(tesseract, htr, kind)
            value = selected["selected_text"]
            if column["key"] == "plot_number":
                first_cell_text = value
            cells.append({
                "column_index": target_index,
                "raw_ocr_value": value,
                "ai_value": value,
                "ai_confidence": selected["confidence"],
                "confidence_source": "hybrid_field_roi",
                "bounding_box": {"left": box[0], "top": box[1], "width": max(box[2] - box[0], 0), "height": max(box[3] - box[1], 0)},
                "source_token_ids": [],
                "audit_metadata": {**selected, "source": "khatauni_table_roi", "schema_key": column["key"]},
            })
        joined = " ".join(cell.get("raw_ocr_value") or "" for cell in cells)
        if re.search(r"\bयोग\b", joined) or (not re.search(r"[\d\u0900-\u097f]", joined, re.UNICODE)):
            continue
        if cells and (first_cell_text or any(cell.get("raw_ocr_value") for cell in cells)):
            if len(holder_lines) >= 2:
                holder_column = next(
                    index for index, column in enumerate(TABLE_COLUMNS)
                    if column["key"] == "holder_name"
                )
                for line_index, line in enumerate(holder_lines):
                    expanded_cells = copy.deepcopy(cells)
                    holder_cell = expanded_cells[holder_column]
                    recognition = line["recognition"]
                    line_box = line["box"]
                    holder_cell.update({
                        "raw_ocr_value": recognition["selected_text"],
                        "ai_value": recognition["selected_text"],
                        "ai_confidence": recognition["confidence"],
                        "bounding_box": {
                            "left": line_box[0], "top": line_box[1],
                            "width": max(line_box[2] - line_box[0], 0),
                            "height": max(line_box[3] - line_box[1], 0),
                        },
                        "audit_metadata": {
                            **recognition,
                            "source": "khatauni_table_roi",
                            "schema_key": "holder_name",
                            "source_physical_row_index": source_row_index,
                            "source_line_index": line_index,
                            "source_line_count": len(holder_lines),
                        },
                    })
                    rows.append({
                        "cells": expanded_cells,
                        "source": "hybrid_table_grid_roi_multiline_holder",
                        "source_row_index": source_row_index,
                        "source_physical_row_index": source_row_index,
                        "source_line_index": line_index,
                        "source_line_count": len(holder_lines),
                    })
            else:
                rows.append({
                    "cells": cells,
                    "source": "hybrid_table_grid_roi",
                    "source_row_index": source_row_index,
                    "source_physical_row_index": source_row_index,
                })
    return rows


def apply_hybrid_recognition(structure: dict[str, Any], original_path: str | None) -> dict[str, Any]:
    started = time.monotonic()
    if not original_path or not os.path.isfile(original_path):
        return structure
    # The existing fixed template only describes the ruled 11-column form.
    # Unknown layouts retain the existing anchor/token extraction, rather than
    # injecting arbitrary crops from unrelated page coordinates.
    grid = _table_grid(original_path)
    if not grid or len(grid[1]) != 12:
        structure["hybrid_metadata"] = {
            "status": "template_not_matched",
            "htr_model": HTR_MODEL_ID,
            "htr_enabled": ENABLE_LOCAL_HTR,
            "htr_max_crops": HTR_MAX_CROPS,
            "recognition_runtime_seconds": round(time.monotonic() - started, 3),
        }
        return structure
    context = _recognition_context()
    try:
        header_results = recognize_header_fields(
            original_path,
            {f["key"]: f for f in structure.get("header_fields", [])},
            context,
        )
    except Exception as exc:
        structure["hybrid_metadata"] = {"status": "failed", "error": f"{type(exc).__name__}: {exc}"}
        return structure
    fields = []
    for field in structure.get("header_fields", []):
        result = header_results.get(field.get("key"))
        if result and result["selected_text"]:
            fields.append({
                **field,
                "ocr_value": result["selected_text"],
                "ocr_confidence": result["confidence"],
                "confidence_source": "hybrid_field_roi",
                "audit_metadata": result,
            })
        elif result and "mixed_script_review" in (result.get("warnings") or []):
            # Do not let a looser whole-page/token association reintroduce
            # Latin-heavy noise after the correctly localized value crop has
            # ruled it untrustworthy.  The original candidate remains in the
            # persisted raw OCR evidence and officer review can enter a value.
            fields.append({
                **field,
                "ocr_value": "",
                "ocr_confidence": None,
                "confidence_source": "hybrid_field_roi",
                "audit_metadata": result,
            })
        else:
            fields.append(field)
    by_key = {field["key"] for field in fields}
    for schema in HEADER_FIELDS:
        if schema["key"] in by_key:
            continue
        result = header_results.get(schema["key"])
        if result:
            fields.append({
                "key": schema["key"],
                "label": schema["label"],
                "ocr_value": result["selected_text"],
                "ocr_confidence": result["confidence"],
                "confidence_source": "hybrid_field_roi" if result["selected_text"] else "unavailable",
                "bounding_box": None,
                "source_token_ids": [],
                "audit_metadata": result,
            })
    try:
        roi_rows = recognize_table_rows(original_path, context)
    except Exception as exc:
        roi_rows = []
        structure["hybrid_table_error"] = f"{type(exc).__name__}: {exc}"
    old_populated = sum(bool(cell.get("raw_ocr_value") or cell.get("ai_value")) for row in structure.get("rows", []) for cell in row.get("cells", []))
    new_populated = sum(bool(cell.get("raw_ocr_value") or cell.get("ai_value")) for row in roi_rows for cell in row.get("cells", []))
    if roi_rows and new_populated >= old_populated:
        structure["rows"] = roi_rows
    structure["header_fields"] = fields
    confidences = [field.get("ocr_confidence") for field in fields if field.get("ocr_value")]
    confidences.extend(cell.get("ai_confidence") for row in structure.get("rows", []) for cell in row.get("cells", []) if cell.get("raw_ocr_value"))
    structure["extraction_summary"] = {
        **(structure.get("extraction_summary") or {}),
        "header_fields_detected": sum(bool(field.get("ocr_value")) for field in fields),
        "header_fields_total": len(fields),
        "table_rows_detected": len(structure.get("rows", [])),
        "ocr_cells_populated": sum(bool(cell.get("raw_ocr_value") or cell.get("ai_value")) for row in structure.get("rows", []) for cell in row.get("cells", [])),
        "high_confidence_values": sum(value is not None and value >= 90 for value in confidences),
        "medium_confidence_values": sum(value is not None and 70 <= value < 90 for value in confidences),
        "low_confidence_values": sum(value is not None and value < 70 for value in confidences),
        "unavailable_values": sum(value is None for value in confidences),
    }
    structure["hybrid_metadata"] = {
        "htr_model": HTR_MODEL_ID,
        "htr_enabled": ENABLE_LOCAL_HTR,
        "htr_max_crops": HTR_MAX_CROPS,
        "htr_attempted_crops": context["htr_budget"].get("attempted", 0),
        "htr_skipped_crops": context["htr_budget"].get("skipped", 0),
        "htr_remaining_crops": context["htr_budget"].get("remaining", 0),
        "htr_state": _htr_cache.get("state"),
        "htr_error": _htr_cache.get("error"),
        "htr_model_cache": _htr_cache.get("cache"),
        "htr_request_cache_entries": len(context["htr_cache"]),
        "tesseract_crop_calls": context["metrics"].get("tesseract_calls", 0),
        "tesseract_crop_cache_hits": context["metrics"].get("tesseract_cache_hits", 0),
        "tesseract_request_cache_entries": len(context["tesseract_cache"]),
        "htr_device": _htr_cache.get("device"),
        "header_field_count": len(header_results),
        "roi_table_rows": len(roi_rows),
        "recognition_runtime_seconds": round(time.monotonic() - started, 3),
    }
    return structure
