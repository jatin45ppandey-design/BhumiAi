from pathlib import Path
import pytesseract
from PIL import Image
from ..config import TESSERACT_CMD, TESSERACT_LANGUAGES
class TesseractProvider:
    name='TESSERACT'
    def run(self,path):
        if not Path(TESSERACT_CMD).is_file(): return None, f'Tesseract executable is unavailable at {TESSERACT_CMD}.'
        try:
            pytesseract.pytesseract.tesseract_cmd=TESSERACT_CMD
            data=pytesseract.image_to_data(Image.open(path),lang=TESSERACT_LANGUAGES,output_type=pytesseract.Output.DICT)
            txt=pytesseract.image_to_string(Image.open(path),lang=TESSERACT_LANGUAGES)
            vals=[float(v) for v in data['conf'] if v not in ('-1','')]
            return {'text':txt,'confidence':sum(vals)/len(vals) if vals else None,'provider':self.name,'languages':TESSERACT_LANGUAGES},None
        except Exception as e: return None,str(e)
