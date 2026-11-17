"""Portable integrity verification, standard library only: python tools/verify_data.py."""
import gzip,hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(path):
 h=hashlib.sha256()
 with path.open('rb') as f:
  for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
 return h.hexdigest()
def main():
 manifest=json.loads((ROOT/'data/manifest.json').read_text(encoding='utf-8'));expected=manifest['counts'];checked={}
 inventories=[manifest['file_inventory']['files']]
 if (ROOT/'package-manifest.json').exists():inventories.append(json.loads((ROOT/'package-manifest.json').read_text(encoding='utf-8'))['files'])
 for inventory in inventories:
  for item in inventory:
   p=(ROOT/item['path']).resolve();assert p.is_relative_to(ROOT.resolve()),('Path outside package',item['path']);assert p.is_file(),item['path'];assert p.stat().st_size==item['bytes'],item['path']
   actual=checked.get(p)
   if not actual:actual=checked[p]=sha(p)
   assert actual==item['sha256'],('Hash mismatch',item['path'])
 catalog=json.loads((ROOT/'data/catalog.json').read_text(encoding='utf-8'))['jobs'];by_id={x['id']:x for x in catalog};assert len(by_id)==len(catalog)==expected['record_count']
 compressed_catalog=ROOT/'data/catalog.json.gz'
 if compressed_catalog.exists():assert gzip.decompress(compressed_catalog.read_bytes())==(ROOT/'data/catalog.json').read_bytes()
 detail_ids=set();body=0;shards={x['detail_shard'] for x in catalog}
 for name in shards:
  p=(ROOT/'data'/name).resolve();assert p.is_relative_to(ROOT.resolve());part=json.loads(p.read_text(encoding='utf-8'))
  for ident,x in part.items():
   assert ident not in detail_ids and ident in by_id and x['id']==ident;detail_ids.add(ident);assert by_id[ident]['detail_shard']==name
   text=x.get('full_text','')
   if text:assert hashlib.sha256(text.encode('utf-8')).hexdigest()==x['text_sha256']==by_id[ident]['text_sha256'];body+=1
 assert detail_ids==set(by_id);assert body==expected['body_count']
 corpus_ids=set()
 with gzip.open(ROOT/'data/corpus.ndjson.gz','rt',encoding='utf-8') as f:
  for line in f:
   x=json.loads(line);assert x['id'] not in corpus_ids;corpus_ids.add(x['id']);assert x['detail_shard']==by_id[x['id']]['detail_shard']
   if x['full_text']:assert hashlib.sha256(x['full_text'].encode('utf-8')).hexdigest()==by_id[x['id']]['text_sha256']
 assert corpus_ids==set(by_id)
 assert sum(x['requirements_available'] for x in catalog)==expected['independent_requirements_denominator']
 print(json.dumps({'files_verified':len(checked),'records':len(catalog),'body':body,'detail_shards':len(shards),'corpus_rows':len(corpus_ids),'passed':True},ensure_ascii=False))
if __name__=='__main__':main()
