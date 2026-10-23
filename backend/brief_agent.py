"""Campaign Plan integration: official reference + app adapter + fixed orchestration."""
import copy
import hashlib
import json
import re
from pathlib import Path
from . import schemas as S, storage as db, evidence_policy as ep
from .clients import llm, ServiceError
from .settings import get_settings

ROOT = Path(__file__).resolve().parent
PLATFORM_NAMES = {"xiaohongshu": "小红书", "wechat": "公众号", "moments": "门店朋友圈"}
PLATFORM_ALIASES = {"xiaohongshu": ("xiaohongshu", "小红书"), "wechat": ("wechat", "公众号", "微信公众号"), "moments": ("moments", "朋友圈", "门店朋友圈")}
SECTIONS = {
    "parsing": ["Campaign Overview", "Target Audience"],
    "audience": ["Target Audience", "Audience"],
    "strategy": ["Key Messages", "Message", "Channel Selection Criteria"],
}


def digest(analysis):
    return hashlib.sha256(json.dumps(analysis, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def normalize(value):
    value = value.lower().replace("huawei", "").replace("华为", "").replace("harmonyos", "鸿蒙")
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]", "", value)


def section(text, title):
    lines=text.splitlines(); start=None; level=0
    for i,line in enumerate(lines):
        m=re.match(r"^(#{1,6})\s+(.+)$",line)
        if m and re.sub(r"^\d+\.\s*", "", m[2].strip())==title:
            start=i;level=len(m[1]);break
    if start is None:raise ServiceError("官方 Campaign Plan 缺少预期章节，请核对固定版本")
    end=len(lines)
    for i in range(start+1,len(lines)):
        m=re.match(r"^(#{1,6})\s+",lines[i])
        if m and len(m[1])<=level:end=i;break
    return "\n".join(lines[start:end])


def instructions(stage):
    source=ROOT/"vendor/campaign-plan"
    meta=json.loads((source/"source.json").read_text(encoding="utf-8"))
    raw=(source/"SKILL.md").read_bytes()
    if hashlib.sha256(raw).hexdigest()!=meta["sha256"]:
        raise ServiceError("官方 Skill 文件与记录版本不一致，请先核对来源")
    adapter=(ROOT/"brief_adapter.md").read_text(encoding="utf-8")
    reference="\n\n".join(section(raw.decode("utf-8"), title) for title in SECTIONS[stage])
    text=("营销方法参考：Anthropic 官方 Campaign Plan（仅加载当前阶段适用章节）。\n"
          +reference+"\n\n应用适配规则优先于参考材料：\n"+section(adapter,"Common")+"\n"+section(adapter,stage.title()))
    version=dict(source_blob=meta["git_blob_sha"],source_sha256=meta["sha256"],adapter_sha256=hashlib.sha256(adapter.encode()).hexdigest(),sections=SECTIONS[stage])
    return text,version


def add_turn(t, text, **extra):
    turns=t.setdefault("dialogue",[])
    turn=dict(id="U"+str(1+sum(x.get("kind")=="user" for x in turns)),kind="user",text=text,at=db.now(),**extra)
    turns.append(turn)
    return turn


def dialogue(t, products):
    if not t.get("dialogue"):add_turn(t,t["raw"])
    if not t.get("initial_choices_recorded"):
        choices=[]
        selected=t.get("selected_product_id",t.get("product_id"))
        prod=next((p for p in products if p["id"]==selected),None)
        if prod:choices.append("已选择产品："+prod["name"])
        platform=t.get("selected_platform",t.get("platform"))
        if platform:choices.append("已选择发布平台："+PLATFORM_NAMES[platform])
        if choices:t["dialogue"].insert(0,dict(id="selection",kind="selection",text="；".join(choices),at=t["created_at"],product_id=selected,platform=platform))
        t["initial_choices_recorded"]=True
    return t["dialogue"]


def verify_provenance(requirements, turns):
    by_id={x["id"]:x["text"] for x in turns}
    for name,field in requirements.items():
        for ref in field["evidence"]:
            if ref["turn_id"] not in by_id or ref["quote"] not in by_id[ref["turn_id"]]:
                raise ServiceError("需求字段 "+name+" 的来源无法定位到用户原话，未采用分析结果")


def resolve_product(requirements, products, turns):
    q=requirements["product_query"]
    query=q["value"] or ""
    # A catalog suggestion alone is never authorization to select a product.
    evidence=" ".join(x["quote"] for x in q["evidence"])
    norm=normalize(query)
    matches=[]
    if norm and norm in normalize(evidence):
        qualifiers=[term for term in ("鸿蒙","windows") if term in norm]
        base=norm
        for term in qualifiers:base=base.replace(term+"版","").replace(term,"")
        full=[p for p in products if norm==normalize(p["name"]+p["category"])]
        matches=full or [p for p in products if base and base in normalize(p["name"])
                 and all(term in normalize(p["name"]+p["category"]) for term in qualifiers)]
        exact=[p for p in matches if normalize(p["name"])==base]
        refs={e["turn_id"] for e in q["evidence"]}
        selected=[turn.get("product_id") for turn in turns if turn["id"] in refs and turn.get("kind")=="selection"]
        answered=any(turn["id"] in refs and turn.get("question_field")=="product_model" for turn in turns)
        # A selector or an answer to an explicit model-choice question disambiguates
        # an exact catalog name. A bare family name in initial prose does not.
        preferred=[p for p in exact if p["id"] in selected]
        if preferred:matches=preferred
        elif answered and len(exact)==1:matches=exact
    candidates=[{k:p[k] for k in ("id","name","category")} for p in matches]
    state="resolved" if len(matches)==1 else "ambiguous" if len(matches)>1 else "unresolved"
    return dict(state=state,product_id=matches[0]["id"] if state=="resolved" else None,
                product_model=matches[0]["name"] if state=="resolved" else None,
                candidates=candidates or [{k:p[k] for k in ("id","name","category")} for p in products[:12]])


def question(field, text, reason, choices=None, kind="missing"):
    return dict(id="pending",field=field,kind=kind,question=text,reason=reason,choices=choices or [])


def normalize_parsing(parsed, products, turns):
    r=parsed["requirements"];resolution=resolve_product(r,products,turns)
    qs=copy.deepcopy(parsed["questions"])
    details={n["category"] for n in parsed.get("detail_requests",[])}
    def needed(q):
        if q["kind"]!="missing" or q["field"] in ("product_query","product_model","platform"):return True
        text=q["question"]
        if ep.commercial_kind(text):return False
        if re.search(r"门店|城市|地址|哪家店",text) and "address" not in details:return False
        if re.search(r"活动时间|活动日期|日程",text) and "schedule" not in details:return False
        if re.search(r"预约|体验安排",text) and "appointment" not in details:return False
        return True
    qs=[q for q in qs if needed(q)]
    if resolution["state"]=="resolved":
        previous=r["product_query"]
        exact=normalize(previous["value"] or "")==normalize(resolution["product_model"])
        r["product_model"]=dict(value=resolution["product_model"],source=previous["source"] if exact else "inferred",evidence=previous["evidence"],reason="按指定知识库产品目录归一型号；等待用户确认")
        qs=[q for q in qs if q["field"] not in ("product_model","product_query") or q["kind"]=="conflict"]
    else:
        r["product_model"]=dict(value=None,source="unknown",evidence=[],reason="型号尚未唯一匹配目录")
        qs=[q for q in qs if q["field"] not in ("product_model","product_query") or q["kind"]=="conflict"]
        qs.append(question("product_model","这次要推广哪个具体型号？请从目录候选中确认。","需要唯一型号才能读取对应产品事实与图片；本助手不替用户进行选购推荐。",[p["name"]+"（"+p["category"]+"）" for p in resolution["candidates"]]))
    p=r["platform"];value=p["value"] or "";evidence=" ".join(x["quote"] for x in p["evidence"]).lower()
    canonical=next((key for key,aliases in PLATFORM_ALIASES.items() if value.lower() in aliases),None)
    evidenced=canonical and any(alias in evidence for alias in PLATFORM_ALIASES[canonical])
    if canonical and p["source"]=="explicit" and evidenced:
        p["value"]=canonical
        qs=[q for q in qs if q["field"]!="platform" or q["kind"]=="conflict"]
    else:
        r["platform"]=dict(value=None,source="unknown",evidence=[],reason="发布平台需要用户明确选择")
        if not any(q["field"]=="platform" for q in qs):
            qs.append(question("platform","这篇图文先发布到哪个平台？","平台会影响写作形式和配图数量。",list(PLATFORM_NAMES.values())))
    if not r["target_audience"]["value"] and not r["scenario"]["value"] and not any(q["field"] in ("target_audience","scenario") for q in qs):
        qs.append(question("target_audience","主要写给谁看，或者希望用于什么场景？","受众和场景均未知，无法形成有针对性的营销策略。"))
    seen=set();unique=[]
    for q in qs:
        key=(q["field"],q["kind"])
        if key not in seen:
            q["id"]="Q"+str(len(unique)+1);unique.append(q);seen.add(key)
    return r,resolution,unique


def projection(a):
    r=a["requirements"];platform=r["platform"]["value"]
    if platform not in PLATFORM_NAMES:return None
    value=lambda key: r[key]["value"] or "待补充"
    m=a.get("message_strategy")
    return dict(audience=value("target_audience")[:300],scenario=value("scenario")[:300],platform=platform,
                goal=value("marketing_goal")[:300],purchase_stage=value("buying_stage")[:100],pain_points=r["customer_needs"]["value"],
                strategy=(m["theme"]+"；"+m["angle"]) if m else "等待补齐关键信息后制定策略",tone=m["tone"] if m else "待制定",
                emphasis=[p["direction"] for p in m["priorities"]] if m else [],questions=[q["question"] for q in a["questions"]])


def context(t):
    from . import evidence_resolution as er
    a=er.analysis_for_execution(t)
    if not a:return t["brief"]
    return {**(projection(a) or {}),**{k:a[k] for k in ("requirements","audience_insight","message_strategy","retrieval_plan")},"knowledge_source":t.get("knowledge_source","ima"),"commercial_requests":a.get("commercial_requests",[]),"content_policy":(t.get("package") or {}).get("content_policy"),"execution_scope":er.boundary(t)}


def assert_ready(t):
    a=t.get("brief_analysis")
    if not a:raise ValueError("请先完成需求分析")
    S.MarketingBrief.model_validate(a)
    if a["status"]!="ready" or a["questions"] or not all(a[k] for k in ("audience_insight","message_strategy","retrieval_plan")):
        raise ValueError("Brief 仍有关键缺项或冲突，请回答问题后重新分析")
    if a["product_resolution"]["state"]!="resolved" or a["product_resolution"]["product_id"]!=t["product_id"]:
        raise ValueError("请确认唯一的产品型号")
    if a["requirements"]["platform"]["value"]!=t["platform"] or t["platform"] not in PLATFORM_NAMES:
        raise ValueError("请确认发布平台")
    S.StrategyResult.model_validate({k:a[k] for k in ("message_strategy","retrieval_plan")})
    return a


def assert_confirmed(t):
    if t.get("brief_analysis"):
        a=assert_ready(t)
        if (t.get("brief_confirmation") or {}).get("analysis_hash")!=digest(a):
            raise ValueError("当前 Brief 尚未经用户确认，不能读取产品事实与图片")


def invalidate(t):
    for key in ("brief","brief_analysis","brief_confirmation","package","plan","document","review","execution_scope","selection_confirmation","writer_outline","writer_stage","platform_selection"):
        t[key]=None
    t["user_image_overrides"]={}


async def run(t, products, persist):
    turns=dialogue(t,products)
    async def stage(name,payload,schema):
        system,version=instructions(name)
        record=dict(id="R"+str(len(t.get("brief_runs",[]))+1),stage=name,model=get_settings()["writer_model"],version=version,input=copy.deepcopy(payload),started_at=db.now(),status="running",knowledge_snapshot=copy.deepcopy(t.get("knowledge_snapshot")))
        t.setdefault("brief_runs",[]).append(record)
        persist(t,"Brief：开始 "+name)
        try:
            result=await llm.complete(record["model"],system,payload,schema,role="writer")
            result=schema.model_validate(result).model_dump()
            record.update(output=result,completed_at=db.now(),status="completed")
            persist(t,"Brief：完成 "+name)
            return result
        except Exception:
            record.update(completed_at=db.now(),status="failed")
            persist(t,"Brief："+name+" 失败，保留本轮记录")
            raise
    parsed=await stage("parsing",dict(dialogue=turns,confirmed_history=t.get("last_confirmed_brief"),products=[{k:p[k] for k in ("id","name","category")} for p in products],supported_platforms=PLATFORM_NAMES),S.ParsingResult)
    verify_provenance(parsed["requirements"],turns)
    for need in parsed.get("commercial_requests",[])+parsed.get("detail_requests",[]):
        verify_provenance({"explicit_request":dict(evidence=need["evidence"])},turns)
    parsed["commercial_requests"]=ep.normalize_needs(parsed.get("commercial_requests",[]),turns)
    requirements,resolution,questions=normalize_parsing(parsed,products,turns)
    a=dict(schema_version="2",status="needs_resolution" if any(q["kind"]=="conflict" for q in questions) else "need_clarification" if questions else "ready",requirements=requirements,commercial_requests=parsed.get("commercial_requests",[]),product_resolution=resolution,questions=questions,audience_insight=None,message_strategy=None,retrieval_plan=None)
    t["brief_analysis"]=None;t["brief_confirmation"]=None;t["brief"]=None
    t["product_id"]=resolution["product_id"];t["platform"]=requirements["platform"]["value"]
    if questions:
        t["brief_analysis"]=a;t["brief"]=projection(a)
        t["status"]="needs_information";t["resume_status"]=t["status"];t["error"]=None
        persist(t,"需求存在冲突，等待确认" if a["status"]=="needs_resolution" else "已定位关键缺项，等待补充回答")
        return
    a["audience_insight"]=await stage("audience",dict(requirements=requirements),S.AudienceInsight)
    strategy=await stage("strategy",dict(requirements=requirements,audience_insight=a["audience_insight"],commercial_requests=a["commercial_requests"],platform=PLATFORM_NAMES[t["platform"]]),S.StrategyResult)
    strategy=S.StrategyResult.model_validate(ep.normalize_strategy(strategy,a["commercial_requests"])).model_dump()
    # Retain the compatibility field but never publish an upstream CTA draft.
    strategy['message_strategy']['cta_direction']=''
    a.update(strategy)
    t["brief_analysis"]=S.MarketingBrief.model_validate(a).model_dump()
    t["brief"]=projection(a);t["status"]="brief_ready";t["resume_status"]="brief_ready";t["error"]=None
    persist(t,"Brief 与证据检索计划完成，等待用户确认；尚未读取产品原文与图片")
