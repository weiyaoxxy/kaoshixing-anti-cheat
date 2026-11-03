#!/usr/bin/env python3
"""Inspect every saved ClearKey PNG and reconcile stream metadata; no empty pass."""
import argparse, csv, hashlib, json
from pathlib import Path
from PIL import Image, ImageChops


def mask(im):
    r,g,b,a=im.split()
    return ImageChops.multiply(ImageChops.multiply(ImageChops.multiply(
        r.point(lambda v:255 if v>=190 else 0),g.point(lambda v:255 if v<=90 else 0)),
        b.point(lambda v:255 if v>=190 else 0)),a.point(lambda v:255 if v>=200 else 0))


def main():
    ap=argparse.ArgumentParser();ap.add_argument('run',type=Path);ap.add_argument('--baseline',type=Path);args=ap.parse_args()
    base=args.run.resolve(); cases=[];csvrows=[]
    with Image.open((args.baseline or base/'plain-false')/'system-window.png') as x:
        plain=x.convert('RGBA');shadow_marker=mask(plain).getbbox()
    assert shadow_marker, 'Baseline shadow-padded window marker required'
    for case in sorted(base.iterdir()):
        if not case.is_dir() or not (case/'player-state.json').exists():continue
        state=json.loads((case/'player-state.json').read_text());report=json.loads((case/'capture/report.json').read_text())
        ocr={str(Path(x['path']).resolve()):x for x in map(json.loads,(case/'media-inspection.jsonl').read_text().splitlines())}
        window=next(x for x in report['cgWindows'] if x['id']==state['windowID'])['bounds']
        display=report['scDisplays'][0]['frame'];images=[]
        for p in sorted(case.rglob('*.png')):
            row={'path':str(p.relative_to(case)),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
            try:
                with Image.open(p) as x:im=x.convert('RGBA')
                if p.name.startswith('video-output-'):
                    roi=(1548,84,1724,212);group='video-output'
                elif p.name=='system-window.png':roi=shadow_marker;group='system-window'
                elif 'display' in str(p.relative_to(case)):
                    sx,sy=im.width/display['width'],im.height/display['height']
                    x=window['X']-display['x']+774
                    y=window['Y']-display['y']+window['Height']-500+42
                    roi=tuple(round(v) for v in (x*sx,y*sy,(x+88)*sx,(y+64)*sy))
                    group='stream-display' if 'sck-stream-display' in str(p) else p.stem
                else:
                    sx,sy=im.width/window['Width'],im.height/window['Height']
                    x,y=774,window['Height']-500+42
                    roi=tuple(round(v) for v in (x*sx,y*sy,(x+88)*sx,(y+64)*sy))
                    group='stream-window' if 'sck-stream-window' in str(p) else p.stem
                assert 0<=roi[0]<roi[2]<=im.width and 0<=roi[1]<roi[3]<=im.height,(p,roi,im.size)
                m=mask(im);area=(roi[2]-roi[0])*(roi[3]-roi[1]);pixels=m.crop(roi).histogram()[255]
                obs=ocr.get(str(p.resolve()));assert obs is not None,'missing OCR record'
                row.update(group=group,width=im.width,height=im.height,markerROI=roi,markerPixels=pixels,
                           markerArea=area,markerCoverage=pixels/area,markerObserved=pixels/area>=0.5,
                           ocrSecret=obs.get('secretDetected'),ocrError=obs.get('error'),
                           publicClearKeyLabelObserved=any('CLEARKEY-PUBLIC' in line for line in obs.get('lines',[])),
                           alphaExtrema=im.getchannel('A').getextrema())
            except Exception as exc:row['error']=str(exc)
            images.append(row);csvrows.append({'case':case.name,**{k:v for k,v in row.items() if not isinstance(v,(list,tuple,dict))}})
        groups={}
        for group in sorted(set(x.get('group','error') for x in images)):
            frames=[x for x in images if x.get('group','error')==group]
            groups[group]={'files':len(frames),'readable':sum('error' not in x for x in frames),
                           'ocrSecretDetected':sum(x.get('ocrSecret') is True for x in frames),
                           'markerDetected':sum(x.get('markerObserved') is True for x in frames),
                           'markerPixelsMin':min((x['markerPixels'] for x in frames if 'markerPixels' in x),default=None),
                           'markerPixelsMax':max((x['markerPixels'] for x in frames if 'markerPixels' in x),default=None)}
        streams={}
        for kind in ['window','display']:
            log=report['stream_'+kind];folder=case/'capture'/log['directory']
            expected={x['file'] for x in log['frames'] if x.get('saved')}
            actual={x.name for x in folder.glob('*.png')}
            pts=[x['ptsSeconds'] for x in log['frames'] if x.get('saved')]
            streams[kind]={'reportedSaved':log['completeFramesSaved'],'filesPresent':len(actual),
                           'expectedFilesExactlyPresent':bool(expected) and expected==actual,
                           'allValidComplete':bool(log['frames']) and all(x.get('sampleValid') and x.get('SCFrameStatusRaw')==0 for x in log['frames']),
                           'ptsSpanSeconds':max(pts)-min(pts) if pts else None,'errors':log.get('streamErrors',[])}
        cases.append({'case':case.name,'playerState':state,'capturePID':report['processID'],
                      'separateCaptureProcess':state['pid']!=report['processID'],
                      'permissionBefore':report['permissionBefore'],'permissionAfter':report['permissionAfter'],
                      'groups':groups,'streams':streams,'images':images})
    summary={'run':str(base),'method':'All saved PNGs decoded with Pillow; synthetic marker ROI RGBA threshold R>=190,G<=90,B>=190,A>=200, positive >=50%; all existing Vision OCR results reconciled. Baseline validates each path. No missing-frame pass.',
             'totalPNGs':sum(len(x['images']) for x in cases),'cases':cases}
    (base/'analysis.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    keys=sorted(set().union(*(row.keys() for row in csvrows)))
    with (base/'analysis.csv').open('w',newline='') as f:w=csv.DictWriter(f,fieldnames=keys);w.writeheader();w.writerows(csvrows)
    print(json.dumps({'totalPNGs':summary['totalPNGs'],'cases':[{'case':x['case'],'groups':x['groups'],'streams':x['streams']} for x in cases]},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
