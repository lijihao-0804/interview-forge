"""Actual Edge checks at a nested route. Own browser/server only."""
import csv,functools,json,threading
from pathlib import Path
from http.server import SimpleHTTPRequestHandler,ThreadingHTTPServer
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1];PACKAGE=ROOT/'通信工程就业数据包';OUT=ROOT/'evidence/browser_qa';OUT.mkdir(parents=True,exist_ok=True)
PREFIX='/research/communications/'
class Handler(SimpleHTTPRequestHandler):
    extensions_map={**SimpleHTTPRequestHandler.extensions_map,'.mjs':'text/javascript'}
    def translate_path(self,path):
        if path.startswith(PREFIX):path=path[len(PREFIX)-1:]
        return super().translate_path(path)
    def log_message(self,*args):pass
def main():
    data=json.loads((PACKAGE/'data/catalog.json').read_text(encoding='utf-8'));jobs=data['jobs'];checks=[];errors=[];failed=[]
    server=ThreadingHTTPServer(('127.0.0.1',0),functools.partial(Handler,directory=str(PACKAGE)));threading.Thread(target=server.serve_forever,daemon=True).start();url=f'http://127.0.0.1:{server.server_port}{PREFIX}'
    def check(name,passed):checks.append({'name':name,'passed':bool(passed)});assert passed,name
    def size(page):return page.evaluate('window.__telecom.filtered().length')
    with sync_playwright() as p:
        browser=p.chromium.launch(executable_path='C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',headless=True)
        try:
            context=browser.new_context(viewport={'width':1500,'height':1050},reduced_motion='reduce',accept_downloads=True);page=context.new_page();page.on('pageerror',lambda e:errors.append(str(e)));page.on('response',lambda r:failed.append({'url':r.url,'status':r.status}) if r.status>=400 and r.url.startswith(url) else None)
            page.goto(url,wait_until='load');page.wait_for_function('window.__telecom !== undefined')
            expected=[j for j in jobs if j['student_confirmed'] and j['tier'] in ['A','B']]
            check('default student direct pool agrees with Python',size(page)==len(expected));check('all source records loaded',page.evaluate('window.__telecom.jobs.length')==len(jobs));check('initial view not scrolled',page.evaluate('scrollY')==0)
            check('eight conclusions rendered',page.locator('.insight').count()==8);check('four charts rendered',all(page.locator('#'+x+' .bar').count()>0 for x in ['careerChart','companyChart','cityChart','skillChart']))
            page.screenshot(path=str(OUT/'overview-light.png'))
            city=next(j['city_tags'][0] for j in expected if j['city_tags']);page.select_option('#city',city);check('city filter agrees with independent data',size(page)==sum(city in j['city_tags'] for j in expected));page.click('#reset')
            page.select_option('#quality','detailed');check('detailed JD filter agrees with recorded rubric',size(page)==sum(j['detailed_jd'] for j in expected));page.click('#reset')
            page.select_option('#status','deadline_passed');check('expired notice filter uses separate status field',size(page)==sum(j['current_status']=='deadline_passed' for j in expected));page.click('#reset')
            page.locator('.technology-panel>summary').click();page.fill('#techSearch','LangChain');check('full technical dictionary is searchable including zeros',page.locator('#techTable tr').count()==1)
            lc=next(t for t,d in data['terms'].items() if d['label']=='LangChain');expected_lc=sum(j['skill_eligible'] and lc in j['technology_ids'] for j in expected);check('full dictionary table denominator and count agree',page.locator('#techTable td').nth(2).inner_text()==f'{expected_lc:,}')
            page.locator('#techTable button').click();check('technical table drills to exact qualification cohort',size(page)==expected_lc);page.click('#reset');page.fill('#techSearch','')
            skill=next(t for t,d in data['terms'].items() if d['label']=='Python');page.select_option('#skill',skill);pyrows=[j for j in expected if j['skill_eligible'] and skill in j['technology_ids']];check('atomic Python filter agrees with data',size(page)==len(pyrows))
            with page.expect_download() as info:page.click('#csv')
            info.value.save_as(str(OUT/'filtered.csv'))
            with (OUT/'filtered.csv').open(encoding='utf-8-sig',newline='') as f:exported=list(csv.DictReader(f))
            check('CSV exports every matching row',len(exported)==len(pyrows));check('CSV protects ID fields',all(x['id'].startswith("'") or not x['id'].isdigit() for x in exported))
            restored=context.new_page();restored.goto(page.url);restored.wait_for_function('window.__telecom !== undefined');check('nested URL restores filters',size(restored)==len(pyrows) and restored.input_value('#skill')==skill);restored.close()
            page.locator('.job-bottom button').first.click();page.wait_for_selector('#detailBody .detail-copy');check('full archived JD loads lazily',len(page.locator('#detailBody').inner_text())>300);check('source link safe target',page.locator('#detailBody>a').get_attribute('rel')=='noopener noreferrer');page.screenshot(path=str(OUT/'jd-detail.png'));page.keyboard.press('Escape')
            page.click('#reset');page.select_option('#scope','all');page.select_option('#tier','all');check('all-layer occupation reference available',size(page)==len(jobs));page.select_option('#scope','experience');check('experience signal filter uses independent flag',size(page)==sum(j['experience_signal'] for j in jobs))
            page.select_option('#scope','all');page.fill('#search',jobs[0]['id']);check('exact archived record ID is searchable',size(page)==1);page.fill('#search','')
            page.click('#reset');page.select_option('#tier','C');check('catalog family is a separate selectable layer',size(page)==sum(j['student_confirmed'] and j['tier']=='C' for j in jobs));page.click('#reset')
            page.fill('#search','无此岗位zzzz');check('empty result is explained',size(page)==0 and page.locator('.empty').is_visible());page.click('#reset')
            report=context.new_page();r=report.goto(url+'reports/通信工程专业就业报告.html');check('report reachable at nested route',r.status==200 and report.locator('table').count()>=10);report.screenshot(path=str(OUT/'report.png'));report.close()
            page.evaluate('scrollTo(0,0)');page.click('#theme');check('dark theme toggles',page.locator('html').get_attribute('data-theme')=='dark');page.screenshot(path=str(OUT/'overview-dark.png'))
            page.click('#theme');page.set_viewport_size({'width':390,'height':844});page.screenshot(path=str(OUT/'overview-mobile.png'));check('mobile has no horizontal overflow',page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'));check('mobile filter controls stay inside viewport',page.locator('#city').evaluate('(e)=>e.getBoundingClientRect().right<=innerWidth'))
            # Exercise plain JSON fallback in an isolated context.
            fallback=browser.new_context();fallback.route('**/data/catalog.json.gz',lambda route:route.fulfill(status=404,body='missing'))
            fp=fallback.new_page();fp.goto(url);fp.wait_for_function('window.__telecom !== undefined');check('plain catalog fallback works',fp.evaluate('window.__telecom.jobs.length')==len(jobs));fallback.close()
            check('no browser runtime errors',not errors);check('no failed package resources',not failed);context.close()
        finally:browser.close();server.shutdown();server.server_close()
    result={'passed':all(x['passed'] for x in checks),'checks':checks,'runtime_errors':errors,'resource_failures':failed};(OUT/'verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(result,ensure_ascii=False))
if __name__=='__main__':main()
