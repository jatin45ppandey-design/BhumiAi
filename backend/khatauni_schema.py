"""Configurable Hindi Khatauni schema.

Only labels and aliases live here.  Operational values are always supplied by
Tesseract OCR or by an officer correction.
"""

HEADER_FIELDS = [
    {"key": "district", "label": "जनपद", "aliases": ["जनपद", "जिला", "district"]},
    {"key": "tehsil", "label": "तहसील", "aliases": ["तहसील", "tehsil"]},
    {"key": "revenue_village", "label": "राजस्व ग्राम", "aliases": ["राजस्व ग्राम"]},
    {"key": "village_name", "label": "ग्राम का नाम", "aliases": ["ग्राम का नाम", "ग्राम", "गांव", "village"]},
    {"key": "village_code", "label": "ग्राम कोड", "aliases": ["ग्राम कोड", "गांव कोड", "village code"]},
    {"key": "pargana", "label": "परगना", "aliases": ["परगना", "pargana"]},
    {"key": "crop_year", "label": "फसली वर्ष", "aliases": ["फसली वर्ष", "फसली साल", "वर्ष"]},
    {"key": "khata_number", "label": "खाता संख्या", "aliases": ["खाता संख्या", "खाता सं", "खाता नं", "खाता नम्बर", "khata number"]},
    {"key": "holder_name", "label": "खातेदार का नाम", "aliases": ["खातेदार का नाम", "भूमिधर का नाम", "खातेदार", "भूमिधर", "holder name", "owner name"]},
    {"key": "guardian_name", "label": "पिता / पति का नाम", "aliases": ["पिता का नाम", "पति का नाम", "पिता पति", "guardian name", "father name"]},
    {"key": "patwari_circle", "label": "पटवारी हल्का", "aliases": ["पटवारी हल्का", "हल्का"]},
    {"key": "patwari_name", "label": "पटवारी का नाम", "aliases": ["पटवारी का नाम", "पटवारी"]},
    {"key": "lekhpal_name", "label": "लेखपाल का नाम", "aliases": ["लेखपाल का नाम", "लेखपाल"]},
    {"key": "issue_date", "label": "निर्गमन तिथि", "aliases": ["निर्गमन तिथि", "जारी दिनांक", "जारी तिथि"]},
]

TABLE_COLUMNS = [
    {"key": "serial_number", "label": "क्रम संख्या", "aliases": ["क्रम संख्या", "क्रमांक", "क्र सं"]},
    {"key": "plot_number", "label": "गाटा / खसरा संख्या", "aliases": ["गाटा संख्या", "गाटा सं", "खसरा संख्या", "खसरा सं", "खसरा नं", "plot number", "khasra number"]},
    {"key": "holder_name", "label": "खातेदार / भूमिधर का नाम", "aliases": ["खातेदार का नाम", "भूमिधर का नाम", "खातेदार", "भूमिधर", "नाम", "owner name"]},
    {"key": "guardian_name", "label": "पिता / पति / संरक्षक का नाम", "aliases": ["पिता का नाम", "पति का नाम", "संरक्षक का नाम", "पिता पति संरक्षक"]},
    {"key": "residence", "label": "निवास स्थान", "aliases": ["निवास स्थान", "पता", "निवास"]},
    {"key": "share", "label": "हिस्सा", "aliases": ["हिस्सा", "अंश"]},
    {"key": "area", "label": "क्षेत्रफल / रकबा", "aliases": ["क्षेत्रफल", "रकबा", "area"]},
    {"key": "land_type", "label": "भूमि का प्रकार", "aliases": ["भूमि का प्रकार", "भूमि प्रकार"]},
    {"key": "irrigation_source", "label": "सिंचाई का साधन", "aliases": ["सिंचाई का साधन", "सिंचाई साधन"]},
    {"key": "revenue", "label": "लगान", "aliases": ["लगान", "राजस्व", "revenue"]},
    {"key": "land_category", "label": "भूमि की श्रेणी", "aliases": ["भूमि की श्रेणी", "श्रेणी"]},
    {"key": "order_remarks", "label": "आदेश / परिवर्तन विवरण / टिप्पणी", "aliases": ["आदेश", "परिवर्तन विवरण", "टिप्पणी", "remarks"]},
]

HEADER_BY_KEY = {field["key"]: field for field in HEADER_FIELDS}
TABLE_BY_KEY = {field["key"]: field for field in TABLE_COLUMNS}
ALL_SCHEMA_FIELDS = [*HEADER_FIELDS, *TABLE_COLUMNS]
