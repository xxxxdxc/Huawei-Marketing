"""Exact quote localization with a deliberately small formatting equivalence set."""
import copy,hashlib
from pydantic import Field
from .schemas import Strict,Fact

class FactCorrections(Strict):
    facts:list[Fact]=Field(max_length=10)

PUNCT={"，":",","；":";","：":":","（":"(","）":")"}

def normalized(text):
    chars=[];positions=[]
    for index,char in enumerate(text):
        if char.isspace() or char in "\u200b\ufeff":continue
        # Full-width ASCII is formatting, unlike arbitrary Unicode compatibility folds.
        value=chr(ord(char)-0xfee0) if 0xff01<=ord(char)<=0xff5e else PUNCT.get(char,char)
        chars.append(value);positions.append(index)
    return ''.join(chars),positions

def locate(text,quote):
    needle,_=normalized(quote);haystack,positions=normalized(text)
    if not needle:return None
    start=haystack.find(needle)
    if start<0:return None
    left=positions[start];right=positions[start+len(needle)-1]+1
    return left,right,text[left:right]

def reconcile(package):
    sources={s['id']:s for s in package.get('sources',[])};kept=[];rejected=[];seen=set()
    counts={f['id']:sum(x['id']==f['id'] for x in package.get('facts',[])) for f in package.get('facts',[])}
    repairs=package.setdefault('quote_repairs',[])
    for original in package.get('facts',[]):
        fact=copy.deepcopy(original);source=sources.get(fact.get('source_id'))
        match=locate(source.get('text',''),fact.get('quote','')) if source else None
        reason='duplicate_id' if counts[fact['id']]>1 else 'source_missing' if not source else 'quote_not_found' if not match else None
        if reason:
            rejected.append(dict(fact=fact,reason=reason));continue
        left,right,quote=match
        if quote!=fact['quote']:
            audit=dict(fact_id=fact['id'],source_id=source['id'],original_quote=fact['quote'],quote=quote,start=left,end=right,source_sha256=hashlib.sha256(source['text'].encode()).hexdigest(),method='bounded_format_equivalence')
            if audit not in repairs:repairs.append(audit)
            fact['quote']=quote
        kept.append(fact);seen.add(fact['id'])
    package['facts']=kept
    quarantine=package.setdefault('rejected_facts',[])
    for item in rejected:
        if item not in quarantine:quarantine.append(item)
    if 'all_facts' in package:package['all_facts']=copy.deepcopy(kept)
    for row in package.get('coverage',[]):
        old=row.get('fact_ids',[]);valid=[x for x in old if x in seen];row['fact_ids']=valid
        if valid==old:continue
        if row['status'] in ('supported','partial'):
            row['status']='partial' if valid else 'not_found'
            row['reason']='部分摘录未通过定位，保留已定位事实。' if valid else '该方向未保留可定位的事实摘录。'
            if valid:
                row.setdefault('missing_details',[]).append('部分事实摘录未定位，不能使用被隔离的卡片。')
                row.setdefault('usage_limits',[]).append('仅引用仍保留的事实，不扩展被隔离的结论。')
    package['unresolved_fact_ids']=sorted({x['fact']['id'] for x in quarantine if x['fact']['id'] not in seen})
    return rejected
