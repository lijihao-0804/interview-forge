import requests,pathlib,hashlib,json
b=pathlib.Path(r'E:\JAVA\AI+agent\笔记\AI就业调研_2026-11-17\专题\通信工程_2026-11-18\campus_bulk\source_archive');s=requests.Session();s.headers['User-Agent']='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36'
urls={
'union_2027_tju_authorization':'https://job.tju.edu.cn/recruitment/content/type/2/id/6404.html',
'shandong_unicom_2027_university_notice':'https://school.gxjy.sdei.edu.cn/qut/jiuye/zhaopingg/detail/17601',
'zte_2027_nankai_notice':'https://career.nankai.edu.cn/correcruit/content/id/117127.html',
'sasac_central_enterprise_directory':'https://wap.sasac.gov.cn/n2588045/n27271785/n27271792/c14159097/content.html',
'cict_group_organization':'https://www.cict.com/p1/AboutOrganization.jhtml'
}
manifest=[]
for name,url in urls.items():
 try:
  r=s.get(url,timeout=45); ext='.html'; p=b/(name+ext);p.write_bytes(r.content);meta={'name':name,'url':url,'resolved_url':r.url,'status':r.status_code,'path':'source_archive/'+p.name,'bytes':len(r.content),'sha256':hashlib.sha256(r.content).hexdigest(),'content_type':r.headers.get('content-type')};manifest.append(meta);print(name,r.status_code,len(r.content),meta['sha256'])
 except Exception as e:print('ERR',name,repr(e))
(b/'authority_sources_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
