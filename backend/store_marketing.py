"""Per-task operator information and current-platform store marketing policy.

No model calls or product facts here. Extraction rides the existing Writer outline;
every accepted value must be a literal span of an actual user turn.
"""
import copy,re
from typing import Literal
from pydantic import BaseModel,ConfigDict,Field

VERSION='platform_store_v1'

class Strict(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)

class UserSpan(Strict):
    turn_id:str=Field(min_length=1)
    quote:str=Field(min_length=1,max_length=1500)

class StoreDetail(Strict):
    field:Literal['name','location','contact','hours','service']
    value:str=Field(min_length=1,max_length=300)
    evidence:UserSpan

class StoreContext(Strict):
    details:list[StoreDetail]=Field(default_factory=list,max_length=15)
    wechat_exception:UserSpan|None=None


def user_turns(t):
    turns=[{k:x[k] for k in ('id','text')} for x in t.get('dialogue',[]) if x.get('kind')=='user' and x.get('change_kind')!='platform_only']
    if not turns and t.get('raw'):turns=[dict(id='raw',text=t['raw'])]
    return turns


def checked_context(t,raw=None):
    context=StoreContext.model_validate(raw or {}).model_dump()
    turns={x['id']:x['text'] for x in user_turns(t)}
    def check(span):
        if span['turn_id'] not in turns or span['quote'] not in turns[span['turn_id']]:
            raise ValueError('门店信息来源不能定位到用户原话')
    seen=set()
    for detail in context['details']:
        check(detail['evidence'])
        if detail['value'] not in detail['evidence']['quote']:raise ValueError('门店信息不能超出用户逐字提供的内容')
        key=(detail['field'],detail['value'])
        if key in seen:raise ValueError('门店信息重复')
        seen.add(key)
    exception=context['wechat_exception']
    if exception:
        check(exception)
        text=exception['quote']
        clauses=re.split(r'[。！？；;，,\n]',text)
        affirmative=lambda c:bool(re.search(r'门店|本店|我们店|店铺|到店|预约|联系我',c) and re.search(r'加入|添加|加上|写|介绍|保留|宣传|推广|引导|需要|要',c) and not re.search(r'不要|不写|不加|无需|不用|不需要|去掉|删除|移除|不含|别',c))
        scoped=any(('公众号' in c or 'wechat' in c.lower()) and affirmative(c) for c in clauses)
        changes=t.get('platform_changes') or []
        origin=changes[0]['from_platform'] if changes else t.get('platform')
        scoped_platform=origin
        by_turn={c['turn_id']:c['to_platform'] for c in changes}
        for turn in t.get('dialogue',[]):
            if turn.get('id') in by_turn:scoped_platform=by_turn[turn['id']]
            if turn.get('id')==exception['turn_id']:break
        fresh_wechat=scoped_platform=='wechat'
        if not scoped and not (fresh_wechat and any(affirmative(c) and not re.search(r'小红书|朋友圈|公众号|wechat',c,re.I) for c in clauses)):
            raise ValueError('公众号门店营销例外须有针对该公众号的明确用户要求，不能继承通用到店目标')
        # A later explicit revocation wins over an earlier exception.
        ids=list(turns);index=ids.index(exception['turn_id'])
        for later in list(turns.values())[index+1:]:
            if re.search(r'(?:公众号|wechat)[^。！？\n]{0,18}(?:不要|不写|不加|无需|不用|去掉|删除)[^。！？\n]{0,15}(?:门店|到店|店铺)',later,re.I):
                context['wechat_exception']=None
                break
    return context


def policy(t,context=None,extracting=False):
    context=checked_context(t,context if context is not None else t.get('store_marketing_context'))
    platform=t['platform']
    if platform not in ('wechat','xiaohongshu','moments'):raise ValueError('不支持的门店营销平台')
    enabled=platform!='wechat' or bool(context['wechat_exception'])
    return dict(version=VERSION,platform=platform,enabled=enabled,
        mode='store_closing' if enabled else 'product_only',
        placement='root_cta_only',allow_empty_cta=not enabled,
        missing_details='generic_nonblocking',
        closing_length='brief' if platform=='moments' else 'natural',
        details=context['details'],wechat_exception=context['wechat_exception'],
        extracting_context=extracting)


GUIDANCE='''门店营销按store_marketing_policy和当前目标平台执行，优先于Brief继承的到店目标及旧平台结尾。
公众号默认只做产品宣传，不写门店、销售联系、预约、咨询到店；可自然收尾并将根级cta留空。仅用户明确要求这篇公众号也加入门店营销时例外，不能只因资料里有门店或旧平台目标有到店就启用。
小红书和朋友圈默认需要销售人员所在门店的营销：正文保持产品宣传，结尾根级cta自然承接真实门店资料并给一句咨询引导，不逐段插广告。朋友圈更精简，小红书可稍展开。
门店信息只取store_user_evidence里的真实用户原话，不能从产品知识库推断所在门店。名字、位置、联系方式、营业时间及服务均不可编造，也不能把华为官方售后政策说成该门店服务，不能虚构现货、优惠、体验设备或服务承诺。
没有具体门店资料不阻塞，不自行追问；用“欢迎私信了解我们的门店”等通用结尾，不编造地址和服务。用户要求必须写具体信息而未提供时，沿用Brief的缺项追问机制，不在正文用免责声明补缺。用户给过的门店资料仍完整保存在内部，公众号不营销时不输出。
extracting_context=true只用于大纲阶段：先提取并自查store_context，公众号初始enabled=false不排除本次原话明确授权的例外；仅有合法wechat_exception原话时，大纲才可规划门店CTA。draft/repair的策略已由程序计算，不得自行更改。
outline在store_context中提取门店details，每条value须逐字来自evidence.quote，turn_id与quote须对应输入原话；wechat_exception只引用明确要求公众号门店营销的原话。没有信息则details=[]、wechat_exception=null。字段不是产品事实，不分配Fact ID。不能把“不要门店”或“仅小红书要门店”标为公众号例外。下游必须沿用程序校验后store_marketing_policy，修订不得改变启用状态。
'''


def payload(t,extracting=False):
    # Context remains separate from the product evidence package.
    context=checked_context(t,t.get('store_marketing_context'))
    return dict(store_user_evidence=user_turns(t),store_marketing_context=context,
                store_marketing_policy=policy(t,context,extracting))


STORE_WORDS=r'门店|本店|我们店|店铺|到店|店里|私信|预约(?:体验|咨询|选购)|联系我|咨询我们|咨询我|加微|微信号|联系电话'


def document_issues(t,document,context=None):
    p=policy(t,context);issues=[]
    def issue(location,detail):
        issues.append(dict(category='platform',location=location,detail=detail,severity='error',repairable=True))
    fields=[('标题',document['title']),('导语',document['lead']),('行动引导',document['cta'])]
    fields.extend((para['heading'] or '正文段落',para[k]) for para in document['paragraphs'] for k in ('text','caption'))
    fields.extend(('标签',tag) for tag in document['tags'])
    identifiers=[d['value'] for d in p['details'] if d['field'] in ('name','contact','hours') or (d['field']=='location' and len(d['value'])>6)]
    if not p['enabled']:
        for loc,text in fields:
            if re.search(STORE_WORDS,text) or any(v in text for v in identifiers):
                issue(loc,'公众号默认不写所在门店营销，请删除门店信息和销售咨询/到店引导；可自然收尾，cta允许为空')
    else:
        names=[d['value'] for d in p['details'] if d['field']=='name']
        cta=document['cta']
        if not (re.search(r'门店|本店|我们店|店铺|到店|店里',cta) or any(n in cta for n in names)):
            issue('行动引导','本平台结尾需要承接销售人员所在门店；无门店资料时用通用门店引导，不编造信息')
        if names and not any(n in cta for n in names):
            issue('行动引导','请用用户已提供的真实门店名称自然承接结尾，不以泛化门店话语替代本次门店')
        for loc,text in fields:
            if loc=='行动引导':continue
            if any(v in text for v in identifiers):issue(loc,'具体门店信息仅在结尾根级cta自然承接，不进入产品正文、标题、导语、图注或标签')
    return issues


def is_store_request(clause):
    """Keep operator identity/closing musts out of product Fact-ID coverage.

    Mixed clauses and commercial/product claims remain under original evidence gates.
    """
    parts=re.split(r'和|及|同时|并且|并|、',clause)
    # Unknown conjuncts remain product musts; never drop a new product feature
    # merely because its clause also mentions a store.
    if len(parts)>1 and any(not re.search(r'门店|本店|我们店|店名|店址|地址|位置|营业时间|联系方式|联系电话|电话|微信号|店铺',part) for part in parts):return False
    return bool(re.search(r'门店|本店|我们店|店名|店址|营业时间|联系方式|联系电话|微信号',clause) and
        not re.search(r'重量|屏幕|触控|续航|接口|处理器|电池|容量|配置|投屏|性能|兼容|卖点|参数|价格|优惠|补贴|赠品',clause))
