from pathlib import Path
import cv2
def enhance(src:str, dest:str):
    img=cv2.imread(src)
    if img is None: raise ValueError('Only image preprocessing is supported for this local MVP')
    gray=cv2.cvtColor(img,cv2.COLOR_BGR2GRAY); gray=cv2.fastNlMeansDenoising(gray,None,10,7,21)
    clahe=cv2.createCLAHE(clipLimit=2.0,tileGridSize=(8,8)); out=clahe.apply(gray)
    out=cv2.adaptiveThreshold(out,255,cv2.ADAPTIVE_THRESH_GAUSSIAN_C,cv2.THRESH_BINARY,31,11)
    Path(dest).parent.mkdir(parents=True,exist_ok=True); cv2.imwrite(dest,out); return dest
