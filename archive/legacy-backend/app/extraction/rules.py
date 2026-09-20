import re
FIELDS=['Owner Name','Khasra Number','Khata Number','Area','Village','Tehsil','District','Document/Record Number']
PAT={'Owner Name':r'(?:Owner|Name)\s*[:\-]\s*([^\n]+)','Khasra Number':r'(?:Khasra)\s*(?:No\.?|Number)?\s*[:\-]\s*([^\n]+)','Khata Number':r'(?:Khata)\s*(?:No\.?|Number)?\s*[:\-]\s*([^\n]+)','Area':r'(?:Area)\s*[:\-]\s*([^\n]+)','Village':r'(?:Village)\s*[:\-]\s*([^\n]+)','Tehsil':r'(?:Tehsil)\s*[:\-]\s*([^\n]+)','District':r'(?:District)\s*[:\-]\s*([^\n]+)','Document/Record Number':r'(?:Record|Document)\s*(?:No\.?|Number)?\s*[:\-]\s*([^\n]+)'}
def extract(text): return {k:(re.search(v,text,re.I).group(1).strip() if re.search(v,text,re.I) else None) for k,v in PAT.items()}
