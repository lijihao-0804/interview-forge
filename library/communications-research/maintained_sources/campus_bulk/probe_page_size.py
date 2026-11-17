import requests
url='https://fe.zhaopin.com/grace/api/dsc/search-job-list';h={'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36','Origin':'https://zglt.zhaopin.com','Referer':'https://zglt.zhaopin.com/scjobs/index.html','Content-Type':'application/json'}
r=requests.post(url,json={'orgNumbers':['105347'],'jobSource':2,'pageIndex':1,'pageSize':100},headers=h,timeout=30)
print(r.status_code,len(r.content)); d=r.json();print(d.get('code'),d.get('message'),d.get('data',{}).get('pageInfo'),len(d.get('data',{}).get('jobList',[])))
