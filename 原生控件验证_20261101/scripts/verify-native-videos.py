#!/usr/bin/env python3
"""Full decode and PTS validation; selected semantic frames remain representative."""
from pathlib import Path
import argparse,subprocess,json,concurrent.futures,hashlib

parser=argparse.ArgumentParser();parser.add_argument('cases',nargs='+',type=Path);args=parser.parse_args()
paths=sorted({p.resolve() for case in args.cases for p in case.rglob('*.mp4')})
def check(p):
    probe=subprocess.run(['/opt/homebrew/bin/ffprobe','-v','error','-select_streams','v:0','-show_entries','stream=codec_name,width,height,nb_frames,duration','-of','json',str(p)],capture_output=True,text=True,timeout=20)
    decode=subprocess.run(['/opt/homebrew/bin/ffmpeg','-v','error','-i',str(p),'-fps_mode','passthrough','-enc_time_base','demux','-f','null','-'],capture_output=True,text=True,timeout=90)
    times=subprocess.run(['/opt/homebrew/bin/ffprobe','-v','error','-select_streams','v:0','-show_frames','-show_entries','frame=best_effort_timestamp_time','-of','json',str(p)],capture_output=True,text=True,timeout=90)
    ts=[float(f['best_effort_timestamp_time']) for f in json.loads(times.stdout).get('frames',[]) if 'best_effort_timestamp_time' in f]
    metadata=json.loads(probe.stdout);duration=float(metadata.get('streams',[{}])[0].get('duration',0))
    frames=[]
    dest=p.parent/'video-frames';dest.mkdir(exist_ok=True)
    for label,t in [('start',min(.5,duration/3)),('middle',duration/2),('end',max(0,duration-.2))]:
        output=dest/(p.stem+'-'+label+'.png')
        r=subprocess.run(['/opt/homebrew/bin/ffmpeg','-v','error','-ss',str(t),'-i',str(p),'-frames:v','1','-update','1','-y',str(output)],capture_output=True,text=True,timeout=25)
        frames.append({'label':label,'requestedSeconds':t,'firstInputPTSAtOrAfterRequest':next((v for v in ts if v>=t),None),'path':str(output),'returnCode':r.returncode,'errors':r.stderr})
    return {'video':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'metadata':metadata,
        'fullDecodeReturnCode':decode.returncode,'fullDecodeErrors':decode.stderr,'frameProbeErrors':times.stderr,
        'inputFrameCount':len(ts),'nonIncreasingPTS':sum(b<=a for a,b in zip(ts,ts[1:])),
        'representativeFrames':frames,'scope':'All video frames decoded; OCR/content interpretation is only on the three selected representative frames, not the complete movie.'}
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:rows=list(executor.map(check,paths))
root=Path(__file__).resolve().parent.parent
(root/'research/video-integrity.json').write_text(json.dumps({'files':rows},ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'files':len(rows),'decodeFailures':sum(r['fullDecodeReturnCode']!=0 or bool(r['fullDecodeErrors']) for r in rows),'timestampFailures':sum(bool(r['frameProbeErrors']) or r['nonIncreasingPTS']>0 for r in rows)},ensure_ascii=False))
