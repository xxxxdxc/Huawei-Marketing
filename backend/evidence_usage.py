"""Partial retrieval answers are not blanket publication claims."""
import re
GUIDANCE="""检索完整性与可宣传事实分开判断。用户确认提交的原文是本任务可用的用户提供依据，不再因link_verified=false或缺少未明确要求的完整测试脚注单独阻塞。复合问题只回答一部分时用coverage.status=partial，fact_ids列出已支持的事实，missing_details说明未回答的部分，usage_limits说明不能扩展的结论；不得把已有事实清空后统一判not_found。容量与续航分别使用：54 Wh不证明续航；“视频播放最长18小时”只能保持“视频播放”“最长”，不能变成办公/课堂18小时、全天无忧或与另一配置的重量拼接。已经明确的版本/约/最高/测试场景仍须保留；未知的额外脚注留工作人员区，不当作消费者免责声明。只有用户明确要求完整条件、真实型号/安全/必要兼容门槛、同条件资料冲突或没有可用事实时才阻塞相关内容。原文中的“不得承诺”“容量不等于续航”等写作边界不是产品卖点，不生成产品Fact。"""

def guidance_fact(fact):
    text=fact.get('claim','').strip()
    return bool(re.search(r'^(?:不得(?:未经核验|承诺|夸大|推断|声称|直接认定)|不应(?:承诺|夸大|推断|写成|声称)|不能(?:据此|未经|将|把|承诺|推断|直接(?:等同|认定)|等同)|需(?:要)?核验|必须核验|未经核验|电池容量不等于|容量不等于)|(?:不得未经核验|不能据此推断)|(?:知识库|资料|原文|文档).{0,14}(?:提示|限制|边界).{0,18}(?:不得|核验|承诺|容量不能等同|容量不等于)',text))

def user_clauses(t):
    turns=t.get('dialogue') or [dict(id='legacy_raw',text=t.get('raw',''),kind='user')]
    for turn in turns:
        if turn.get('kind','user')!='user':continue
        for clause in re.split(r'[。；;\n]',turn.get('text','')):
            if clause.strip():yield dict(turn_id=turn.get('id','user'),quote=clause)

def related(request,text):
    # Only identify related user requirements, never infer a product fact here.
    from .evidence_resolution import topics
    return bool(topics(request['question']) & topics(text))

def explicit_musts(t,request):
    return [ref for ref in user_clauses(t) if related(request,ref['quote']) and re.search(r'必须|务必|不可省略|不能省略|否则.{0,8}不生成|没有.{0,30}不生成|缺少.{0,30}不生成',ref['quote']) and not re.search(r'不再要求|无需|可以不写|可省略',ref['quote'])]

def complete_conditions_required(t,request):
    from .evidence_resolution import topics
    for ref in user_clauses(t):
        text=ref['quote']
        if re.search(r'不再要求|无需|不需要|可以不写|可省略|不必|不要要求|别要求|不要求',text):continue
        condition=re.search(r'测试条件|完整.{0,8}(?:条件|脚注|配置|测试)|全部.{0,8}(?:条件|脚注)|测试.{0,6}(?:条件|脚注)',text)
        must=re.search(r'必须|务必|需要|要求|请(?:给出|提供|包含)|(?:没有|缺少).{0,30}不生成',text)
        if condition and must and (related(request,text) or not topics(text)):return True
    return False


def partial_is_blocked(t,request):
    return request.get('guardrail','none')!='none' or complete_conditions_required(t,request)
