"""Synthetic boundary fixtures only; NOT observed job-market time-series data."""
import gzip,json,subprocess,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def write(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v),encoding='utf-8')
def period(p,date,rows):
    write(p/'data/analysis.json',{'compiled_at':date});write(p/'data/rules/processing-version.json',{'version':'fixture','professional_rule_sha256':'same','dictionary_sha256':'same','extractor_sha256':'same'});write(p/'data/catalog.json',{'terms':{t:{'label':t} for t in ['Python','Java','Rust']}})
    with gzip.open(p/'data/corpus.ndjson.gz','wt',encoding='utf-8') as f:
        for row in rows:row['source_snapshot']=date;f.write(json.dumps(row)+'\n')
def row(id,group,skills,q):return {'id':id,'source_job_id':id,'official_id_verified':True,'parent_group':group,'source_collection':'fixture_channel','tier':'A','kind':'full','skill_eligible':True,'student_confirmed':True,'city_tags':['fixture'],'career_track':'fixture','technology_ids':skills,'requirements':q}
def main():
    checks=[]
    with tempfile.TemporaryDirectory(prefix='compare_fixture_',dir=ROOT/'evidence') as temp:
        root=Path(temp);old=root/'old';new=root/'new';period(old,'2026-01-01',[row('1','A',['Python'],'v1'),row('2','A',['Java'],'v1')]);period(new,'2026-02-01',[row('1','A',['Python','Rust'],'v2'),row('3','B',['Java'],'v1')])
        cmd=[sys.executable,str(ROOT/'scripts/compare_periods.py'),str(old),str(new),'--output',str(root/'result.json')]
        result=subprocess.run(cmd,capture_output=True,text=True);assert result.returncode==0,result.stderr
        data=json.loads((root/'result.json').read_text());co=data['cohorts']['common_group_channels'];assert co['old_qualification_denominator']==2 and co['new_qualification_denominator']==1;checks.append('common employer/channel denominator correct')
        py=next(t for t in co['technologies'] if t['term_id']=='Python');assert py['percentage_point_change']==50;checks.append('mention-rate percentage-point change correct')
        assert data['cohorts']['common_official_jobs']['old_qualification_denominator']==1;assert data['paired_changes'][0]['added_technologies']==['Rust'];checks.append('stable official job qualification changes paired')
        with gzip.open(new/'data/corpus.ndjson.gz','wt',encoding='utf-8') as f:
            stale=row('1','A',['Python'],'v1');stale['source_snapshot']='2026-01-01';f.write(json.dumps(stale)+'\n')
        failure=subprocess.run(cmd[:-1]+[str(root/'stale.json')],capture_output=True,text=True);assert failure.returncode!=0 and 'No genuinely newer captured records' in failure.stderr;checks.append('date relabeling without new capture rejected')
        write(new/'data/rules/processing-version.json',{'version':'different','professional_rule_sha256':'same','dictionary_sha256':'same','extractor_sha256':'same'});failure=subprocess.run(cmd[:-1]+[str(root/'version.json')],capture_output=True,text=True);assert failure.returncode!=0 and 'Incomparable version' in failure.stderr;checks.append('different processing rules rejected')
        write(new/'data/analysis.json',{'compiled_at':'2026-01-01'});failure=subprocess.run(cmd[:-1]+[str(root/'same_date.json')],capture_output=True,text=True);assert failure.returncode!=0 and 'two distinct chronologically ordered real periods' in failure.stderr;checks.append('single identical period rejected')
    write(ROOT/'evidence/compare_verification.json',{'passed':True,'fixture_only':True,'checks':checks});print(json.dumps({'passed':True,'checks':checks}))
if __name__=='__main__':main()
