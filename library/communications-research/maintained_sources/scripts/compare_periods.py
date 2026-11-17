"""Compare TWO genuine topic snapshots with identical processing identities.
No baseline is synthesized. A vanished listing is an observation, not confirmed closure.
"""
import argparse,collections,gzip,json
from pathlib import Path
def load(p):return json.loads(p.read_text(encoding='utf-8'))
def rows(p):return [json.loads(x) for x in gzip.open(p/'data/corpus.ndjson.gz','rt',encoding='utf-8')]
def selected(xs,args):
    return [j for j in xs if j['tier'] in ['A','B'] and j['kind']=='full' and j['skill_eligible'] and (args.include_nonstudents or j['student_confirmed']) and (not args.city or args.city in j['city_tags']) and (not args.track or args.track==j['career_track'])]
def metrics(xs):
    c=collections.Counter(t for j in xs for t in set(j['technology_ids']));return len(xs),c
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('old',type=Path);p.add_argument('new',type=Path);p.add_argument('--output',required=True,type=Path);p.add_argument('--city');p.add_argument('--track');p.add_argument('--include-nonstudents',action='store_true');args=p.parse_args()
    olda=load(args.old/'data/analysis.json');newa=load(args.new/'data/analysis.json');assert olda['compiled_at']<newa['compiled_at'],'Need two distinct chronologically ordered real periods'
    oldr=load(args.old/'data/rules/processing-version.json');newr=load(args.new/'data/rules/processing-version.json')
    for key in ['version','professional_rule_sha256','dictionary_sha256','extractor_sha256']:
        assert oldr[key]==newr[key],f'Incomparable {key}: reprocess both source corpora with identical rules'
    old=selected(rows(args.old),args);new_all=selected(rows(args.new),args)
    assert all(j.get('source_snapshot','')<=olda['compiled_at'] for j in old),'Old source date after compilation date'
    assert all(j.get('source_snapshot','')<=newa['compiled_at'] for j in new_all),'New source date after compilation date'
    new=[j for j in new_all if olda['compiled_at']<str(j.get('source_snapshot') or '')<=newa['compiled_at']]
    assert new,'No genuinely newer captured records: changing only --as-of is not a new observation'
    # Matched employer + channel controls some source-composition differences.
    common={(j['parent_group'],j['source_collection']) for j in old}&{(j['parent_group'],j['source_collection']) for j in new}
    cohorts={'common_group_channels':([j for j in old if (j['parent_group'],j['source_collection']) in common],[j for j in new if (j['parent_group'],j['source_collection']) in common]),'all_sample':(old,new)}
    def stable(xs):return {(j['parent_group'],j['source_collection'],str(j.get('source_job_id'))):j for j in xs if j.get('official_id_verified') and j.get('source_job_id')}
    oi=stable(old);ni=stable(new);paired=set(oi)&set(ni);cohorts['common_official_jobs']=([oi[k] for k in paired],[ni[k] for k in paired])
    terms=load(args.new/'data/catalog.json')['terms'];result={'old_period':olda['compiled_at'],'new_period':newa['compiled_at'],'newly_captured_eligible_records':len(new),'stale_new_period_records_excluded':len(new_all)-len(new),'filters':{'city':args.city,'track':args.track,'students_only':not args.include_nonstudents},'common_group_channels':sorted(common),'cohorts':{},'paired_changes':[],'missing_official_ids_observed':sorted(set(oi)-set(ni)),'new_official_ids_observed':sorted(set(ni)-set(oi)),'warning':'Source disappearance is not confirmed closure; newly covered channels are not market growth. Mention rates describe this sample only. Stale retained records are excluded from the newer period observations.'}
    for name,(xs,ys) in cohorts.items():
        nd,oc=metrics(xs);nn,nc=metrics(ys);result['cohorts'][name]={'old_qualification_denominator':nd,'new_qualification_denominator':nn,'technologies':[{'term_id':t,'name':v['label'],'old_mentions':oc[t],'new_mentions':nc[t],'old_share':oc[t]/nd if nd else None,'new_share':nc[t]/nn if nn else None,'percentage_point_change':100*(nc[t]/nn-oc[t]/nd) if nd and nn else None} for t,v in terms.items()]}
    for k in sorted(paired):
        before=oi[k];after=ni[k];b=set(before['technology_ids']);a=set(after['technology_ids'])
        if before['requirements']!=after['requirements']:result['paired_changes'].append({'key':k,'old_id':before['id'],'new_id':after['id'],'qualification_text_changed':True,'added_technologies':sorted(a-b),'removed_technologies':sorted(b-a)})
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open('x',encoding='utf-8') as f:json.dump(result,f,ensure_ascii=False,indent=2)
    print(f'Wrote {args.output}; paired official jobs={len(paired)}, common group/channels={len(common)}')
if __name__=='__main__':main()
