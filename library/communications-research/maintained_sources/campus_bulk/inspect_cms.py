import pathlib,re
p=pathlib.Path(r'E:\JAVA\AI+agent\笔记\AI就业调研_2026-11-17\专题\通信工程_2026-11-18\campus_bulk\source_archive\union_zhaopin_cms-data-41c20234.js')
t=p.read_text(encoding='utf-8')
for pat in ['function y(', 'const y=', 'function p(', 'axios', 'baseURL', 'request(', 'function useHttp', 'dscSearchJobList({']:
 i=t.find(pat);print('\nPAT',pat,'pos',i)
 if i>=0:print(t[max(0,i-600):i+1800])
