import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import khatauni_hybrid as h
import pytesseract
import numpy as np
from PIL import Image,ImageOps
pytesseract.pytesseract.tesseract_cmd=h.TESSERACT_CMD
im=Image.open(sys.argv[1])
grid=h._table_grid(sys.argv[1])
(ox,oy),xs,ys,_=grid
crops={'khata':h._crop(im,next(r.box for r in h.HEADER_REGIONS if r.key=='khata_number'))}
for i in range(len(ys)-2):
    crops['plot_'+str(i)]=im.crop((ox+xs[0]+4,oy+ys[i]+4,ox+xs[1]-4,oy+ys[i+1]-4))
for key,crop in crops.items():
    clean=h._clean_crop(crop,remove_slanted=True)
    clean.save('diagnostics/'+key+'_numeric.png')
    print(key, flush=True)
    for name,c in [('raw',h._prepare_crop(crop,4)),('clean',h._prepare_crop(clean,4))]:
        for mode in [7,13]:
            d=pytesseract.image_to_data(c,lang='hin+eng',config=f'--psm {mode} -c tessedit_char_whitelist=0123456789./-',output_type=pytesseract.Output.DICT)
            print(name,mode,[(t,cf) for t,cf in zip(d['text'],d['conf']) if t.strip()],flush=True)
    mask=np.asarray(clean)<128
    occupied=np.any(mask,axis=0)
    start=None
    spans=[]
    for x,used in enumerate([*occupied,False]):
        if used and start is None: start=x
        if not used and start is not None:
            spans.append((start,x)); start=None
    for left,right in spans:
        c=ImageOps.expand(clean.crop((left,0,right,clean.height)),border=10,fill=255)
        d=pytesseract.image_to_data(c.resize((c.width*3,c.height*3)),lang='hin+eng',config='--psm 10 -c tessedit_char_whitelist=0123456789./-',output_type=pytesseract.Output.DICT)
        print('glyph',[(t,cf) for t,cf in zip(d['text'],d['conf']) if t.strip()],flush=True)
