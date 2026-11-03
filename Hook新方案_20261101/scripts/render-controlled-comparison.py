#!/usr/bin/env python3
"""Create a four-panel evidence figure from app-only captured PNGs.

Use the managed Python with Pillow. Source paths, hashes and crop geometry are
retained in the adjacent .sources.json. No desktop/display frame is used.
"""
from pathlib import Path
import argparse
import hashlib
import json
import math
import re
from datetime import datetime, timezone
from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
FONT = '/System/Library/Fonts/STHeiti Medium.ttc'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('matrix', type=Path)
    parser.add_argument('--frame', default='frame-010.png')
    args = parser.parse_args()
    matrix = args.matrix.resolve()
    out = ROOT / 'report-assets'
    out.mkdir(exist_ok=True)
    title_font = ImageFont.truetype(FONT, 48)
    subtitle_font = ImageFont.truetype(FONT, 29)
    heading_font = ImageFont.truetype(FONT, 34)
    note_font = ImageFont.truetype(FONT, 26)
    footer_font = ImageFont.truetype(FONT, 23)
    canvas = Image.new('RGB', (3600, 2440), '#edf1f5')
    draw = ImageDraw.Draw(canvas)
    draw.text((48, 28), '独立捕获探针实验，非 ToDesk 远端截图', font=title_font, fill='#12324c')
    draw.text((48, 96), '真实原生 AppKit 窗口；未启用媒体层保护。仅在独立捕获进程中加载或移除 hook。', font=subtitle_font, fill='#40546a')
    roles = [
        ('baseline', 'A · baseline：未加载 hook', '题目、原生输入内容与公共窗口正常可见', '#2e5f8c'),
        ('audit', 'B · audit：加载 hook，仅记录调用', '内容保持可见，核对加载本身没有隐藏画面', '#49748b'),
        ('block', 'C · block：加载 hook，遮蔽目标窗口', '考试窗口变黑；公共窗口保留，动态计数继续更新', '#a13e36'),
        ('recovery', 'D · recovery：新进程不加载 hook', '原生考试内容恢复可见，形成移除后的正对照', '#346a50'),
    ]
    records = []
    for index, (case, heading, note, color) in enumerate(roles):
        source = matrix / case / 'capture/sck-stream-application' / args.frame
        state = json.loads((matrix / case / 'target-before.json').read_text())
        report = json.loads((matrix / case / 'capture/report.json').read_text())
        assert report['applicationFilter']['processID'] == state['ownerPID']
        assert report['applicationFilter']['exceptingWindows'] == []
        display_id = report['applicationFilter']['displayID']
        display = next(d['frame'] for d in report['scDisplays'] if d['id'] == display_id)
        image = Image.open(source).convert('RGBA')
        boxes = [state[name]['bounds'] for name in ('exam', 'control')]
        left = min(b['x'] for b in boxes)
        top = min(b['y'] for b in boxes)
        right = max(b['x'] + b['width'] for b in boxes)
        bottom = max(b['y'] + b['height'] for b in boxes)
        sx, sy = image.width / display['width'], image.height / display['height']
        crop = [max(0, math.floor((left - display['x']) * sx) - 8),
                max(0, math.floor((top - display['y']) * sy) - 8),
                min(image.width, math.ceil((right - display['x']) * sx) + 8),
                min(image.height, math.ceil((bottom - display['y']) * sy) + 8)]
        cropped = image.crop(crop)
        # App-only frames have transparent areas outside the app's windows.
        # Showing transparency on gray makes an opaque black target explicit.
        background = Image.new('RGBA', cropped.size, '#e6ebf1')
        background.alpha_composite(cropped)
        composited = background.convert('RGB')
        card_x = 48 + (index % 2) * 1768
        card_y = 164 + (index // 2) * 1092
        card_w, card_h = 1736, 1064
        draw.rounded_rectangle((card_x, card_y, card_x + card_w, card_y + card_h), radius=20, fill='white', outline='#cbd4df', width=2)
        draw.text((card_x + 22, card_y + 20), heading, font=heading_font, fill=color)
        draw.text((card_x + 22, card_y + 68), note, font=note_font, fill='#34475b')
        target_w = card_w - 44
        target_h = round(composited.height * target_w / composited.width)
        assert target_h <= 886, 'Unexpected geometry exceeds panel bounds'
        displayed = composited.resize((target_w, target_h), Image.Resampling.LANCZOS)
        image_x, image_y = card_x + 22, card_y + 112
        canvas.paste(displayed, (image_x, image_y))
        draw.rectangle((image_x, image_y, image_x + target_w, image_y + target_h), outline='#cbd4df', width=1)
        draw.text((card_x + 22, card_y + 1018), f'应用捕获流 · {args.frame} · 原始图 {image.width}×{image.height}', font=footer_font, fill='#53677c')
        records.append({'case': case, 'source': str(source.relative_to(ROOT)),
                        'sourceSHA256': hashlib.sha256(source.read_bytes()).hexdigest(),
                        'sourceSizePixels': list(image.size), 'cropPixelsLTRB': crop,
                        'cropMeaning': 'Union of complete exam/control CG window bounds plus 8-pixel margin',
                        'windowBoundsCG': {'exam': boxes[0], 'control': boxes[1]},
                        'displayFrameCG': display, 'displayID': display_id,
                        'captureScope': 'application', 'applicationOwnerPID': state['ownerPID'],
                        'panelImageRectPixels': [image_x, image_y, target_w, target_h],
                        'alphaBackground': '#e6ebf1', 'resize': 'LANCZOS',
                        'contentRetouched': False})
    draw.text((48, 2370), '透明区域以浅灰显示；只裁去窗口之外空白，完整保留考试遮蔽区域和公共对照。此图为 4 张代表帧，统计依据另见 281 张图的分析。', font=footer_font, fill='#40546a')
    destination = out / 'controlled-comparison.png'
    canvas.save(destination, optimize=True)
    provenance = {'createdAtUTC': datetime.now(timezone.utc).isoformat(),
                  'matrix': str(matrix.relative_to(ROOT)), 'output': str(destination.relative_to(ROOT)),
                  'outputSHA256': hashlib.sha256(destination.read_bytes()).hexdigest(),
                  'outputSizePixels': list(canvas.size), 'font': FONT,
                  'title': '独立捕获探针实验，非 ToDesk 远端截图',
                  'sourcePolicy': 'Application-filter captures only; no desktop or third-party remote-client screenshot.',
                  'sources': records}
    (out / 'controlled-comparison.sources.json').write_text(json.dumps(provenance, ensure_ascii=False, indent=2) + '\n')
    print(destination)


if __name__ == '__main__':
    main()
