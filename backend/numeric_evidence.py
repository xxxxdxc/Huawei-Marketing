"""Finite numeric presentation matching; quote evidence, never derived product facts."""
import re,unicodedata
from decimal import Decimal

VERSION='numeric_atoms_v1'
GUIDANCE='''数值程序检查只证明数值和单位在引用原文中存在，不能证明该数值属于正确型号、部位、配置或测试条件。共享单位7.6/7.3 mm可分别表述为7.6 mm和7.3 mm，7.60与7.6等值；这不允许左右互换、把展开厚度说成闭合厚度、丢失约/最高/典型值或由容量推导续航。numeric_checks为格式与引用匹配记录，不替代逐条语义核验；仍需把每项实际主张与对应原文及条件核对。'''

NUMBER=r'[-+]?\d+(?:\.\d+)?'
UNITS=r'毫米|千克|英寸|小时|mm|kg|Wh|GB|TB|Hz|nits|cm|元|克|g|W|h'
PATTERN=re.compile(r'(?<![\dA-Za-z_.\-+])(?P<values>'+NUMBER+r'(?:\s*[/×xX*]\s*'+NUMBER+r')*)\s*(?P<unit>'+UNITS+r')(?![a-zA-Z])',re.I)
ALIASES={'毫米':'mm','千克':'kg','克':'g','小时':'h'}


def normalize(text):return unicodedata.normalize('NFKC',text)


def number_key(value):
    # Decimal.normalize() uses context precision; formatting preserves every digit.
    result=format(Decimal(value),'f')
    if '.' in result:result=result.rstrip('0').rstrip('.')
    return '0' if Decimal(result)==0 else result


def atoms(text):
    """Do not borrow a unit across sentences/facts, convert units, or do arithmetic."""
    text=normalize(text);out=[]
    for match in PATTERN.finditer(text):
        raw=match['values'];unit=ALIASES.get(match['unit'],match['unit']).lower()
        values=re.findall(NUMBER,raw)
        # Short integer fractions and arithmetic products are not numeric lists.
        # Only a 3-value dimension chain or an explicitly contextual pair is
        # treated as dimensions; two-factor arithmetic is kept literal.
        prefix=text[max(0,match.start()-20):match.start()]
        contextual=bool(re.search(r'左右|左.*右|分别|尺寸|厚度|宽|深|高|长|内存|容量|可选',prefix))
        fraction='/' in raw and len(values)==2 and all('.' not in v for v in values) and 0<Decimal(values[0])<Decimal(values[1])<=10 and not re.search(r'左右|分别|可选|内存|容量',prefix)
        product=bool(re.search(r'[×xX*]',raw)) and len(values)==2 and not contextual
        if fraction or product:
            out.append(dict(value=re.sub(r'\s+','',raw),unit=unit,expression=match.group(),literal=True))
            continue
        for value in values:
            out.append(dict(value=number_key(value),unit=unit,expression=match.group(),literal=False))
    return out


def key(atom):return atom['value'],atom['unit'],atom['literal']


def audit(t):
    facts={f['id']:f for f in t['package']['facts']}
    evidence={fid:atoms(f['quote']) for fid,f in facts.items()}
    document=t['document'];plan_ids={fid for s in (t.get('plan') or {}).get('sections',[]) for fid in s['fact_ids']}
    declared={fid for p in document['paragraphs'] for fid in p['fact_ids']}
    root_ids=plan_ids & declared & facts.keys()
    fields=[('标题',document['title'],root_ids),('导语',document['lead'],root_ids),('行动引导',document['cta'],root_ids)]
    fields.extend(('标签',tag,root_ids) for tag in document['tags'])
    for p in document['paragraphs']:
        ids=set(p['fact_ids']) & facts.keys()
        fields.extend([('正文 '+p['section_id'],p['text'],ids),('图注 '+p['section_id'],p['caption'],ids)])
    issues=[];checks=[];seen=set()
    for location,text,ids in fields:
        for atom in atoms(text):
            matched=[fid for fid in sorted(ids) if any(key(e)==key(atom) for e in evidence[fid])]
            check=dict(location=location,expression=atom['expression'],value=atom['value'],unit=atom['unit'],
                cited_fact_ids=sorted(ids),matched_fact_ids=matched,
                evidence=[dict(fact_id=fid,quote=facts[fid]['quote'],source_id=facts[fid]['source_id']) for fid in matched],
                supported=bool(matched))
            checks.append(check)
            if matched:continue
            dedup=(location,key(atom))
            if dedup in seen:continue
            seen.add(dedup)
            issues.append(dict(category='fact',location=location,
                detail='数值或单位没有对应原文依据：'+atom['value']+' '+atom['unit']+'（表达：'+atom['expression']+'；本位置引用：'+('、'.join(sorted(ids)) or '无')+'）。已识别共享单位和等值小数，请核对数值、单位及事实引用；部位/版本/条件另作语义核验。',
                severity='error',repairable=True))
    return dict(version=VERSION,checks=checks,issues=issues)
