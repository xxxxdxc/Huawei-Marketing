"""Reviewer scope claims and edit routing. No model, task or source mutations."""
import copy
import re
from . import evidence_resolution as er

VERSION = "review_scope_guard_v1"
GUIDANCE = """核验执行边界时，以review_scope中的实际prohibited_topics及其请求/方向绑定为唯一清单。
不得把普通PPT、柱状图、会议材料、使用场景扩展成其他禁写主题。例如用户只舍弃续航和电池容量，普通数据图表不构成越界；仅画面实际出现产品续航/电池宣传时才可报告。
每条声称“重新引入已舍弃主题”的issue必须填写scope_evidence：topic为清单中的key，request_ids/direction_ids对应实际取舍，field和section_id/image_id精确定位，quote逐字引用正文/图注或已核验图片visual_description中的实际证据。没有可定位证据，不得把推测写成违规。
“约L×W×H mm”中的约修饰整组尺寸，不应因每个数前未重复约而报错；数值、单位及必要配置仍须对照本段引用。图片背景中的任务内容不等于电脑具备该内容所述产品性能。不要把演示文稿里的通用数字当成本产品参数。
category=image的意见默认由配图编辑处理，repairable=false；不得让文字定向修订阶段换图、删图或增加图片。
"""


def context(t):
    scope = t.get("execution_scope") or {}
    analysis = t.get("brief_analysis") or {}
    requests = (analysis.get("retrieval_plan") or {}).get("facts", [])
    directions = (analysis.get("message_strategy") or {}).get("priorities", [])
    omitted = set(scope.get("omitted_request_ids", []))
    dropped = set(scope.get("omitted_direction_ids", []))
    result = []
    for topic in scope.get("prohibited_topics", []):
        if topic not in er.TOPICS:
            continue
        request_ids = [r["id"] for r in requests if r["id"] in omitted and topic in er.topics(r.get("question", ""))]
        direction_ids = [r["id"] for r in directions if r["id"] in dropped and topic in er.topics(r.get("direction", ""))]
        # Dropping a direction also authorizes exclusion of its related requests.
        request_ids += [r["id"] for r in requests if r.get("direction_id") in direction_ids]
        result.append(dict(topic=topic, label=er.TOPICS[topic][0],
                           request_ids=sorted(set(request_ids)), direction_ids=sorted(set(direction_ids))))
    return dict(version=VERSION, omitted_request_ids=sorted(omitted),
                omitted_direction_ids=sorted(dropped), prohibited_topics=result,
                ordinary_scene_is_not_product_claim=True)


def _source(t, evidence):
    d = t["document"]
    field = evidence.get("field")
    if field in ("title", "lead", "cta"):
        if evidence.get("section_id") is not None or evidence.get("image_id") is not None:
            return None
        return d[field]
    if field == "tags":
        if evidence.get("section_id") is not None or evidence.get("image_id") is not None:
            return None
        return " ".join(d["tags"])
    paragraphs = {p["section_id"]: p for p in d["paragraphs"]}
    paragraph = paragraphs.get(evidence.get("section_id"))
    if not paragraph:
        return None
    if field in ("paragraph", "caption"):
        if evidence.get("image_id") is not None:
            return None
        return paragraph["text" if field == "paragraph" else "caption"]
    if field == "image":
        iid = evidence.get("image_id")
        if not iid or paragraph["image_id"] != iid:
            return None
        image = next((im for im in t["package"]["images"] if im["id"] == iid), None)
        if image and image.get("visual_checked") is True:
            # Existing visual evidence, not model-written provenance or source filename.
            return image.get("visual_description", "")
    return None


SCOPE_WORDS = re.compile(r"舍弃|已放弃|禁写主题|禁止主题|omitted.{0,24}(?:topic|direction)|discarded.{0,24}topic", re.I)


DIMENSION_CHAIN = re.compile(r"约\s*(\d+(?:\.\d+)?)\s*[×xX*]\s*(\d+(?:\.\d+)?)\s*[×xX*]\s*(\d+(?:\.\d+)?)\s*(mm|cm)\b", re.I)

def dimension_approximation(t, issue):
    """Resolve only a mechanical 'missing 约' claim with the exact cited chain."""
    import unicodedata
    if issue["category"] != "fact" or issue.get("scope_evidence") is not None:
        return None
    detail = issue["detail"]
    if not ("约" in detail and re.search(r"尺寸|长度|宽度|厚度", detail) and re.search(r"修饰|覆盖|限定|近似", detail)):
        return None
    # Mixed objections remain for independent review; this rule never resolves them.
    if re.search(r"配置|版本|重量|电池|测试|型号|换算|计算|不一致|不符|错误|条件", detail):
        return None
    normal = lambda s: unicodedata.normalize("NFKC", s).replace("\u00a0", " ")
    def exact_number(value):
        whole, _, fraction = value.partition(".")
        fraction = fraction.rstrip("0")
        return (whole.lstrip("0") or "0") + ("." + fraction if fraction else "")
    canonical = lambda m: tuple(exact_number(m[i]) for i in (1, 2, 3)) + (m[4].lower(),)
    mentioned = list(DIMENSION_CHAIN.finditer(normal(detail)))
    if len(mentioned) != 1:
        return None
    target = canonical(mentioned[0])
    paragraphs = [p for p in t["document"]["paragraphs"] if
                  p["heading"] == issue["location"] or re.search(r"(?<![A-Za-z0-9])"+re.escape(p["section_id"])+r"(?![A-Za-z0-9])", issue["location"])]
    if len(paragraphs) != 1:
        return None
    paragraph = paragraphs[0]
    actual = list(DIMENSION_CHAIN.finditer(normal(paragraph["text"])))
    # One clearly scoped chain only; do not confuse a correct example with another claim.
    all_chains = re.findall(r"\d+(?:\.\d+)?\s*[×xX*]\s*\d+(?:\.\d+)?\s*[×xX*]\s*\d+(?:\.\d+)?\s*(?:mm|cm)\b", normal(paragraph["text"]), re.I)
    if len(actual) != 1 or len(all_chains) != 1 or canonical(actual[0]) != target:
        return None
    cited = [f["id"] for f in t["package"]["facts"] if f["id"] in paragraph["fact_ids"]
             and any(canonical(m) == target for m in DIMENSION_CHAIN.finditer(normal(f["quote"])))]
    if not cited:
        return None
    return dict(section_id=paragraph["section_id"], fact_ids=cited, quoted_chain=actual[0][0],
                reason="正文与本段所引原文均以“约”修饰同一整组尺寸；无需逐项重复近似限定。")


def check(t, issues):
    """Unproven scope opinions cannot disappear into an automatic approval."""
    accepted, audit, errors = [], [], []
    bindings = {b["topic"]: b for b in context(t)["prohibited_topics"]}
    for index, original in enumerate(issues):
        issue = copy.deepcopy(original)
        proof = dimension_approximation(t, issue)
        if proof:
            audit.append(dict(issue_index=index, accepted=False, resolved_by="dimension_approximation_prefix",
                              proof=proof, reasons=[proof["reason"]], original_issue=copy.deepcopy(original)))
            continue
        evidence = issue.get("scope_evidence")
        scope_claim = evidence is not None or bool(SCOPE_WORDS.search(issue["detail"]))
        reasons = []
        if scope_claim:
            if not isinstance(evidence, dict):
                reasons.append("没有提供对应舍弃请求和原文依据")
            else:
                binding = bindings.get(evidence.get("topic"))
                if not binding:
                    reasons.append("所指主题不在用户实际舍弃范围内")
                else:
                    refs, dirs = evidence.get("request_ids", []), evidence.get("direction_ids", [])
                    if (not refs and not dirs or set(refs) - set(binding["request_ids"])
                            or set(dirs) - set(binding["direction_ids"])):
                        reasons.append("请求或方向编号与该舍弃主题不匹配")
                source = _source(t, evidence)
                quote = evidence.get("quote", "")
                if not isinstance(quote, str) or not quote or source is None or quote not in source:
                    reasons.append("引用不能定位到当前正文、图注或已核验画面说明")
                if evidence.get("topic") not in er.topics(quote if isinstance(quote, str) else ""):
                    reasons.append("引用未提供所指舍弃主题的直接依据")
            if reasons:
                error = f"核验意见 {index + 1}（{issue.get('location') or '全文'}）需复核：" + "；".join(reasons) + "。原文和配图已保留，请重新核验。"
                errors.append(error)
                audit.append(dict(issue_index=index, accepted=False, reasons=reasons, original_issue=copy.deepcopy(original)))
                continue
            audit.append(dict(issue_index=index, accepted=True, original_issue=copy.deepcopy(original)))
        if issue["category"] == "image":
            issue["repairable"] = False
            audit.append(dict(issue_index=index, route="image_editor", original_repairable=original.get("repairable")))
        accepted.append(issue)
    return accepted, audit, errors
