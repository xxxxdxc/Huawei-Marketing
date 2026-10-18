"""Auditable local evidence trade-offs. Canonical Brief and raw coverage stay immutable."""
import copy
import hashlib
import json
import re
from . import brief_agent as ba, evidence_policy as ep, storage as db
from .clients import ServiceError

TOPICS = {
    "battery": ("续航表现", r"续航|电池(?:使用|工作|运行)时(?:间|长)|不用.{0,6}(?:插座|充电)|全天|一整天|从早.{0,4}到晚|battery\s*life"),
    "battery_capacity": ("电池容量", r"电池容量|battery\s*capacity|瓦时|\bWh\b"),
    "charging": ("充电性能", r"充电速度|快充|充电时长|充电功率|charging"),
    "portability": ("轻便/重量", r"轻便|轻薄|便携|重量|机身厚度|携带负担|portability"),
    "compatibility": ("软件/系统兼容", r"兼容|适配|驱动|软件支持|应用支持|compatib"),
    "performance": ("性能", r"性能|处理器|CPU|GPU|跑分|算力|流畅"),
    "display": ("屏幕", r"屏幕|显示屏|触控屏|触摸屏|触屏|色域|分辨率|OLED|刷新率"),
    "stylus": ("手写笔支持", r"手写笔|触控笔|触屏笔|stylus"),
    "price": ("价格", r"价格|售价|报价|到手价|金额|多少钱"),
    "promotion": ("优惠", r"优惠|补贴|折扣|赠品|促销|领券"),
    "safety": ("安全条件", r"电压|安全|禁忌|风险|充电协议"),
}
RULES = """必须遵守 execution_scope：已由用户明确舍弃的请求、方向、关联事实和主题不得在标题、导语、正文、图注、标签、CTA或图片画面中重新出现；即使原始资料或原始Brief提及也不能恢复。execution_scope.relaxed_constraints 是用户已明确授权本次放宽的原条件，仅对其列明请求生效；其余硬条件继续执行。只使用 execution_brief 和当前可用事实，不把缺证改称已验证，不把取舍说明写进营销正文。Reviewer必须逐项检查遗漏边界，包括同义改写；修订只删除越界表达，不恢复已舍弃方向。"""


def digest(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode()).hexdigest()


def topics(text):
    return {key for key,(_,pattern) in TOPICS.items() if re.search(pattern,text,re.I)}


def raw_package(t):
    p=copy.deepcopy(t.get("package") or {})
    if "all_facts" in p:p["facts"]=copy.deepcopy(p["all_facts"])
    if "all_conflicts" in p:p["conflicts"]=copy.deepcopy(p["all_conflicts"])
    return p


def assert_scope(t):
    scope=t.get("execution_scope")
    if scope and scope["brief_hash"]!=ba.digest(t.get("brief_analysis")):
        raise ServiceError("执行取舍与当前 Brief 不一致，请重新预览并确认")
    return scope


def protected_reason(t,r):
    if not r.get("waivable",True) or r.get("guardrail","none")!="none":
        return "该请求属于不可局部舍弃的产品身份、安全或必要兼容门槛"
    if re.search(r"安全|禁忌|电压|充电协议|产品身份|确认.*型号|核对.*型号",r["question"]):
        return "涉及产品身份或必要安全核查，不能通过内容取舍绕过"
    explicit=[]
    for name in ("customer_needs","user_constraints"):
        field=t["brief_analysis"]["requirements"][name]
        if field["source"]=="explicit":explicit.extend(field["value"])
    if "compatibility" in topics(r["question"]) and any(
        re.search(r"必须|务必|必需|一定要|需要运行|需要使用|正常运行|不能缺",v)
        and ("compatibility" in topics(v) or re.search(r"软件|应用|Windows|Photoshop|CAD",v,re.I))
        for v in explicit):
        return "兼容性是用户明确需求，需补充证据或整体修改需求"
    return None


def dependency_closure(t,request_ids,direction_ids):
    a=t["brief_analysis"];requests=a["retrieval_plan"]["facts"]
    by_id={r["id"]:r for r in requests};directions={d["id"]:d for d in a["message_strategy"]["priorities"]}
    if not set(request_ids)<=set(by_id) or not set(direction_ids)<=set(directions):
        raise ValueError("取舍范围包含不存在的请求或方向")
    # A direction groups requests; it is not a dependency edge. In particular,
    # identity checks and independently supported features may share a direction.
    roots=set(request_ids)|{r["id"] for r in requests if r["direction_id"] in direction_ids}
    omitted=set(roots);dropped=set(direction_ids);reasons={}
    previous=assert_scope(t) or {}
    omitted.update(previous.get("omitted_request_ids",[]));dropped.update(previous.get("omitted_direction_ids",[]))
    for rid in omitted:reasons[rid]=dict(kind="selected_or_inherited",via=rid)
    cov={c["request_id"]:c for c in t["package"].get("coverage",[])}
    seed_sets=[topics(by_id[x]["question"]) for x in roots]
    removed_topics=set().union(*(keys for keys in seed_sets if len(keys)==1)) if seed_sets else set()
    removed_topics.update(previous.get("prohibited_topics",[]))
    changed=True
    while changed:
        before=set(omitted)
        lost_facts={fid for drop in omitted if cov.get(drop,{}).get("status")=="conflict" for fid in cov.get(drop,{}).get("fact_ids",[])}
        for r in requests:
            rid=r["id"]
            if rid in omitted:continue
            reason=None
            deps=set(r.get("depends_on",[])) & omitted
            if deps:reason=dict(kind="explicit_dependency",via=sorted(deps))
            shared=lost_facts & set(cov.get(rid,{}).get("fact_ids",[]))
            if shared:reason=dict(kind="shared_evidence",via=sorted(shared))
            # Legacy subject fallback uses the request itself, never its parent
            # heading, and cannot silently remove a mandatory prerequisite.
            overlap=removed_topics & topics(r["question"])
            if overlap and not protected_reason(t,r):reason=dict(kind="shared_subject",via=sorted(overlap))
            if reason:omitted.add(rid);reasons[rid]=reason
        changed=before!=omitted
    for did in directions:
        members=[r for r in requests if r["direction_id"]==did]
        remaining=[r for r in members if r["id"] not in omitted and r.get("guardrail","none")!="identity"]
        if any(r["id"] in omitted for r in members) and not remaining:dropped.add(did)
    return omitted,dropped,reasons


def refusal_constraints(t,omitted):
    a=t["brief_analysis"];requests={r["id"]:r for r in a["retrieval_plan"]["facts"]};result=[]
    old=assert_scope(t) or {};accepted=set(old.get("acknowledged_constraint_ids",[]))
    turns=t.get("dialogue") or [dict(id="legacy_raw",kind="user",text=t.get("raw",""))]
    for rid in sorted(omitted):
        r=requests[rid];kind=ep.request_kind(r);refs=[]
        if kind in ep.COMMERCIAL:
            refs=ep.hard_rule(kind,turns)
        else:
            keys=topics(r["question"])
            for turn in reversed(turns):
                if turn.get("kind","user")!="user":continue
                clauses=re.split(r"[。；;\n]",turn["text"])
                matching=[c for c in clauses if topics(c)&keys]
                if any(ep.RELAX.search(c) for c in matching):break
                found=[dict(turn_id=turn["id"],quote=c) for c in matching if ep.REFUSAL.search(c)]
                if found:refs=found;break
        if refs:
            cid="C"+digest(dict(request_id=rid,evidence=refs))[:20]
            result.append(dict(id=cid,request_id=rid,evidence=refs,
                description="原要求缺少该项就不生成；需明确授权本次舍弃该项",
                requires_ack=cid not in accepted))
    return result


def project(t,omitted,dropped):
    """Derive execution data, never alter original request statuses."""
    view=copy.deepcopy(t);a=view["brief_analysis"];p=raw_package(t);view["package"]=p
    requests=a["retrieval_plan"]["facts"]
    cov={c["request_id"]:c for c in p.get("coverage",[])}
    surviving_support={fid for r in requests if r["id"] not in omitted and cov.get(r["id"],{}).get("status")=="supported" for fid in cov[r["id"]]["fact_ids"]}
    blocked_facts={fid for rid in omitted for fid in cov.get(rid,{}).get("fact_ids",[])}-surviving_support
    for conflict in p.get("conflicts",[]):
        if isinstance(conflict,dict):
            for rid in conflict["request_ids"]:
                blocked_facts.update(cov.get(rid,{}).get("fact_ids",[]))
    retained=[r for r in requests if r["id"] not in omitted]
    allowed_facts={fid for r in retained for fid in cov.get(r["id"],{}).get("fact_ids",[]) if cov.get(r["id"],{}).get("status")=="supported"}-blocked_facts
    p["facts"]=[f for f in p.get("facts",[]) if f["id"] in allowed_facts]
    # Unsupported/conflicting retained requests stay exactly as reported, except
    # references to quarantined facts are removed so they cannot be used as support.
    p["coverage"]=[copy.deepcopy(cov[r["id"]]) for r in retained if r["id"] in cov]
    for c in p["coverage"]:
        c["fact_ids"]=[fid for fid in c["fact_ids"] if fid in allowed_facts]
        if c["status"]=="supported" and not c["fact_ids"]:
            c.update(status="not_found",reason="关联事实已被舍弃或隔离；不构成当前执行依据")
    active_conflicts=[]
    for conflict in p.get("conflicts",[]):
        if isinstance(conflict,str) or not conflict.get("request_ids") or not set(conflict["request_ids"])<=omitted:
            active_conflicts.append(conflict)
    p["conflicts"]=active_conflicts
    a["retrieval_plan"]["facts"]=retained
    a["retrieval_plan"]["images"]=[r for r in a["retrieval_plan"]["images"] if r["direction_id"] not in dropped]
    a["message_strategy"]["priorities"]=[d for d in a["message_strategy"]["priorities"] if d["id"] not in dropped]
    for direction in a["message_strategy"]["priorities"]:
        if any(r["id"] in omitted and r["direction_id"]==direction["id"] for r in requests):
            kept=[r["question"] for r in retained if r["direction_id"]==direction["id"] and r.get("guardrail","none")!="identity"]
            direction["direction"]="核实本次保留内容："+"；".join(kept)
            direction["reason"]="根据用户本次取舍，仅保留独立请求；不恢复已舍弃的延伸用途"
    labels=[d["direction"] for d in a["message_strategy"]["priorities"]]
    a["message_strategy"]["theme"]="围绕本次保留方向创作："+"；".join(labels)
    a["message_strategy"]["angle"]="仅展开本次保留方向，所有客观陈述以允许使用的事实为依据"
    cats={ep.request_kind(r) for r in retained}
    a["commercial_requests"]=[n for n in a.get("commercial_requests",[]) if n["category"] in cats]
    return view,blocked_facts


def prohibited_topics(t,omitted):
    requests=t["brief_analysis"]["retrieval_plan"]["facts"]
    removed=set().union(*(topics(r["question"]) for r in requests if r["id"] in omitted)) if omitted else set()
    kept=set().union(*(topics(r["question"]) for r in requests if r["id"] not in omitted)) if any(r["id"] not in omitted for r in requests) else set()
    return sorted(removed-kept)


def image_allowed(t,image,prohibited=None):
    keys=prohibited if prohibited is not None else (assert_scope(t) or {}).get("prohibited_topics",[])
    # A visible description is reusable, whereas an unreviewed index is not OCR evidence.
    visible=image.get("visual_description","") if image.get("visual_checked") else ""
    return not any(re.search(TOPICS[key][1],visible,re.I) for key in keys)


def evaluate(t,omitted,dropped):
    from .workflow import verify_facts,PLATFORMS
    blockers=[]
    try:
        ba.assert_confirmed(t)
        if not t.get("brief_analysis"):raise ValueError("旧任务需先完成结构化 Brief")
    except (ValueError,ServiceError) as e:return None,[],[dict(code="identity_or_brief",reason=str(e),waivable=False)]
    p=raw_package(t);a=t["brief_analysis"]
    if p.get("product",{}).get("id")!=t["product_id"]:
        blockers.append(dict(code="product_identity",reason="资料型号与任务不一致",waivable=False))
    if p.get("knowledge_source",t.get("knowledge_source","ima"))!=t.get("knowledge_source","ima"):
        blockers.append(dict(code="source_mismatch",reason="资料来源与任务不一致",waivable=False))
    if (t.get("knowledge_snapshot") or {}).get("sha256") and (p.get("knowledge_snapshot") or {}).get("sha256")!=t["knowledge_snapshot"]["sha256"]:
        blockers.append(dict(code="snapshot_mismatch",reason="已保存证据快照与任务不一致",waivable=False))
    for r in a["retrieval_plan"]["facts"]:
        reason=protected_reason(t,r)
        if r["id"] in omitted and reason:blockers.append(dict(code="non_waivable",request_id=r["id"],reason=reason,waivable=False))
    try:
        verify_facts(p)
        # Validate the full original coverage/conflict structure before filtering.
        ep.apply(dict(t,package=copy.deepcopy(p)))
        view,excluded=project(t,omitted,dropped)
        gaps=ep.apply(view)
    except (ServiceError,KeyError,ValueError) as e:
        blockers.append(dict(code="evidence_integrity",reason=str(e),waivable=False));return None,[],blockers
    for gap in gaps:blockers.append(dict(code=gap["blocking_reason"],request_id=gap["request"]["id"],reason=gap.get("reason") or gap["coverage"]["reason"],waivable=not bool(protected_reason(t,gap["request"]))))
    if view["package"].get("conflicts"):
        blockers.append(dict(code="active_conflict",reason="保留范围仍存在未解决冲突",waivable=False))
    product_ids={r["id"] for r in view["brief_analysis"]["retrieval_plan"]["facts"] if ep.request_kind(r)=="product" and r.get("guardrail","none")!="identity"}
    valid_product_facts={f["id"] for f in view["package"]["facts"] if f.get("category","product")=="product" and ep.commercial_kind(f["claim"]+" "+f["quote"]) is None}
    has_product=any(c["request_id"] in product_ids and c["status"]=="supported" and set(c["fact_ids"])&valid_product_facts for c in view["package"]["coverage"])
    if not view["brief_analysis"]["message_strategy"]["priorities"] or not has_product:
        blockers.append(dict(code="empty_content",reason="剩余方向没有可用的产品事实，不能生成空内容或仅价格促销",waivable=False))
    images=[im for im in p.get("asset_candidates",p.get("images",[])) if im.get("model_verified") and im.get("usable",True) and image_allowed(t,im,prohibited_topics(t,omitted))]
    from .settings import ASSETS
    for im in images:
        if im.get("sha256"):
            path=ASSETS/im["id"]
            if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=im["sha256"]:
                blockers.append(dict(code="image_integrity",reason="已核对图片文件缺失或内容改变，请刷新资料",waivable=False))
    minimum=PLATFORMS[t["platform"]]["min_images"]
    if len(images)<minimum:blockers.append(dict(code="image_shortage",reason=f"当前候选图片{len(images)}张，平台至少需要{minimum}张；请先补充素材",waivable=False))
    return view,sorted(excluded),blockers


def preview(t,request_ids=(),direction_ids=()):
    # Read-only: even policy normalization occurs on deep copies.
    if len(request_ids)!=len(set(request_ids)) or len(direction_ids)!=len(set(direction_ids)):
        raise ValueError("取舍范围编号不可重复")
    a=t.get("brief_analysis")
    if not a or not a.get("retrieval_plan") or not t.get("package"):
        raise ValueError("尚无可审查的结构化 Brief 与资料包，请先完成需求确认和检索")
    omitted,dropped,reasons=dependency_closure(t,request_ids,direction_ids)
    view,excluded,blockers=evaluate(t,omitted,dropped)
    requests=a["retrieval_plan"]["facts"];cov={c["request_id"]:c for c in t["package"].get("coverage",[])}
    directions=a["message_strategy"]["priorities"]
    prohibited=prohibited_topics(t,omitted)
    payload=dict(task_id=t["id"],version=t["version"],selected_request_ids=sorted(request_ids),selected_direction_ids=sorted(direction_ids),
        omitted_request_ids=sorted(omitted),omitted_direction_ids=sorted(dropped),
        removed=[dict(request=copy.deepcopy(r),coverage=copy.deepcopy(cov.get(r["id"])),dependency=reasons.get(r["id"])) for r in requests if r["id"] in omitted],
        affected_directions=[dict(direction=copy.deepcopy(d),request_ids=[r["id"] for r in requests if r["direction_id"]==d["id"]],
            selected=d["id"] in direction_ids,reason="整个方向已舍弃" if d["id"] in dropped else "仅移除已舍弃请求及其依赖，保留独立依据；当前方向："+next((x["direction"] for x in (view or {}).get("brief_analysis",{}).get("message_strategy",{}).get("priorities",[]) if x["id"]==d["id"]),d["direction"])) for d in directions if d["id"] in dropped or any(r["id"] in omitted and r["direction_id"]==d["id"] for r in requests)],
        retained=[dict(request=copy.deepcopy(r),coverage=copy.deepcopy(cov.get(r["id"]))) for r in requests if r["id"] not in omitted],
        retained_directions=copy.deepcopy(view["brief_analysis"]["message_strategy"]["priorities"]) if view else [],
        retained_fact_ids=[f["id"] for f in view["package"]["facts"]] if view else [],
        excluded_fact_ids=excluded,
        excluded_image_ids=[im["id"] for im in t["package"].get("asset_candidates",t["package"].get("images",[])) if not image_allowed(t,im,prohibited)],
        remaining_blockers=blockers,
        required_constraint_acks=refusal_constraints(t,omitted),prohibited_topics=prohibited,
        prohibited_topic_labels=[TOPICS[x][0] for x in prohibited],
        can_apply=bool(omitted) and not blockers,
        next_status="plan_ready",requires_plan_confirmation=True,requires_asset_review=any(not i.get("visual_checked") for i in t["package"].get("images",[])),
        original_brief_hash=ba.digest(a),original_coverage=copy.deepcopy(t["package"].get("coverage",[])))
    binding=dict(task_id=t["id"],payload=payload,package=raw_package(t),dialogue=t.get("dialogue"),scope=t.get("execution_scope"),
        product_id=t.get("product_id"),snapshot=t.get("knowledge_snapshot"))
    payload["preview_id"]="E"+digest(binding)
    return payload


def confirm(t,body):
    if not body.confirmed:raise ValueError("请先查看取舍及关联影响，并明确确认")
    result=preview(t,body.drop_request_ids,body.drop_direction_ids)
    if result["preview_id"]!=body.preview_id:raise ValueError("取舍预览已更新，请重新预览并确认")
    needed={c["id"] for c in result["required_constraint_acks"] if c["requires_ack"]}
    given=set(body.acknowledged_constraint_ids)
    if len(given)!=len(body.acknowledged_constraint_ids) or needed!=given:
        raise ValueError("需逐项明确确认放宽受影响的拒绝降级约束，不能隐式解除")
    if not result["can_apply"]:raise ValueError("当前取舍仍有不可绕过的门槛或剩余核心证据缺口")
    prior=assert_scope(t) or {}
    authorization=dict(id="R"+digest(dict(preview=result["preview_id"],at=db.now()))[:24],at=db.now(),
        authorized_version=t["version"]+1,preview_id=result["preview_id"],
        original_brief_hash=result["original_brief_hash"],original_confirmation=copy.deepcopy(t["brief_confirmation"]),
        original_requests=copy.deepcopy(t["brief_analysis"]["retrieval_plan"]),
        original_coverage=copy.deepcopy(t["package"]["coverage"]),
        original_evidence_hash=digest(raw_package(t)),preview=copy.deepcopy(result),
        acknowledged_constraint_ids=sorted(set(prior.get("acknowledged_constraint_ids",[]))|given))
    t.setdefault("resolution_history",[]).append(authorization)
    t["execution_scope"]=dict(id=authorization["id"],brief_hash=result["original_brief_hash"],source_brief_hash=result["original_brief_hash"],
        omitted_request_ids=result["omitted_request_ids"],omitted_direction_ids=result["omitted_direction_ids"],
        prohibited_topics=result["prohibited_topics"],excluded_fact_ids=result["excluded_fact_ids"],
        acknowledged_constraint_ids=authorization["acknowledged_constraint_ids"],authorized_at=authorization["at"])
    for key in ("plan","document","review","repair_before"):t[key]=None
    t["user_image_overrides"]={}
    t["error"]=None
    return result


def apply(t):
    scope=assert_scope(t)
    if not scope:return ep.apply(t)
    view,_,blockers=evaluate(t,set(scope["omitted_request_ids"]),set(scope["omitted_direction_ids"]))
    if not view:raise ServiceError("取舍执行证据无效："+str(blockers))
    original=raw_package(t);p=t["package"]
    p["all_facts"]=original.get("facts",[]);p["all_conflicts"]=original.get("conflicts",[])
    for key in ("facts","conflicts","content_policy"):p[key]=copy.deepcopy(view["package"][key])
    p["execution_coverage"]=copy.deepcopy(view["package"]["coverage"])
    p["content_policy"]["execution_scope"]=boundary(t)
    # Never replace original p.coverage with the filtered or recomputed execution view.
    p["evidence_gaps"]=[dict(blocking_reason=b["code"],reason=b["reason"],request_id=b.get("request_id")) for b in blockers]
    return p["evidence_gaps"]


def boundary(t):
    scope=assert_scope(t)
    if not scope:return None
    accepted=set(scope.get("acknowledged_constraint_ids",[]));relaxed={}
    for record in t.get("resolution_history",[]):
        for constraint in record.get("preview",{}).get("required_constraint_acks",[]):
            if constraint["id"] in accepted:
                relaxed[constraint["id"]]={k:copy.deepcopy(constraint[k]) for k in ("id","request_id","evidence","description")}
    return dict(scope,prohibited_topic_labels=[TOPICS[x][0] for x in scope["prohibited_topics"]],
        relaxed_constraints=list(relaxed.values()),rules=RULES)


def analysis_for_execution(t):
    scope=assert_scope(t)
    if not scope:return t.get("brief_analysis")
    return project(t,set(scope["omitted_request_ids"]),set(scope["omitted_direction_ids"]))[0]["brief_analysis"]


def package_for_model(t):
    if not t.get("execution_scope"):return t.get("package")
    p=copy.deepcopy(t["package"])
    for key in ("all_facts","all_conflicts","coverage","asset_candidates"):p.pop(key,None)
    p["execution_scope"]=boundary(t)
    return p


def text_issues(t,text,location):
    scope=assert_scope(t)
    if not scope:return []
    issues=[]
    for key in scope["prohibited_topics"]:
        if re.search(TOPICS[key][1],text,re.I):
            issues.append(dict(category="compliance",location=location,detail="重新引入用户已明确舍弃的方向："+TOPICS[key][0],severity="error",repairable=True))
    return issues


def assert_plan(t,plan):
    if not t.get("execution_scope"):return
    text=" ".join([plan["angle"],plan["title_direction"],plan["cta"],*[s["heading"]+" "+s["purpose"]+" "+s["image_reason"] for s in plan["sections"]]])
    if text_issues(t,text,"内容规划"):raise ValueError("内容规划重新引入已舍弃方向，请按执行边界重新规划")


def rebind_platform(t,old_hash,new_hash,turn_id):
    scope=t.get("execution_scope")
    if scope:
        if scope["brief_hash"]!=old_hash:raise ValueError("原取舍授权已失效，不能通过切换平台绕过")
        scope=copy.deepcopy(scope);scope["brief_hash"]=new_hash
        scope.setdefault("platform_bindings",[]).append(dict(from_hash=old_hash,to_hash=new_hash,turn_id=turn_id))
        t["execution_scope"]=scope


def review_summary(t):
    p=preview(t)
    cov={c["request_id"]:c for c in t["package"].get("coverage",[])};omitted=set(p["omitted_request_ids"])
    facts={f["id"]:f for f in raw_package(t).get("facts",[])}
    unmet=[]
    for r in t["brief_analysis"]["retrieval_plan"]["facts"]:
        c=cov.get(r["id"])
        if not c or c["status"]!="supported":
            unmet.append(dict(request=copy.deepcopy(r),coverage=copy.deepcopy(c),found=[facts[f] for f in (c or {}).get("fact_ids",[]) if f in facts],
                missing=(c or {}).get("reason","尚无覆盖报告"),direction_id=r["direction_id"],affected_direction_ids=sorted(dependency_closure(t,[r["id"]],[])[1]),omitted=r["id"] in omitted,
                blocking=r["id"] in {b.get("request_id") for b in p["remaining_blockers"]},can_drop=protected_reason(t,r) is None,non_waivable_reason=protected_reason(t,r)))
    unmet.sort(key=lambda u:(u["omitted"],not u["blocking"],u["request"]["priority"]!="required"))
    return dict(version=t["version"],knowledge_source=t.get("knowledge_source","ima"),
        knowledge_snapshot=t.get("knowledge_snapshot"),local_archive_path=t.get("knowledge_zip_path") if t.get("knowledge_source")=="local_zip" else None,unmet_requirements=unmet,
        available_facts=[copy.deepcopy(facts[fid]) for fid in p["retained_fact_ids"] if fid in facts],
        blockers=p["remaining_blockers"],execution_scope=boundary(t),task_upload_supported=False,
        material_requirements=[dict(request_id=u["request"]["id"],type=ep.request_kind(u["request"]),
            question=u["request"]["question"],conditions=u["request"].get("conditions",[]),
            document_types=[TOPICS[key][0]+"的官方说明、参数与测试/适用条件" for key in sorted(topics(u["request"]["question"]))] or ["可定位的官方原文及适用条件"],
            target_model=t["brief_analysis"]["product_resolution"]["product_model"]) for u in unmet],
        refresh=dict(method="POST",path=f"/api/tasks/{t['id']}/refresh-evidence",body=dict(version=t["version"]),
            description="更新任务原资料源后主动刷新目录、原文、图片及覆盖；保留历史与已授权取舍。无任务级上传。"),
        actions=["adjust_content","refresh_evidence","modify_requirements"])
