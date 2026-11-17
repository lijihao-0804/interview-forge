"""Freeze a dictionary and its extractor without replacing any existing version."""
import argparse,datetime,hashlib,json,re,shutil
from pathlib import Path
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--dictionary',type=Path,required=True);p.add_argument('--extractor',type=Path,required=True);p.add_argument('--registry',type=Path,required=True);a=p.parse_args()
    dictionary=json.loads(a.dictionary.read_text(encoding='utf-8'));version=dictionary['dictionary_version']
    if not re.fullmatch(r'[A-Za-z0-9_.-]+',version):raise ValueError('Use an ASCII version identifier')
    root=a.registry.resolve().parent;root.mkdir(parents=True,exist_ok=True)
    registry=json.loads(a.registry.read_text(encoding='utf-8')) if a.registry.exists() else {'schema_version':'employment-processing-registry-v1','versions':{}}
    if version in registry['versions']:raise FileExistsError('Processing version already registered: '+version)
    dest=root/'processing_versions'/version;dest.mkdir(parents=True,exist_ok=False)
    files={}
    for source,name in [(a.dictionary,'dictionary.json'),(a.extractor,'technology_enrich.py')]:
        target=dest/name;shutil.copyfile(source,target);assert sha(target)==sha(source);files[name]={'path':target.relative_to(root).as_posix(),'sha256':sha(target)}
    entry={'dictionary_version':version,'dictionary_sha256':hashlib.sha256(json.dumps(dictionary,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode('utf-8')).hexdigest(),'extractor_sha256':sha(a.extractor),'archived_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'files':files}
    registry['versions'][version]=entry
    temp=a.registry.with_suffix('.tmp');temp.write_text(json.dumps(registry,ensure_ascii=False,indent=2),encoding='utf-8');temp.replace(a.registry)
    print(json.dumps(entry,ensure_ascii=False))
if __name__=='__main__':main()
