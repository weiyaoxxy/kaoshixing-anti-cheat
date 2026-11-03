from pathlib import Path
from docx import Document
from docx.shared import Cm, Pt, RGBColor
from docx.oxml.ns import qn
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_CELL_VERTICAL_ALIGNMENT
from docx.oxml import OxmlElement

root = Path(__file__).resolve().parent
workspace = root.parents[2]
doc = Document()
sec=doc.sections[0]
sec.page_width=Cm(21); sec.page_height=Cm(29.7)
sec.top_margin=Cm(2); sec.bottom_margin=Cm(2)
sec.left_margin=Cm(2); sec.right_margin=Cm(2)
for name in ['Normal','Title','Heading 1','Heading 2','Caption']:
    st=doc.styles[name]
    st.font.name='Arial';st.font.size=Pt(11)
    st.element.get_or_add_rPr().get_or_add_rFonts().set(qn('w:eastAsia'),'PingFang SC')
    st.paragraph_format.space_after=Pt(8)
    st.paragraph_format.line_spacing=1.18
for name,size in [('Title',24),('Heading 1',16),('Heading 2',13)]:
    doc.styles[name].font.size=Pt(size)
    doc.styles[name].font.color.rgb=RGBColor.from_string('143B57')
doc.add_heading('macOS 考试窗口防截屏',0)
doc.add_paragraph('文档渲染环境验证 · 2026-11-01 · 内部 QA')
doc.add_heading('中文、表格与截图',1)
doc.add_paragraph('该页仅验证中文字体、API 名称和截图排版。已验证、未验证和理论推断应在正式报告中分别标明。AVSampleBufferDisplayLayer.preventsCapture 与 NSWindow.sharingType = .none 不能仅凭赋值成功判断有效。')
t=doc.add_table(rows=1,cols=3);t.alignment=WD_TABLE_ALIGNMENT.CENTER;t.style='Light Shading Accent 1';t.autofit=False
for c,w in zip(t.columns,[Cm(4),Cm(4),Cm(9)]): c.width=w
for c,s in zip(t.rows[0].cells,['项目','证据状态','说明']):c.text=s
for vals in [('受保护显示','未在本页判断','渲染测试不产生防截屏结论。'),('内部录制','未在本页判断','仅使用现有截图检验文档图像清晰度。')]:
    row=t.add_row()
    for c,s in zip(row.cells,vals):
        c.text=s;c.vertical_alignment=WD_CELL_VERTICAL_ALIGNMENT.CENTER
        mar=OxmlElement('w:tcMar')
        for edge in ['top','left','bottom','right']:
            el=OxmlElement('w:'+edge);el.set(qn('w:w'),'110');el.set(qn('w:type'),'dxa');mar.append(el)
        c._tc.get_or_add_tcPr().append(mar)
doc.add_paragraph('')
img=workspace/'artifacts/smoke-baseline/source-reference.png'
if img.exists():doc.add_picture(str(img),width=Cm(16.5))
doc.add_paragraph('图 1：现有 Demo 渲染源截图，仅用于文档排版验证。',style='Caption')
footer=sec.footer.paragraphs[0];footer.text='内部环境验证页 · 不作为技术实验结果'
doc.save(root/'smoke.docx')
print(root/'smoke.docx')
