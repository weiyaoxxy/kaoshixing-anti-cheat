from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
from copy import deepcopy
from lxml import etree
import re

SRC = Path('/Users/weiyao/Desktop/试卷修改版/G4期中试卷（40%修改版）.docx')
OUT = SRC.with_name('G4期中试卷（40%修改·排版修正版）.docx')
NS = {'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main',
      'wp':'http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing',
      'a':'http://schemas.openxmlformats.org/drawingml/2006/main'}
W='{'+NS['w']+'}'; WP='{'+NS['wp']+'}'

def prop(parent, name, **attrs):
    e=parent.find(W+name)
    if e is None: e=etree.SubElement(parent,W+name)
    for k,v in attrs.items(): e.set(W+k,str(v))
    return e

def ppr(p):
    e=p.find(W+'pPr')
    if e is None:
        e=etree.Element(W+'pPr');p.insert(0,e)
    return e

def txt(p): return ''.join(p.xpath('.//w:t/text()',namespaces=NS))

def table(widths, borders=False):
    t=etree.Element(W+'tbl');pr=etree.SubElement(t,W+'tblPr')
    prop(pr,'tblW',w=sum(widths),type='dxa');prop(pr,'tblLayout',type='fixed')
    mar=prop(pr,'tblCellMar')
    for k,n in [('top',40),('bottom',40),('left',70),('right',70)]:prop(mar,k,w=n,type='dxa')
    b=prop(pr,'tblBorders')
    for edge in ['top','left','bottom','right','insideH','insideV']:
        prop(b,edge,val='single' if borders else 'nil',sz='4',color='808080')
    grid=etree.SubElement(t,W+'tblGrid')
    for width in widths:prop(grid,'gridCol',w=width) if False else etree.SubElement(grid,W+'gridCol',{W+'w':str(width)})
    return t

def cell(row,width):
    c=etree.SubElement(row,W+'tc');pr=etree.SubElement(c,W+'tcPr')
    prop(pr,'tcW',w=width,type='dxa');prop(pr,'vAlign',val='top')
    return c

def inline_picture(anchor, max_width_pt=124, max_height_pt=144):
    ext=anchor.find(WP+'extent');cx=int(ext.get('cx'));cy=int(ext.get('cy'))
    scale=min(max_width_pt*12700/cx,max_height_pt*12700/cy)
    cx,cy=round(cx*scale),round(cy*scale)
    inline=etree.Element(WP+'inline',distT='0',distB='0',distL='0',distR='0')
    for child in anchor:
        if etree.QName(child).localname in ['extent','effectExtent','docPr','cNvGraphicFramePr','graphic']:
            inline.append(deepcopy(child))
    for e in inline.xpath('./wp:extent|.//a:xfrm/a:ext',namespaces=NS):e.set('cx',str(cx));e.set('cy',str(cy))
    p=etree.Element(W+'p');pr=ppr(p);prop(pr,'jc',val='center');prop(pr,'spacing',before=0,after=0)
    run=etree.SubElement(p,W+'r');drawing=etree.SubElement(run,W+'drawing');drawing.append(inline)
    return p

with ZipFile(SRC) as zin:
    root=etree.fromstring(zin.read('word/document.xml'))
    ps=root.xpath('//w:p',namespaces=NS)
    original_texts=[txt(p) for p in ps if not p.xpath('.//w:txbxContent',namespaces=NS)]
    # Remove application-sensitive hard page/column breaks and automatic spacing.
    for p in ps:
        pr=ppr(p)
        for e in list(pr.findall(W+'pageBreakBefore')):pr.remove(e)
        prop(pr,'snapToGrid',val=0)
        spacing=prop(pr,'spacing')
        spacing.set(W+'beforeAutospacing','0');spacing.set(W+'afterAutospacing','0')
        if txt(p).strip() and not p.xpath('.//w:txbxContent',namespaces=NS):
            spacing.set(W+'after','70')
            spacing.set(W+'line','264')
            spacing.set(W+'lineRule','auto')
        for br in p.xpath('./w:r/w:br[@w:type="column" or @w:type="page"]',namespaces=NS):br.getparent().remove(br)
        if not txt(p).strip() and not p.xpath('.//w:drawing|.//w:pict',namespaces=NS):
            prop(pr,'spacing',before=0,after=0,line=20,lineRule='exact')
    for grid in root.xpath('//w:docGrid',namespaces=NS):grid.set(W+'type','default')

    # Keep each question attached to its answer choices, using small groups.
    for start,end in [(48,49),(50,52),(53,55),(56,57),(58,59),(60,61),(62,63),(64,65),(66,67),(68,69),
                      (73,74),(75,76),(77,78),(79,80),(81,82),
                      (106,107),(108,111),(112,113),(114,115),(116,119),
                      (155,156),(157,158),(159,162),(163,166),(167,170)]:
        for i in range(start,end):prop(ppr(ps[i]),'keepNext',val=1)
        prop(ppr(ps[end]),'keepNext',val=0)

    # Inline picture cells follow their passages and do not reserve page-sized
    # floating-object areas in Word/WPS.
    for docid,start,end in [('2',87,90),('1',99,104),('3',127,130),('5',151,153)]:
        anchor=root.xpath('//wp:anchor[wp:docPr[@id="'+docid+'"]]',namespaces=NS)[0]
        picture=inline_picture(anchor)
        drawing=anchor.getparent();drawing.getparent().remove(drawing)
        blocks=ps[start:end+1]
        parent=blocks[0].getparent();at=parent.index(blocks[0])
        t=table([7900,2748]);row=etree.SubElement(t,W+'tr')
        prop(etree.SubElement(row,W+'trPr'),'cantSplit')
        left=cell(row,7900);right=cell(row,2748)
        for p in blocks:parent.remove(p);left.append(p)
        right.append(picture);parent.insert(at,t)

    # Replace the floating writing frame with a normal ruled table.
    old=ps[186];parent=old.getparent();at=parent.index(old)
    writing=table([10648],borders=True)
    for edge in ['top','bottom']:prop(writing.find(W+'tblPr').find(W+'tblCellMar'),edge,w=0,type='dxa')
    for i in range(12):
        row=etree.SubElement(writing,W+'tr');rp=etree.SubElement(row,W+'trPr')
        prop(rp,'cantSplit');prop(rp,'trHeight',val=880,hRule='atLeast')
        c=cell(row,10648);p=etree.SubElement(c,W+'p');pr=ppr(p)
        prop(pr,'spacing',before=0,after=0,line=360,lineRule='exact');prop(pr,'snapToGrid',val=0)
        prop(pr,'keepNext',val=1 if i<11 else 0)
        if i==0:
            run=etree.SubElement(p,W+'r');rr=etree.SubElement(run,W+'rPr')
            prop(rr,'rFonts',ascii='Times New Roman',hAnsi='Times New Roman');prop(rr,'sz',val=24)
            etree.SubElement(run,W+'t').text='My ______________'
    parent.remove(old);parent.insert(at,writing)
    # Leave a real paragraph following the table for Word's end marker.
    if parent[-2] is writing:parent.insert(len(parent)-1,etree.Element(W+'p'))

    # All normal exam paragraphs remain verbatim; only layout containers change.
    final_texts=[txt(p) for p in root.xpath('//w:p',namespaces=NS)]
    for text in original_texts:
        if text.strip() and text not in ('My ______________',):assert text in final_texts,text
    data=etree.tostring(root,encoding='UTF-8',xml_declaration=True,standalone=True)
    with ZipFile(OUT,'w',ZIP_DEFLATED) as zout:
        for entry in zin.infolist():zout.writestr(entry,data if entry.filename=='word/document.xml' else zin.read(entry.filename))
print(OUT)
