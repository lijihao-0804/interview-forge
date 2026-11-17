"""Portable, streaming example: python tools/analyze_example.py --direction 'AI Infra'."""
import argparse,collections,gzip,json
from pathlib import Path
def main():
 p=argparse.ArgumentParser();p.add_argument('--input',type=Path,default=Path(__file__).resolve().parents[1]/'data/corpus.ndjson.gz');p.add_argument('--direction',default='AI Infra');args=p.parse_args()
 skills=collections.Counter();companies=collections.Counter();records=denominator=0
 with gzip.open(args.input,'rt',encoding='utf-8') as f:
  for line in f:
   row=json.loads(line)
   if row['title_direction']!=args.direction:continue
   records+=1
   if not row['requirements_available']:continue
   denominator+=1;companies[row['company']]+=1;skills.update(set(row['skills_in_requirement']))
 print(json.dumps({'direction':args.direction,'records':records,'requirements_denominator':denominator,'companies':companies,'skills':[{'skill':k,'n':v,'denominator':denominator,'pct':round(v/denominator*100,2) if denominator else None} for k,v in skills.most_common(15)],'note':'资格词提及，不代表必须精通；不是全国需求份额。'},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
