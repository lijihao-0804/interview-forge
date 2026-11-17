"""Optional backend index. Does not run a server or alter the input corpus.
python tools/build_sqlite.py --output jobs.sqlite
"""
import argparse,gzip,hashlib,json,sqlite3
from pathlib import Path
def build(source,output,limit=None,technology_index=None):
 if output.exists():raise FileExistsError('目标已存在，换一个新路径以保留旧索引：'+str(output))
 technology_path=technology_index or source.parent/'technology-index.json'
 technology=json.loads(technology_path.read_text(encoding='utf-8')) if technology_path.exists() else None
 if technology_index and technology is None:raise FileNotFoundError(str(technology_index))
 if technology and technology.get('source_corpus_sha256'):
  h=hashlib.sha256()
  with source.open('rb') as f:
   for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
  if h.hexdigest()!=technology['source_corpus_sha256']:raise ValueError('技术索引与输入语料SHA256不一致')
 db=sqlite3.connect(output)
 try:
  db.executescript('CREATE TABLE jobs(id TEXT PRIMARY KEY,company TEXT,title TEXT,family TEXT,direction TEXT,city TEXT,summary TEXT,description TEXT,requirements TEXT,requirements_available INTEGER,body_chars INTEGER,clarity INTEGER,url TEXT,detail_shard TEXT); CREATE TABLE job_skills(job_id TEXT,skill TEXT,PRIMARY KEY(job_id,skill)); CREATE INDEX by_company_direction ON jobs(company,direction); CREATE INDEX by_skill ON job_skills(skill,job_id);')
  db.executescript('CREATE TABLE technology_terms(id TEXT PRIMARY KEY,name TEXT,category TEXT,type TEXT,aliases_json TEXT); CREATE TABLE job_technologies(job_id TEXT,technology_id TEXT,field TEXT,PRIMARY KEY(job_id,technology_id,field)); CREATE INDEX by_technology_field ON job_technologies(technology_id,field,job_id);')
  term_ids={t['id'] for t in technology['terms']} if technology else set()
  if technology:
   db.executemany('INSERT INTO technology_terms VALUES(?,?,?,?,?)',[(t['id'],t['name'],t['category'],t.get('type',''),json.dumps(t.get('aliases',[]),ensure_ascii=False)) for t in technology['terms']])
  try:db.execute("CREATE VIRTUAL TABLE jobs_fts USING fts5(id UNINDEXED,title,description,requirements,tokenize='trigram')");fts='trigram'
  except sqlite3.OperationalError:db.execute('CREATE VIRTUAL TABLE jobs_fts USING fts5(id UNINDEXED,title,description,requirements)');fts='unicode61'
  n=0
  with gzip.open(source,'rt',encoding='utf-8') as f:
   for line in f:
    x=json.loads(line);db.execute('INSERT INTO jobs VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(x['id'],x['company'],x['title'],x['job_family'],x['title_direction'],x['city'],x['summary'],x['description'],x['requirements'],x['requirements_available'],x['body_chars'],x['clarity_score'],x['url'],x.get('detail_shard','')))
    db.executemany('INSERT INTO job_skills VALUES(?,?)',[(x['id'],k) for k in set(x['skills_in_requirement'])]);db.execute('INSERT INTO jobs_fts VALUES(?,?,?,?)',(x['id'],x['title'],x['description'],x['requirements_analysis']));n+=1
    if technology:
     if x['id'] not in technology['jobs']:raise ValueError('技术索引缺少岗位ID：'+x['id'])
     for field in ['requirement','duty','fulltext','preferred']:
      values=set(technology['jobs'][x['id']].get(field,[]))
      if not values<=term_ids:raise ValueError('技术索引引用未知词项')
      db.executemany('INSERT INTO job_technologies VALUES(?,?,?)',[(x['id'],tid,field) for tid in values])
    if limit and n>=limit:break
  db.execute('CREATE TABLE build_metadata(key TEXT PRIMARY KEY,value TEXT)');db.executemany('INSERT INTO build_metadata VALUES(?,?)',[('rows',str(n)),('fts_tokenizer',fts),('technology_dictionary_version',technology.get('dictionary_version','') if technology else ''),('snapshot_date',technology.get('snapshot_date','') if technology else ''),('note','trigram适合至少3字符查询；短中文词可使用参数化LIKE回退。字段技术表分别记录资格/职责/全文/显式优先。')]);db.commit()
  assert db.execute('SELECT count(*) FROM jobs').fetchone()[0]==n
  return {'rows':n,'fts_tokenizer':fts,'technology_terms':len(term_ids),'technology_mentions':db.execute('SELECT count(*) FROM job_technologies').fetchone()[0],'output':str(output)}
 finally:db.close()
def main():
 p=argparse.ArgumentParser();p.add_argument('--input',type=Path,default=Path(__file__).resolve().parents[1]/'data/corpus.ndjson.gz');p.add_argument('--technology-index',type=Path);p.add_argument('--output',type=Path,required=True);p.add_argument('--limit',type=int);args=p.parse_args();print(json.dumps(build(args.input,args.output,args.limit,args.technology_index),ensure_ascii=False))
if __name__=='__main__':main()
