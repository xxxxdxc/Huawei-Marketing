"""One authorized full re-review of frozen task; no Writer calls or automatic repair."""
import asyncio,copy,json,sqlite3,hashlib,time
from pathlib import Path
from unittest.mock import patch
from backend import workflow as w,storage as db,model_output as mo
from backend.clients import usage_capture
from backend.settings import ROOT,get_settings

FOLDER=ROOT/'.local/numeric_review_evals/20261021_fold_recheck'

def save(name,value):
    (FOLDER/name).write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')

def hashes():
    with sqlite3.connect(db.DB.as_uri()+'?mode=ro',uri=True) as conn:
        return {tid:hashlib.sha256(raw.encode()).hexdigest() for tid,raw in conn.execute('SELECT id,payload FROM tasks')}

async def main():
    if (FOLDER/'result.json').exists():raise RuntimeError('Existing real re-review retained; no automatic rerun')
    frozen=json.loads((FOLDER/'before_task.json').read_text(encoding='utf-8'))
    t=db.get(frozen['id'])
    if t['version']!=frozen['version'] or db.digest(t)!=db.digest(frozen):raise RuntimeError('Task changed after freezing; stop without overwriting')
    if t['status'] in w.BUSY:raise RuntimeError('Task already running')
    original=copy.deepcopy(t['document']);expected=t['version'];before=hashes();calls=[];errors=[];start=time.perf_counter()
    def event(task,note):
        nonlocal expected
        if task['document']!=original:raise RuntimeError('Re-review must never modify document')
        task.setdefault('events',[]).append(dict(at=db.now(),text=note))
        task['events']=task['events'][-60:]
        result=db.save(task,note,expected=expected);expected=result['version']
        print(note,flush=True);return result
    token=usage_capture.set(calls)
    try:
        with patch.object(w,'event',event),patch.object(w.pw,'repair',side_effect=AssertionError('No repair authorized')),patch.object(mo,'DATA',FOLDER):
            await w.review(t,allow_repair=False)
    except Exception as exc:
        errors.append(str(exc))
        if db.get(t['id'])['version']==expected:
            t.update(status='error',resume_status='needs_review',error=str(exc)[:400])
            event(t,'重新核验未完成，原稿已保留：'+str(exc)[:200])
    finally:usage_capture.reset(token)
    current=db.get(t['id']);after=hashes()
    other_changes=[tid for tid in set(before)|set(after) if tid!=t['id'] and before.get(tid)!=after.get(tid)]
    result=dict(task_id=t['id'],before_version=frozen['version'],after_version=current['version'],model=get_settings()['reviewer_model'],
        seconds=time.perf_counter()-start,calls=calls,http_calls=len(calls),total_tokens=sum(c.get('usage',{}).get('total_tokens',0) for c in calls),
        errors=errors,status=current['status'],review=current.get('review'),document_unchanged=current['document']==original,
        other_task_changes=other_changes,task=current)
    save('result.json',result)
    print(json.dumps({k:result[k] for k in ('status','seconds','http_calls','total_tokens','document_unchanged','other_task_changes','errors')},ensure_ascii=False),flush=True)
    if result.get('review'):print(json.dumps(result['review']['issues'],ensure_ascii=False),flush=True)

if __name__=='__main__':asyncio.run(main())
