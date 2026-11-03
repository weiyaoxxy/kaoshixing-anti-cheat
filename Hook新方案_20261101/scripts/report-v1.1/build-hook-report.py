from pathlib import Path
import json, hashlib, re
from docx import Document
from docx.shared import Pt, RGBColor, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_CELL_VERTICAL_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.opc.constants import RELATIONSHIP_TYPE as RT

BASE=Path(__file__).resolve().parents[2]
DOC=Document(); sec=DOC.sections[0]
sec.page_width=Cm(21);sec.page_height=Cm(29.7)
sec.top_margin=Cm(1.6);sec.bottom_margin=Cm(1.6);sec.left_margin=Cm(1.8);sec.right_margin=Cm(1.8)
sec.header_distance=Cm(.55);sec.footer_distance=Cm(.55)
INK='17324D';BLUE='24638A';GRAY='526476';PALE='EFF4F7';TEAL='176B63'
def font(run,size=10.5,bold=False,color=None):
    run.font.name='Arial';run.font.size=Pt(size);run.bold=bold
    rf=run._element.get_or_add_rPr().get_or_add_rFonts()
    for k in list(rf.attrib):
        if k.endswith('Theme'):del rf.attrib[k]
    for k,v in [('ascii','Arial'),('hAnsi','Arial'),('eastAsia','PingFang SC')]:rf.set(qn('w:'+k),v)
    if color:run.font.color.rgb=RGBColor.from_string(color)
    return run
for name in ['Normal','Body Text','Caption','Title','Subtitle','Heading 1','Heading 2']:
    st=DOC.styles[name];st.font.name='Arial';st.font.size=Pt(10.5)
    rf=st.element.get_or_add_rPr().get_or_add_rFonts()
    for k in list(rf.attrib):
        if k.endswith('Theme'):del rf.attrib[k]
    for k,v in [('ascii','Arial'),('hAnsi','Arial'),('eastAsia','PingFang SC')]:rf.set(qn('w:'+k),v)
    st.paragraph_format.space_after=Pt(7);st.paragraph_format.line_spacing=1.16
DOC.styles['Heading 1'].paragraph_format.space_after=Pt(12)
DOC.styles['Heading 2'].paragraph_format.space_before=Pt(10)
DOC.styles['Heading 2'].paragraph_format.space_after=Pt(5)
DOC.styles['Caption'].paragraph_format.space_after=Pt(9)
DOC.core_properties.title='macOS 原生考试窗口：Hook 新方案验证报告'
DOC.core_properties.subject='独立捕获进程拦截；ToDesk与UU原版软件验证'
DOC.core_properties.author='技术验证项目'
DOC.core_properties.keywords='Hook; ScreenCaptureKit; ToDesk; UU; 原生控件; 捕获拦截'
font(sec.header.paragraphs[0].add_run('独立技术方案  /  macOS 原生考试窗口捕获拦截'),8.2,color=GRAY)
f=sec.footer.paragraphs[0];f.alignment=WD_ALIGN_PARAGRAPH.RIGHT
font(f.add_run('2026-11-01  ·  验证报告 1.1  |  '),8,color=GRAY)
field=OxmlElement('w:fldSimple');field.set(qn('w:instr'),'PAGE');f._p.append(field)
PAGES=[]
def page(title,subtitle=None):
    PAGES.append(title)
    p=DOC.add_paragraph(style='Heading 1');p.paragraph_format.page_break_before=len(PAGES)>1
    font(p.add_run(title),19,True,INK)
    if subtitle:para(subtitle,9.5,color=GRAY)
def para(text,size=10.5,bold=False,color=None):
    p=DOC.add_paragraph();font(p.add_run(text),size,bold,color);return p
def sub(text):
    p=DOC.add_paragraph(style='Heading 2');font(p.add_run(text),12,True,BLUE);return p
def note(text):return para(text,9,color=GRAY)
def table(headers,rows,widths,size=9.2,center=()):
    t=DOC.add_table(rows=1,cols=len(headers));t.alignment=WD_TABLE_ALIGNMENT.CENTER;t.autofit=False
    for c,w in zip(t.columns,widths):c.width=Cm(w)
    for c,w,s in zip(t.rows[0].cells,widths,headers):c.width=Cm(w);c.text=s
    h=OxmlElement('w:tblHeader');h.set(qn('w:val'),'true');t.rows[0]._tr.get_or_add_trPr().append(h)
    for row in rows:
        for c,w,s in zip(t.add_row().cells,widths,row):c.width=Cm(w);c.text=str(s)
    for ri,row in enumerate(t.rows):
        row._tr.get_or_add_trPr().append(OxmlElement('w:cantSplit'))
        for ci,c in enumerate(row.cells):
            c.vertical_alignment=WD_CELL_VERTICAL_ALIGNMENT.CENTER
            props=c._tc.get_or_add_tcPr();m=OxmlElement('w:tcMar')
            for side,val in [('top','95'),('bottom','95'),('left','110'),('right','110')]:
                e=OxmlElement('w:'+side);e.set(qn('w:w'),val);e.set(qn('w:type'),'dxa');m.append(e)
            props.append(m);shade=OxmlElement('w:shd');shade.set(qn('w:fill'),INK if ri==0 else PALE if ri%2 else 'FFFFFF');props.append(shade)
            b=OxmlElement('w:tcBorders');bottom=OxmlElement('w:bottom');bottom.set(qn('w:val'),'single');bottom.set(qn('w:sz'),'4');bottom.set(qn('w:color'),'D4E0E8');b.append(bottom);props.append(b)
            for p in c.paragraphs:
                p.paragraph_format.line_spacing=1.07;p.paragraph_format.space_after=Pt(1)
                if ci in center:p.alignment=WD_ALIGN_PARAGRAPH.CENTER
                for r in p.runs:font(r,size,ri==0,'FFFFFF' if ri==0 else INK)
    p=DOC.add_paragraph();p.paragraph_format.space_after=Pt(1);p.paragraph_format.space_before=Pt(0);font(p.add_run(''),2)
    return t
def figure(path,caption,width=17.4):
    p=DOC.add_paragraph();p.alignment=WD_ALIGN_PARAGRAPH.CENTER
    r=p.add_run();r.add_picture(str(BASE/path),width=Cm(width))
    for node in r._r.xpath('.//wp:docPr'):node.set('descr',caption)
    p.paragraph_format.keep_with_next=True;p.paragraph_format.space_after=Pt(4)
    p=DOC.add_paragraph(style='Caption');font(p.add_run(caption),8.7,color=GRAY)
def hyperlink(label,url):
    p=DOC.add_paragraph();p.paragraph_format.space_after=Pt(5)
    rel=p.part.relate_to(url,RT.HYPERLINK,is_external=True)
    h=OxmlElement('w:hyperlink');h.set(qn('r:id'),rel);r=OxmlElement('w:r');rp=OxmlElement('w:rPr');clr=OxmlElement('w:color');clr.set(qn('w:val'),BLUE);rp.append(clr);r.append(rp);tx=OxmlElement('w:t');tx.text=label;r.append(tx);h.append(r);p._p.append(h)
def code(text):
    p=para(text,8.6,color=INK);p.paragraph_format.line_spacing=1.05
    sh=OxmlElement('w:shd');sh.set(qn('w:fill'),PALE);p._p.get_or_add_pPr().append(sh)
exec((Path(__file__).with_name('report-content.py')).read_text(),globals())
out=BASE/'docs/Hook新方案验证报告_v1.1_UU连线验证.docx';DOC.save(out)
qa=BASE/'docs/Hook报告排版QA_v1.1';qa.mkdir(exist_ok=True)
(qa/'page-plan.json').write_text(json.dumps(PAGES,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'file':str(out),'plannedPages':len(PAGES),'sha256':hashlib.sha256(out.read_bytes()).hexdigest()},ensure_ascii=False))
