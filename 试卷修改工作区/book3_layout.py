from lxml import etree
from copy import deepcopy
import re

NS={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main','wp':'http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing','a':'http://schemas.openxmlformats.org/drawingml/2006/main','pic':'http://schemas.openxmlformats.org/drawingml/2006/picture','r':'http://schemas.openxmlformats.org/officeDocument/2006/relationships'}
W='{'+NS['w']+'}'
def E(tag, **attrs):
 e=etree.Element(W+tag)
 for k,v in attrs.items(): e.set(W+k,str(v))
 return e

def text_run(text,size=24):
 r=E('r'); rp=E('rPr'); rp.append(E('rFonts',ascii='Times New Roman',hAnsi='Times New Roman',eastAsia='Songti SC')); rp.append(E('sz',val=size)); r.append(rp); t=E('t');t.text=text;t.set('{http://www.w3.org/XML/1998/namespace}space','preserve');r.append(t);return r

def para(text='',line=280):
 p=E('p'); pp=E('pPr');pp.append(E('spacing',before=0,after=0,line=line,lineRule='atLeast'));p.append(pp)
 if text:p.append(text_run(text))
 return p

def cropped_picture(crop,ident,width=80,height=58):
 # Reuse the existing six-picture montage, cropping the requested cell.
 cx=int(width*12700);cy=int(height*12700)
 xml=f'''<w:r xmlns:w="{NS['w']}" xmlns:wp="{NS['wp']}" xmlns:a="{NS['a']}" xmlns:pic="{NS['pic']}" xmlns:r="{NS['r']}"><w:drawing><wp:inline distT="0" distB="0" distL="0" distR="0"><wp:extent cx="{cx}" cy="{cy}"/><wp:effectExtent l="0" t="0" r="0" b="0"/><wp:docPr id="{ident}" name="Preserved vocabulary picture {ident}"/><wp:cNvGraphicFramePr><a:graphicFrameLocks noChangeAspect="1"/></wp:cNvGraphicFramePr><a:graphic><a:graphicData uri="{NS['pic']}"><pic:pic><pic:nvPicPr><pic:cNvPr id="0" name="Original vocabulary picture"/><pic:cNvPicPr/></pic:nvPicPr><pic:blipFill><a:blip r:embed="rId43"/><a:srcRect l="{crop[0]}" t="{crop[1]}" r="{crop[2]}" b="{crop[3]}"/><a:stretch><a:fillRect/></a:stretch></pic:blipFill><pic:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr></pic:pic></a:graphicData></a:graphic></wp:inline></w:drawing></w:r>'''
 return etree.fromstring(xml.encode())

def fix_layout(root):
 ps=root.xpath('//w:p',namespaces=NS)
 for idx in (111,161):
  p=ps[idx]
  for n in p.xpath('./w:r/w:rPr/w:position',namespaces=NS):n.getparent().remove(n)
  spacing=p.find('w:pPr/w:spacing',NS)
  spacing.set(W+'lineRule','atLeast');spacing.set(W+'line',str(int(spacing.get(W+'line'))+180));spacing.set(W+'before','180')
 # Keep the first reading question with its choices across the page boundary.
 pp=ps[263].find('w:pPr',NS)
 if pp is None:pp=E('pPr');ps[263].insert(0,pp)
 if pp.find('w:keepNext',NS) is None:pp.append(E('keepNext'))
 # Replace only the malformed six-image vocabulary montage with an inline grid.
 old=ps[179];table=E('tbl');pr=E('tblPr');pr.append(E('tblW',w=8200,type='dxa'));pr.append(E('tblLayout',type='fixed'))
 borders=E('tblBorders')
 for edge in ('top','left','bottom','right','insideH','insideV'):borders.append(E(edge,val='nil'))
 pr.append(borders);m=E('tblCellMar')
 for edge in ('top','bottom'):m.append(E(edge,w=50,type='dxa'))
 for edge in ('left','right'):m.append(E(edge,w=80,type='dxa'))
 pr.append(m);table.append(pr);grid=E('tblGrid');grid.append(E('gridCol',w=4100));grid.append(E('gridCol',w=4100));table.append(grid)
 # Crops in 1/1000 percent of the unchanged 351x324 source image.
 entries=[('1.',(71000,0,0,74000),'_ _ _',82,58),('2.',(0,0,75000,75000),'s a l a d',62,58),('3.',(0,32000,75000,41000),'_ _ _ _',62,58),('4.',(73000,30000,7000,41000),'_ _ _ _ _',47,58),('5.',(0,80000,71000,0),'____________',80,53),('6.',(77000,76000,0,0),'_ _ _ _ _ _ _',62,58)]
 for row in range(3):
  tr=E('tr');trpr=E('trPr');trpr.append(E('cantSplit'));tr.append(trpr)
  for col in range(2):
   num,crop,answer,width,height=entries[row*2+col];tc=E('tc');tcpr=E('tcPr');tcpr.append(E('tcW',w=4100,type='dxa'));tcpr.append(E('vAlign',val='center'));tc.append(tcpr)
   p=para();p.find('w:pPr',NS).append(E('jc',val='center'));p.append(text_run(num+'  '));p.append(cropped_picture(crop,5000+row*2+col,width,height));tc.append(p)
   p=para(answer,line=300);p.find('w:pPr',NS).append(E('jc',val='center'));tc.append(p)
   tr.append(tc)
  table.append(tr)
 old.getparent().replace(old,table)
 # Keep answer fields visible when they otherwise wrap as trailing spaces.
 for t in ps[250].xpath('.//w:r/w:t',namespaces=NS):
  run=t.getparent();u=run.find('w:rPr/w:u',NS)
  if u is not None and t.text and not t.text.strip() and len(t.text)>=14:
   t.text='\u00a0__________';u.getparent().remove(u)

 # Prevent a question number being separated from its answer line.
 for t in ps[250].xpath('.//w:t',namespaces=NS):
  if t.text and re.search(r'[2-6]\.\s+$', t.text):
   t.text=re.sub(r'([2-6]\.)\s+$',r'\1',t.text)
 # Restore the writing section's five full-width ruled answer lines.
 for idx in range(289,294):
  p=ps[idx]
  for child in list(p):
   if child.tag!=W+'pPr':p.remove(child)
  pp=p.find('w:pPr',NS)
  if pp is None:pp=E('pPr');p.insert(0,pp)
  for child in list(pp):
   if child.tag in (W+'pBdr',W+'ind',W+'spacing'):pp.remove(child)
  pp.append(E('spacing',before=0,after=0,line=620,lineRule='exact'))
  p.append(text_run('_'*68))

 # Make all Chinese notes and fullwidth punctuation portable on this Mac.
 for run in root.xpath('//w:r',namespaces=NS):
  text=''.join(run.xpath('./w:t/text()',namespaces=NS))
  if re.search(r'[\u3400-\u9fff\uff08\uff09]',text):
   rp=run.find('w:rPr',NS)
   if rp is None:rp=E('rPr');run.insert(0,rp)
   rf=rp.find('w:rFonts',NS)
   if rf is None:rf=E('rFonts');rp.insert(0,rf)
   for key in ('ascii','hAnsi','eastAsia','cs'):rf.set(W+key,'Arial Unicode MS')
   for key in ('asciiTheme','hAnsiTheme','eastAsiaTheme','cstheme'):rf.attrib.pop(W+key,None)
