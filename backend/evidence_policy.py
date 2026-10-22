"""Deterministic omission policy for optional commercial claims."""
import copy
import re
from .clients import ServiceError
from . import evidence_usage as usage

COMMERCIAL={"price","promotion"}

def commercial_kind(text):
    if re.search(r"优惠|促销|折扣|补贴|赠品|赠送|满减|返利|领券|立减|分期|积分",text):return "promotion"
    if re.search(r"价格|售价|报价|现价|到手价|多少钱|金额|[¥￥]\s*\d|\d+(?:\.\d+)?\s*元",text):return "price"
    return None


def request_kind(request):
    return request.get("category") if request.get("category") in COMMERCIAL else commercial_kind(request["question"]) or "product"


# These patterns validate the *refusal to generate*, not the word "必须" alone.
PRICE_ANCHOR=r"价格|售价|报价|到手价|金额|多少钱"
PROMO_ANCHOR=r"优惠|促销|补贴|赠品|折扣|返利|领券"
REFUSAL=re.compile(r"(?:否则|不然).{0,10}(?:不生成|不要生成|别生成|不出稿|不要出稿|不写了|取消生成)|(?:没有|缺少|找不到|查不到|无法核实|拿不到).{0,35}(?:不生成|不要生成|别生成|不出稿|停止生成|暂停生成)|(?:只有|必须先).{0,35}才(?:能|可以)?(?:生成|出稿)")
RELAX=re.compile(r"可(?:以)?省略|允许省略|可以不写|可不写|找不到.{0,12}(?:不写|省略|跳过)|没有.{0,12}(?:不写|省略|也.{0,5}生成)|不再要求.{0,12}(?:必须|不生成)")


def hard_rule(category, turns):
    anchor=PRICE_ANCHOR if category=="price" else PROMO_ANCHOR
    for turn in reversed(turns):
        if turn.get("kind","user")!="user":continue
        clauses=[c for c in re.split(r"[。；;\n]",turn["text"]) if re.search(anchor,c)]
        if not clauses and RELAX.search(turn["text"]) and not re.search(PRICE_ANCHOR+"|"+PROMO_ANCHOR,turn["text"]):return []
        for clause in reversed(clauses):
            if RELAX.search(clause) and re.search(r"取消|不再要求|不强求",clause):return []
            refusal=REFUSAL.search(clause)
            if refusal:
                # A different item's explicit condition must not block this item.
                prefix=clause[:refusal.end()]
                mentions=[(m.start(),kind) for kind,pattern in (("price",PRICE_ANCHOR),("promotion",PROMO_ANCHOR)) for m in re.finditer(pattern,prefix)]
                mentions.sort()
                joint=bool(re.search(r"(?:价格|金额).{0,5}[和及与、].{0,5}(?:优惠|补贴)|(?:优惠|补贴).{0,5}[和及与、].{0,5}(?:价格|金额)",prefix))
                if mentions and mentions[-1][1]!=category and not joint:
                    if RELAX.search(clause):return []
                    continue
                return [dict(turn_id=turn["id"],quote=clause[max(0,refusal.start()-300):refusal.end()+100])]
            if RELAX.search(clause):return []
    return []


def normalize_needs(needs, turns):
    result=copy.deepcopy(needs)
    for need in result:
        refs=hard_rule(need["category"],turns)
        need["on_missing"]="block" if refs else "omit"
        need["blocking_evidence"]=refs
    return result


def normalize_strategy(strategy, needs):
    result=copy.deepcopy(strategy);allowed={n["category"] for n in needs}
    plan=result["retrieval_plan"]
    for r in plan["facts"]:
        r["category"]=request_kind(r)
        if r.get("guardrail","none")=="none":r["waivable"]=True
    plan["facts"]=[r for r in plan["facts"] if r["category"]=="product" or r["category"] in allowed]
    products=[r for r in plan["facts"] if r["category"]=="product"]
    if not products:raise ServiceError("策略缺少产品事实检索任务，请重新分析需求")
    if not any(r["priority"]=="required" for r in products):products[0]["priority"]="required"
    for need in needs:
        if not any(r["category"]==need["category"] for r in plan["facts"]):
            used={r["id"] for r in plan["facts"]};rid="COMM-"+need["category"]
            while rid in used:rid+="-1"
            if len(plan["facts"])>=8:
                optional=next((r for r in reversed(plan["facts"]) if r["category"]=="product" and r["priority"]=="supporting"),None)
                if optional:plan["facts"].remove(optional)
                else:raise ServiceError("策略检索任务过多，无法保留用户明确的价格优惠请求，请精简后重试")
            plan["facts"].append(dict(id=rid,direction_id=products[0]["direction_id"],category=need["category"],question=need["request"],conditions=["具体型号和配置","渠道与采集时间","适用资格与有效期；缺证则省略"],priority="supporting"))
    used={r["direction_id"] for r in plan["facts"]}
    result["message_strategy"]["priorities"]=[d for d in result["message_strategy"]["priorities"] if d["id"] in used]
    plan["images"]=[r for r in plan["images"] if r["direction_id"] in used]
    return result


def apply(t):
    """Decide per request. Priority never creates a commercial blocking rule."""
    p=t["package"];a=t["brief_analysis"];requests=a["retrieval_plan"]["facts"]
    by_request={r["id"]:r for r in requests};coverage=p.get("coverage",[])
    ids=[c["request_id"] for c in coverage]
    if len(ids)!=len(set(ids)) or set(ids)!=set(by_request):raise ServiceError("事实检索覆盖结果不完整，未继续规划")
    all_facts=copy.deepcopy(p["facts"]);fact_ids={f["id"] for f in all_facts}
    for c in coverage:
        if not set(c["fact_ids"])<=fact_ids:raise ServiceError("覆盖结果引用了不存在的事实")
        if c["status"] in ("supported","partial") and not c["fact_ids"]:raise ServiceError("检索任务没有事实依据却被标记为已支持")
        if c["status"]=="not_found" and c["fact_ids"]:raise ServiceError("未命中的检索任务不能引用事实")
    by_coverage={c["request_id"]:c for c in coverage}
    needs=a.get("commercial_requests",[])
    allowed={n["category"] for n in needs}
    # Older confirmed briefs have no positive-intent metadata. Their confirmed
    # commercial search requests are sufficient for omission/retention, not blocking.
    if not needs:allowed={request_kind(r) for r in requests if request_kind(r) in COMMERCIAL}
    turns=t.get("dialogue") or [dict(id="legacy_raw",kind="user",text=t.get("raw",""))]
    hard={kind:hard_rule(kind,turns) for kind in allowed}
    omissions={};gaps=[]
    def missing(rid,status,reason):
        r=by_request[rid]
        omissions[rid]=dict(request_id=rid,category=request_kind(r),status=status,reason=reason,original_priority=r["priority"],requirement_satisfied=False)
    for c in coverage:
        r=by_request[c["request_id"]];kind=request_kind(r)
        if c["status"]!="supported" and kind in COMMERCIAL:missing(r["id"],c["status"],c["reason"])
        elif kind=="product" and (c["status"]=="conflict" or (c["status"]=="partial" and usage.partial_is_blocked(t,r)) or (c["status"] not in ("supported","partial") and (r.get('guardrail','none')!='none' or usage.explicit_musts(t,r) or usage.complete_conditions_required(t,r)))):
            gaps.append(dict(request=r,coverage=c,blocking_reason="product_evidence"))
    conflicts=copy.deepcopy(p.get("conflicts",[]));active=[];sources={s["id"] for s in p["sources"]}
    for conflict in conflicts:
        if isinstance(conflict,str):active.append(conflict);continue
        if not set(conflict["source_ids"])<=sources or not set(conflict["request_ids"])<=set(by_request):raise ServiceError("冲突记录引用了不存在的来源或检索任务")
        if conflict["category"] in COMMERCIAL:
            linked=conflict["request_ids"] or [r["id"] for r in requests if request_kind(r)==conflict["category"]]
            if any(request_kind(by_request[rid])=="product" for rid in linked):raise ServiceError("商业冲突错误关联到产品事实，已停止")
            for rid in linked:missing(rid,"conflict",conflict["detail"])
        else:active.append(conflict["detail"])
    # A product card cannot stand in for price/offer evidence merely because the
    # extractor labelled the request "supported". Preserve unrelated valid items.
    kinds={}
    for f in all_facts:
        kind=f.get("category","product")
        if kind=="product":kind=commercial_kind(f["claim"]+" "+f.get("quote","")) or kind
        kinds[f["id"]]=kind
    valid_financial={}
    for c in coverage:
        kind=request_kind(by_request[c["request_id"]])
        if kind not in COMMERCIAL:continue
        matching={fid for fid in c["fact_ids"] if kinds[fid]==kind}
        valid_financial[c["request_id"]]=matching
        if c["status"]=="supported" and not matching:missing(c["request_id"],"not_usable","只返回其他类别事实，没有该项的独立商业依据")
    good=set();bad=set()
    for c in coverage:
        rid=c["request_id"]
        if request_kind(by_request[rid]) not in COMMERCIAL:continue
        if rid in omissions:
            if omissions[rid]["status"]=="conflict":bad.update(c["fact_ids"])
        else:good.update(valid_financial.get(rid,set()))
    good-=bad
    kept=[];removed=[];kept_kinds=set();boundaries=[]
    for f in all_facts:
        if usage.guidance_fact(f):boundaries.append(copy.deepcopy(f));continue
        kind=kinds[f["id"]]
        if kind in COMMERCIAL:
            if kind not in allowed or f["id"] not in good:removed.append(f["id"]);continue
            kept_kinds.add(kind)
        kept.append(f)
    kept_ids={f["id"] for f in kept}
    for c in coverage:
        r=by_request[c["request_id"]];kind=request_kind(r)
        if c["status"] in ("supported","partial") and not set(c["fact_ids"]) & kept_ids:
            if kind in COMMERCIAL:missing(r["id"],"not_usable","返回的资料不构成该项可引用的独立商业证据")
            elif r.get('guardrail','none')!='none' or usage.explicit_musts(t,r) or usage.complete_conditions_required(t,r):gaps.append(dict(request=r,coverage=c,blocking_reason="product_evidence",reason="该核心请求没有可用的独立产品事实"))
            # An optional product request citing only a removed policy card is omitted.
    blocked=[]
    for rid,decision in omissions.items():
        refs=hard.get(decision["category"],[])
        decision["on_missing"]="block" if refs else "omit"
        decision["blocking_evidence"]=refs
        if refs:
            blocked.append(decision)
            gaps.append(dict(request=by_request[rid],coverage=by_coverage[rid],blocking_reason="user_refuses_generation",blocking_evidence=refs))
    missing_kinds={d["category"] for d in omissions.values()}
    labels={"price":"价格","promotion":"优惠"};notices=[]
    if missing_kinds:
        label="及".join(labels[k] for k in ("price","promotion") if k in missing_kinds)
        if blocked:
            notices.append("未找到可用的"+label+"依据或资料存在冲突。用户明确要求缺少指定内容就不生成，已暂停；请补充依据或修改该条件。")
        else:
            lead=label+"资料存在冲突" if any(d["status"]=="conflict" for d in omissions.values()) else "未找到"+label+"依据"
            notices.append(lead+"，本次不包含这些内容，继续使用已有产品事实做规划；其他有依据的信息继续保留。")
    product_omissions=[dict(request_id=r['id'],reason=by_coverage[r['id']]['reason']) for r in requests if request_kind(r)=='product' and (by_coverage[r['id']]['status']=='not_found' or not set(by_coverage[r['id']]['fact_ids']) & kept_ids)]
    if product_omissions:notices.append('部分产品方向没有可引用依据，本次省略相关内容，继续使用已核验的产品事实。')
    if not any(kinds[f['id']]=='product' for f in kept):
        r=next((r for r in requests if request_kind(r)=='product'),None)
        if r and not any(g['request']['id']==r['id'] for g in gaps):gaps.append(dict(request=r,coverage=by_coverage[r['id']],blocking_reason='product_evidence',reason='没有可用于图文的产品事实'))
    p['omitted_product_requests']=product_omissions
    p["writing_boundaries"]=boundaries
    p["all_facts"]=all_facts;p["all_conflicts"]=conflicts;p["conflicts"]=active;p["facts"]=kept
    omitted_categories=sorted((COMMERCIAL-allowed) | (missing_kinds-kept_kinds))
    p["content_policy"]=dict(omit_commercial=not bool(kept_kinds),allowed_categories=sorted(kept_kinds),requested_categories=sorted(allowed),omitted_categories=omitted_categories,omitted_requests=list(omissions.values()),omitted_fact_ids=removed,blocked_requests=blocked,notices=notices,approval_required=False)
    return gaps
