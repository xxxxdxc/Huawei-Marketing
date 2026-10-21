"""One authorized re-review, original document/assets immutable; no Writer calls."""
import asyncio
import copy
import hashlib
import json
import sqlite3
import time
from unittest.mock import patch
from backend import workflow as w, storage as db, model_output as mo
from backend.clients import usage_capture
from backend.settings import ROOT, get_settings

FOLDER = ROOT / ".local/review-scope-guard-20261021"

def hashes():
    with sqlite3.connect(db.DB.as_uri()+"?mode=ro", uri=True) as c:
        return {tid: hashlib.sha256(raw.encode()).hexdigest() for tid, raw in c.execute("SELECT id,payload FROM tasks")}

async def main():
    if (FOLDER/"result.json").exists():
        raise RuntimeError("Existing result retained; never automatically rerun")
    frozen = json.loads((FOLDER/("task-retry-before.json" if (FOLDER/"task-retry-before.json").exists() else "task-before.json")).read_text(encoding="utf-8"))
    t = db.get(frozen["id"])
    if t["version"] != frozen["version"] or db.digest(t) != db.digest(frozen):
        raise RuntimeError("Task changed since snapshot; do not overwrite")
    if t["status"] in w.BUSY:
        raise RuntimeError("Task already running")
    original = copy.deepcopy(t["document"])
    original_plan = copy.deepcopy(t["plan"])
    original_package = copy.deepcopy(t["package"])
    original_runs = copy.deepcopy(t.get("writer_runs", []))
    expected = t["version"]
    before = hashes()
    calls, errors = [], []
    start = time.perf_counter()
    def event(task, note):
        nonlocal expected
        (FOLDER/"review-checkpoint.json").write_text(json.dumps(task.get("review"),ensure_ascii=False,indent=2),encoding="utf-8")
        if (task["document"] != original or task["plan"] != original_plan
                or task["package"] != original_package or task.get("writer_runs", []) != original_runs):
            raise RuntimeError("Re-review must never change original document, plan, package or Writer records")
        task.setdefault("events", []).append(dict(at=db.now(), text=note))
        task["events"] = task["events"][-60:]
        result = db.save(task, note, expected=expected)
        expected = result["version"]
        print(note, flush=True)
        return result
    complete = w.llm.complete
    async def captured(*args, **kwargs):
        response = await complete(*args, **kwargs)
        (FOLDER/"model-response.json").write_text(json.dumps(response,ensure_ascii=False,indent=2),encoding="utf-8")
        (FOLDER/"model-usage.json").write_text(json.dumps(calls,ensure_ascii=False,indent=2),encoding="utf-8")
        return response
    token = usage_capture.set(calls)
    try:
        t["error"] = None
        with patch.object(w, "event", event), patch.object(w.llm, "complete", captured), patch.object(w.pw, "repair", side_effect=AssertionError("No Writer authorized")), patch.object(mo, "DATA", FOLDER):
            await w.review(t, allow_repair=False)
    except Exception as exc:
        errors.append(str(exc))
        if db.get(t["id"])["version"] == expected:
            t.update(status="error", resume_status="needs_review", error=str(exc)[:400])
            event(t, "重新核验未完成，原稿和配图已保留："+str(exc)[:160])
    finally:
        usage_capture.reset(token)
    current = db.get(t["id"])
    after = hashes()
    result = dict(task_id=t["id"], before_version=frozen["version"], after_version=current["version"],
                  model=get_settings()["reviewer_model"], seconds=time.perf_counter()-start,
                  http_calls=len(calls), total_tokens=sum(c.get("usage", {}).get("total_tokens", 0) for c in calls),
                  calls=calls, errors=errors, status=current["status"], review=current.get("review"),
                  document_unchanged=current["document"] == original, plan_unchanged=current["plan"] == original_plan,
                  package_unchanged=current["package"] == original_package,
                  writer_unchanged=current.get("writer_runs", []) == original_runs,
                  other_task_changes=[tid for tid in set(before)|set(after) if tid != t["id"] and before.get(tid) != after.get(tid)])
    (FOLDER/"result.json").write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({k:v for k,v in result.items() if k not in ("calls","review")},ensure_ascii=False),flush=True)
    if current.get("review"):
        print(json.dumps(dict(issues=current["review"]["issues"], validation_errors=current["review"].get("validation_errors")),ensure_ascii=False),flush=True)

if __name__ == "__main__":
    asyncio.run(main())
