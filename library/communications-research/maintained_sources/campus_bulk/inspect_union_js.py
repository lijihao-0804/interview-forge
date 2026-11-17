import pathlib,re
p=pathlib.Path(r'E:\JAVA\AI+agent\笔记\AI就业调研_2026-11-17\专题\通信工程_2026-11-18\campus_bulk\source_archive\union_zhaopin_mjobs_js.js')
t=p.read_text(encoding='utf-8')
for pat in [r'import[^;]{0,300};',r'\bfunction\s+p\([^)]*\)',r'const\s+p\s*=.{0,300}',r'let\s+p\s*=.{0,300}',r'\bp\s*=\s*\([^)]*\)\s*=>.{0,500}',r'\bUe\([^;]{0,300}']:
 print('\nPAT',pat)
 for x in re.finditer(pat,t):print(x.group(0)[:800])
