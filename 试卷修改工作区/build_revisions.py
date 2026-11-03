from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
from lxml import etree
from difflib import SequenceMatcher
from copy import deepcopy
import json
import re
import sys

WORK = Path(__file__).resolve().parent
OUT = Path('/Users/weiyao/Desktop/试卷修改版')
NS = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
W = '{' + NS['w'] + '}'
XMLSPACE = '{http://www.w3.org/XML/1998/namespace}space'

def ptext(p):
    return ''.join(p.xpath('.//w:t/text()', namespaces=NS))

def splice(p, start, end, replacement):
    nodes = p.xpath('.//w:t', namespaces=NS)
    offset = 0
    done = False
    for node in nodes:
        text = node.text or ''
        nstart, nend = offset, offset + len(text)
        offset = nend
        if end == start:
            if not done and nstart <= start <= nend:
                at = start - nstart
                node.text = text[:at] + replacement + text[at:]
                node.set(XMLSPACE, 'preserve')
                return
        elif nend > start and nstart < end:
            left = text[:max(0, start - nstart)]
            right = text[max(0, end - nstart):]
            node.text = left + (replacement if not done else '') + right
            node.set(XMLSPACE, 'preserve')
            done = True
    if end == start and not done and start == offset:
        nodes[-1].text = (nodes[-1].text or '') + replacement
        nodes[-1].set(XMLSPACE, 'preserve')

def replace_preserving_runs(p, old, new):
    original = ptext(p)
    assert original.count(old) == 1, (old, original)
    offset = original.index(old)
    for tag, i, j, a, b in reversed(SequenceMatcher(None, old, new, autojunk=False).get_opcodes()):
        if tag != 'equal':
            splice(p, offset+i, offset+j, new[a:b])
    assert ptext(p) == original.replace(old, new, 1)

def fix_chinese_fonts(root):
    for run in root.xpath('//w:r', namespaces=NS):
        text = ''.join(run.xpath('./w:t/text()', namespaces=NS))
        if re.search(r'[\u3400-\u9fff]', text):
            original_rp = run.find(W+'rPr')
            replacements = []
            for child in run:
                if child.tag == W+'rPr':
                    continue
                segments = re.split(r'([\u3000-\u303f\u3400-\u9fff\uff00-\uffef]+)', child.text or '') if child.tag == W+'t' else [None]
                for segment in segments:
                    if segment == '':
                        continue
                    nr = etree.Element(W+'r', attrib=dict(run.attrib))
                    rp = deepcopy(original_rp) if original_rp is not None else etree.Element(W+'rPr')
                    nr.append(rp)
                    if segment is not None and re.search(r'[\u3000-\u303f\u3400-\u9fff\uff00-\uffef]', segment):
                        rf = rp.find(W+'rFonts')
                        if rf is None:
                            rf = etree.Element(W+'rFonts')
                            rp.insert(0, rf)
                        for key in ['asciiTheme','hAnsiTheme','eastAsiaTheme','csTheme']:
                            rf.attrib.pop(W+key, None)
                        for key in ['ascii','hAnsi','eastAsia','cs']:
                            rf.set(W+key, 'Arial Unicode MS')
                        rf.set(W+'hint', 'eastAsia')
                    node = deepcopy(child)
                    if segment is not None:
                        node.text = segment
                        node.set(XMLSPACE, 'preserve')
                    nr.append(node)
                    replacements.append(nr)
            parent = run.getparent()
            index = parent.index(run)
            parent.remove(run)
            for nr in replacements:
                parent.insert(index, nr)
                index += 1

def build(label):
    plan = json.loads((WORK / f'{label}_plan.json').read_text())
    src = Path(plan['source'])
    dest = OUT / (src.stem + '（40%修改版）.docx')
    with ZipFile(src) as zin:
        root = etree.fromstring(zin.read('word/document.xml'))
        pars = root.xpath('//w:p', namespaces=NS)
        log = []
        for item in plan['items']:
            for change in item['replacements']:
                idx = change['paragraph_index']
                replace_preserving_runs(pars[idx], change['old'], change['new'])
                log.append({'paragraph': idx, 'old': change['old'], 'new': change['new']})
        for change in plan.get('proofreading', []):
            replace_preserving_runs(pars[change['paragraph_index']], change['old'], change['new'])
            log.append(change)
        fix_chinese_fonts(root)
        if label == 'book3' and (WORK/'book3_layout.py').exists():
            from book3_layout import fix_layout
            fix_layout(root)
        if label == 'g4' and (WORK/'g4_layout.py').exists():
            from g4_layout import fix_layout
            fix_layout(root)
        if label == 'grade2' and (WORK/'grade2_layout.py').exists():
            from grade2_layout import fix_layout
            fix_layout(root)
        docxml = etree.tostring(root, xml_declaration=True, encoding='UTF-8', standalone=True)
        modified_parts = {'word/document.xml': docxml}
        if label == 'grade2':
            for name in zin.namelist():
                if re.fullmatch(r'word/footer\d+\.xml', name):
                    footer = etree.fromstring(zin.read(name))
                    for node in footer.xpath('//w:t', namespaces=NS):
                        if node.text:
                            node.text = node.text.replace('共5页', '共4页')
                    fix_chinese_fonts(footer)
                    modified_parts[name] = etree.tostring(footer, xml_declaration=True, encoding='UTF-8', standalone=True)
        with ZipFile(dest, 'w', ZIP_DEFLATED) as zout:
            for entry in zin.infolist():
                zout.writestr(entry, modified_parts.get(entry.filename, zin.read(entry.filename)))
    (WORK / f'{label}_applied_changes.json').write_text(json.dumps(log, ensure_ascii=False, indent=2))
    with ZipFile(src) as a, ZipFile(dest) as b:
        assert a.namelist() == b.namelist()
        for name in a.namelist():
            if name not in modified_parts:
                assert a.read(name) == b.read(name), name
        updated = etree.fromstring(b.read('word/document.xml'))
        assert updated.find(W+'body') is not None
    print(dest)

if __name__ == '__main__':
    for label in sys.argv[1:]:
        build(label)
