"""Task-local prewriting checkpoints. Reuse data only while its inputs match."""
import hashlib,json
from . import brief_agent as ba

LABELS={"source_retrieval":"资料读取","fact_extraction":"事实提取","image_review":"图片核验","selling_points":"卖点生成"}

def fingerprint(t):
    keys=("product_id","platform","brief","brief_analysis","brief_confirmation","package","knowledge_source","knowledge_snapshot","execution_scope","manual_evidence","user_image_overrides")
    return hashlib.sha256(json.dumps({k:t.get(k) for k in keys},ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def start(t,stage):
    t["prewrite_checkpoint"]={"stage":stage,"state":"running","input_hash":fingerprint(t)}
    t["resume_status"]="needs_review"

def finish(t,failed=False):
    cp=t.get("prewrite_checkpoint")
    if cp and cp.get("state")=="running":cp.update(state="failed" if failed else "complete",input_hash=fingerprint(t))

def legacy_stage(t):
    # Only infer from the latest actual phase event, not an old planner run.
    for e in reversed(t.get("events",[])):
        text=e.get("text","")
        if text.startswith("处理已暂停："):continue
        if "正在按策略筛选图片" in text:return "image_review"
        if "正在生成候选卖点" in text:return "selling_points"
        if "已从" in text and "读取指定型号原文与图片" in text:return "fact_extraction"
        break
    return None

def info(t):
    if t.get("status")!="error" or t.get("plan") or t.get("document"):return None
    cp=t.get("prewrite_checkpoint") or {}
    stage=cp.get("stage") if cp.get("state") in ("running","failed") else None
    if not stage:stage=legacy_stage(t)
    if stage not in LABELS:return None
    reason=None
    try:ba.assert_confirmed(t)
    except ValueError:reason="需求已变更或尚未确认，请先确认当前策略。"
    if cp.get("input_hash") and cp["input_hash"]!=fingerprint(t):reason="需求、资料或取舍已变化，不能沿用这个检查点。"
    if stage!="source_retrieval" and (not t.get("package") or not t["package"].get("sources")):reason="缺少已保存原文，请重新读取资料。"
    return dict(stage=stage,label=LABELS[stage],resumable=reason is None,reason=reason)

def authorize(t):
    view=info(t)
    if not view or not view["resumable"]:raise ValueError((view or {}).get("reason") or "当前没有可恢复的资料处理步骤")
    t["prewrite_checkpoint"]={"stage":view["stage"],"state":"failed","input_hash":fingerprint(t)}
    return view["stage"]

def assert_current(t,stage):
    cp=t.get("prewrite_checkpoint") or {}
    ba.assert_confirmed(t)
    if stage not in LABELS or cp.get("stage")!=stage or cp.get("input_hash")!=fingerprint(t):
        raise ValueError("检查点输入已变化，请刷新任务后重试")
