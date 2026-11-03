from pathlib import Path
import subprocess,json,concurrent.futures
root=Path(__file__).resolve().parent.parent
matrix=Path((root/'artifacts/latest-deep-matrix.txt').read_text().strip())
paths=sorted(matrix.glob('*/*.mp4'))+sorted(matrix.glob('*/*.mov'))
def inspect(p):
 result=subprocess.run(['/opt/homebrew/bin/ffmpeg','-v','error','-i',str(p),'-fps_mode','passthrough','-enc_time_base','demux','-f','null','-'],capture_output=True,text=True,timeout=90)
 probe=subprocess.run(['/opt/homebrew/bin/ffprobe','-v','error','-select_streams','v:0','-show_entries','stream=codec_name,width,height,nb_frames,avg_frame_rate,duration','-of','json',str(p)],capture_output=True,text=True,timeout=15)
 frameprobe=subprocess.run(['/opt/homebrew/bin/ffprobe','-v','error','-select_streams','v:0','-show_frames','-show_entries','frame=best_effort_timestamp_time','-of','json',str(p)],capture_output=True,text=True,timeout=90)
 timestamps=[float(f['best_effort_timestamp_time']) for f in json.loads(frameprobe.stdout).get('frames',[]) if 'best_effort_timestamp_time' in f]
 return {'inputFrameCount':len(timestamps),'inputTimestampNonIncreasing':sum(b<=a for a,b in zip(timestamps,timestamps[1:])),'inputMinimumFrameDeltaSeconds':min((b-a for a,b in zip(timestamps,timestamps[1:])),default=None),'frameProbeErrors':frameprobe.stderr,'path':str(p.relative_to(matrix)),'fullDecodeReturnCode':result.returncode,'decodeErrors':result.stderr,'metadata':json.loads(probe.stdout),'scope':'All packets/frames decoded by ffmpeg; semantic/OCR inspection remains representative frames unless separately stated.'}
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:rows=list(executor.map(inspect,paths))
(matrix/'video-integrity.json').write_text(json.dumps({'files':rows},indent=2))
print('Videos fully decoded:',len(rows),'errors:',sum(r['fullDecodeReturnCode']!=0 or bool(r['decodeErrors']) for r in rows))
