"""Explicit platform-only migration; no model inference or core-strategy mutation."""
import copy
import re
from . import brief_agent as ba, storage as db

PLATFORMS = {"xiaohongshu": "小红书", "wechat": "微信公众号", "moments": "门店朋友圈"}
ALIASES = {"小红书": "xiaohongshu", "微信公众号": "wechat", "公众号": "wechat", "门店朋友圈": "moments", "朋友圈": "moments"}


def detect_platform(instruction):
    """Only recognize anchored, unambiguous commands. Mixed edits use normal Brief."""
    text = instruction.strip()
    match = re.fullmatch(r"(?:将)?(?:目标发布平台|目标平台|发布平台|平台)?(?:改为|改成|换成|切换为|切换到)(小红书|微信公众号|公众号|门店朋友圈|朋友圈)[。！!]?", text)
    if not match:
        match = re.fullmatch(r"将目标发布平台改为(小红书|微信公众号|公众号|门店朋友圈|朋友圈)，保留产品型号、人群和营销目标，重新应用该平台的内容与配图规则。", text)
    return ALIASES[match[1]] if match else None


def eligible(task):
    try:
        if not task.get("brief_analysis") or not task.get("brief_confirmation"):
            return False
        ba.assert_confirmed(task)
        return True
    except ValueError:
        return False


def apply(task, platform, instruction=None):
    if platform not in PLATFORMS:
        raise ValueError("不支持的目标平台")
    if not eligible(task):
        raise ValueError("请先完成并确认 Brief，再使用仅切换平台")
    if platform == task["platform"]:
        raise ValueError("目标平台与当前平台相同")
    old_platform = task["platform"]
    original_confirmation = copy.deepcopy(task["brief_confirmation"])
    original_hash = ba.digest(task["brief_analysis"])
    text = instruction or "将目标发布平台改为" + PLATFORMS[platform]
    ba.add_turn(task, text, change_kind="platform_only")
    turn = task["dialogue"][-1]
    analysis = copy.deepcopy(task["brief_analysis"])
    analysis["requirements"]["platform"] = dict(value=platform, source="explicit",
        evidence=[dict(turn_id=turn["id"], quote=text)], reason="用户明确授权仅修改发布平台")
    task["platform"] = platform
    task["selected_platform"] = platform
    task["brief_analysis"] = analysis
    task["brief"] = ba.projection(analysis)
    new_hash = ba.digest(analysis)
    from . import evidence_resolution as er
    er.rebind_platform(task,original_hash,new_hash,turn["id"])
    change = dict(from_platform=old_platform, to_platform=platform, turn_id=turn["id"],
        original_analysis_hash=original_hash, analysis_hash=new_hash, at=db.now(),
        authorized_version=task["version"] + 1, original_confirmation=original_confirmation)
    task.setdefault("platform_changes", []).append(change)
    task["brief_confirmation"] = dict(analysis_hash=new_hash, at=change["at"],
        authorized_version=change["authorized_version"], authorization="platform_only",
        original_analysis_hash=original_hash)
    task["last_confirmed_brief"] = copy.deepcopy(analysis)
    task["latest_instruction"] = text
    task["raw"] += "\n用户新增修改要求：" + text
    for key in ("plan", "document", "review", "repair_before"):
        task[key] = None
    task["user_image_overrides"] = {}
    task["error"] = None
    ba.assert_confirmed(task)
