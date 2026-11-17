"""Independent catalog/atomic-index validation before packaging; no network access."""
import collections, gzip, hashlib, json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT if (ROOT/'data/catalog.json').exists() else ROOT / '前端交接包_就业数据台'

def main():
    catalog = json.loads((PACKAGE/'data/catalog.json').read_text(encoding='utf-8'))['jobs']
    index = json.loads((PACKAGE/'data/technology-index.json').read_text(encoding='utf-8'))
    manifest=json.loads((PACKAGE/'data/manifest.json').read_text(encoding='utf-8'));expected=manifest['counts']
    terms = {t['id']: t for t in index['terms']}
    by_id = {j['id']: j for j in catalog}
    checks = []
    def check(name, condition, details=None):
        checks.append({'name': name, 'passed': bool(condition), 'details': details})
        assert condition, (name, details)
    check('exact catalog/index one-to-one', set(by_id) == set(index['jobs']) and len(by_id) == expected['record_count'])
    check('atomic dictionary IDs are unique and nonempty', len(terms) == len(index['terms']) and bool(terms))
    names = {t['name'].casefold(): t['id'] for t in terms.values()}
    check('LangChain and LangGraph remain separate atomic terms', 'langchain' in names and 'langgraph' in names and names['langchain'] != names['langgraph'])
    hits = collections.Counter()
    for ident, fields in index['jobs'].items():
        for field in ['requirement', 'duty', 'fulltext']:
            values = fields.get(field, [])
            assert len(values) == len(set(values)) and set(values) <= set(terms), (ident, field)
        if by_id[ident]['requirements_available']:
            hits.update(fields.get('requirement', []))
    check('formal hits are unique dictionary IDs', True)
    q_count=sum(j['requirements_available'] for j in catalog)
    check('legacy qualification denominator matches the snapshot manifest', q_count == expected['independent_requirements_denominator'])
    check('metadata-only records contribute no atomic requirement hits', all(not index['jobs'][j['id']].get('requirement') for j in catalog if not j['body_chars']))
    def sha(path):
        h=hashlib.sha256()
        with path.open('rb') as f:
            for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
        return h.hexdigest()
    check('index binds the exact source corpus', index.get('source_corpus_sha256')==sha(PACKAGE/'data/corpus.ndjson.gz'))
    check('observation date matches the manifest',index.get('snapshot_date')==manifest['snapshot']['date'])
    dictionary=json.loads((PACKAGE/'data/technology/technology_dictionary_v4.json').read_text(encoding='utf-8'))
    canonical_hash=hashlib.sha256(json.dumps(dictionary,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode('utf-8')).hexdigest()
    check('frozen dictionary canonical JSON and extractor match declared code/rule hashes', index.get('dictionary_sha256')==canonical_hash and index.get('extractor_sha256')==sha(PACKAGE/'tools/technology_enrich.py'))
    check('legacy group mappings reference existing atomic IDs', all(set(values)<=set(terms) for values in dictionary.get('legacy_v2_group_mapping',{}).values()))
    compressed = PACKAGE/'data/technology-index.json.gz'
    if compressed.exists():
        check('atomic gzip mirror exact', gzip.decompress(compressed.read_bytes()) == (PACKAGE/'data/technology-index.json').read_bytes())
    with gzip.open(PACKAGE/'data/technology/technology_enrichment_v4.json.gz','rt',encoding='utf-8') as stream:
        enrichment=json.load(stream)
    enriched={j['id']:j for j in enrichment['jobs']}
    assert len(enriched)==len(enrichment['jobs']) and set(enriched)==set(by_id)
    for ident,row in enriched.items():
        for field in ['requirement','duty','fulltext','preferred']:
            assert row['technologies_'+field]==index['jobs'][ident][field],(ident,field,'enrichment/index mismatch')
        assert row['legacy_skills_in_requirement']==by_id[ident]['skills_in_requirement']
        for binding in ['dictionary_version','dictionary_sha256','extractor_sha256','parser_version','source_corpus_sha256','snapshot_date']:
            assert row.get(binding)==index.get(binding),(ident,binding)
    check('portable compressed enrichment agrees with index and retained legacy fields',True)
    del enrichment,enriched
    samples = []
    for name in ['LangChain', 'LangGraph', 'Python', 'CUDA', 'Triton']:
        if name.casefold() not in names: continue
        tid = names[name.casefold()]
        matching = [j for j in catalog if j['requirements_available'] and tid in index['jobs'][j['id']]['requirement']]
        sample = matching[:5]
        for j in sample:
            data = json.loads((PACKAGE/'data'/j['detail_shard']).read_text(encoding='utf-8'))[j['id']]
            text = data.get('requirements_analysis') or data.get('requirements') or ''
            aliases = [name, *terms[tid].get('aliases', [])]
            # Simple independent literal evidence for these long unambiguous names.
            assert any(alias.casefold() in text.casefold() for alias in aliases if isinstance(alias, str)), (j['id'], name)
            assert hashlib.sha256(data['full_text'].encode('utf-8')).hexdigest() == j['text_sha256']
        samples.append({'name': name, 'qualification_n': len(matching), 'independently_checked_samples': len(sample)})
    check('source-field samples and original full-text hashes', True, samples)
    evidence_path=PACKAGE/'data/technology/technology_evidence_v4.ndjson.gz'
    evidence_rows=0;spans=0
    with gzip.open(evidence_path,'rt',encoding='utf-8') as e, gzip.open(PACKAGE/'data/corpus.ndjson.gz','rt',encoding='utf-8') as c:
        entries=(json.loads(line) for line in e);entry=next(entries,None)
        for line in c:
            row=json.loads(line);ident=row['id'];proved=collections.defaultdict(set)
            if entry is not None and entry['job_id']==ident:
                evidence_rows+=1
                assert entry['dictionary_version']==index['dictionary_version']
                for binding in ['dictionary_sha256','extractor_version','extractor_sha256','parser_version','source_corpus_sha256','snapshot_date']:
                    assert entry.get(binding)==index.get(binding),(ident,binding,'different extraction run')
                for hit in entry['evidence']:
                    text=row.get(hit['field']) or '';start,end=hit['offset_start'],hit['offset_end_exclusive']
                    assert 0<=start<end<=len(text) and text[start:end].casefold()==hit['matched_alias'].casefold(),(ident,hit)
                    assert text[hit['snippet_start']:hit['snippet_end_exclusive']]==hit['snippet'],(ident,'snippet')
                    assert hit['term_id'] in terms and hit['job_id']==ident
                    proved[hit['field']].add(hit['term_id']);spans+=1
                entry=next(entries,None)
            req_field='requirements_analysis' if str(row.get('requirements_analysis') or '').strip() else 'requirements'
            expected=index['jobs'][ident]
            assert set(expected['requirement'])==(proved[req_field] if row['requirements_available'] else set()),(ident,'requirement evidence')
            assert set(expected['duty'])==proved['description'] and set(expected['fulltext'])==proved['full_text'],(ident,'body evidence')
        assert entry is None,'Evidence contains unmatched/out-of-order job IDs'
    check('all archived evidence spans and each indexed term match exact source fields', True, {'evidence_jobs':evidence_rows,'spans_verified':spans,'offset_unit':'Python Unicode code points'})
    report = {'checks': checks, 'dictionary_version': index['dictionary_version'], 'terms': len(terms), 'observed_requirement_terms': len(hits), 'qualification_denominator': q_count, 'source_samples': samples, 'passed': True}
    (PACKAGE/'reports/technology-verification.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False))

if __name__ == '__main__': main()
