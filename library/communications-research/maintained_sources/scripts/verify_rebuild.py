"""Actually rebuild from the shipped workbench, then compare complete records and aggregates."""
import gzip,json,os,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];P=ROOT/'通信工程就业数据包';WORK=P/'maintained_sources';DEST=ROOT/'evidence/rebuilt_smoke'
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def corpus(p):return {j['id']:j for j in (json.loads(x) for x in gzip.open(p/'data/corpus.ndjson.gz','rt',encoding='utf-8'))}
def main():
    env=dict(os.environ,PYTHONIOENCODING='utf-8',PYTHONDONTWRITEBYTECODE='1');logs=[]
    for name in ['build_topic.py','build_report.py']:
        cmd=[sys.executable,'-B',str(WORK/'scripts'/name),'--topic-root',str(WORK),'--upstream',str(WORK/'upstream'),'--output',str(DEST)]
        result=subprocess.run(cmd,cwd=ROOT,env=env,capture_output=True,text=True,encoding='utf-8');logs.append({'command':name,'exit_code':result.returncode,'stdout':result.stdout,'stderr':result.stderr});assert result.returncode==0,logs[-1]
    before=corpus(P);after=corpus(DEST);assert before.keys()==after.keys()
    differences=[]
    for id in before:
        if before[id]!=after[id]:differences.append({'id':id,'keys':[k for k in set(before[id])|set(after[id]) if before[id].get(k)!=after[id].get(k)]})
    assert not differences,differences[:5]
    assert read(P/'data/analysis.json')==read(DEST/'data/analysis.json')
    assert read(P/'data/catalog.json')==read(DEST/'data/catalog.json')
    assert (P/'reports/通信工程专业就业报告.md').read_text(encoding='utf-8')==(DEST/'reports/通信工程专业就业报告.md').read_text(encoding='utf-8')
    result={'passed':True,'records_compared':len(before),'complete_record_objects_equal':True,'catalog_equal':True,'analysis_equal':True,'report_equal':True,'subprocesses':logs};(ROOT/'evidence/rebuild_verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps({k:v for k,v in result.items() if k!='subprocesses'}))
if __name__=='__main__':main()
