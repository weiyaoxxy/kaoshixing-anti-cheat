"""Small layout repairs for G4; all paragraphs and exam content are preserved."""
from lxml import etree
from copy import deepcopy
import re

NS = {
    'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main',
    'wp': 'http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing',
    'a': 'http://schemas.openxmlformats.org/drawingml/2006/main',
    'v': 'urn:schemas-microsoft-com:vml',
}
W = '{' + NS['w'] + '}'


def fix_layout(root):
    ps = root.xpath('//w:body//w:p', namespaces=NS)
    # Keep each major exam block on its original spread after Chinese glyphs
    # regain their true line metrics in the renderer.
    for index in range(42, 47):
        spacing = ps[index].find(W + 'pPr').find(W + 'spacing')
        spacing.set(W + 'beforeAutospacing', '0')
        spacing.set(W + 'afterAutospacing', '0')
    # A small vocabulary illustration was just tall enough to push its final
    # question to a separate page once Chinese instructions were visible.
    for ext in ps[46].xpath('.//wp:extent|.//a:xfrm/a:ext', namespaces=NS):
        ext.set('cx', str(round(int(ext.get('cx')) * 0.8)))
        ext.set('cy', str(round(int(ext.get('cy')) * 0.8)))
    for index in (47, 98, 174):
        ppr = ps[index].find(W + 'pPr')
        before = ppr.find(W + 'pageBreakBefore')
        if before is None:
            before = etree.SubElement(ppr, W + 'pageBreakBefore')
        before.set(W + 'val', '1')
    for index in (70, 71, 83, 171, 172, 173):
        spacing = ps[index].find(W + 'pPr').find(W + 'spacing')
        for name in list(spacing.attrib):
            del spacing.attrib[name]
        spacing.set(W + 'before', '0')
        spacing.set(W + 'after', '0')
        spacing.set(W + 'line', '20')
        spacing.set(W + 'lineRule', 'exact')
    columnbreak = etree.Element(W + 'r')
    etree.SubElement(columnbreak, W + 'br').set(W + 'type', 'column')
    ps[72].insert(1, columnbreak)

    # Reassign the underline to the moved cloze gaps instead of inheriting
    # underline formatting from the old character offsets.
    for index in (88, 89):
        p = ps[index]
        text = ''.join(p.xpath('./w:r/w:t/text()', namespaces=NS))
        template = deepcopy(p.xpath('./w:r[w:t]/w:rPr', namespaces=NS)[0])
        for old in template.findall(W + 'u'):
            template.remove(old)
        for run in list(p.findall(W + 'r')):
            if run.find(W + 'drawing') is None:
                p.remove(run)
        for piece in re.split(r'(\s+[123]\s+)', text):
            if not piece:
                continue
            run = etree.SubElement(p, W + 'r')
            rp = deepcopy(template)
            run.append(rp)
            under = etree.SubElement(rp, W + 'u')
            under.set(W + 'val', 'single' if re.fullmatch(r'\s+[123]\s+', piece) else 'none')
            node = etree.SubElement(run, W + 't')
            node.set('{http://www.w3.org/XML/1998/namespace}space', 'preserve')
            node.text = piece

    # Restore ordinary aligned option tabs after changing all three labels.
    p = ps[156]
    template = deepcopy(p.xpath('./w:r/w:rPr', namespaces=NS)[0])
    for run in list(p.findall(W + 'r')):
        p.remove(run)
    tabs = p.find(W + 'pPr').find(W + 'tabs')
    if tabs is None:
        tabs = etree.SubElement(p.find(W + 'pPr'), W + 'tabs')
    for stop in list(tabs):
        tabs.remove(stop)
    for pos in (3000, 6000):
        stop = etree.SubElement(tabs, W + 'tab')
        stop.set(W + 'val', 'left')
        stop.set(W + 'pos', str(pos))
    for i, label in enumerate(('A. Three people', 'B. Four people', 'C. Five people')):
        run = etree.SubElement(p, W + 'r')
        run.append(deepcopy(template))
        if i:
            etree.SubElement(run, W + 'tab')
        node = etree.SubElement(run, W + 't')
        node.set('{http://www.w3.org/XML/1998/namespace}space', 'preserve')
        node.text = label + (' ' if i < 2 else '')

    # The mascot photo was below the printable page. Put it in the existing
    # blank area above the next reading passage, on the same spread.
    mascot = root.xpath('//wp:anchor[wp:docPr[@id="3"]]', namespaces=NS)[0]
    ph = mascot.find('wp:positionH', NS)
    pv = mascot.find('wp:positionV', NS)
    ph.set('relativeFrom', 'page')
    pv.set('relativeFrom', 'page')
    ph.find('wp:posOffset', NS).text = str(round(13.25 * 914400))
    pv.find('wp:posOffset', NS).text = str(round(1.65 * 914400))
    height = round(2.5 * 914400)
    width = round(height * 2621915 / 3413125)
    for ext in mascot.xpath('./wp:extent|.//a:xfrm/a:ext', namespaces=NS):
        ext.set('cx', str(width))
        ext.set('cy', str(height))

    # Shorten the writing box slightly so its lower border stays inside the
    # page, retaining the title and every original ruled answer line.
    box = root.xpath('//wp:anchor[wp:docPr[@id="4"]]', namespaces=NS)[0]
    for ext in box.xpath('./wp:extent|.//a:xfrm/a:ext', namespaces=NS):
        ext.set('cy', str(440 * 12700))
    boxpara = box.xpath('ancestor::w:p[1]', namespaces=NS)[0]
    for rect in boxpara.xpath('.//v:rect', namespaces=NS):
        rect.set('style', rect.get('style').replace('height:497.35pt', 'height:440pt'))
    for p in boxpara.xpath('.//w:txbxContent/w:p', namespaces=NS):
        ppr = p.find(W + 'pPr')
        if ppr is None:
            ppr = etree.Element(W + 'pPr')
            p.insert(0, ppr)
        snap = ppr.find(W + 'snapToGrid')
        if snap is None:
            snap = etree.SubElement(ppr, W + 'snapToGrid')
        snap.set(W + 'val', '0')
        spacing = ppr.find(W + 'spacing')
        if spacing is not None and spacing.get(W + 'line') == '567':
            spacing.set(W + 'line', '480')
            spacing.set(W + 'before', '0')
            spacing.set(W + 'after', '0')
