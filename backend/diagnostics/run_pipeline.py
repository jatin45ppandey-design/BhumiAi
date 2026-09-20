"""Real local API regression; uploads a distinct test copy, never seeds answers.

Run from backend: .venv/Scripts/python.exe -X utf8 diagnostics/run_pipeline.py IMAGE
All values are actual engine output. Correction test adds/removes whitespace
through the same API as the form. It does not approve a legal record.
"""
import hashlib
import json
import sys
import time
import urllib.request
import urllib.parse
import uuid
from pathlib import Path

base = 'http://127.0.0.1:8000'
source = Path(sys.argv[1])
out = Path(__file__).resolve().parent / ('run_' + time.strftime('%Y%m%d_%H%M%S'))
out.mkdir()
timings = {}

def request(path, method='GET', body=None, content_type='application/json'):
    started = time.monotonic()
    data = json.dumps(body).encode() if isinstance(body,dict) else body
    req = urllib.request.Request(base+path,data=data,method=method,headers={'Content-Type':content_type})
    with urllib.request.urlopen(req,timeout=300) as response:
        result = json.load(response)
    timings[path] = round(time.monotonic()-started,3)
    return result

def save(name, data):
    (out/(name+'.json')).write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')

original = source.read_bytes()
original_hash = hashlib.sha256(original).hexdigest()
officer = request('/api/auth/login','POST',{'email':'officer@example.com','name':'Demo Officer','role':'officer','password':'demo123'})['user']
boundary = uuid.uuid4().hex
fields = {'document_type':'Khatauni','state':'Unverified','district':'Unverified',
          'tehsil':'Unverified','village':'Unverified','officer_id':str(officer['id'])}
parts = []
for key,value in fields.items():
    parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n'.encode())
filename = 'recognition-regression-'+uuid.uuid4().hex+source.suffix
parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{filename}"\r\nContent-Type: application/octet-stream\r\n\r\n'.encode()+original+b'\r\n')
parts.append(f'--{boundary}--\r\n'.encode())
uploaded = request('/api/documents/officer-upload','POST',b''.join(parts),'multipart/form-data; boundary='+boundary)
save('upload',uploaded)
doc = uploaded['document_id']
prefix = f'/api/officer/documents/{doc}'
print('document',doc,'output',out,flush=True)
pre = request(prefix+'/preprocess','POST')
save('preprocess',pre)
ocr = request(prefix+'/ocr?processed_path='+urllib.parse.quote(pre['processed_file_path']),'POST')
save('ocr',ocr)
assert ocr['status']=='COMPLETED' and ocr['tokens']
print('OCR',ocr['token_count'],ocr['overall_confidence'],flush=True)
extracted = request(prefix+'/extract?ocr_id='+str(ocr['ocr_id']),'POST')
save('extraction',extracted)
print('extracted',extracted['summary'],flush=True)
field = next(item for item in extracted['items'] if item.get('ai_value'))
path = prefix+f'/dynamic-fields/{field["id"]}?officer_id={officer["id"]}'
request(path,'PATCH',{'officer_value':field['ai_value']+' '})
saved = request(prefix+'/digitization')
changed = next(item for item in saved['items'] if item['id']==field['id'])
assert changed['officer_value']==field['ai_value']+' '
assert changed['ai_value']==field['ai_value']
assert changed['audit_metadata']==field['audit_metadata']
request(path,'PATCH',{'officer_value':field['ai_value']})
table = extracted['tables'][0]
cell = next(cell for cell in table['cells'] if cell.get('ai_value'))
cell_path = prefix+f'/tables/{table["id"]}/cells/{cell["id"]}?officer_id={officer["id"]}'
request(cell_path,'PATCH',{'officer_value':cell['ai_value']+' '})
saved = request(prefix+'/digitization')
changed_cell = next(c for t in saved['tables'] for c in t['cells'] if c['id']==cell['id'])
assert changed_cell['officer_value']==cell['ai_value']+' '
assert changed_cell['ai_value']==cell['ai_value']
assert changed_cell['audit_metadata']==cell['audit_metadata']
request(cell_path,'PATCH',{'officer_value':cell['ai_value']})
save('saved_form',request(prefix+'/digitization'))
checks = {}
for path in ['/health','/api/officer/dashboard','/api/officer/submissions','/api/officer/audit','/api/verified-records/']:
    request(path)
    checks[path]='PASS'
for path in [f'/uploads/{filename}','/uploads/'+urllib.parse.quote(Path(pre['processed_file_path']).name)]:
    with urllib.request.urlopen(base+path) as r:
        assert r.status==200 and r.read()
    checks[path]='PASS'
with urllib.request.urlopen('http://127.0.0.1:3000/officer/review/'+str(doc)) as r:
    assert r.status==200
assert hashlib.sha256(source.read_bytes()).hexdigest()==original_hash
checks.update(original_unchanged=True,field_correction=True,cell_correction=True,
              recognition_evidence_preserved=True,frontend_http=True,browser_interaction='NOT VERIFIED')
save('verification',{'checks':checks,'timings_seconds':timings,'original_sha256':original_hash})
print('API regression PASS; browser interaction NOT VERIFIED',flush=True)
