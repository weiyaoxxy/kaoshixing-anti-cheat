from pathlib import Path
import json, hashlib, shutil, re
from datetime import datetime
from docx import Document
from docx.shared import Inches, Pt, RGBColor, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_CELL_VERTICAL_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.opc.constants import RELATIONSHIP_TYPE as RT
from PIL import Image, ImageDraw, ImageFont

ROOT=Path(__file__).resolve().parents[2]
OLD=ROOT.parent
ASSETS=ROOT/'report-assets'; ASSETS.mkdir(exist_ok=True)
OUT=ROOT/'交付报告';OUT.mkdir(exist_ok=True)
D=Document()
sec=D.sections[0]
sec.page_width=Cm(21);sec.page_height=Cm(29.7)
sec.top_margin=Cm(1.65);sec.bottom_margin=Cm(1.65);sec.left_margin=Cm(1.8);sec.right_margin=Cm(1.8)
sec.header_distance=Cm(.6);sec.footer_distance=Cm(.65)
INK='17324D';BLUE='245D87';GRAY='526476';PALE='EDF3F7'

def font(run,size=None,bold=None,color=None):
    run.font.name='Arial'
    rpr=run._element.get_or_add_rPr();rf=rpr.rFonts
    if rf is None: rf=OxmlElement('w:rFonts');rpr.insert(0,rf)
    for attr in ['asciiTheme','hAnsiTheme','eastAsiaTheme','cstheme']:
        rf.attrib.pop(qn('w:'+attr),None)
    for name,val in [('ascii','Arial'),('hAnsi','Arial'),('eastAsia','PingFang SC')]:rf.set(qn('w:'+name),val)
    if size:run.font.size=Pt(size)
    if bold is not None:run.bold=bold
    if color:run.font.color.rgb=RGBColor.from_string(color)
    return run
for name in ['Normal','Body Text','Caption','Title','Subtitle','Heading 1','Heading 2','Heading 3']:
    st=D.styles[name];st.font.name='Arial';st.font.size=Pt(10.5)
    rf=st.element.get_or_add_rPr().get_or_add_rFonts()
    for k in list(rf.attrib):
        if k.endswith('Theme'):del rf.attrib[k]
    rf.set(qn('w:eastAsia'),'PingFang SC');rf.set(qn('w:ascii'),'Arial');rf.set(qn('w:hAnsi'),'Arial')
    st.paragraph_format.space_after=Pt(6)
    st.paragraph_format.line_spacing=1.16
D.styles['Heading 1'].font.size=Pt(19);D.styles['Heading 1'].font.color.rgb=RGBColor.from_string(INK)
D.styles['Heading 1'].paragraph_format.space_after=Pt(12)
D.styles['Heading 2'].font.size=Pt(12);D.styles['Heading 2'].font.color.rgb=RGBColor.from_string(BLUE)
D.styles['Heading 2'].paragraph_format.space_before=Pt(8)
D.styles['Caption'].font.size=Pt(9);D.styles['Caption'].font.color.rgb=RGBColor.from_string(GRAY)
D.styles['Caption'].paragraph_format.space_after=Pt(8)
D.core_properties.title='macOS 原生控件保护专项验证报告'
D.core_properties.subject='原生输入、受保护显示、外部捕获、中文候选窗及隐藏源窗口验证'
D.core_properties.author='技术预研'
D.core_properties.keywords='macOS; ScreenCaptureKit; preventsCapture; 考试; 技术验证'
header=sec.header.paragraphs[0]
font(header.add_run('技术预研  /  macOS 考试内容捕获保护'),8.5,color=GRAY)
header.paragraph_format.space_after=Pt(0)
footer=sec.footer.paragraphs[0];footer.alignment=WD_ALIGN_PARAGRAPH.RIGHT
font(footer.add_run('2026-11-01  ·  专项验证 v1.0  |  '),8,color=GRAY)
f=OxmlElement('w:fldSimple');f.set(qn('w:instr'),'PAGE');footer._p.append(f)
PAGE=0
PAGES=[]

def page(title,short=None):
    global PAGE
    PAGE+=1;PAGES.append((PAGE,title))
    if PAGE > 1:
        title = f'{PAGE-1:02d}  ' + re.sub(r'^\d{1,2}\s+', '', title)
    p=D.add_paragraph(style='Heading 1');font(p.add_run(title),19,bold=True,color=INK)
    p.paragraph_format.page_break_before = PAGE > 1
    if short:ptext(short,9.5,color=GRAY)

def ptext(text,size=10.5,bold=False,color=None):
    p=D.add_paragraph();font(p.add_run(text),size,bold,color);return p

def h2(text):
    p=D.add_paragraph(style='Heading 2');font(p.add_run(text),12,bold=True,color=BLUE);return p

def note(text):
    p=ptext(text,9.5,color=GRAY)
    p.paragraph_format.space_before=Pt(4)
    return p

def table(headers,rows,widths=None,size=9):
    t=D.add_table(rows=1, cols=len(headers));t.alignment=WD_TABLE_ALIGNMENT.CENTER;t.autofit=False
    widths=widths or [17.4/len(headers)]*len(headers)
    for col,w in zip(t.columns,widths):col.width=Cm(w)
    for cell,w,text in zip(t.rows[0].cells,widths,headers):
        cell.width=Cm(w);cell.text=text
    repeat=OxmlElement('w:tblHeader');repeat.set(qn('w:val'),'true');t.rows[0]._tr.get_or_add_trPr().append(repeat)
    for row in rows:
        for cell,w,text in zip(t.add_row().cells,widths,row):cell.width=Cm(w);cell.text=str(text)
    for ri,row in enumerate(t.rows):
        # Prevent splitting individual rows, without fixed heights.
        trpr=row._tr.get_or_add_trPr();cant=OxmlElement('w:cantSplit');trpr.append(cant)
        for ci,cell in enumerate(row.cells):
            cell.vertical_alignment=WD_CELL_VERTICAL_ALIGNMENT.CENTER
            tcpr=cell._tc.get_or_add_tcPr();m=OxmlElement('w:tcMar')
            for k,v in [('top','85'),('bottom','85'),('left','105'),('right','105')]:
                e=OxmlElement('w:'+k);e.set(qn('w:w'),v);e.set(qn('w:type'),'dxa');m.append(e)
            tcpr.append(m)
            shade=OxmlElement('w:shd');shade.set(qn('w:fill'),INK if ri==0 else ('F0F4F7' if ri%2 else 'FFFFFF'));tcpr.append(shade)
            borders=OxmlElement('w:tcBorders');bottom=OxmlElement('w:bottom');bottom.set(qn('w:val'),'single');bottom.set(qn('w:sz'),'4');bottom.set(qn('w:color'),'D7E1E8');borders.append(bottom);tcpr.append(borders)
            for p in cell.paragraphs:
                p.paragraph_format.space_after=Pt(1);p.paragraph_format.line_spacing=1.07
                if ci==0 and widths[ci]<2:p.alignment=WD_ALIGN_PARAGRAPH.CENTER
                for run in p.runs:font(run,size,ri==0,'FFFFFF' if ri==0 else INK)
    D.add_paragraph().paragraph_format.space_after=Pt(1)
    return t

def imagefile(src,caption,width=6.5,crop=None):
    src=Path(src);dest=ASSETS/(hashlib.sha256(src.read_bytes()).hexdigest()[:10]+'-'+src.name)
    if src.resolve()!=dest.resolve():
        if crop:
            with Image.open(src) as im:im.crop(crop).save(dest)
        else:shutil.copy2(src,dest)
    p=D.add_paragraph();p.alignment=WD_ALIGN_PARAGRAPH.CENTER
    r=p.add_run();r.add_picture(str(dest),width=Inches(width))
    for node in r._r.xpath('.//wp:docPr'):node.set('descr',caption)
    p.paragraph_format.space_after=Pt(4);p.paragraph_format.keep_with_next=True
    p=D.add_paragraph(style='Caption');font(p.add_run(caption),9,color=GRAY)
    return dest

def link(p,label,url):
    rid=p.part.relate_to(url,RT.HYPERLINK,is_external=True)
    hyper=OxmlElement('w:hyperlink');hyper.set(qn('r:id'),rid)
    run=OxmlElement('w:r');rpr=OxmlElement('w:rPr');c=OxmlElement('w:color');c.set(qn('w:val'),BLUE);rpr.append(c);u=OxmlElement('w:u');u.set(qn('w:val'),'single');rpr.append(u);run.append(rpr)
    txt=OxmlElement('w:t');txt.text=label;run.append(txt);hyper.append(run);p._p.append(hyper)


blocks=json.loads((Path(__file__).with_name('report_content.json')).read_text())
md=[]
for b in blocks:
    kind=b['kind']
    if kind=='page':
        page(b['text'],b.get('short'));md.append('# '+b['text']+'\n'+b.get('short','')+'\n')
    elif kind in ['p','note','h2']:
        if kind=='p':ptext(b['text'])
        elif kind=='note':note(b['text'])
        else:h2(b['text'])
        md.append(('## ' if kind=='h2' else '')+b['text']+'\n')
    elif kind=='table':
        t=table(b['headers'],b['rows'],b.get('widths'),b.get('size',9))
        for row in t.rows:
            for ci in b.get('center',[]):
                for p in row.cells[ci].paragraphs:p.alignment=WD_ALIGN_PARAGRAPH.CENTER
        md.append('| '+' | '.join(b['headers'])+' |\n| '+ ' | '.join(['---']*len(b['headers']))+' |\n'+'\n'.join('| '+' | '.join(str(c).replace('\n','<br>') for c in row)+' |' for row in b['rows'])+'\n')
    elif kind=='image':
        imagefile(ROOT/b['src'],b['caption'],width=b.get('width',6.5))
        md.append('!['+b['caption']+'](../'+b['src']+')\n')
    elif kind=='link':
        p=D.add_paragraph();link(p,b['text'],b['url']);md.append('['+b['text']+']('+b['url']+')\n')
filename=OUT/'原生控件保护_专项验证报告_v1.0.docx'
D.save(filename)
(OUT/'document-page-plan.json').write_text(json.dumps(PAGES,ensure_ascii=False,indent=2))
(ROOT/'docs/原生控件验证报告.md').write_text('\n'.join(md))
print(filename)
