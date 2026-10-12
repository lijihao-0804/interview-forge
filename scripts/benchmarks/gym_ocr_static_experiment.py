"""Offline OCR experiments on fixed, manually labelled screenshots.

Artifacts and model outputs are stored locally; this script has no browser actions.
"""
from __future__ import annotations

import argparse
import base64
import io
import itertools
import json
import re
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / '.maintenance' / 'ocr-static-20261012'
LEGACY = Path(r'C:\Users\20303\Desktop\研一1\体育场馆预约\exploration')
FONT = r'C:\Windows\Fonts\msyh.ttc'
TRUTH = {
    'old1':[2,4,1], 'old2':[4,1,3], 'old3':[4,2,3], 'old4':[2,3,4],
    'old5':[2,4,1], 'old6':[4,2,1], 'old7':[2,1,4],
    'sample8':[4,3,1], 'sample9':[5,4,3], 'sample10':[3,1,4],
    'sample11':[4,2,3], 'sample12':[3,1,4], 'sample13':[1,2,4]}


def save_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def prepare():
    import ddddocr
    OUT.mkdir(parents=True, exist_ok=True)
    det = ddddocr.DdddOcr(det=True, show_ad=False)
    sources = [(f'old{i}', LEGACY/'samples'/f'sample{i}-captcha.png', None, list(t))
               for i, t in enumerate(['研这五', '公山沙', '导让教', '日今越', '五原成', '穿众的'], 1)]
    sources.append(('old7', LEGACY/'web-captcha-current.png', None, list('啦的从')))
    filenames = [
        'cad0a6c5-011f-45f9-ae8e-fb64c7bc4d09', 'c7818838-b264-420a-9529-a11d92c6b52a',
        '1ff414f5-b0fe-48f6-937a-99be71f90a53', '944bccb4-c580-490c-93d3-cfb30ae6b2ad',
        'e0040052-ec14-4e01-8018-6e2df6d01093', '4750696f-1b89-4804-ad53-73ef934b9c7a']
    regions = [(20,82,432,278),(26,86,439,282),(19,83,433,279),
               (18,83,432,279),(18,83,431,279),(21,80,435,276)]
    targets = ['儿非到','话好轻','思令找','量件里','众旁边','山青从']
    for i, (name, region, ts) in enumerate(zip(filenames, regions, targets), 8):
        sources.append((f'sample{i}', Path(r'C:\Users\20303\AppData\Local\Temp')/f'codex-clipboard-{name}.png', region, list(ts)))
    manifest, cards = [], []
    for name, source, region, ts in sources:
        img = Image.open(source).convert('RGB')
        if region: img = img.crop(region)
        path = OUT/f'{name}.png'; img.save(path)
        raw = io.BytesIO(); img.save(raw, format='PNG')
        original_boxes=[list(map(int,b)) for b in det.detection(raw.getvalue()) if b[2]-b[0]>=10 and b[3]-b[1]>=10]
        boxes=sorted(original_boxes,key=lambda b:(b[0],b[1]))
        manifest.append({'name':name,'image':str(path),'source':str(source),'targets':ts,'boxes':boxes,'truth':TRUTH[name],'det_order':[boxes.index(b)+1 for b in original_boxes]})
        marked = img.resize((img.width*2,img.height*2),Image.Resampling.NEAREST)
        draw=ImageDraw.Draw(marked)
        for j,(x1,y1,x2,y2) in enumerate(boxes,1):
            draw.rectangle((x1*2,y1*2,x2*2,y2*2),outline='red',width=2)
            draw.rectangle((x1*2,y1*2,x1*2+24,y1*2+22),fill='white')
            draw.text((x1*2+3,y1*2),str(j),font=ImageFont.truetype(FONT,18),fill='black')
        marked.thumbnail((830,390))
        card=Image.new('RGB',(850,430),'white'); card.paste(marked,(10,35))
        ImageDraw.Draw(card).text((10,3),name+' '+''.join(ts),font=ImageFont.truetype(FONT,22),fill='black')
        cards.append(card)
    save_json(OUT/'manifest.json',manifest)
    for start in range(0,len(cards),4):
        page=Image.new('RGB',(1700,860),'#dddddd')
        for j,card in enumerate(cards[start:start+4]):page.paste(card,((j%2)*850,(j//2)*430))
        page.save(OUT/f'contact-{start//4+1}.png')
    print(json.dumps([{'name':m['name'],'targets':m['targets'],'boxes':m['boxes']} for m in manifest],ensure_ascii=False))


def montage(item, context=False):
    img=Image.open(item['image']).convert('RGB')
    count=len(item['boxes']); strip=Image.new('RGB',(count*200,210),'white')
    for i,bx in enumerate(item['boxes']):
        crop=img.crop(bx); crop.thumbnail((170,155))
        crop=crop.resize((max(1,round(crop.width*min(170/crop.width,155/crop.height))),max(1,round(crop.height*min(170/crop.width,155/crop.height)))),Image.Resampling.LANCZOS)
        strip.paste(crop,(i*200+(200-crop.width)//2,40+(155-crop.height)//2))
        ImageDraw.Draw(strip).text((i*200+85,5),str(i+1),font=ImageFont.truetype(FONT,26),fill='black')
    if not context:return strip
    scene=img.resize((count*200,round(img.height*count*200/img.width)),Image.Resampling.LANCZOS)
    both=Image.new('RGB',(count*200,scene.height+230),'white');both.paste(scene,(0,0));both.paste(strip,(0,scene.height+20))
    return both


def evaluate(item,pred,coordinates=False):
    if coordinates:
        img=Image.open(item['image']); ids=[]
        for point in pred:
            try:
                x,y=float(point[0])*img.width/1000,float(point[1])*img.height/1000
                ids.append(next((i for i,(x1,y1,x2,y2) in enumerate(item['boxes'],1) if x1<=x<=x2 and y1<=y<=y2),0))
            except (TypeError,ValueError,IndexError):ids.append(0)
    else:
        ids=[]
        for v in pred:
            try:ids.append(int(v))
            except (TypeError,ValueError):ids.append(0)
    ids=(ids+[0]*len(item['targets']))[:len(item['targets'])]
    correct=sum(a==b for a,b in zip(ids,item['truth']))
    return {'ids':ids,'correct_chars':correct,'all_correct':correct==len(item['truth']),
            'assigned_complete':all(1<=i<=len(item['boxes']) for i in ids) and len(set(ids))==len(item['truth'])}


def api(args):
    from concurrent.futures import ThreadPoolExecutor,as_completed
    import requests
    data=json.loads((OUT/'manifest.json').read_text(encoding='utf-8'))
    if args.names:data=[x for x in data if x['name'] in args.names.split(',')]
    keypath=ROOT/'.maintenance'/'deepseek-api-key.txt'
    if not keypath.is_file():keypath=ROOT/'data'/'gym-deepseek-key.txt'
    key=keypath.read_text(encoding='utf-8').strip()
    if not key.startswith('sk-'):raise ValueError('Missing API key')
    output=OUT/f'api-{args.method}-{args.thinking}-{args.run}.jsonl'
    if output.exists():raise FileExistsError('Choose a fresh --run value; existing records are preserved')
    def one(item):
        coords=args.method=='coordinates'
        if coords:
            img=Image.open(item['image']).convert('RGB'); scale=max(1,1000/img.width)
            img=img.resize((round(img.width*scale),round(img.height*scale)),Image.Resampling.LANCZOS)
            prompt='识别图片中的彩色旋转汉字，并定位下列目标字符：'+','.join(item['targets'])+'。每个目标字符在图中出现一次。背景文字不是目标。按目标顺序返回每个字符的中心位置，坐标使用相对于整张图片宽高的0到1000整数坐标。只输出JSON，例如 {"points":[[123,456],[300,200],[500,800]]}。'
        else:
            img=montage(item,context=args.method=='context')
            prompt='这是中文艺术字辨认实验。'+('上半部为原始图片，下半部为' if args.method=='context' else '')+'从同一图片提取的编号小图，有汉字，也可能有背景物体。汉字可能旋转、倾斜、扭曲。请将目标字符 '+','.join(item['targets'])+' 分别匹配到编号小图。每个目标字符在这些图中出现一次，三个目标必须分配到三个不同编号，其余小图是干扰项。综合比较所有小图的字形，选择最符合的唯一分配。按目标顺序只输出JSON，例如 {"boxes":[2,4,1]}。'
        img.save(OUT/f"input-{args.method}-{item['name']}.png")
        buf=io.BytesIO();img.save(buf,format='PNG')
        payload={'model':'deepseek-flash','messages':[{'role':'system','content':'你是视觉字形匹配器。仅返回请求的JSON对象，不得解释或输出Markdown。'}, {'role':'user','content':[{'type':'text','text':prompt},{'type':'image_url','image_url':{'url':'data:image/png;base64,'+base64.b64encode(buf.getvalue()).decode('ascii')}}]}],
                 'thinking':{'type':'disabled' if args.thinking=='none' else 'enabled'},'max_tokens':512 if args.thinking=='none' else 2048,
                 'response_format':{'type':'json_object'}}
        if args.thinking!='none':payload['reasoning_effort']=args.thinking
        else:payload['temperature']=0
        started=time.perf_counter();result={'name':item['name'],'method':args.method,'thinking':args.thinking,'truth':item['truth']}
        try:
            response=requests.post('https://api.deepseek.com/chat/completions',headers={'Authorization':'Bearer '+key},json=payload,timeout=(15,55))
            response.raise_for_status();body=response.json();message=body['choices'][0]['message'];answer=message.get('content') or ''
            match=re.search(r'\{.*\}',answer,re.S); obj=json.loads(match.group(0)) if match else {};pred=obj.get('points' if coords else 'boxes',[])
            result.update(evaluate(item,pred,coordinates=coords));result.update({'answer':answer,'usage':body.get('usage',{}),'finish_reason':body['choices'][0].get('finish_reason')})
        except Exception as exc:result.update({'error':type(exc).__name__,'correct_chars':0,'all_correct':False,'assigned_complete':False})
        result['seconds']=round(time.perf_counter()-started,3)
        return result
    rows=[]
    with ThreadPoolExecutor(max_workers=2) as pool,output.open('w',encoding='utf-8') as fp:
        futures=[pool.submit(one,x) for x in data]
        for future in as_completed(futures):
            result=future.result();rows.append(result);fp.write(json.dumps(result,ensure_ascii=False)+'\n');fp.flush()
            print(json.dumps({k:v for k,v in result.items() if k not in ('answer','usage')},ensure_ascii=False),flush=True)
    print(json.dumps({'samples':len(rows),'all_correct':sum(x['all_correct'] for x in rows),'correct_chars':sum(x['correct_chars'] for x in rows),'mean_s':sum(x['seconds'] for x in rows)/len(rows)},ensure_ascii=False))


def best_unique(score):
    if score.ndim!=2 or score.shape[0]==0 or score.shape[1]<score.shape[0]:
        raise ValueError('Not enough detected boxes for a distinct assignment')
    choices=[]
    for ids in itertools.permutations(range(score.shape[1]),score.shape[0]):
        value=sum(score[t,b] for t,b in enumerate(ids));choices.append((float(value),ids))
    choices.sort(reverse=True)
    return [i+1 for i in choices[0][1]], choices[0][0]-choices[1][0]


def probability_match(img,boxes,targets,models,padding=0):
    scores=np.zeros((len(models),len(targets),len(boxes)))
    for bi,bx in enumerate(boxes):
        x1,y1,x2,y2=bx
        crop=img.crop((max(0,x1-padding),max(0,y1-padding),min(img.width,x2+padding),min(img.height,y2+padding)))
        for mi,model in enumerate(models):
            result=model.classification(crop,probability=True)
            probs=np.asarray(result['probabilities']);probs=probs.reshape((-1,probs.shape[-1]));charset=result['charset']
            for ti,char in enumerate(targets):
                if char in charset:scores[mi,ti,bi]=float(probs[:,charset.index(char)].max())
    mean=scores.mean(axis=0)
    ids,gap=best_unique(np.log(mean+1e-12))
    return ids,gap,mean


def probability(args):
    import random
    import ddddocr
    import psutil
    data=json.loads((OUT/'manifest.json').read_text(encoding='utf-8'))
    if args.names:data=[x for x in data if x['name'] in args.names.split(',')]
    started=time.perf_counter();det=ddddocr.DdddOcr(det=True,show_ad=False)
    models=[ddddocr.DdddOcr(show_ad=False,beta=b) for b in ([False,True] if args.model=='dual' else [args.model=='beta'])]
    init_s=time.perf_counter()-started;rows=[];rng=random.Random(20261012)
    for repeat in range(1,args.repeat+1):
        for item in data:
            img=Image.open(item['image']).convert('RGB');raw=io.BytesIO();img.save(raw,format='PNG');started=time.perf_counter()
            boxes=[list(map(int,b)) for b in det.detection(raw.getvalue()) if b[2]-b[0]>=10 and b[3]-b[1]>=10]
            targets=list(item['targets']);order=list(range(len(targets)))
            if args.drop_target:
                removed=item['boxes'][item['truth'][0]-1]
                boxes=[b for b in boxes if b!=removed]
            if args.shuffle:rng.shuffle(boxes);rng.shuffle(order);targets=[targets[i] for i in order]
            if args.negative:targets[0]='猫' if '猫' not in targets else '狗'
            pred,gap,scores=probability_match(img,boxes,targets,models,padding=args.padding)
            elapsed=time.perf_counter()-started
            canonical=[item['boxes'].index(boxes[i-1])+1 for i in pred];restored=[0]*len(order)
            for i,k in enumerate(order):restored[k]=canonical[i]
            stats=evaluate(item,restored)
            if args.negative:stats['all_correct']=False;stats['correct_chars']=0
            locations=[{'target':item['targets'][i],'box':item['boxes'][b-1],'center':[(item['boxes'][b-1][0]+item['boxes'][b-1][2])/2,(item['boxes'][b-1][1]+item['boxes'][b-1][3])/2]} for i,b in enumerate(restored)]
            row={'name':item['name'],'repeat':repeat,'model':args.model,'padding':args.padding,'shuffle':args.shuffle,'negative':args.negative,'drop_target':args.drop_target,'targets':targets,'log_gap':round(gap,4),'seconds':round(elapsed,4),'selected_probabilities':[float(scores[i,b-1]) for i,b in enumerate(pred)],'locations':locations,**stats};rows.append(row)
            if not args.negative and not args.drop_target:
                marked=img.resize((img.width*3,img.height*3),Image.Resampling.NEAREST);draw=ImageDraw.Draw(marked)
                for n,loc in enumerate(locations,1):
                    x1,y1,x2,y2=loc['box'];cx,cy=loc['center'];draw.rectangle((x1*3,y1*3,x2*3,y2*3),outline='#00b040',width=3);draw.ellipse((cx*3-5,cy*3-5,cx*3+5,cy*3+5),fill='#ff0000');draw.text((x1*3,max(0,y1*3-30)),str(n)+':'+loc['target'],font=ImageFont.truetype(FONT,26),fill='#ff0000',stroke_width=1,stroke_fill='white')
                marked.save(OUT/f"prediction-{item['name']}.png")
        print(json.dumps({'repeat':repeat,'all_correct':sum(x['all_correct'] for x in rows if x['repeat']==repeat),'n':len(data),'mean_s':sum(x['seconds'] for x in rows if x['repeat']==repeat)/len(data)},ensure_ascii=False),flush=True)
    save_json(OUT/f'probability-{args.run}.json',{'init_s':round(init_s,4),'rss_mb':round(psutil.Process().memory_info().rss/2**20,2),'rows':rows})


def local(args):
    import ast
    import ddddocr
    from paddleocr import PaddleOCR
    data=json.loads((OUT/'manifest.json').read_text(encoding='utf-8'))
    if args.names:data=[x for x in data if x['name'] in args.names.split(',')]
    path=ROOT/'interview_forge'/'services'/'gym_automation.py';tree=ast.parse(path.read_text(encoding='utf-8'))
    node=next(x for x in tree.body if isinstance(x,ast.FunctionDef) and x.name=='assign_targets')
    scope={};exec(compile(ast.Module(body=[node],type_ignores=[]),str(path),'exec'),scope);production=scope['assign_targets']
    std=ddddocr.DdddOcr(show_ad=False);beta=ddddocr.DdddOcr(show_ad=False,beta=True)
    paddle=PaddleOCR(use_angle_cls=True,lang='ch',show_log=False)
    rows=[]
    angles=[float(v) for v in args.angles.split(',')]
    for item in data:
        img=Image.open(item['image']).convert('RGB');started=time.perf_counter();entries=[];scores=np.zeros((2,len(item['targets']),len(item['boxes'])))
        texts=[]
        for bi,bx in enumerate(item['boxes']):
            crop=img.crop(bx);entry={'id':bi+1,'box':bx,'paddle_chars':''};variants=[]
            for angle in angles:
                view=crop if angle==0 else crop.rotate(angle,resample=Image.Resampling.BICUBIC,expand=True,fillcolor='white')
                for mi,(tag,ocr) in enumerate([('std',std),('beta',beta)]):
                    result=ocr.classification(view,probability=True)
                    if angle==0:entry[tag]=result['text']
                    probs=np.asarray(result['probabilities']);probs=probs.reshape((-1,probs.shape[-1]));charset=result['charset']
                    peaks=[float(probs[:,charset.index(t)].max()) if t in charset else 0.0 for t in item['targets']]
                    scores[mi,:,bi]=np.maximum(scores[mi,:,bi],peaks)
                    variants.append({'model':tag,'angle':angle,'text':result['text'],'target_peaks':peaks})
            entries.append(entry);texts.append(variants)
        results=paddle.ocr(np.asarray(img),cls=True)
        for line in (results[0] or []):
            poly,(text,confidence)=line;xs=[x[0] for x in poly];ys=[x[1] for x in poly];px1,py1,px2,py2=min(xs),min(ys),max(xs),max(ys)
            han=[c for c in text if '\u4e00'<=c<='\u9fff']
            for entry in entries:
                x1,y1,x2,y2=entry['box'];cx,cy=(x1+x2)/2,(y1+y2)/2
                for k,ch in enumerate(han):
                    ccx=px1+(px2-px1)*(k+.5)/len(han);ccy=(py1+py2)/2
                    if abs(ccx-cx)<=(px2-px1)/len(han) and abs(ccy-cy)<=(py2-py1):entry['paddle_chars']+=ch
        methods={}
        ordered=[entries[i-1] for i in item['det_order']]
        for name,routes in [('std',['std']),('beta',['beta']),('dual',['std','beta']),('current_local',['std','beta','paddle_chars'])]:
            es=[{**e,**{r:'' for r in ('std','beta','paddle_chars') if r not in routes}} for e in ordered]
            mapping=production(es,item['targets']);pred=[mapping[t]['id'] if t in mapping else 0 for t in item['targets']]
            methods[name]=evaluate(item,pred)
        for name,score in [('prob_max',np.max(scores,axis=0)),('prob_mean',np.mean(scores,axis=0))]:
            pred,gap=best_unique(np.log(score+1e-12));methods[name]={**evaluate(item,pred),'log_gap':round(gap,4)}
        row={'name':item['name'],'seconds':round(time.perf_counter()-started,3),'methods':methods,'entries':entries,'scores':scores.tolist(),'variants':texts};rows.append(row)
        print(json.dumps({'name':item['name'],'seconds':row['seconds'],'methods':methods},ensure_ascii=False),flush=True)
    save_json(OUT/f'local-{args.run}.json',rows)
    for method in rows[0]['methods']:
        print(method,sum(x['methods'][method]['all_correct'] for x in rows),'/',len(rows),sum(x['methods'][method]['correct_chars'] for x in rows),'/',len(rows)*3)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('mode',choices=['prepare','api','local','probability']);parser.add_argument('--method',choices=['montage','context','coordinates'],default='montage');parser.add_argument('--thinking',choices=['none','low','high'],default='none');parser.add_argument('--run',default='1');parser.add_argument('--names',default='');parser.add_argument('--angles',default='0');parser.add_argument('--repeat',type=int,default=1);parser.add_argument('--padding',type=int,default=0);parser.add_argument('--model',choices=['std','beta','dual'],default='dual');parser.add_argument('--shuffle',action='store_true');parser.add_argument('--negative',action='store_true');parser.add_argument('--drop-target',action='store_true');args=parser.parse_args()
    if args.mode=='prepare':prepare()
    elif args.mode=='api':api(args)
    elif args.mode=='local':local(args)
    else:probability(args)
