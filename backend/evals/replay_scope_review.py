"""Re-evaluate a captured real review with deterministic rules; zero provider calls."""
import asyncio
import copy
import hashlib
import json
import sqlite3
from unittest.mock import patch
from backend import workflow as w, storage as db, schemas as S
from backend.settings import ROOT

FOLDER=ROOT/".local/review-scope-guard-20261021"

async def main():
    if (FOLDER/"replay-result.json").exists():
        raise RuntimeError("Keep existing replay result; no repeated saves")
    source=json.loads((FOLDER/"result.json").read_text(encoding="utf-8"))
    raw=json.loads((FOLDER/"model-response.json").read_text(encoding="utf-8"))
    S.Review.model_validate(raw)
    t=db.get(source["task_id"])
    if t["version"]!=source["after_version"] or db.digest(t)!=source["review"]["document_hash"]:
        raise RuntimeError("Task changed after captured review; do not overwrite")
    if raw["issues"]!=source["review"]["raw_model_issues"]:
        raise RuntimeError("Captured response does not match the saved review")
    before={k:copy.deepcopy(t.get(k)) for k in ("document","plan","package","writer_runs")}
    with sqlite3.connect(db.DB.as_uri()+"?mode=ro",uri=True) as c:
        before_hashes={id:hashlib.sha256(payload.encode()).hexdigest() for id,payload in c.execute("SELECT id,payload FROM tasks")}
    expected=t["version"]
    def event(task,note):
        nonlocal expected
        if any(task.get(k)!=v for k,v in before.items()):
            raise RuntimeError("Replay must not change original content or Writer records")
        if task.get("review"):
            task["review"]["model_response_replayed"]=True
            task["review"]["source_model_checked_at"]=source["review"]["checked_at"]
            task["review"]["source_response_sha256"]=hashlib.sha256((FOLDER/"model-response.json").read_bytes()).hexdigest()
            note+="（复用已保存的模型响应，程序复核未增加模型调用）"
        task.setdefault("events",[]).append(dict(at=db.now(),text=note))
        task["events"]=task["events"][-60:]
        result=db.save(task,note,expected=expected);expected=result["version"]
        return result
    replay_count=0
    async def replay(model,system,payload,schema,**kwargs):
        nonlocal replay_count
        if schema is not S.Review or payload["document"]!=before["document"] or kwargs.get("role")!="reviewer":
            raise RuntimeError("Only the original Reviewer response may be replayed")
        replay_count+=1
        return copy.deepcopy(raw)
    with patch.object(w,"event",event),patch.object(w.llm,"complete",replay),patch.object(w.pw,"repair",side_effect=AssertionError("No Writer authorized")):
        await w.review(t,allow_repair=False)
    current=db.get(t["id"])
    with sqlite3.connect(db.DB.as_uri()+"?mode=ro",uri=True) as c:
        after_hashes={id:hashlib.sha256(payload.encode()).hexdigest() for id,payload in c.execute("SELECT id,payload FROM tasks")}
    result=dict(task_id=t["id"],before_version=source["after_version"],after_version=current["version"],
                status=current["status"],review=current["review"],source_model=source["model"],
                http_calls=0,replayed_responses=replay_count,
                original_content_unchanged=all(current.get(k)==v for k,v in before.items()),
                other_task_changes=[id for id in set(before_hashes)|set(after_hashes) if id!=t["id"] and before_hashes.get(id)!=after_hashes.get(id)])
    (FOLDER/"replay-result.json").write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({k:v for k,v in result.items() if k!="review"},ensure_ascii=False))
    print(json.dumps(dict(issues=result["review"]["issues"],validation_errors=result["review"]["validation_errors"],audit=result["review"]["scope_audit"]),ensure_ascii=False))

if __name__=="__main__":
    asyncio.run(main())
