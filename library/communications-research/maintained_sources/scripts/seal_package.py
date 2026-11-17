"""Seal only after all final-topic checks pass. Immutable version ZIP + complete file hashes."""
import datetime,hashlib,json,shutil,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'通信工程就业数据包'
def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()
def main():
    check_paths=[ROOT/'evidence/data_verification.json',ROOT/'evidence/browser_qa/verification.json',ROOT/'evidence/compare_verification.json',ROOT/'evidence/rule_verification.json',ROOT/'evidence/rebuild_verification.json']
    results=[]
    for p in check_paths:
        result=json.loads(p.read_text(encoding='utf-8'));assert result['passed'],p;results.append({'path':str(p.relative_to(ROOT)),'sha256':sha(p)})
    qa=OUT/'reports/qa';qa.mkdir(parents=True,exist_ok=True)
    for p in check_paths:shutil.copy2(p,qa/(p.parent.name+'_'+p.name))
    for p in (ROOT/'evidence/browser_qa').glob('*.png'):shutil.copy2(p,qa/p.name)
    a=json.loads((OUT/'data/analysis.json').read_text(encoding='utf-8'));stats={'records':a['all']['records'],'groups':a['all']['groups'],'hiring_unit_names':a['all']['units'],'direct_major_records':a['direct']['records'],'student_direct_records':a['students']['records'],'student_skill_denominator':a['students']['technology_denominator']}
    receipt='# 本期验收与数据边界\n\n'+json.dumps(stats,ensure_ascii=False,indent=2)+'\n\n专业/年限/学生/来源类型/职业边界42项fixtures通过；数据正文哈希、证据偏移、详情分片及统计交叉核对通过；真实Edge在嵌套路径测试筛选、完整技术表、导出、详情、明暗主题和手机布局；离线工作台重建后与本包ID、分类、技能与正文一致。\n\n真实分期只有本次基线，比较器5项合成边界测试不构成市场历史数据。source_archives.zip包含公开来源存档，不应在网页中执行其HTML。部分来源只有可抽取正文/表行时保留实际范围，不能称其有独立完整JD。\n\n本专题含既有28,344条主语料的专业子集，不能与主看板直接相加。新补采以source_collection区分；相同官方岗位ID去重，招聘池/表行和逐岗JD分别统计。\n\n文件清单与SHA-256见data/manifest.json；ZIP外部哈希见作者专题目录的交付清单。\n'
    receipt=receipt.replace('42项fixtures',str(json.loads((ROOT/'evidence/rule_verification.json').read_text(encoding='utf-8'))['total_checks'])+'项fixtures')
    receipt=receipt.replace('比较器5项合成边界测试','比较器'+str(len(json.loads((ROOT/'evidence/compare_verification.json').read_text(encoding='utf-8'))['checks']))+'项合成边界测试')
    (OUT/'reports/验收说明.md').write_text(receipt,encoding='utf-8')
    files=[{'path':p.relative_to(OUT).as_posix(),'bytes':p.stat().st_size,'sha256':sha(p)} for p in sorted(OUT.rglob('*')) if p.is_file() and p.relative_to(OUT).as_posix()!='data/manifest.json' and '__pycache__' not in p.parts]
    manifest={'schema':'communications-handoff-manifest/1','version':'communications-v1','compiled_at':a['compiled_at'],'sealed_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'stats':stats,'checks':results,'files':files,'file_count':len(files),'trend_periods':1,'note':'File hashes exclude this manifest itself. Detailed-JD subsets and source audits must not be counted as additional jobs.'}
    (OUT/'data/manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    for item in files:assert sha(OUT/item['path'])==item['sha256']
    frozen=ROOT/'versions/communications_v1/通信工程就业数据包_v1.zip';frozen.parent.mkdir(parents=True,exist_ok=True)
    assert not frozen.exists(),'Immutable version already exists; use a new version, never overwrite a sealed ZIP'
    with zipfile.ZipFile(frozen,'x',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for p in sorted(OUT.rglob('*')):
            if p.is_file() and '__pycache__' not in p.parts:z.write(p,p.relative_to(OUT.parent))
    with zipfile.ZipFile(frozen) as z:assert z.testzip() is None
    shutil.copy2(frozen,ROOT/'通信工程就业数据包.zip')
    result={'version':'communications-v1','stats':stats,'package_folder':str(OUT),'frozen_zip':str(frozen),'zip_bytes':frozen.stat().st_size,'zip_sha256':sha(frozen),'verified_file_hashes':len(files),'source_v4_zip_sha256':sha(ROOT.parents[1]/'versions/frontend_v4/前端交接包_就业数据台_v4.zip')}
    (ROOT/'交付清单_v1.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(result,ensure_ascii=False))
if __name__=='__main__':main()
