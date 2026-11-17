"""Independent dataset, qualification span and aggregation integrity verification."""
import collections,gzip,json,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];P=ROOT/'通信工程就业数据包'
def main():
    catalog=json.loads((P/'data/catalog.json').read_text(encoding='utf-8'));a=json.loads((P/'data/analysis.json').read_text(encoding='utf-8'));rows=[json.loads(x) for x in gzip.open(P/'data/corpus.ndjson.gz','rt',encoding='utf-8')];ids=[j['id'] for j in rows];checks=[]
    def check(name,value):checks.append({'name':name,'passed':bool(value)});assert value,name
    check('unique record IDs',len(ids)==len(set(ids)));check('catalog and corpus agree',set(ids)=={j['id'] for j in catalog['jobs']});check('all original texts preserved',all(j.get('full_text') for j in rows));check('source URLs use HTTP',all(str(j.get('url','')).startswith(('http://','https://')) for j in rows));check('record kinds valid',all(j['kind'] in ['full','table','batch'] for j in rows));check('batch shared never direct or skills denominator',all(j['tier']=='D' and not j['skill_eligible'] for j in rows if j['kind']=='batch'));check('table rows outside skills denominator',not any(j['skill_eligible'] for j in rows if j['kind']=='table'))
    terms=set(catalog['terms']);span_count=0
    for j in rows:
        assert set(j['technology_ids'])<=terms
        assert len(j['technology_ids'])==len(set(j['technology_ids']))
        assert set(j['technology_ids'])=={e['term_id'] for e in j['technology_evidence']}
        assert hashlib.sha256(str(j['full_text']).encode()).hexdigest()==j['provenance']['text_sha256']
        if j['tier']=='C':assert j['undergraduate_catalog_applicable']
        if j['schema_review_required']:assert not j['skill_eligible']
        if j['source_collection']=='soe_sources':
            if j.get('professional_access_denominator_eligible') is not True:assert j['tier']=='D'
            if j['skill_eligible']:
                p=j['qualification_parse_provenance'];assert j['full_text'][p['full_text_offset_start']:p['full_text_offset_end_exclusive']]==j['requirements']
        for e in j['technology_evidence']:
            text=j[e['field']];assert text[e['offset_start']:e['offset_end_exclusive']]==e['matched_text'];span_count+=1
    check('all technical evidence spans and text hashes valid',True)
    cache={}
    for meta in catalog['jobs']:
        shard=meta['detail_shard']
        if shard not in cache:cache[shard]=json.loads((P/shard).read_text(encoding='utf-8'))
        assert cache[shard][meta['id']]['full_text']
    check('every metadata row resolves to full archived detail',True)
    for scope,subset in [('all',rows),('direct',[j for j in rows if j['tier'] in ['A','B']]),('students',[j for j in rows if j['tier'] in ['A','B'] and j['student_confirmed']])]:
        out=a[scope];assert len(subset)==out['records'];assert len({j['parent_group'] for j in subset})==out['groups'];assert len({j['hiring_unit_key'] for j in subset})==out['units'];assert sum(j['skill_eligible'] for j in subset)==out['technology_denominator']
        co=collections.Counter(t for j in subset if j['skill_eligible'] for t in set(j['technology_ids']));assert co==dict(out['technologies']);check(scope+' aggregates independently recomputed',True)
    check('audit rejection excluded',not any(j['id']=='小米-7660104107810326822' for j in rows));check('audit explicit-field omission recovered',any(j['id']=='华为-127002' and j['tier']=='B' for j in rows));check('no fake temporal claims in analysis',a['compiled_at']=='2026-11-18' and 'trend' not in a)
    result={'passed':True,'checks':checks,'records':len(rows),'technical_evidence_spans':span_count,'shards':len(cache)};(ROOT/'evidence/data_verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(result,ensure_ascii=False))
if __name__=='__main__':main()
