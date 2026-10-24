"""Offline benchmark of explicitly labelled Studio screenshots, not generated art.
Example labels: {"source":"studio_capture","samples":[{"file":"a.png",
"rect":[0,0,200,40],"kind":"draft","expected":"Giá 100k"}, ...]}
Does not send images anywhere and never operates Studio.
"""
import argparse,hashlib,json,time
from pathlib import Path
from PIL import Image
from studio_vision import read_image,ocr_model_info
from studio_vision_logic import exact_message,same_author,clock_reading,normalize

def run(labels,output):
 labels=Path(labels);manifest=json.loads(labels.read_text(encoding='utf-8'));results=[];images=set()
 for sample in manifest.get('samples',[]):
  image_path=labels.parent/sample['file'];digest=hashlib.sha256(image_path.read_bytes()).hexdigest()
  with Image.open(image_path) as image:
   rect=sample.get('rect',[0,0,image.width,image.height]);x,y,w,h=rect
   if min(x,y)<0 or min(w,h)<1 or x+w>image.width or y+h>image.height:raise ValueError('Invalid labelled crop')
   started=time.perf_counter();lines=read_image(image.crop((x,y,x+w,y+h)));seconds=time.perf_counter()-started
  text=' '.join(row['text'] for row in lines);expected=sample['expected'];kind=sample.get('kind','draft')
  match=clock_reading(lines)==expected if kind=='clock' else same_author(text,expected) if kind=='author' else exact_message(text,expected)
  results.append(dict(file=sample['file'],sha256=digest,kind=kind,expected=expected,read=text,matched=match,exact=normalize(text)==normalize(expected),seconds=round(seconds,4)))
  images.add(digest)
 report=dict(model=ocr_model_info()[1],source=manifest.get('source','unknown'),unique_images=len(images),samples=len(results),matched=sum(r['matched'] for r in results),exact=sum(r['exact'] for r in results),twenty_real_screenshots_supplied=manifest.get('source')=='studio_capture' and len(images)>=20,results=results)
 # Meeting the sample count is evidence, not automatic approval for unattended LIVE.
 report['native_live_acceptance']='NOT_PERFORMED'
 Path(output).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');return report
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('labels');p.add_argument('--output',default='ocr_benchmark.json');a=p.parse_args();r=run(a.labels,a.output);print(json.dumps({k:v for k,v in r.items() if k!='results'},ensure_ascii=False))
