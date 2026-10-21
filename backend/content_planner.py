"""Evidence-grounded selection and composition, with immutable candidate provenance."""
import copy,hashlib,json,re,time
from pathlib import Path
from difflib import SequenceMatcher
from . import planner_schemas as P,brief_agent as ba,evidence_resolution as er
from .clients import llm,usage_capture
from .settings import get_settings
from .content_layout import default_position,validate_layout
from . import publication_rules as pub,evidence_policy as ep

WEIGHTS={'audience':35,'evidence':35,'differentiation':15,'image':15}
BUDGETS={'xiaohongshu':(300,500),'wechat':(600,900),'moments':(80,150)}
SUGGESTED_COUNTS={'moments':(1,1),'xiaohongshu':(2,3),'wechat':(3,4)}
ROOT=Path(__file__).parent
METHOD_SOURCES=['content-strategy']
from .marketing_methods import PLANNER_METHOD,METHOD_GUARD
ADAPTER=(ROOT/'planner_adapter.md').read_text(encoding='utf-8-sig')+'\n'+METHOD_GUARD+PLANNER_METHOD+'\n'+pub.CORE
CANDIDATE_PROMPT="""你是Content Planner候选取舍阶段，只做内容选择与编排准备，不写平台文案。product_id原样返回。每个候选绑定真实fact_ids，说明回应的audience_need；产品利益须能由引用事实支持，不能将待验证假设当作事实。不要重复同一论点凑候选。
scores四项0到4整数并附reason：audience需求关联、evidence证据直接支持、differentiation本篇辨识度（不代表竞品领先）、image真实画面支持。无相关图image_ids为空且image分为0。不能将外观照片当作参数证明。完整conditions供内部核验，保留配置、约、最高、测试条件。
每个候选给recommendation为recommended或alternative，并给recommendation_reason，解释为何本篇推荐或暂不采用。建议人数见suggested_point_counts，只是少量选用建议，不凑数、不机械TopK；明确需求、重复程度、证据和篇幅共同决定。低分不构成省略必须内容的授权。至少推荐一个候选，并覆盖mandatory_requests与mandatory_needs。mandatory_need_ids仅引用用户明确必须需求的编号，说明该候选事实支持的必须内容；普通检索required不是必写文案。request_ids对应实际有支持事实的检索请求；编号只能来自输入。遵守execution_scope与content_policy。"""
PLAN_PROMPT="""你是Content Planner段落编排阶段，只安排内容、事实和图片，不生成最终文案、不设计平台写作Skills。product_id原样返回。selected_point_ids必须与输入selected_point_ids集合完全一致，不增选、不漏选；每个选中候选至少由一段真实事实承接。排序帮助取舍，不代表段落必须照排名排列。
不选择固定叙事框架，不输出narrative或framework；用简短composition_rationale解释为什么采用这个先后顺序和段落安排。
每段有heading（工作人员内部阅读提示）、purpose（写作目标）、reader_question、role、point_ids、fact_ids、image_id、image_reason、image_position、target_chars。argument/objection必须引用事实和选中候选；其他段可无事实，但不得加入未获支持的客观结论。每个point_id必须由本段至少一条对应事实支持，不能只挂编号。各段回答不同问题，保留实质限定，不把内部证据注释当作写作任务。
只使用选中候选的事实。图片只用已核验图片、不重复凑数，每段至多一图。项目平台契约（不是social Skill）：wechat为before_section/after_section且order=null；xiaohongshu为carousel、moments为grid，order从1连续排列；无图none/order=null。总图数与policy一致，target_chars合计符合budget。CTA只放根级cta，不额外堆CTA段。
schema_version为2，保留angle/title_direction/sections/cta契约；title_direction只指内容题目方向，不写实际标题或软文。遵守execution_scope，不恢复已舍弃主题。"""

def digest(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def content_fingerprint(plan):
    return digest({k:v for k,v in plan.items() if k!='planning_analysis'})

def check_input(t):
    from .workflow import verify_facts
    p=t['package'];product=p.get('product') or {}
    if product.get('id')!=t['product_id']:raise ValueError('规划资料型号与已确认型号不一致')
    verify_facts(p)
    if not p.get('facts'):raise ValueError('没有可用于规划的已核验事实')
    if p.get('conflicts') or p.get('evidence_gaps'):raise ValueError('事实冲突或证据门槛尚未解决，不能进入规划')
    for f in p['facts']:
        if not f.get('quote','').strip():raise ValueError('事实卡缺少原文证据')
        if f.get('product_id',t['product_id'])!=t['product_id']:raise ValueError('事实卡属于其他型号')
    seen=set()
    for image in p['images']:
        if image['id'] in seen:raise ValueError('输入图片编号重复')
        seen.add(image['id'])
        if not image.get('model_verified') or not image.get('visual_checked') or image.get('usable') is False:raise ValueError('图片型号或可用性尚未通过核对')
        if image.get('product_id',t['product_id'])!=t['product_id']:raise ValueError('图片卡属于其他型号')
        if image.get('model') and product.get('name'):
            a=ba.normalize(image['model']);b=ba.normalize(product['name'])
            if a not in b and b not in a:raise ValueError('图片型号与任务不一致')

def mandatory_needs(t):
    """Only explicit user musts become publication constraints, never retrieval priority."""
    from .store_marketing import is_store_request
    a=er.analysis_for_execution(t) or {};out=[]
    marker=re.compile(r"必须|一定要|务必|不能遗漏|不能漏|不可省略|不能省略|必写")
    negative=re.compile(r"必须不|不得(?!遗漏|漏|省略)|禁止|不要|不能写|不写|不提|不包含|不出现|避免|无需")
    for field in ("user_constraints","customer_needs","marketing_goal"):
        item=(a.get("requirements") or {}).get(field) or {}
        if item.get("source")!="explicit":continue
        values=item.get("value") or []
        if isinstance(values,str):values=[values]
        for value in values:
            if not isinstance(value,str):continue
            clauses=[x.strip() for x in re.split(r"[。；;，,\\n]",value) if x.strip()]
            for clause in clauses:
                matching=[r for r in item.get("evidence",[]) if marker.search(r.get("quote","")) and (ba.normalize(clause) in ba.normalize(r.get("quote","")))]
                if negative.search(clause) or not (marker.search(clause) or matching):continue
                if is_store_request(clause):continue
                if clause in {x["text"] for x in out}:continue
                out.append(dict(id="M"+str(len(out)+1),text=clause,field=field,evidence=copy.deepcopy(matching or item.get("evidence",[]))))
    return out

def request_context(t):
    a=er.analysis_for_execution(t) or {}
    requests={r['id']:r for r in (a.get('retrieval_plan') or {}).get('facts',[])}
    p=t['package']
    coverage={c['request_id']:c for c in (p.get('execution_coverage') or p.get('coverage') or [])}
    blocking_categories={c['category'] for c in a.get('commercial_requests',[]) if c.get('on_missing')=='block'}
    mandatory=[]
    for rid,r in requests.items():
        kind=ep.request_kind(r)
        if kind in ep.COMMERCIAL:
            if kind not in blocking_categories:continue
        else:continue
        c=coverage.get(rid,{})
        ids=[fid for fid in c.get('fact_ids',[]) if fid in {f['id'] for f in p['facts']}]
        if c.get('status') not in ('supported','partial') or not ids:
            raise ValueError('必须内容尚无可用依据，请先补充资料或修改需求：'+rid)
        mandatory.append(dict(request_id=rid,question=r['question'],fact_ids=ids))
    return requests,coverage,mandatory

def shared_context(t,policy):
    requests,coverage,mandatory=request_context(t)
    return dict(product_id=t['product_id'],product=t['package']['product'],brief=ba.context(t),
        facts=t['package']['facts'],
        images=[{k:v for k,v in i.items() if k in ('id','name','model','description','visual_description','selection_reason','width','height','model_verified','visual_checked')} for i in t['package']['images']],
        policy=policy,condition_presentation=pub.condition_guidance(t['package']['facts']),
        suggested_point_counts=SUGGESTED_COUNTS[t['platform']],retrieval_requests=list(requests.values()),mandatory_requests=mandatory,mandatory_needs=mandatory_needs(t))

def candidate_context_hash(t):
    from .workflow import PLATFORMS
    return digest(shared_context(t,PLATFORMS[t['platform']]))

def rank_candidates(t,result):
    result=P.CandidateBatch.model_validate(result).model_dump()
    if result['product_id']!=t['product_id']:raise ValueError('候选卖点返回了其他型号')
    facts={f['id']:f for f in t['package']['facts']};images={i['id']:i for i in t['package']['images']}
    requests,coverage,_=request_context(t)
    need_ids={n['id'] for n in mandatory_needs(t)}
    ranked=[];seen=set()
    for c in result['candidates']:
        if c['id'] in seen:raise ValueError('候选卖点编号重复')
        seen.add(c['id'])
        if len(c['fact_ids'])!=len(set(c['fact_ids'])) or not set(c['fact_ids'])<=facts.keys():raise ValueError('候选卖点引用了不存在或重复的事实')
        if len(c['image_ids'])!=len(set(c['image_ids'])) or not set(c['image_ids'])<=images.keys():raise ValueError('候选卖点引用了不存在或重复的图片')
        scores=c['scores']
        if scores['evidence']['value']==0:raise ValueError('候选卖点没有直接证据支持')
        if not c['image_ids'] and scores['image']['value']!=0:raise ValueError('没有图片支持时不能声称图片支持得分')
        linked={rid for rid in requests if set(c['fact_ids'])&set(coverage.get(rid,{}).get('fact_ids',[]))}
        if not set(c['request_ids'])<=linked:raise ValueError('候选卖点关联了没有对应证据的检索请求')
        c['request_ids']=sorted(linked)
        if len(c['mandatory_need_ids'])!=len(set(c['mandatory_need_ids'])) or not set(c['mandatory_need_ids'])<=need_ids:raise ValueError('候选卖点引用不存在或重复的必须需求编号')
        c['conditions']=list(dict.fromkeys([facts[x]['conditions'] for x in c['fact_ids'] if facts[x].get('conditions')]+c['conditions']))
        text=' '.join([c['direction'],c['audience_need'],c['recommendation_reason'],*c['conditions'],*[x['reason'] for x in scores.values()]])
        if er.text_issues(t,text,'候选卖点'):raise ValueError('候选卖点重新引入已舍弃方向')
        c['total_score']=sum(scores[k]['value']*weight/4 for k,weight in WEIGHTS.items())
        ranked.append(c)
    ranked.sort(key=lambda x:(-x['total_score'],x['id']))
    for index,c in enumerate(ranked):c['rank']=index+1
    return ranked

def validate_selection(t,candidates,selected):
    if not isinstance(selected,list) or not 1<=len(selected)<=8 or len(selected)!=len(set(selected)):raise ValueError('请选择1至8个不同的候选卖点')
    by_id={c['id']:c for c in candidates}
    if len(by_id)!=len(candidates) or not set(selected)<=by_id.keys():raise ValueError('所选卖点编号不存在或已失效')
    _,_,mandatory=request_context(t)
    supported={fid for cid in selected for fid in by_id[cid]['fact_ids']}
    missing=[r for r in mandatory if not set(r['fact_ids'])<=supported]
    needs=mandatory_needs(t)
    covered_needs={nid for cid in selected for nid in by_id[cid].get('mandatory_need_ids',[])}
    missing_needs=[n for n in needs if n['id'] not in covered_needs]
    if missing_needs:raise ValueError('所选卖点未覆盖用户明确必须内容：'+'；'.join(n['text'] for n in missing_needs)+'。如需放宽，请明确修改需求。')
    if missing:raise ValueError('所选卖点未覆盖Brief中的必须内容：'+'；'.join(r['request_id']+' '+r['question'] for r in missing)+'。如需放宽，请明确修改需求。')
    return list(selected)

def trusted_candidates(t):
    check_input(t)
    plan=t.get('plan') or {};a=plan.get('planning_analysis') or {}
    if a.get('origin')!='model' or not a.get('candidates'):raise ValueError('当前没有可信候选卖点，请先完成内容规划')
    if a.get('candidate_context_hash') and a['candidate_context_hash']!=candidate_context_hash(t):raise ValueError('候选对应的需求或资料已变化，请重新规划，不能沿用旧评分')
    fields=set(P.SellingPoint.model_fields)
    raw=[]
    for item in a['candidates']:
        c={k:copy.deepcopy(v) for k,v in item.items() if k in fields}
        c.setdefault('recommendation','recommended' if item['id'] in (plan.get('selected_point_ids') or []) else 'alternative')
        c.setdefault('recommendation_reason','旧版候选记录，保留原选用状态；可由用户明确调整')
        c.setdefault('request_ids',[])
        c.setdefault('mandatory_need_ids',[])
        raw.append(c)
    return rank_candidates(t,dict(product_id=t['product_id'],candidates=raw))

def validate(t,plan,enforce_count=True):
    p=t['package'];images={i['id']:i for i in p['images']}
    if plan.get('product_id') and plan['product_id']!=t['product_id']:raise ValueError('规划型号与任务不一致')
    validate_layout(plan,t['platform'])
    a=plan.get('planning_analysis') or {};generated=a.get('status')=='generated'
    candidates={c['id']:c for c in a.get('candidates',[])}
    bound=bool(candidates) and a.get('origin')=='model'
    selected_list=plan.get('selected_point_ids') or []
    selected=set(selected_list)
    if generated or bound:validate_selection(t,list(candidates.values()),selected_list)
    if bound and a.get('candidate_context_hash') and a['candidate_context_hash']!=candidate_context_hash(t):raise ValueError('候选对应的资料或需求已变化，请重新规划')
    covered=set();questions=set();warnings=[];arguments=[]
    for sec in plan['sections']:
        if len(sec['fact_ids'])!=len(set(sec['fact_ids'])):raise ValueError('段落事实编号重复')
        if sec['image_id'] and (not images.get(sec['image_id'],{}).get('model_verified') or images[sec['image_id']].get('usable') is False):raise ValueError('规划使用了未核对或已拒绝的图片')
        if generated and (not sec.get('reader_question') or not sec.get('role') or not sec.get('image_position')):raise ValueError('新规划缺少段落策划字段')
        if generated or bound:
            point_list=sec.get('point_ids') or [];points=set(point_list)
            if len(points)!=len(point_list) or not points<=selected:raise ValueError('段落引用重复或未入选卖点')
            allowed={fid for cid in points for fid in candidates[cid]['fact_ids']}
            if not set(sec['fact_ids'])<=allowed:raise ValueError('段落事实超出对应候选卖点范围')
            if sec.get('role') in ('argument','objection') and (not sec['fact_ids'] or not points):raise ValueError('论证段落必须绑定真实事实和候选卖点')
            if sec['fact_ids'] and not points:raise ValueError('有产品事实的段落必须绑定候选卖点')
            for cid in points:
                if not set(sec['fact_ids'])&set(candidates[cid]['fact_ids']):raise ValueError('段落所选卖点没有实际事实承接')
            covered.update(points)
        q=re.sub(r'\W','',sec.get('reader_question') or sec['purpose']).lower()
        if generated and q in questions:raise ValueError('不同段落重复回答同一个读者问题')
        questions.add(q)
        for old in arguments:
            if SequenceMatcher(None,q,old).ratio()>.83:warnings.append('段落读者问题可能语义重复，请审阅：'+sec['id'])
        arguments.append(q)
        if len(sec['fact_ids'])>3:warnings.append('单段承载较多事实，请检查信息负担：'+sec['id'])
    if (generated or bound) and covered!=selected:raise ValueError('入选卖点没有对应事实段落，调整选择请使用按所选卖点更新大纲')
    if generated or bound:
        actual_facts={fid for sec in plan['sections'] for fid in sec['fact_ids']}
        if any(not set(r['fact_ids'])<=actual_facts for r in request_context(t)[2]):raise ValueError('大纲遗漏Brief中的必须事实，不能只选卖点而不实际承接')
    if generated:
        budget=sum(s.get('target_chars') or 0 for s in plan['sections'])
        lo,hi=BUDGETS[t['platform']]
        if not lo<=budget<=hi:raise ValueError(f'规划篇幅预算需为{lo}至{hi}字，目前{budget}')
    er.assert_plan(t,plan)
    return list(dict.fromkeys(warnings))

def selection_fingerprint(plan):
    return digest({k: plan.get(k) for k in ('product_id','selected_point_ids')} | {
        'candidates': (plan.get('planning_analysis') or {}).get('candidates',[])})


def validate_selection_plan(t, plan):
    check_input(t)
    if plan.get('product_id') != t['product_id']:raise ValueError('卖点选择型号不一致')
    if plan.get('phase') != 'selection' or plan.get('sections'):raise ValueError('卖点选择不能包含段落结构')
    a=plan.get('planning_analysis') or {}
    if a.get('origin') != 'model' or not a.get('candidates'):raise ValueError('缺少可信候选卖点')
    if a.get('candidate_context_hash') != candidate_context_hash(t):raise ValueError('候选对应的需求或资料已变化，请重新选择')
    validate_selection(t,a['candidates'],plan.get('selected_point_ids'))
    er.assert_plan(t,plan)
    # Revalidate saved provenance; never trust IDs merely because they were stored.
    fields=set(P.SellingPoint.model_fields)
    ranked=rank_candidates(t,dict(product_id=t['product_id'],candidates=[{k:v for k,v in c.items() if k in fields} for c in a['candidates']]))
    if ranked != a['candidates']:raise ValueError('候选评分或证据记录不一致')
    return []


def selection_plan(t, candidates, selected, input_hash=None):
    selected=validate_selection(t,candidates,selected)
    brief=ba.context(t)
    result=dict(schema_version='3',phase='selection',product_id=t['product_id'],
        angle=brief.get('strategy') or brief.get('goal') or '依据已核验事实选择核心卖点',
        title_direction='',sections=[],cta=(ba.context(t).get('message_strategy') or {}).get('cta_direction') or brief.get('goal','咨询'),
        selected_point_ids=list(selected),planning_analysis=dict(status='generated',origin='model',
            candidates=copy.deepcopy(candidates),weights=WEIGHTS,input_hash=input_hash,
            candidate_context_hash=candidate_context_hash(t),selection_contract='2',
            method_sources=METHOD_SOURCES,mandatory_needs=mandatory_needs(t)))
    validate_selection_plan(t,result)
    return result


async def generate(t,policy,base,candidates=None,selected_point_ids=None):
    """Planner selects only. Updating a trusted selection makes zero model calls."""
    check_input(t)
    start=time.perf_counter();calls=[];token=usage_capture.set(calls)
    model=get_settings()['writer_model'];shared=shared_context(t,policy)
    run=dict(model=model,input_hash=digest(shared),prompt_hash=digest([ADAPTER,CANDIDATE_PROMPT]),
        source_commit='e85f3cbc2e4a79bf33b2a12e9bdd9087d414735b',method_sources=METHOD_SOURCES,
        mode='selected_points' if candidates is not None else 'initial',status='running')
    t.setdefault('planner_runs',[]).append(run)
    try:
        if candidates is None:
            before=time.perf_counter()
            candidates=rank_candidates(t,await llm.complete(model,base+'\n'+ADAPTER+'\n'+CANDIDATE_PROMPT,shared,P.CandidateBatch))
            run['candidate_seconds']=time.perf_counter()-before
            selected_point_ids=[c['id'] for c in candidates if c['recommendation']=='recommended']
        result=selection_plan(t,candidates,selected_point_ids,run['input_hash'])
        run.update(status='complete',candidates=copy.deepcopy(candidates),output_hash=digest(result))
        return result
    except Exception as e:
        run.update(status='failed',error=str(e)[:1000]);raise
    finally:
        run.update(seconds=time.perf_counter()-start,calls=calls)
        usage_capture.reset(token)


def reconcile(old,incoming,platform):
    """Client edits cannot replace recommendation scores or execution selection."""
    if old and old.get('schema_version')=='3':
        # A client may echo trusted selection/structure, never supply its replacement.
        if content_fingerprint(old)!=content_fingerprint(incoming):
            raise ValueError('卖点选择请使用保存卖点接口；段落结构由 Writer 生成')
        return copy.deepcopy(old)
    plan=copy.deepcopy(incoming)
    if not old or old.get('schema_version')!='2':
        if plan.get('schema_version')=='2':plan['planning_analysis']={'status':'user_modified','warnings':['用户提供规划，未执行模型评分']}
        return plan
    if content_fingerprint(old)==content_fingerprint(plan):
        plan['planning_analysis']=copy.deepcopy(old.get('planning_analysis'));return plan
    for key in ('schema_version','product_id','narrative','composition_rationale'):
        if key not in plan and key in old:plan[key]=copy.deepcopy(old[key])
    plan['schema_version']='2'
    if not plan.get('product_id'):plan['product_id']=old.get('product_id')
    original_selection=old.get('selected_point_ids') or []
    if 'selected_point_ids' in plan and set(plan['selected_point_ids'] or [])!=set(original_selection):
        raise ValueError('卖点选择已变化，请点击按所选卖点更新大纲，不可直接替换当前执行集合')
    plan['selected_point_ids']=copy.deepcopy(original_selection)
    old_sections={s['id']:s for s in old['sections']}
    candidates={c['id']:c for c in (old.get('planning_analysis') or {}).get('candidates',[])}
    layout_edited=any('image_position' in s and s.get('image_position')!=old_sections.get(s['id'],{}).get('image_position') for s in plan['sections'])
    image_index=0
    for sec in plan['sections']:
        previous=old_sections.get(sec['id'],{})
        for key in ('reader_question','role','point_ids','image_position','target_chars'):
            if key not in sec and key in previous:sec[key]=copy.deepcopy(previous[key])
        if 'point_ids' not in sec:
            sec['point_ids']=[cid for cid in original_selection if set(sec['fact_ids'])&set(candidates[cid]['fact_ids'])]
        if not sec.get('reader_question'):sec['reader_question']=sec['purpose']
        if not sec.get('role'):sec['role']='argument' if sec['fact_ids'] else 'opening'
        if sec['image_id']:image_index+=1
        if not sec['image_id']:sec['image_position']=default_position(platform,None,0)
        elif not sec.get('image_position') or sec['image_position']['kind']=='none' or (platform!='wechat' and not layout_edited):
            sec['image_position']=default_position(platform,sec['image_id'],image_index)
    a=copy.deepcopy(old.get('planning_analysis') or {})
    a.update(status='user_modified',warnings=['用户修改后的结构已保留；原评分与推荐仅为生成时记录，不代表当前大纲的最新评价'],based_on_hash=content_fingerprint(plan))
    plan['planning_analysis']=a
    return plan

def public_plan(plan):
    """Read-only compatibility projection for historical narrative and candidates."""
    plan=copy.deepcopy(plan)
    if not plan.get('composition_rationale') and plan.get('narrative'):
        n=plan['narrative'];plan['composition_rationale']=n.get('ordering_rationale') or n.get('reason') or ''
    selected=set(plan.get('selected_point_ids') or [])
    for c in (plan.get('planning_analysis') or {}).get('candidates',[]):
        c.setdefault('recommendation','recommended' if c['id'] in selected else 'alternative')
        c.setdefault('recommendation_reason','旧版候选记录，按已执行大纲呈现；调整选用需明确更新大纲')
    return plan

def execution_plan(plan):
    result=copy.deepcopy(plan);result.pop('planning_analysis',None)
    return result
