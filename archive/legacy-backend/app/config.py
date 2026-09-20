import os
from pathlib import Path

from dotenv import load_dotenv

ENV_PATH = Path(__file__).resolve().parents[1] / ".env"
load_dotenv(ENV_PATH)

# Explicit native executable keeps OCR independent of the Windows PATH.
TESSERACT_CMD = os.getenv('TESSERACT_CMD', r'C:\Program Files\Tesseract-OCR\tesseract.exe')
TESSERACT_LANGUAGES = os.getenv('TESSERACT_LANGUAGES', 'hin+eng')
BHASHINI_UDYAT_KEY = os.getenv('BHASHINI_UDYAT_KEY')
BHASHINI_INFERENCE_KEY = os.getenv('BHASHINI_INFERENCE_KEY')
