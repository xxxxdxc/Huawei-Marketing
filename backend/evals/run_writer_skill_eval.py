"""Six explicitly authorized real Writer outputs on frozen evidence, no task DB writes.
Usage: python -m backend.evals.run_writer_skill_eval prepare|before|after --folder PATH
"""
import argparse,asyncio,copy,hashlib,importlib.util,json,shutil,time
from pathlib import Path
from unittest.mock import patch
from backend import workflow as w,platform_writer as pw,content_planner as cp,clients,model_output as mo
from backend.settings import get_settings
from backend.clients import usage_capture

ROOT=Path(__file__).resolve().parents[2]

def save(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def prepare(folder):
    if (folder/'manifest.json').exists():raise ValueError('Frozen evaluation already exists')
    materials=ROOT/'.local/planner_evals/materials/ima_fresh_20261021_055235'
    previous=ROOT/'.local/planner_evals/runs/20261021_v2'
    old_manifest=json.loads((previous/'manifest.json').read_text(encoding='utf-8'))
    folder.mkdir(parents=True,exist_ok=True)
    for name in ('workflow.py','platform_writer.py','marketing_methods.py'):
        shutil.copyfile(ROOT/'backend'/name,folder/('baseline_'+name))
    save(folder/'baseline_methods.json',dict(writer_method=pw.WRITER_METHOD,method_guard=pw.METHOD_GUARD))
    cases=[]
    for cid,platform,chosen in [('CP01','moments',['C1']),('CP06','wechat',['C01','C02']),('CP11','xiaohongshu',['C01','C02'])]:
        record=json.loads((previous/(cid+'_after.json')).read_text(encoding='utf-8'))
        original=record['plan'];pid=original['product_id']
        pack=json.loads((materials/(pid+'_verified.json')).read_text(encoding='utf-8'))
        persona=next(c['brief'] for c in old_manifest['cases'] if c['id']==cid)
        brief=persona | dict(platform=platform,tone='自然、具体',emphasis=[],questions=[])
        t=dict(id='writer-eval-'+cid,product_id=pid,platform=platform,knowledge_source='ima',
            status='writing',resume_status='plan_ready',version=1,brief=brief,package=pack,events=[],document=None,review=None,user_image_overrides={})
        raw=[];selected=set(chosen)
        for candidate in original['planning_analysis']['candidates']:
            c={k:copy.deepcopy(v) for k,v in candidate.items() if k in cp.P.SellingPoint.model_fields}
            c.setdefault('recommendation','recommended' if c['id'] in selected else 'alternative')
            c.setdefault('recommendation_reason','固定评测复用历史模型候选，集合在运行前锁定')
            raw.append(c)
        ranked=cp.rank_candidates(t,dict(product_id=pid,candidates=raw))
        t['plan']=cp.selection_plan(t,ranked,chosen)
        t['selection_confirmation']=dict(selection_hash=cp.selection_fingerprint(t['plan']),authorization='isolated_evaluation_authorized')
        images=[]
        for im in pack['images']:
            source=materials/'assets'/im['id']
            if not source.is_file():source=ROOT/'.local/assets'/im['id']
            if not source.is_file():raise ValueError('Missing verified image')
            if im.get('sha256') and sha(source)!=im['sha256']:raise ValueError('Changed image bytes')
            target=folder/'assets'/im['id'];target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target)
            images.append(dict(id=im['id'],sha256=sha(source)))
        target=folder/'inputs'/(cid+'.json');save(target,t)
        cases.append(dict(id=cid,platform=platform,product_id=pid,selected_point_ids=chosen,input_sha256=sha(target),images=images,
            candidate_source=str((previous/(cid+'_after.json')).relative_to(ROOT)),candidate_source_sha256=sha(previous/(cid+'_after.json'))))
    conf=get_settings()
    save(folder/'manifest.json',dict(cases=cases,models={k:conf[k] for k in ('writer_model','reviewer_model')},vision=conf['vision'],
        baseline_source_hashes={name:sha(folder/('baseline_'+name)) for name in ('workflow.py','platform_writer.py','marketing_methods.py')},
        method='3 platform cases x before/after once; same frozen input within each pair; no cherry-picking; maximum one existing repair then re-review; provider JSON retries retained and counted',
        rubric={'organization':'main line, concrete progression, no list of disconnected features','naturalness':'specific reader language and platform-appropriate prose','redundancy':'no repeated conclusions or CTA','evidence':'all actual claims and necessary conditions, not only IDs','image_relation':'visible content supports associated paragraph, not parameter proof'},
        quality_assessment='agent close reading with excerpts, distinct from program checks and independent factual reviewer; one run per arm cannot establish stability',
        shared_context='Existing verified ima snapshots; no fresh facts or model candidate generation',isolated=True))
    print('Frozen 3 inputs and baseline; no model calls during preparation',flush=True)


def load_baseline(folder):
    def module(name,path):
        spec=importlib.util.spec_from_file_location('backend.'+name,path)
        value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value
    baseline=module('_frozen_writer',folder/'baseline_platform_writer.py')
    methods=json.loads((folder/'baseline_methods.json').read_text(encoding='utf-8'))
    baseline.WRITER_METHOD=methods['writer_method'];baseline.METHOD_GUARD=methods['method_guard']
    flow=module('_frozen_workflow',folder/'baseline_workflow.py');flow.pw=baseline
    return flow


async def run(folder,arm,recover_structure=False):
    manifest=json.loads((folder/'manifest.json').read_text(encoding='utf-8'))
    if {k:get_settings()[k] for k in ('writer_model','reviewer_model')}!=manifest['models']:raise ValueError('Models changed after freezing')
    flow=load_baseline(folder) if arm=='before' else w
    for case in manifest['cases']:
        out=folder/(case['id']+'_'+arm+'.json')
        previous=json.loads(out.read_text(encoding='utf-8')) if out.exists() else None
        structure_only=bool(recover_structure and previous and previous['errors'] and not previous['task'].get('document') and arm=='after')
        if recover_structure and not structure_only:continue
        if structure_only:
            out=folder/(case['id']+'_'+arm+'_recovery.json')
            if out.exists():
                supplement=json.loads(out.read_text(encoding='utf-8'))
                if supplement.get('errors') and supplement['task'].get('document') and not supplement.get('review_retry') and any(word in ' '.join(supplement['errors']) for word in ('524','超时','网络')):
                    previous=supplement;structure_only=False
                else:
                    print(case['id'],'supplement exists; not regenerated',flush=True);continue
        if previous and not previous.get('errors'):
            print(case['id'],arm,'exists; not regenerated',flush=True);continue
        review_only=bool(previous and previous['task'].get('document') and any(word in ' '.join(previous['errors']) for word in ('524','超时','网络')) and not previous.get('review_retry'))
        if previous and not review_only and not structure_only:
            print(case['id'],arm,'failed result retained; not regenerated',flush=True);continue
        path=folder/'inputs'/(case['id']+'.json')
        if sha(path)!=case['input_sha256']:raise ValueError('Frozen input changed')
        t=copy.deepcopy(previous['task']) if review_only or structure_only else json.loads(path.read_text(encoding='utf-8'))
        prior_calls=previous['calls'] if review_only or structure_only else []
        old_run_count=len(t.get('writer_runs',[])) if review_only or structure_only else 0
        calls=[];errors=[];start=time.perf_counter()
        def event(task,note):
            task['events'].append(dict(at=round(time.perf_counter()-start,3),text=note))
            save(folder/(case['id']+'_'+arm+'_partial.json'),task)
            print(case['id'],arm,note,flush=True)
            return task
        token=usage_capture.set(calls)
        try:
            with patch.object(w,'event',event),patch.object(flow,'event',event),patch.object(clients,'ASSETS',folder/'assets'),patch.object(mo,'DATA',folder):
                if review_only:
                    t['error']=None
                    await flow.review(t,allow_repair=not bool(t.get('repair_before')))
                else:await flow.write(t)
        except Exception as exc:
            errors.append(str(exc));t['status']='error';t['error']=str(exc)
        finally:usage_capture.reset(token)
        # Stage capture context is separate; merge original usage records without duplicating by schema/role.
        stage_calls=[c for r in t.get('writer_runs',[])[old_run_count:] for c in r.get('calls',[])]
        combined=prior_calls+stage_calls+calls
        result=dict(case_id=case['id'],arm=arm,input_sha256=case['input_sha256'],seconds=(previous['seconds'] if review_only or structure_only else 0)+time.perf_counter()-start,
            prior_errors=(previous.get('prior_errors',[])+previous['errors']) if review_only or structure_only else [],review_retry=review_only,structure_retry=structure_only or bool(previous and previous.get("structure_retry")),errors=errors,task=t,calls=combined,http_calls=len(combined),total_tokens=sum(c.get('usage',{}).get('total_tokens',0) for c in combined))
        if t.get('document'):
            result['first_document']=t.get('repair_before') or t['document']
            result['deterministic_issues']=w.deterministic_review(t)
        save(out,result)
        print(case['id'],arm,t['status'],'seconds',round(result['seconds'],2),'http',len(combined),'tokens',result['total_tokens'],flush=True)
        if errors and any(x in errors[-1] for x in ('HTTP 401','HTTP 403','API 预扣额度不足','HTTP 402')):raise RuntimeError('Stop on provider access/quota failure')


def main():
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['prepare','before','after']);p.add_argument('--folder',required=True);p.add_argument('--recover-structure',action='store_true')
    args=p.parse_args();folder=Path(args.folder).resolve()
    if not folder.is_relative_to(ROOT/'.local'):raise ValueError('Evaluation artifacts must stay inside project .local')
    if args.mode=='prepare':prepare(folder)
    else:asyncio.run(run(folder,args.mode,args.recover_structure))
if __name__=='__main__':main()
