"""Export topic rows into indexed SQLite; all counts remain job-record counts."""
import argparse,gzip,json,sqlite3
from pathlib import Path
def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--package',type=Path,default=Path(__file__).resolve().parents[1]/'通信工程就业数据包');ap.add_argument('--output',type=Path);args=ap.parse_args();p=args.package
    target=args.output or p/'data/communications.sqlite';target.parent.mkdir(parents=True,exist_ok=True)
    if target.exists():target.unlink() # exact single generated database path supplied by caller
    con=sqlite3.connect(target)
    try:
        con.executescript('''PRAGMA foreign_keys=ON;
        CREATE TABLE jobs(id TEXT PRIMARY KEY,title TEXT,company TEXT,hiring_unit_name TEXT,hiring_unit_key TEXT,parent_group TEXT,ownership_group TEXT,tier TEXT,major_scope TEXT,major_quote TEXT,student_confirmed INTEGER,student_status TEXT,experience_signal INTEGER,experience_note TEXT,degree_raw TEXT,career_track TEXT,kind TEXT,skill_eligible INTEGER,detailed_jd INTEGER,source_collection TEXT,source_snapshot TEXT,current_status TEXT,source_job_id TEXT,official_id_verified INTEGER,url TEXT,description TEXT,requirements TEXT,full_text TEXT,provenance_json TEXT);
        CREATE TABLE cities(job_id TEXT REFERENCES jobs(id),city TEXT,PRIMARY KEY(job_id,city));
        CREATE TABLE terms(id TEXT PRIMARY KEY,label TEXT,category TEXT);
        CREATE TABLE job_technologies(job_id TEXT REFERENCES jobs(id),term_id TEXT REFERENCES terms(id),field TEXT,PRIMARY KEY(job_id,term_id,field));
        CREATE TABLE technology_evidence(job_id TEXT REFERENCES jobs(id),term_id TEXT REFERENCES terms(id),field TEXT,offset_start INTEGER,offset_end_exclusive INTEGER,matched_text TEXT);
        CREATE TABLE metadata(key TEXT PRIMARY KEY,value_json TEXT);
        CREATE INDEX jobs_group_track ON jobs(parent_group,career_track);CREATE INDEX jobs_student_tier ON jobs(student_confirmed,tier);CREATE INDEX cities_name ON cities(city);CREATE INDEX tech_term ON job_technologies(term_id,field);''')
        fields=[x[1] for x in con.execute('PRAGMA table_info(jobs)')]
        catalog=json.loads((p/'data/catalog.json').read_text(encoding='utf-8'))
        con.executemany('INSERT INTO terms VALUES(?,?,?)',[(t,v['label'],v['category']) for t,v in catalog['terms'].items()])
        n=0
        with gzip.open(p/'data/corpus.ndjson.gz','rt',encoding='utf-8') as f:
            for line in f:
                j=json.loads(line);values=[]
                for key in fields:
                    val=json.dumps(j['provenance'],ensure_ascii=False) if key=='provenance_json' else j.get(key)
                    if isinstance(val,bool):val=int(val)
                    values.append(val)
                con.execute('INSERT INTO jobs VALUES('+','.join('?' for _ in fields)+')',values)
                con.executemany('INSERT INTO cities VALUES(?,?)',[(j['id'],c) for c in set(j['city_tags'])])
                con.executemany('INSERT INTO job_technologies VALUES(?,?,?)',[(j['id'],t,field) for field,key in [('qualification','technology_ids'),('duty','technology_duty_ids')] for t in j[key]])
                con.executemany('INSERT INTO technology_evidence VALUES(?,?,?,?,?,?)',[(j['id'],e['term_id'],e['field'],e['offset_start'],e['offset_end_exclusive'],e['matched_text']) for e in j['technology_evidence']]);n+=1
        for name,filename in [('analysis','analysis.json'),('rules','rules/processing-version.json')]:
            if (p/'data'/filename).exists():con.execute('INSERT INTO metadata VALUES(?,?)',(name,(p/'data'/filename).read_text(encoding='utf-8')))
        try:
            con.execute('CREATE VIRTUAL TABLE jobs_fts USING fts5(id UNINDEXED,title,company,requirements,description)');con.execute('INSERT INTO jobs_fts SELECT id,title,company,requirements,description FROM jobs');fts=True
        except sqlite3.OperationalError:fts=False
        con.commit();assert con.execute('PRAGMA integrity_check').fetchone()[0]=='ok';assert con.execute('SELECT COUNT(*) FROM jobs').fetchone()[0]==n
        check=con.execute("SELECT COUNT(DISTINCT j.id) FROM jobs j JOIN job_technologies x ON j.id=x.job_id JOIN terms t ON t.id=x.term_id WHERE j.student_confirmed=1 AND j.tier IN ('A','B') AND j.skill_eligible=1 AND x.field='qualification' AND t.label='Python'").fetchone()[0]
        print(json.dumps({'records':n,'terms':len(catalog['terms']),'student_direct_python':check,'fts5':fts,'integrity':'ok','database':str(target)},ensure_ascii=False))
    finally:con.close()
if __name__=='__main__':main()
