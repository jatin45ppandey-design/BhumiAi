"""Local, guarded seven-column Khatauni recognition. Templates contain no values.

Each TIFF page is one isolated value crop: Tesseract applies PSM 7 to each
independently while loading a language model only once per field-type batch.
"""
from __future__ import annotations

from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
import logging
import os
import re
import time

import cv2
import numpy as np
import pytesseract
from PIL import Image, ImageOps

from config import TESSERACT_CMD
from khatauni_schema import HEADER_FIELDS, TABLE_COLUMNS
from khatauni_structured import annotate_structure, build_digital_khatauni

LOG = logging.getLogger(__name__)
DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")
LEFT_KEYS = ("district", "tehsil", "revenue_village", "village_name", "village_code", "pargana", "crop_year")
RIGHT_KEYS = ("khata_number", "holder_name", "guardian_name", "patwari_circle", "patwari_name", "lekhpal_name", "issue_date")
COLUMN_KEYS = ("serial_number", "plot_number", "holder_name", "guardian_name", "residence", "share", "area")
EXPECTED_X = np.array([0, .071, .216, .409, .587, .748, .859, 1])
WHITELISTS = {"digits": "0123456789", "year": "0123456789-", "date": "0123456789/-", "share": "0123456789/", "area": "0123456789."}
PATTERNS = {"digits": r"[0-9]+", "year": r"[0-9]{4}-[0-9]{2,4}", "date": r"[0-9]{1,2}[/\-][0-9]{1,2}[/\-][0-9]{4}", "share": r"[0-9]+(?:/[0-9]+)?", "area": r"[0-9]+(?:\.[0-9]+)?"}


def field_kind(key):
    if key in {"village_code", "khata_number", "serial_number", "plot_number"}:
        return "digits"
    return {"crop_year": "year", "issue_date": "date", "share": "share", "area": "area"}.get(key, "hindi")


def clean_value(value, key):
    value = re.sub(r"\s+", " ", value or "").strip()
    # Anchored complete label prefixes only; never remove words inside names.
    schema = next((f for f in HEADER_FIELDS if f["key"] == key), {})
    for label in sorted([schema.get("label", ""), *schema.get("aliases", [])], key=len, reverse=True):
        if label:
            value = re.sub(r"^" + re.escape(label) + r"(?=\s|[:：\-–—])\s*[:：\-–—]*\s*", "", value, count=1)
    value = re.sub(r"^(?:का नाम|नाम)\s*[:：\-–—]+\s*", "", value)
    value = value.strip(" |_:：;~–—-.,'\"")
    if field_kind(key) != "hindi":
        return re.sub(r"\s+", "", value.translate(DIGITS).replace("–", "-").replace("−", "-"))
    # Isolated numeric marker before an entirely Hindi place name is noise.
    if key in {"district", "tehsil", "revenue_village", "village_name", "pargana"}:
        value = re.sub(r"^[0-9०-९]\s+(?=[\u0900-\u097f])", "", value)
    return value


def valid_value(value, kind):
    if kind != "hindi":
        return bool(re.fullmatch(PATTERNS[kind], value))
    letters = re.findall(r"[A-Za-z\u0900-\u097f]", value)
    devanagari = re.findall(r"[\u0900-\u097f]", value)
    return bool(letters and len(devanagari) / len(letters) >= .85)


def _positions(mask, horizontal, fraction):
    counts = np.count_nonzero(mask, axis=1 if horizontal else 0)
    extent = mask.shape[1 if horizontal else 0]
    indexes = np.flatnonzero(counts > extent * fraction)
    groups = np.split(indexes, np.where(np.diff(indexes) > 3)[0] + 1)
    return [int(np.mean(group)) for group in groups if len(group)]


def prepare_page(image):
    """Rectify the outer ruled frame, then require the expected grid geometry.

    Return None on unrecognised layouts. Recognition also checks printed title
    and header labels before accepting coordinates.
    """
    source = np.asarray(image.convert("L"))
    scale = min(1., 1600 / max(source.shape))
    probe = cv2.resize(source, None, fx=scale, fy=scale) if scale < 1 else source
    mask = cv2.threshold(probe, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
    contours, _ = cv2.findContours(mask, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    for contour in sorted(contours, key=cv2.contourArea, reverse=True)[:16]:
        if cv2.contourArea(contour) < probe.size * .55:
            continue
        polygon = cv2.approxPolyDP(contour, .015 * cv2.arcLength(contour, True), True)
        if len(polygon) != 4 or not cv2.isContourConvex(polygon):
            continue
        points = polygon[:, 0].astype(np.float32) / scale
        sums, differences = points.sum(axis=1), np.diff(points, axis=1).ravel()
        ordered = np.array([points[np.argmin(sums)], points[np.argmin(differences)], points[np.argmax(sums)], points[np.argmax(differences)]])
        w = np.linalg.norm(ordered[1] - ordered[0])
        h = np.linalg.norm(ordered[3] - ordered[0])
        if not .70 < w / max(h, 1) < .90:
            continue
        width, height = 1400, round(1400 * h / w)
        transform = cv2.getPerspectiveTransform(ordered, np.float32([[0, 0], [width-1, 0], [width-1, height-1], [0, height-1]]))
        gray = cv2.warpPerspective(source, transform, (width, height), borderValue=255)
        binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
        inverse = 255 - binary
        horizontal = cv2.morphologyEx(inverse, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (width//10, 1)))
        vertical = cv2.morphologyEx(inverse, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (1, height//10)))
        xs = _positions(vertical[int(height*.54):], False, .7)
        ys = _positions(horizontal, True, .60)
        # Frame edges may disappear during warp; interior columns must exist.
        xs = [0, *[x for x in xs if .025*width < x < .98*width], width-1]
        if len(xs) != 8 or np.max(np.abs(np.array(xs)/width - EXPECTED_X)) > .022:
            continue
        table_ys = [y for y in ys if y > height*.49]
        if not table_ys or abs(table_ys[0]/height-.514) > .025:
            continue
        if table_ys[-1] < height*.98:
            table_ys.append(height-1)
        if len(table_ys) < 5 or abs(table_ys[1]/height-.604) > .025:
            continue
        # Blank/mismatched row spacing must not become guessed records.
        gaps = np.diff(table_ys[1:]) / height
        if np.any(gaps < .025) or np.any(gaps > .10):
            continue
        return {"gray": gray, "binary": binary, "xs": xs, "ys": table_ys, "transform": transform.tolist()}
    return None


def _batch(crops, language, whitelist=""):
    """PSM 7 applies to each crop page, never to the original full page."""
    if not crops:
        return []
    config = "--psm 7" + (" -c tessedit_char_whitelist=" + whitelist if whitelist else "")
    with TemporaryDirectory(prefix="bhumi-roi-") as directory:
        path = str(Path(directory) / "crops.tiff")
        pages = [ImageOps.expand(Image.fromarray(crop), border=12, fill=255) for crop in crops]
        pages[0].save(path, save_all=True, append_images=pages[1:], compression="tiff_deflate")
        data = pytesseract.image_to_data(path, lang=language, config=config, output_type=pytesseract.Output.DICT, timeout=45)
    output = [{"raw_text": "", "confidence": None, "tokens": []} for _ in crops]
    for i, word in enumerate(data["text"]):
        page = int(data["page_num"][i])-1
        if not word.strip() or not 0 <= page < len(output):
            continue
        output[page]["tokens"].append({"text": word, "confidence": float(data["conf"][i])})
    for item in output:
        item["raw_text"] = " ".join(t["text"] for t in item["tokens"])
        confidences = [t["confidence"] for t in item["tokens"] if t["confidence"] >= 0]
        item["confidence"] = sum(confidences)/len(confidences) if confidences else None
    return output


def recognize(image, prepared=None):
    """Return existing schema + real crop tokens, or None for generic fallback."""
    from khatauni_hybrid import _maybe_htr, _recognition_context, _select
    started = time.perf_counter()
    page = prepared if prepared is not None else prepare_page(image)
    if page is None:
        return None
    gray, binary = page["gray"], page["binary"]
    height, width = gray.shape
    pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD
    prior_preprocessing_time = page.get("preprocessing_seconds", 0.)
    preprocessing_time = time.perf_counter()-started + prior_preprocessing_time
    def crop(box, source=None):
        x1,y1,x2,y2 = box
        return (gray if source is None else source)[y1:y2, x1:x2]
    def relative(box):
        return tuple(round(v*(width if i%2 == 0 else height)) for i,v in enumerate(box))
    checks = _batch([crop(relative(b)) for b in [( .1,.02,.9,.075), (.01,.105,.15,.135), (.01,.15,.15,.18)]], "hin+eng")
    check_text = [c["raw_text"] for c in checks]
    if not (re.search("खतौनी|जमाबन्दी|जमाबंदी", check_text[0]) and "जनपद" in check_text[1] and "तहसील" in check_text[2]):
        return None
    # Remove long form underlines once, preserving the unmodified page above.
    # The kernel is wider than individual Hindi words/shirorekhas.
    rules = cv2.morphologyEx(255-binary, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (width//5, 1)))
    rules = cv2.dilate(rules, np.ones((3,1),np.uint8))
    gray = gray.copy()
    binary = binary.copy()
    gray[rules > 0] = 255
    binary[rules > 0] = 255
    jobs = []
    left_bands = ((.100,.130),(.140,.172),(.184,.220),(.229,.264),(.279,.307),(.321,.354),(.371,.400))
    right_bands = ((.099,.130),(.146,.178),(.186,.220),(.234,.275),(.280,.316),(.329,.365),(.379,.412))
    for keys, x1, x2, bands in [(LEFT_KEYS,.17,.46,left_bands), (RIGHT_KEYS,.743,.98,right_bands)]:
        for row,key in enumerate(keys):
            jobs.append({"key":key, "box":relative((x1,bands[row][0],x2,bands[row][1])), "row":None})
    header_count = len(jobs)
    xs,ys = page["xs"],page["ys"]
    # Last band is the printed total; recognise its label rather than creating
    # a fake data row. Actual rows are selected by their numeric serial cell.
    for row,(top,bottom) in enumerate(zip(ys[1:-1],ys[2:])):
        for col,key in enumerate(COLUMN_KEYS):
            jobs.append({"key":key, "box":(xs[col]+7,top+7,xs[col+1]-7,bottom-7), "row":row})
    context = _recognition_context()
    passes = 1  # template label batch
    header_time = table_time = htr_time = 0.
    # Limit concurrency: each batch still has independent per-crop OCR pages.
    for subset, timing_key in [(jobs[:header_count], "header"), (jobs[header_count:], "table")]:
        section_start = time.perf_counter()
        groups = defaultdict(list)
        for job in subset:
            groups[field_kind(job["key"])].append(job)
        def recognize_group(entry):
            kind, group = entry
            batch_count = 1
            candidates = _batch([crop(j["box"]) for j in group], "hin+eng" if kind == "hindi" else "eng", WHITELISTS.get(kind,""))
            weak = []
            for job,candidate in zip(group,candidates):
                candidate["text"] = clean_value(candidate["raw_text"],job["key"])
                candidate["format_valid"] = valid_value(candidate["text"],kind)
                job["candidate"] = candidate
                if not candidate["format_valid"] or (candidate["confidence"] or 0) < (85 if kind == "hindi" else 70):
                    weak.append(job)
            if weak:
                alternatives = _batch([crop(j["box"],binary) for j in weak], "hin" if kind == "hindi" else "eng", WHITELISTS.get(kind,""))
                batch_count += 1
                for job,alternative in zip(weak,alternatives):
                    alternative["text"] = clean_value(alternative["raw_text"],job["key"])
                    alternative["format_valid"] = valid_value(alternative["text"],kind)
                    primary = job["candidate"]
                    evidence = [dict(primary),dict(alternative)]
                    best = max(evidence,key=lambda c:(c["format_valid"],c["confidence"] or 0))
                    job["candidate"] = {**best,"passes":evidence}
            return batch_count
        with ThreadPoolExecutor(max_workers=3) as pool:
            passes += sum(pool.map(recognize_group, groups.items()))
        elapsed = time.perf_counter()-section_start
        if timing_key == "header": header_time = elapsed
        else: table_time = elapsed
    tokens = []
    raw_lines = []
    inverse_transform = np.eye(3) if prepared is not None else np.linalg.inv(np.asarray(page["transform"]))
    data_rows = {j["row"] for j in jobs[header_count:] if j["key"] == "serial_number" and j["candidate"]["format_valid"]}
    for index,job in enumerate(jobs):
        candidate = job["candidate"]
        kind = field_kind(job["key"])
        candidate.setdefault("passes", [dict(candidate)])
        candidate["pass_agreement"] = sum(c["text"] == candidate["text"] for c in candidate["passes"])/len(candidate["passes"])
        fallback_start = time.perf_counter()
        htr = {"text":"","status":"skipped","reason":"non_data_row"}
        if job["row"] is None or job["row"] in data_rows:
            htr = _maybe_htr(Image.fromarray(crop(job["box"])),candidate,"handwritten" if kind == "hindi" else "numeric",context["htr_budget"],context["htr_cache"])
        htr_time += time.perf_counter()-fallback_start
        result = _select(candidate, htr, "handwritten" if kind == "hindi" else "numeric")
        value = clean_value(result["selected_text"],job["key"])
        if not valid_value(value,kind):
            result.update(selected_text="",confidence=None)
            result["warnings"].append("field_pattern_mismatch")
        else:
            result["selected_text"] = value
        x1,y1,x2,y2 = job["box"]
        corners = cv2.perspectiveTransform(np.float32([[[x1,y1],[x2,y1],[x2,y2],[x1,y2]]]), inverse_transform)[0]
        left,top = np.floor(corners.min(axis=0)).astype(int)
        right,bottom = np.ceil(corners.max(axis=0)).astype(int)
        bbox = {"left":int(max(0,left)),"top":int(max(0,top)),
            "width":int(min(image.width,right)-max(0,left)),
            "height":int(min(image.height,bottom)-max(0,top))}
        result.update(roi=[x1/width,y1/height,x2/width,y2/height],recognizer="seven_column_value_roi",schema_key=job["key"])
        job["result"] = result
        job["bbox"] = bbox
        raw_lines.append(candidate["raw_text"])
        if candidate["raw_text"]:
            tokens.append({"id":index,"text":candidate["raw_text"],"confidence":candidate["confidence"],"bbox":bbox,"page_num":1,"block_num":1,"par_num":1,"line_num":index+1,"word_num":1})
    headers = []
    for schema in HEADER_FIELDS:
        job = next(j for j in jobs[:header_count] if j["key"] == schema["key"])
        result = job["result"]
        headers.append({"key":schema["key"],"label":schema["label"],"ocr_value":result["selected_text"],"ocr_confidence":result["confidence"],"confidence_source":"hybrid_field_roi","bounding_box":job["bbox"],"source_token_ids":[],"audit_metadata":result})
    rows = []
    for row in sorted({j["row"] for j in jobs[header_count:]}):
        row_jobs = [j for j in jobs[header_count:] if j["row"] == row]
        if not next(j for j in row_jobs if j["key"] == "serial_number")["result"]["selected_text"]:
            continue
        cells=[]
        for job in row_jobs:
            result=job["result"]
            cells.append({"column_index":next(i for i,c in enumerate(TABLE_COLUMNS) if c["key"]==job["key"]),"raw_ocr_value":result["selected_text"],"ai_value":result["selected_text"],"ai_confidence":result["confidence"],"confidence_source":"hybrid_field_roi","bounding_box":job["bbox"],"source_token_ids":[],"audit_metadata":result})
        rows.append({"cells":cells,"source":"seven_column_grid_roi"})
    structure={"document_type":"khatauni","header_fields":headers,"table_headers":[c["label"] for c in TABLE_COLUMNS],"rows":rows,"extraction_summary":{"header_fields_detected":sum(bool(f["ocr_value"]) for f in headers),"header_fields_total":len(headers),"table_rows_detected":len(rows),"ocr_cells_populated":sum(bool(c["raw_ocr_value"]) for r in rows for c in r["cells"])},"hybrid_metadata":{"status":"seven_column_template_matched","htr_attempted_crops":context["htr_budget"]["attempted"],"tesseract_batches":passes}}
    structure=annotate_structure(structure)
    confidences = [f["ocr_confidence"] for f in headers if f["ocr_value"]]
    confidences.extend(c["ai_confidence"] for row in rows for c in row["cells"] if c["raw_ocr_value"])
    structure["extraction_summary"].update({
        "high_confidence_values": sum(c is not None and c >= 90 for c in confidences),
        "medium_confidence_values": sum(c is not None and 70 <= c < 90 for c in confidences),
        "low_confidence_values": sum(c is not None and c < 70 for c in confidences),
        "unavailable_values": sum(c is None for c in confidences),
    })
    structure["digital_khatauni"]=build_digital_khatauni(structure)
    timings={"preprocessing":preprocessing_time,"header_ocr":header_time,"htr_fallback":htr_time,"table_extraction":table_time,"total":time.perf_counter()-started+prior_preprocessing_time}
    if os.getenv("BHUMIAI_OCR_TIMINGS", "").lower() in {"1","true"}:
        LOG.warning("Local Khatauni recognition timings (seconds): %s",timings)
    return {"structure":structure,"tokens":tokens,"raw_text":"\n".join(raw_lines),"image_width":image.width,"image_height":image.height,"timings":timings}
