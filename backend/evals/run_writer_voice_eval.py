"""One authorized screenshot rewrite; immutable source snapshot, no task DB writes.
Run: python -m backend.evals.run_writer_voice_eval --folder .local/... --task-id ID --version 26
"""
import argparse,asyncio,copy,hashlib,json,sqlite3,time
from pathlib import Path
from unittest.mock import patch
from backend import workflow as w,platform_writer as pw,content_planner as cp,clients,model_output as mo
from backend.clients import usage_capture
from backend.settings import ROOT,ASSETS,get_settings


def save(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')


def rows_hash():
    with sqlite3.connect((ROOT/'.local/tasks.sqlite3').as_uri()+'?mode=ro',uri=True) as db:
        return {tid:hashlib.sha256(raw.encode()).hexdigest() for tid,raw in db.execute('SELECT id,payload FROM tasks')}


def public_copy(doc):
    return '\n\n'.join([doc['title'],doc['lead'],*[p['text'] for p in doc['paragraphs']],doc['cta'],' '.join(doc['tags'])])


async def run(args):
    folder=Path(args.folder).resolve()
    if not folder.is_relative_to(ROOT/'.local'):raise ValueError('Private artifacts must stay in .local')
    if (folder/'manifest.json').exists():raise ValueError('Existing evaluation retained; no regeneration')
    folder.mkdir(parents=True,exist_ok=True)
    before_rows=rows_hash()
    with sqlite3.connect((ROOT/'.local/tasks.sqlite3').as_uri()+'?mode=ro',uri=True) as db:
        row=db.execute('SELECT payload FROM versions WHERE task_id=? AND version=?',(args.task_id,args.version)).fetchone()
    if not row:raise ValueError('Requested screenshot version not found')
    original=json.loads(row[0]);save(folder/'original_task.json',original)
    (folder/'before.md').write_text(public_copy(original['document']),encoding='utf-8')
    t=copy.deepcopy(original)
    if not pw.confirmed(t):raise ValueError('Screenshot selection confirmation does not match')
    t['plan'].update(phase='selection',sections=[])
    for key in ('writer_outline','writer_stage','repair_before','document','review','error'):t[key]=None
    t.update(id='isolated-writer-voice-'+args.task_id,writer_runs=[],events=[],status='writing')
    save(folder/'frozen_input.json',t)
    assets=[]
    for im in t['package']['images']:
        p=ASSETS/im['id']
        if not p.is_file():raise ValueError('Missing frozen image: '+im['id'])
        digest=hashlib.sha256(p.read_bytes()).hexdigest()
        if im.get('sha256') and digest!=im['sha256']:raise ValueError('Image bytes changed')
        assets.append(dict(id=im['id'],sha256=digest))
    files=['platform_writer.py','publication_rules.py','writer_skills.md','marketing_methods.py','workflow.py','planner_sources.json']
    manifest=dict(source_task_id=args.task_id,source_version=args.version,original_payload_sha256=hashlib.sha256(row[0].encode()).hexdigest(),
        source='saved screenshot original vs one real rewrite, not two newly generated arms',prior_attempt=args.prior_attempt,
        model_settings={k:get_settings()[k] for k in ('writer_model','reviewer_model','vision')},images=assets,
        source_hashes={name:hashlib.sha256((ROOT/'backend'/name).read_bytes()).hexdigest() for name in files},
        task_hashes_before=before_rows,isolated=True,method='one workflow; outline + draft + independent review; at most one existing repair and full re-review; existing structured JSON retry retained; no evaluator retries')
    save(folder/'manifest.json',manifest)
    calls=[];errors=[];start=time.perf_counter();requests=[]
    complete=clients.llm.complete
    async def captured(model,system,payload,schema,**kw):
        index=len(requests)+1
        requests.append(dict(index=index,schema=schema.__name__,model=model,system_sha256=hashlib.sha256(system.encode()).hexdigest()))
        save(folder/'requests'/f'{index:02d}_{schema.__name__}.json',dict(model=model,system=system,payload=payload,schema=schema.model_json_schema(),image_ids=[im['id'] for im in kw.get('images') or []]))
        return await complete(model,system,payload,schema,**kw)
    def event(task,note):
        task['events'].append(dict(at=round(time.perf_counter()-start,3),text=note))
        save(folder/'partial.json',task);print(note,flush=True)
        return task
    token=usage_capture.set(calls)
    try:
        with patch.object(w,'event',event),patch.object(clients.llm,'complete',captured),patch.object(mo,'DATA',folder),patch.object(w.db,'save',side_effect=AssertionError('Evaluation must never write task DB')):
            await w.write(t)
    except Exception as exc:
        errors.append(str(exc));t['status']='error';t['error']=str(exc)
    finally:usage_capture.reset(token)
    # Stage ContextVars capture Writer calls separately from independent review.
    combined=[c for r in t.get('writer_runs',[]) for c in r.get('calls',[])]+calls
    after_rows=rows_hash()
    result=dict(seconds=time.perf_counter()-start,errors=errors,task=t,requests=requests,calls=combined,http_calls=len(combined),
        total_tokens=sum(c.get('usage',{}).get('total_tokens',0) for c in combined),task_db_unchanged=before_rows==after_rows,
        deterministic_issues=w.deterministic_review(t) if t.get('document') else None,
        original_voice_issues=w.pub.style_issues(original['document'],voice=True))
    save(folder/'result.json',result)
    if t.get('document'):(folder/'after.md').write_text(public_copy(t['document']),encoding='utf-8')
    print(json.dumps({k:result[k] for k in ('seconds','errors','http_calls','total_tokens','task_db_unchanged')},ensure_ascii=False),flush=True)
    print('Final status:',t['status'],flush=True)


def main():
    p=argparse.ArgumentParser();p.add_argument('--folder',required=True);p.add_argument('--task-id',required=True);p.add_argument('--version',type=int,required=True);p.add_argument('--prior-attempt')
    asyncio.run(run(p.parse_args()))
if __name__=='__main__':main()
