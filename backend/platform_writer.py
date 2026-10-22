"""Platform Writer owns composition and drafting; no new user confirmation."""
import copy,time
from . import planner_schemas as P,content_planner as cp,publication_rules as pub,brief_agent as ba,store_marketing as sm
from .clients import llm,usage_capture
from .settings import get_settings
from .marketing_methods import WRITER_METHOD,METHOD_GUARD,writer_bundle

VOICE_VERSION='brand_promotion_v1'
REVIEW_GUIDANCE="""本次Writer采用成熟品牌宣传口吻。核验事实与必要条件的职责不变；若需要修复，请说明缺少的具体条件或无依据子结论，不要求成稿播报资料来源或引导消费者到店核对未知性能。模型生成的Brief策略和候选推荐理由不是用户逐字要求；通用到店营销目标由根级CTA一次承接，正文不逐段到店。70Wh容量不能支持续航无忧，额定/最高功率不能推导充满时长。已选薄弱点可以合并到相关段落，只写已知；不要求独立成段。"""



def writing_payload(payload):
    """Writer-only projection: preserve requirements/evidence, omit model workflow advice.

    Source Brief/Planner/Reviewer data remains unchanged in the task and run audit.
    """
    out=copy.deepcopy(payload)
    brief=out.get('brief') or {}
    allowed=('audience','scenario','platform','goal','purchase_stage','pain_points','tone',
             'emphasis','requirements','audience_insight','knowledge_source',
             'commercial_requests','content_policy','execution_scope')
    out['brief']={k:v for k,v in brief.items() if k in allowed}
    strategy=brief.get('message_strategy') or {}
    if strategy.get('theme'):out['brief']['core_theme']=strategy['theme']
    if 'selected_points' in out:
        out['selected_points']=[{k:v for k,v in c.items() if k not in ('scores','recommendation_reason')} for c in out['selected_points']]
    out.pop('retrieval_requests',None)
    requirements=brief.get('requirements') or {}
    goal=(requirements.get('marketing_goal') or {}).get('value') or brief.get('goal','')
    out['writer_contract']=dict(version=VOICE_VERSION,voice='成熟品牌宣传，推荐明确、自然顺畅、适度文采',
        marketing_goal=goal,selected_points='全部保留；薄弱事实可合并，不推导无依据收益',
        body='不播报资料或编排，不安排到店核对；门店营销遵循当前平台store_marketing_policy，仅在根级cta承接',
        reviewer_suggestions='修复事实风险，不照搬建议措辞；未证实子结论省略')
    return out


STRUCTURE_PROMPT="""你是 Platform Writer 的结构规划阶段，仅输出结构，不写最终正文。
从用户已确认的卖点和读者购买阶段出发，先确定全文唯一的main_takeaway，再组织有递进的读者问题。
仅有容量/功率等数字的薄弱卖点优先合并进相关段落作辅助信息，不单列资料播报式段落。不要把候选排名当段落顺序，不要求一卖点一段；可合并关联卖点，也可把一个复杂卖点拆成不同问题。每个选中卖点都须有实际事实承接，不增选或漏选。
用成熟品牌宣传的主线组织全文，不安排逐段到店核对或资料咨询。先判断读者已知什么、最关心什么，按理解和决策需要安排，而非参数清单。没有必要不增加独立开场/总结段；不套固定文章模板。
每段明确purpose、reader_question、reader_progress（本段新增理解）、connection_to_previous（与前段的具体承接，首段说明为何从此切入），禁止多个段落换句话重复同一结论。
仅引用选中卖点的事实；argument/objection需绑定point_ids与fact_ids。任何段落的每一个point_id都必须由本段fact_ids中属于该候选的至少一条事实承接，不能只贴卖点标签；没有产品事实的开场或过渡段point_ids与fact_ids都应为空。每项利益必须由所引事实支持，不能把场景假设当成产品能力。
按平台确定段落长短与用图。图片image_id必须从输入images逐字复制完整ID（不改写、不补全、不根据相似前缀重建）；没有匹配图则用null，绝不编造ID。图片从核验池选，不限于候选预选图，但必须说明与本段的实际画面关联；不把外观当参数证明，不重复使用图片。每段最多一图。
wechat图片位置before_section/after_section且order=null；xiaohongshu为carousel、moments为grid，序号1起连续；无图none/order=null。总图数遵守policy硬性范围；recommended_images仅为建议，小红书至少1张，推荐3–6张，不为推荐范围凑图、补图或删图，target_chars总和符合budget。
heading仅工作人员阅读提示；CTA仅根级，不另设CTA段。composition_rationale说明全文为什么这样推进，不输出框架名称或最终标题。selected_point_ids和product_id原样保留。
输出前检查：全文是否围绕main_takeaway、各段是否增加新信息、承接是否具体、卖点是否齐全、用图是否相关。只返回结构化规划。
"""
DRAFT_PROMPT="""你是 Platform Writer 的正文阶段。根据内部已校验的结构规划完成单篇营销图文。
沿用本次Writer结构的段落数量、顺序、section_id、图片和事实范围，落实全文主线及各段承接；不要照抄内部heading、purpose或reader_question。
用消费者熟悉的语言把事实与具体需求连起来，功能转收益必须有证据；避免参数堆砌、抽象口号、重复开场、重复结尾和机械模板。
遵守copywriting的分单元打磨和整篇通读方法，备选、自检、诊断留在内部。生成标题、导语、正文、图片说明、标签与唯一CTA；标题和导语也不可超出所选事实范围。
保持宣传作者身份，不讲解编排过程、不播报资料、不指导到店核对。不得加入新卖点、个人亲测、未经证实的比较或促销。保留影响结论的必要条件，通用防御性说明不进入推文。正文不放段落标题。
"""

def confirmed(t):
    plan=t.get('plan') or {};confirmation=t.get('selection_confirmation') or {}
    return plan.get('schema_version')=='3' and confirmation.get('selection_hash')==cp.selection_fingerprint(plan)


def validate_outline(t,selection,result):
    from .workflow import validate_plan
    result=P.WriterOutline.model_validate(result).model_dump()
    context=sm.checked_context(t,result.get('store_context') or t.get('store_marketing_context'))
    result['store_context']=context
    # Reject forbidden/missing store closing before drafting, without inventing one.
    stub=dict(title='',lead='',paragraphs=[],tags=[],cta=result['cta'])
    store_errors=sm.document_issues(t,stub,context)
    if store_errors:raise ValueError(store_errors[0]['detail'])
    if result['product_id']!=t['product_id']:raise ValueError('Writer结构返回其他型号')
    chosen=selection['selected_point_ids']
    if len(set(result['selected_point_ids']))!=len(result['selected_point_ids']) or set(result['selected_point_ids'])!=set(chosen):raise ValueError('Writer改变了用户确认的卖点集合')
    if any(s['role']=='cta' for s in result['sections']):raise ValueError('Writer不能另设重复行动引导段')
    composed=copy.deepcopy(selection)
    composed.update(phase='composed',angle=result['angle'],title_direction=result['title_direction'],
        composition_rationale=result['composition_rationale'],cta=result['cta'],
        sections=[{k:v for k,v in s.items() if k not in ('connection_to_previous','reader_progress')} for s in result['sections']])
    validate_plan(t,composed)
    # Exact duplicates are deterministic; semantic quality still requires model evaluation.
    progress=[''.join(s['reader_progress'].split()) for s in result['sections']]
    if len(progress)!=len(set(progress)):raise ValueError('Writer段落重复相同信息增量')
    return result,composed


async def compose(t,base):
    from .workflow import PLATFORMS,event
    selection=copy.deepcopy(t['plan'])
    if not confirmed(t):raise ValueError('请先确认核心卖点，再开始组织和写稿')
    cp.validate_selection_plan(t,dict(selection,phase='selection',sections=[]))
    selected=set(selection['selected_point_ids'])
    points=[c for c in selection['planning_analysis']['candidates'] if c['id'] in selected]
    fids={fid for c in points for fid in c['fact_ids']}
    shared=cp.shared_context(t,PLATFORMS[t['platform']])
    payload=shared|dict(selected_point_ids=selection['selected_point_ids'],
        selected_points=[{k:v for k,v in c.items() if k!='scores'} for c in points],
        facts=[f for f in shared['facts'] if f['id'] in fids],budget=cp.BUDGETS[t['platform']])
    payload=writing_payload(payload)|sm.payload(t,extracting=True)
    start=time.perf_counter();calls=[];token=usage_capture.set(calls)
    methods=writer_bundle(t['platform'],'outline')
    system=base+'\n'+methods['text']+'\n'+pub.PLANNER+'\n'+STRUCTURE_PROMPT+'\n'+sm.GUIDANCE
    run=dict(status='running',model=get_settings()['writer_model'],method_sources=methods['method_sources'],
        skill_sources=methods['sources'],case_sources=methods['case_sources'],skill_adapter_sha256=methods['adapter_sha256'],
        input_hash=cp.digest(payload),prompt_hash=cp.digest(system),request_prompt_hash=cp.digest([system,P.WriterOutline.model_json_schema()]),stage='outline')
    t.setdefault('writer_runs',[]).append(run)
    t['writer_stage']='outlining';event(t,'Writer正在组织全文主线、段落与配图')
    try:
        raw=await llm.complete(run['model'],system,payload,P.WriterOutline)
        try:outline,composed=validate_outline(t,selection,raw)
        except ValueError:
            run['rejected_outline']=copy.deepcopy(raw)
            raise
        run.update(status='complete',output_hash=cp.digest(outline))
        t['plan']=composed;t['writer_outline']=outline
        t['store_marketing_context']=copy.deepcopy(outline['store_context'])
        return composed
    except Exception as exc:
        run.update(status='failed',error=str(exc)[:1000]);raise
    finally:
        run.update(seconds=time.perf_counter()-start,calls=calls)
        usage_capture.reset(token)


REPAIR_PROMPT="""你是 Platform Writer 的定向文字修订阶段。只修复核验指出的问题。
输出TextRepair：root_changes只含需要修改的title/lead/cta/tags；paragraph_changes按section_id仅提交需要修改的text或caption；null或未填写表示保留原值，空字符串表示有意清空。
图片ID、段落数量/顺序、内部标题和fact_ids由程序固定，不输出这些字段；不得通过修改图注把已知图改称另一张图。
按Copy Editing点编辑模式，只改变问题句和维持连贯所需的最小上下文，不重新组织全文。
Reviewer建议仅用于识别风险，不是必用措辞；不采用“资料里列有”“到店问清楚”等修订补丁。用自然措辞补足必要条件或删除无依据句子，不恢复通用免责声明，不新增产品事实、卖点或已省略的价格优惠。
没有可修改的文字时返回空root_changes和空paragraph_changes；内部修订说明不得写入成稿。
"""


def validate_repair(payload,result):
    """A style edit cannot change structural/evidence/image authorization."""
    plan=payload['plan'];sections=plan['sections']
    if [p['section_id'] for p in result['paragraphs']]!=[s['id'] for s in sections]:raise ValueError('定向修订改变了段落编号或顺序，原稿已保留')
    for index,(para,sec) in enumerate(zip(result['paragraphs'],sections)):
        if para['image_id']!=sec['image_id']:raise ValueError(f'自动文字修订尝试改变第{index+1}段配图，已拒绝该结果；原稿和首次核验报告已保留')
        if len(set(para['fact_ids']))!=len(para['fact_ids']) or not set(para['fact_ids'])<=set(sec['fact_ids']):raise ValueError('定向修订超出段落事实范围，原稿已保留')
    original=payload['document']
    names=[p['heading'] for p in original['paragraphs']]
    headings={p['heading']:p['section_id'] for p in original['paragraphs'] if p['heading'] and names.count(p['heading'])==1}
    # Enforce local edits only where all reported locations unambiguously resolve.
    locations={i['location'] for i in payload['issues']}
    root_names={'标题':'title','导语':'lead','行动引导':'cta','标签':'tags'}
    if locations and all(loc in headings or loc in root_names for loc in locations):
        allowed={headings[loc] for loc in locations if loc in headings}
        for before,after in zip(original['paragraphs'],result['paragraphs']):
            if before['section_id'] not in allowed and before!=after:raise ValueError('定向修订修改了无关段落，原稿已保留')
        for key in ('title','lead','cta','tags'):
            if key not in {root_names[loc] for loc in locations if loc in root_names} and original[key]!=result[key]:raise ValueError('定向修订修改了无关字段，原稿已保留')
    return result


def apply_text_repair(payload, raw):
    """Only explicit text patches enter the original immutable Document structure."""
    from .schemas import TextRepair, Document
    # Compatibility for historical direct callers/evaluation fixtures. Actual model
    # transport validates TextRepair, so full-document model responses cannot enter.
    if isinstance(raw, dict) and "paragraphs" in raw:
        Document.model_validate(raw)
        return validate_repair(payload, raw)
    try:
        patch = TextRepair.model_validate(raw).model_dump()
    except ValueError as exc:
        raise ValueError("自动文字修订返回了不允许修改的字段或无效格式。原稿和首次核验报告已保留，请重新核验或手动编辑对应文字。") from exc
    result = copy.deepcopy(payload["document"])
    paragraphs = {p["section_id"]: p for p in result["paragraphs"]}
    seen = set()
    for key, value in patch["root_changes"].items():
        if value is not None:
            result[key] = value
    for change in patch["paragraph_changes"]:
        sid = change["section_id"]
        if sid not in paragraphs or sid in seen:
            raise ValueError("文字修订引用未知或重复段落，原稿与核验报告已保留")
        seen.add(sid)
        for key in ("text", "caption"):
            if change[key] is not None:
                paragraphs[sid][key] = change[key]
    Document.model_validate(result)
    return validate_repair(payload, result)


async def document_call(t,base,payload,schema,stage):
    payload=writing_payload(payload)|sm.payload(t)
    from .schemas import TextRepair
    wire_schema=TextRepair if stage=='repair' else schema
    start=time.perf_counter();calls=[];token=usage_capture.set(calls)
    methods=writer_bundle(t['platform'],stage)
    system=base+'\n'+methods['text']+(pub.REPAIR+REPAIR_PROMPT if stage=='repair' else pub.WRITER+DRAFT_PROMPT)+'\n'+sm.GUIDANCE
    run=dict(status='running',stage=stage,model=get_settings()['writer_model'],method_sources=methods['method_sources'],
        skill_sources=methods['sources'],case_sources=methods['case_sources'],skill_adapter_sha256=methods['adapter_sha256'],
        input_hash=cp.digest(payload),prompt_hash=cp.digest(system),request_prompt_hash=cp.digest([system,wire_schema.model_json_schema()]))
    if stage=='repair':run['revision_issues']=copy.deepcopy(payload['issues'])
    t.setdefault('writer_runs',[]).append(run)
    try:
        raw=await llm.complete(run['model'],system,payload,wire_schema)
        if stage=='repair':
            run['text_patch']=copy.deepcopy(raw)
            result=apply_text_repair(payload,raw)
        else:result=raw
        run.update(status='complete',output_hash=cp.digest(result));return result
    except Exception as exc:
        if stage=='repair' and 'raw' in locals():run['rejected_output']=copy.deepcopy(raw)
        run.update(status='failed',error=str(exc)[:1000]);raise
    finally:
        run.update(seconds=time.perf_counter()-start,calls=calls)
        usage_capture.reset(token)


async def draft(t,base,payload,schema):
    return await document_call(t,base,payload,schema,'draft')


async def repair(t,base,payload,schema):
    return await document_call(t,base,payload,schema,'repair')
