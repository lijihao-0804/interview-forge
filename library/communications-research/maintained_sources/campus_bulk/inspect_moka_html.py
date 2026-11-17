import pathlib,re,html
b=pathlib.Path(r'E:\JAVA\AI+agent\笔记\AI就业调研_2026-11-17\专题\通信工程_2026-11-18\campus_bulk\source_archive')
t=(b/'zte_mokahr.html').read_text(encoding='utf-8',errors='replace')
for k in ['window.TurboApply','window.MATERIAL_PLATFORM_HOST','window.orgMainLocale','data-site-id','siteId','orgId','__APOLLO_STATE__']:
 i=t.find(k);print('\nKEY',k,i); print(t[i:i+2500] if i>=0 else '')
