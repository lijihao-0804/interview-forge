"""Optional backend index. Does not run a server or alter the input corpus.
python tools/build_sqlite.py --output jobs.sqlite
"""
import argparse,gzip,json,sqlite3
from pathlib import Path
def build(source,output,limit=None):
 if output.exists():raise FileExistsError('目标已存在，换一个新路径以保留旧索引：'+str(output))
 db=sqlite3.connect(output)
 try:
  db.executescript('CREATE TABLE jobs(id TEXT PRIMARY KEY,company TEXT,title TEXT,family TEXT,direction TEXT,city TEXT,summary TEXT,description TEXT,requirements TEXT,requirements_available INTEGER,body_chars INTEGER,clarity INTEGER,url TEXT,detail_shard TEXT); CREATE TABLE job_skills(job_id TEXT,skill TEXT,PRIMARY KEY(job_id,skill)); CREATE INDEX by_company_direction ON jobs(company,direction); CREATE INDEX by_skill ON job_skills(skill,job_id);')
  try:db.execute("CREATE VIRTUAL TABLE jobs_fts USING fts5(id UNINDEXED,title,description,requirements,tokenize='trigram')");fts='trigram'
  except sqlite3.OperationalError:db.execute('CREATE VIRTUAL TABLE jobs_fts USING fts5(id UNINDEXED,title,description,requirements)');fts='unicode61'
  n=0
  with gzip.open(source,'rt',encoding='utf-8') as f:
   for line in f:
    x=json.loads(line);db.execute('INSERT INTO jobs VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(x['id'],x['company'],x['title'],x['job_family'],x['title_direction'],x['city'],x['summary'],x['description'],x['requirements'],x['requirements_available'],x['body_chars'],x['clarity_score'],x['url'],x.get('detail_shard','')))
    db.executemany('INSERT INTO job_skills VALUES(?,?)',[(x['id'],k) for k in set(x['skills_in_requirement'])]);db.execute('INSERT INTO jobs_fts VALUES(?,?,?,?)',(x['id'],x['title'],x['description'],x['requirements_analysis']));n+=1
    if limit and n>=limit:break
  db.execute('CREATE TABLE build_metadata(key TEXT PRIMARY KEY,value TEXT)');db.executemany('INSERT INTO build_metadata VALUES(?,?)',[('rows',str(n)),('fts_tokenizer',fts),('note','trigram适合至少3字符查询；短中文词可使用参数化LIKE回退。')]);db.commit()
  assert db.execute('SELECT count(*) FROM jobs').fetchone()[0]==n
  return {'rows':n,'fts_tokenizer':fts,'output':str(output)}
 finally:db.close()
def main():
 p=argparse.ArgumentParser();p.add_argument('--input',type=Path,default=Path(__file__).resolve().parents[1]/'data/corpus.ndjson.gz');p.add_argument('--output',type=Path,required=True);p.add_argument('--limit',type=int);args=p.parse_args();print(json.dumps(build(args.input,args.output,args.limit),ensure_ascii=False))
if __name__=='__main__':main()
