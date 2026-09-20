"""Local recognition experiment; no answers or database writes."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import cv2
import numpy as np
from PIL import Image, ImageOps
import khatauni_hybrid as h

image = Image.open(sys.argv[1]).convert('RGB')
for r in h.HEADER_REGIONS:
    if r.kind != 'handwritten':
        continue
    crop = h._crop(image, r.box)
    clean = h._clean_crop(crop)
    mask = np.array(clean) < 128
    occupied = np.any(mask, axis=0)
    spans = []
    start = None
    for x, used in enumerate([*occupied, False]):
        if used and start is None:
            start = x
        if not used and start is not None:
            if spans and start-spans[-1][1] < max(6, clean.height*.20):
                spans[-1] = (spans[-1][0], x)
            else:
                spans.append((start,x))
            start = None
    print(r.key, spans, flush=True)
    for left,right in spans:
        if right-left < 5:
            continue
        word = ImageOps.expand(clean.crop((left,0,right,clean.height)),border=5,fill=255)
        print(h._htr_candidate(word), flush=True)
