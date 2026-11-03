from lxml import etree
import re

NS={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main','wp':'http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing','a':'http://schemas.openxmlformats.org/drawingml/2006/main','wps':'http://schemas.microsoft.com/office/word/2010/wordprocessingShape','v':'urn:schemas-microsoft-com:vml'}
W='{'+NS['w']+'}'

def prop(parent,tag):
    e=parent.find(W+tag)
    if e is None:
        e=etree.SubElement(parent,W+tag)
    return e

def break_before(p,needle):
    nodes=p.xpath('.//w:t',namespaces=NS)
    text=''.join(n.text or '' for n in nodes)
    off=text.index(needle)
    pos=0
    for n in nodes:
        s=n.text or ''
        if pos<=off<pos+len(s):
            k=off-pos
            n.text=s[:k]
            br=etree.Element(W+'br')
            n.addnext(br)
            t=etree.Element(W+'t');t.text=s[k:];t.set('{http://www.w3.org/XML/1998/namespace}space','preserve');br.addnext(t)
            return
        pos+=len(s)

def fix_layout(root):
    ps=root.xpath('//w:p',namespaces=NS)
    # Use installed fonts for imported Chinese text and SimSun answer rules.
    for run in root.xpath('//w:r',namespaces=NS):
        txt=''.join(run.xpath('./w:t/text()',namespaces=NS))
        rp=prop(run,'rPr');rf=prop(rp,'rFonts')
        existing=' '.join(rf.attrib.values())
        if re.search(r'[\u3400-\u9fff]',txt):
            for k in ['ascii','hAnsi','eastAsia','cs']:rf.set(W+k,'Arial Unicode MS')
        elif 'SimSun' in existing:
            for k in ['ascii','hAnsi','cs']:rf.set(W+k,'Times New Roman')
            rf.set(W+'eastAsia','Arial Unicode MS')
    # Explicit wrapping keeps the response parentheses attached to question 3.
    break_before(ps[27],'()     3.A.hair')
    break_before(ps[236],'()     3.A.fifty')
    # Restore the scale of one malformed A/box label.
    for run in ps[174].xpath('./w:r',namespaces=NS):
        if ''.join(run.xpath('./w:t/text()',namespaces=NS)).strip():
            rp=prop(run,'rPr')
            prop(rp,'sz').set(W+'val','22');prop(rp,'szCs').set(W+'val','22')
    # Imported text boxes are shorter than a text line: give their labels room.
    for idx in [162,169,175,182]:
        p=ps[idx]
        for anc in p.iterancestors():
            if etree.QName(anc).localname=='anchor':
                ext=anc.find('wp:extent',NS)
                if ext is not None and int(ext.get('cy','0'))<200000:ext.set('cy','240000')
                for ext in anc.xpath('.//a:xfrm/a:ext',namespaces=NS):
                    if int(ext.get('cy','0'))<200000:ext.set('cy','240000')
                break
    # Replace fragile space-only answer rules with visible, printable rules.
    for idx in [349,350]:
        for run in ps[idx].xpath('./w:r',namespaces=NS):
            txt=''.join(run.xpath('./w:t/text()',namespaces=NS))
            rp=prop(run,'rPr')
            if txt.isspace() and rp.find(W+'u') is not None:
                nodes=run.findall(W+'t')
                nodes[0].text='____________'
                for n in nodes[1:]:n.text=''
                rp.remove(rp.find(W+'u'))
            for s in list(rp.findall(W+'spacing')):rp.remove(s)
        pp=prop(ps[idx],'pPr');sp=prop(pp,'spacing');sp.set(W+'line','360');sp.set(W+'lineRule','auto')
    # The source omits the cat answer label; place it beside item 4 on its row.
    p=ps[266];pp=prop(p,'pPr');ind=prop(pp,'ind');ind.set(W+'left','600')
    run=etree.Element(W+'r');rp=etree.SubElement(run,W+'rPr')
    rf=etree.SubElement(rp,W+'rFonts');rf.set(W+'ascii','Times New Roman');rf.set(W+'hAnsi','Times New Roman')
    etree.SubElement(rp,W+'sz').set(W+'val','25')
    t=etree.SubElement(run,W+'t');t.set('{http://www.w3.org/XML/1998/namespace}space','preserve');t.text='3.c _ _                     '
    first=p.find(W+'r');p.insert(list(p).index(first),run)
    # Remove broken scanned margin rules while retaining the name text boxes.
    for idx in [3,227]:
        for drawing in list(ps[idx].xpath('.//w:drawing',namespaces=NS)):
            if not drawing.xpath('.//w:txbxContent',namespaces=NS):
                drawing.getparent().remove(drawing)
    # Keep the restored cat label and the forty label in their picture columns.
    t.text='3. __________'
    etree.SubElement(run,W+'tab')
    tabs=prop(pp,'tabs');tab=etree.SubElement(tabs,W+'tab');tab.set(W+'val','left');tab.set(W+'pos','3920')
    # Conventional sentence spacing and even leading in the reading passage.
    for idx in [349,350]:
        for node in ps[idx].xpath('./w:r/w:t',namespaces=NS):
            if node.text:node.text=re.sub(r'\.([A-Z])',r'. \1',node.text)
        prop(prop(ps[idx],'pPr'),'spacing').set(W+'before','0')
    # Separate the A label from its square so the square retains checkbox size.
    from copy import deepcopy
    for r in list(ps[174].xpath('./w:r',namespaces=NS)):
        txt=''.join(r.xpath('./w:t/text()',namespaces=NS))
        if 'A□' in txt:
            label=deepcopy(r)
            for n in label.xpath('./w:t',namespaces=NS):n.text='A '
            r.addprevious(label)
            for n in r.xpath('./w:t',namespaces=NS):n.text='□'
            prop(prop(r,'rPr'),'sz').set(W+'val','50')
            prop(prop(r,'rPr'),'szCs').set(W+'val','50')
            for e in list(prop(r,'rPr').findall(W+'spacing')):e.getparent().remove(e)
    prop(prop(ps[174],'pPr'),'spacing').set(W+'line','610')
    prop(prop(ps[174],'pPr'),'spacing').set(W+'lineRule','exact')
    # These four labels use legacy VML text boxes, not DrawingML anchors.
    for idx in [162,169,175,182]:
        p=ps[idx]
        for shape in p.iterancestors():
            if etree.QName(shape).localname=='shape':
                style=shape.get('style','')
                style=re.sub(r'width:[^;]+;', 'width:14pt;',style)
                style=re.sub(r'height:[^;]+;', 'height:18pt;',style)
                shape.set('style',style)
                break
        sp=prop(prop(p,'pPr'),'spacing');sp.set(W+'before','0');sp.set(W+'line','280');sp.set(W+'lineRule','exact')
    # Position identification fields explicitly, avoiding legacy rotated-box overlap.
    for outer_idx, inner_indices, ypos in [(3,[4,5],3800),(227,[228,229],800)]:
        outer=ps[outer_idx]
        for idx in inner_indices:
            p=ps[idx]
            for child in list(p):
                if child.tag!=W+'pPr':p.remove(child)
            run=etree.SubElement(p,W+'r');rp=etree.SubElement(run,W+'rPr')
            rf=etree.SubElement(rp,W+'rFonts')
            for k in ['ascii','hAnsi','eastAsia','cs']:rf.set(W+k,'Arial Unicode MS')
            etree.SubElement(rp,W+'sz').set(W+'val','20')
            etree.SubElement(rp,W+'szCs').set(W+'val','20')
            t=etree.SubElement(run,W+'t');t.text='姓名：__________    班级：__________    学号：__________';t.set('{http://www.w3.org/XML/1998/namespace}space','preserve')
            pp2=prop(p,'pPr');sp=prop(pp2,'spacing');sp.set(W+'before','0');sp.set(W+'line','300');sp.set(W+'lineRule','exact')
        for anchor in outer.xpath('.//wp:anchor[.//w:txbxContent]',namespaces=NS):
            ph=anchor.find('wp:positionH',NS);ph.set('relativeFrom','page');ph.find('wp:posOffset',NS).text=str(1900*635)
            pv=anchor.find('wp:positionV',NS);pv.set('relativeFrom','page');pv.find('wp:posOffset',NS).text=str(ypos*635)
            ext=anchor.find('wp:extent',NS);ext.set('cx',str(10000*635));ext.set('cy',str(400*635))
            for xf in anchor.xpath('.//a:xfrm',namespaces=NS):xf.set('rot','0')
            for ext in anchor.xpath('.//a:xfrm/a:ext',namespaces=NS):ext.set('cx',str(10000*635));ext.set('cy',str(400*635))
        for shape in outer.xpath('.//v:shape[.//w:txbxContent]',namespaces=NS):
            shape.set('style',f'position:absolute;margin-left:95pt;margin-top:{ypos/20}pt;mso-position-vertical-relative:page;mso-position-horizontal-relative:page;width:500pt;height:20pt;z-index:251694080;rotation:0;')
    # Reinstate imported answer rules without changing prompts or pictures.
    for idx in [297,302,309,313]:
        p=ps[idx]
        for r in p.xpath('./w:r',namespaces=NS):
            txt=''.join(r.xpath('./w:t/text()',namespaces=NS))
            if txt.strip()=='一':
                r.find(W+'t').text='____________'
                rp=prop(r,'rPr');rf=prop(rp,'rFonts')
                for k in ['ascii','hAnsi','eastAsia','cs']:rf.set(W+k,'Times New Roman')
                prop(rp,'sz').set(W+'val','22');prop(rp,'szCs').set(W+'val','22')
                for tag in ['spacing','w','position']:
                    for e in list(rp.findall(W+tag)):rp.remove(e)
    # The stray Chinese 二 in item 4 is an OCR artifact of the answer rule.
    for n in ps[266].xpath('./w:r/w:t',namespaces=NS):
        if n.text and '二' in n.text:n.text=n.text.replace('二','__')
    # Imported answer paragraphs had exact line heights below 3 pt, clipping rules.
    for idx in [297,302,309,313]:
        sp=prop(prop(ps[idx],'pPr'),'spacing')
        sp.set(W+'line','300');sp.set(W+'lineRule','exact')
