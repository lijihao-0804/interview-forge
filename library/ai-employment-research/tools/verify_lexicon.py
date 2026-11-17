"""Independent positive/negative extraction fixtures; never writes a market snapshot."""
import argparse, importlib.util, json, re, sys
from pathlib import Path

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--extractor', type=Path, required=True)
    p.add_argument('--dictionary', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a=p.parse_args()
    spec=importlib.util.spec_from_file_location('atomic_lexicon_verifier_target', a.extractor)
    module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
    dictionary=module.read_dictionary(a.dictionary);nodes=module.make_automaton(dictionary)
    terms={t['id']:t for t in dictionary['terms']}
    fixtures=[
        ('中文相邻技术词', '熟悉Python和LangChain、LangGraph', ['Python','LangChain','LangGraph'], []),
        ('C++不得拆成C', '熟悉C++', ['C++'], ['C']),
        ('明确C与C++', '掌握C/C++', ['C','C++'], []),
        ('英文前端要求', 'Experience with React and Vue', ['React','Vue.js'], []),
        ('英文语言要求', 'Proficiency in Rust', ['Rust'], []),
        ('后端技术枚举', 'Python, Flask and FastAPI', ['Python','Flask','FastAPI'], []),
        ('数据平台枚举', 'Hadoop/Spark/Hive', ['Apache Hadoop','Apache Spark','Apache Hive'], []),
        ('调度平台枚举', 'Ray, Slurm and Kubernetes', ['Ray platform','Kubernetes'], []),
        ('普通动词', 'We go beyond expectations and react to changes. We spark curiosity.', [], ['Go','React','Apache Spark']),
        ('相似词与普通用语', 'Provide prompt responses and support teams using Torchlight.', [], ['Prompt engineering','PyTorch']),
        ('JavaScript不是Java', 'JavaScript framework', ['JavaScript'], ['Java']),
        ('Unicode偏移', '🧠熟悉Python', ['Python'], []),
        ('JD英文前端列表', 'Experience with open-source technologies (e.g. Linux, Spring, React)', ['React','Linux'], []),
        ('JD英文语言上下文', 'Exposure to multi-agent orchestration frameworks in Rust and Python.', ['Rust','Python'], []),
        ('JD英文计算平台', 'Proficiency with distributed computing frameworks (Spark, EMR, Redshift, Hive)', ['Apache Spark','Apache Hive'], []),
        ('JD模型服务列表', 'Ray/MLflow/model serving', ['Ray platform'], []),
        ('JD调度器列表', 'workloads on Slurm, Kubernetes', ['Kubernetes'], []),
        ('业务分析工具', '熟练使用Excel、Tableau和Power BI', ['Excel','Tableau','Power BI'], []),
        ('设计工具', '熟悉Figma、Axure和Photoshop', ['Figma','Axure','Photoshop'], []),
        ('游戏引擎', '熟悉Unity和Unreal Engine游戏开发', ['Unity','Unreal Engine'], []),
        ('普通英文非工具', 'excellent performance and unity across teams; sketch a plan', [], ['Excel','Unity','Sketch']),
        ('统计分析工具', '熟悉SPSS或SAS进行统计建模', ['SPSS','SAS'], []),
        ('三维制作工具', '熟悉Blender、3ds Max与Houdini制作', ['Blender','3ds Max','Houdini'], []),
    ]
    checks=[]
    for label,text,wanted,forbidden in fixtures:
        matches=module.find_matches(text,nodes);names={terms[m['term_id']]['name'] for m in matches}
        def canonical(name):
            return next((t['name'] for t in terms.values() if any(alias.casefold()==name.casefold() for alias in [t['name'],*t.get('aliases',[])])),name)
        ok={canonical(name) for name in wanted}<=names and not {canonical(name) for name in forbidden}&names
        for m in matches:
            assert text[m['start']:m['end']].casefold()==m['alias'].casefold(), (label,m)
        if label in ['调度平台枚举','JD调度器列表']:ok=ok and any('slurm' in name.casefold() for name in names)
        if label=='Unicode偏移':ok=ok and any(m['start']==3 and terms[m['term_id']]['name']=='Python' for m in matches)
        checks.append({'name':label,'passed':ok,'text':text,'found':sorted(names),'expected':wanted,'forbidden':forbidden})
    for text in ['熟悉Triton算子','Triton Inference Server和Triton','OpenAI Triton和Triton Inference Server以及Triton']:
        matches=module.find_matches(text,nodes);triton=[m for m in matches if 'triton' in terms[m['term_id']]['name'].casefold()]
        occurrences=list(re.finditer(r'Triton',text,re.I))
        ok=all(any(m['start']<=occ.start() and m['end']>=occ.end() for m in triton) for occ in occurrences)
        checks.append({'name':'Triton各处提及均保留','passed':ok,'text':text,'found':sorted({terms[m['term_id']]['name'] for m in triton})})
    result={'synthetic_fixture':True,'real_registry_writes':0,'dictionary_version':dictionary['dictionary_version'],'checks':checks,'passed':all(x['passed'] for x in checks)}
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'passed':result['passed'],'checks':len(checks),'failed':[x for x in checks if not x['passed']]},ensure_ascii=False))
    return 0 if result['passed'] else 1

if __name__=='__main__':sys.exit(main())
