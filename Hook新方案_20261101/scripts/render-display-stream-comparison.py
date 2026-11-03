#!/usr/bin/env python3
"""Extract only the two synthetic windows from legacy full-display captures."""
from pathlib import Path
import argparse, hashlib, json
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
p = argparse.ArgumentParser()
p.add_argument('matrix', type=Path)
a = p.parse_args()
matrix = a.matrix.resolve()
out = ROOT / 'report-assets'
out.mkdir(exist_ok=True)
font = '/System/Library/Fonts/STHeiti Medium.ttc'
def f(size): return ImageFont.truetype(font, size)
canvas = Image.new('RGB', (3600, 2600), '#eef2f6')
d = ImageDraw.Draw(canvas)
d.text((90, 46), 'CGDisplayStream 独立捕获探针：两种创建入口', font=f(62), fill='#132d4d')
d.text((90, 132), '非 UU / ToDesk 远端截图；只摘取合成考试窗与公共窗，拼版不代表桌面原始布局', font=f(35), fill='#405875')
provenance = {'matrix': str(matrix), 'description': 'Each card contains two separate exact synthetic window crops, rearranged side by side and independently resized; not the original desktop layout.', 'sources': []}
for i, (case, title, result) in enumerate([
    ('queue-baseline', 'DispatchQueue · 无 hook', '题目标记与公共窗口均可读'),
    ('queue-block', 'DispatchQueue · block', '考试区域变黑；公共窗口仍可读'),
    ('runloop-baseline', 'RunLoop · 无 hook', '题目标记与公共窗口均可读'),
    ('runloop-block', 'RunLoop · block', '考试区域变黑；公共窗口仍可读'),
]):
    x, y = 70 + (i % 2) * 1750, 230 + (i // 2) * 1150
    d.rounded_rectangle((x, y, x+1710, y+1110), radius=24, fill='white', outline='#d1dae5', width=3)
    d.text((x+30, y+25), title, font=f(44), fill='#133b62')
    d.text((x+30, y+86), result, font=f(32), fill='#1c7550' if case.endswith('block') else '#445871')
    source = matrix / case / 'capture/frame-0001.png'
    report = json.loads((matrix / case / 'capture/report.json').read_text())
    state = json.loads((matrix / case / 'target-before.json').read_text())
    display = report['displayBoundsPoints']
    with Image.open(source) as image:
        image.load()
        sx, sy = image.width/display['width'], image.height/display['height']
        entry = {'case': case, 'source': str(source.relative_to(ROOT)), 'sha256': hashlib.sha256(source.read_bytes()).hexdigest(), 'originalDimensions': list(image.size), 'displayBoundsPoints': display, 'crops': []}
        for kind, destx, desty, maxw, maxh in [('exam', x+30, y+150, 1090, 925), ('control', x+1150, y+200, 530, 500)]:
            b = state[kind]['bounds']
            crop = [round((b['x']-display['x'])*sx), round((b['y']-display['y'])*sy), round((b['x']+b['width']-display['x'])*sx), round((b['y']+b['height']-display['y'])*sy)]
            fragment = image.crop(crop).convert('RGB')
            fragment.thumbnail((maxw,maxh), Image.Resampling.LANCZOS)
            canvas.paste(fragment,(destx,desty))
            entry['crops'].append({'window':kind,'windowID':state[kind]['windowID'],'boundsPoints':b,'pixelCropLTRB':crop,'resizedDimensions':list(fragment.size),'positionOnComposite':[destx,desty],'resize':'LANCZOS; original pixels preserved except crop and resize'})
        d.text((x+1150,y+150), '独立公共对照窗', font=f(31), fill='#425773')
        d.text((x+1150,y+490), '实际图像裁剪', font=f(29), fill='#52657d')
        d.text((x+1150,y+535), '未重绘目标内容', font=f(29), fill='#52657d')
        provenance['sources'].append(entry)
d.text((90, 2545), '代表帧仅用于展示；判定依据为 8 个进程的生命周期、hook 日志、41 张 PNG 的 OCR 及公共 LIVE-TICK 对照。', font=f(29), fill='#425773')
canvas.save(out / 'display-stream-comparison.png')
(out / 'display-stream-comparison.sources.json').write_text(json.dumps(provenance,ensure_ascii=False,indent=2)+'\n')
print(out / 'display-stream-comparison.png')
