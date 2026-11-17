import json
from collect_foreign_extra_v2 import apple,OUT
r=apple()
(OUT/'apple_retry_expanded_audit.json').write_text(json.dumps(r,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in r.items() if k!='pages'},ensure_ascii=False))
