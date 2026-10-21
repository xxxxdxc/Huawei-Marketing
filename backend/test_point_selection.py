"""Selection contract/API tests: isolated synthetic evidence, no paid models."""
import asyncio,copy,unittest
from unittest.mock import AsyncMock,patch
from fastapi.testclient import TestClient
from backend.test_workflow import prepared
from backend import workflow as w,content_planner as cp,storage as db,planner_schemas as P
from backend.clients import ServiceError
from backend.content_layout import default_position
from backend.main import app

def batch(t,selected=('C1',)):
    candidates=[]
    for cid,fid,value in (('C1','F01',3),('C2','F02',4)):
        candidates.append(dict(id=cid,direction='测试方向'+cid,audience_need='测试需求'+cid,
            fact_ids=[fid],image_ids=[t['package']['images'][0]['id']],conditions=[],request_ids=[],mandatory_need_ids=[n['id'] for n in cp.mandatory_needs(t)] if cid=='C1' else [],
            recommendation='recommended' if cid in selected else 'alternative',
            recommendation_reason='依据需求选择，非机械TopK',scores={k:dict(value=value,reason='隔离判断') for k in cp.WEIGHTS}))
    return dict(product_id=t['product_id'],candidates=candidates)

def compose(payload):
    selected=payload['selected_point_ids'];platform=payload['brief']['platform']
    n=max(len(selected),w.PLATFORMS[platform]['min_images']);images=payload['images']
    candidates={c['id']:c for c in payload['ranked_candidates']}
    budget={'moments':100,'wechat':700,'xiaohongshu':400}[platform]
    sections=[]
    for i in range(n):
        cid=selected[i%len(selected)];image=images[i]['id'] if i<len(images) else None
        sections.append(dict(id=f'P{i+1}',heading='内部'+str(i),purpose='目标'+str(i),reader_question='问题'+str(i),
            role='argument',point_ids=[cid],fact_ids=candidates[cid]['fact_ids'],image_id=image,
            image_reason='测试画面',image_position=default_position(platform,image,i+1),
            target_chars=budget//n+(budget%n if i==0 else 0)))
    return dict(schema_version='2',product_id=payload['product_id'],angle='测试切入',title_direction='题目方向',
        composition_rationale='先回应读者问题，再按证据展开',selected_point_ids=list(selected),sections=sections,cta='咨询方向')

def task(platform='moments',selected=('C1',),canonical=False,legacy=True):
    if canonical:
        from backend.test_platform_change import task as canonical_task
        t=canonical_task(images=1)
        from backend import brief_agent as ba
        t['dialogue'].append(dict(id='U2',kind='user',text='必须包含携带重量'))
        t['brief_analysis']['requirements']['user_constraints']=dict(value=['必须包含携带重量'],source='explicit',reason='用户明确要求',evidence=[dict(turn_id='U2',quote='必须包含携带重量')])
        t['brief']=ba.projection(t['brief_analysis'])
        t['brief_confirmation']['analysis_hash']=ba.digest(t['brief_analysis'])
    else:t=prepared()
    t['platform']=platform;t['brief']['platform']=platform
    n=w.PLATFORMS[platform]['min_images']
    if not canonical:t['package']['images']=[dict(id=chr(97+i)*20,model_verified=True,visual_checked=True,usable=True) for i in range(n)]
    t['package']['sources'].append(dict(id='S2',title='测试原文',text='测试型号的屏幕事实只用于隔离测试。',path='fixture'))
    t['package']['facts'].append(dict(id='F02',category='product',claim='测试屏幕事实',quote='测试型号的屏幕事实只用于隔离测试。',source_id='S2',conditions='测试版本'))
    async def fake(model,system,payload,schema,**kwargs):
        if schema is P.CandidateBatch:return batch(t,selected)
        if schema is P.ContentPlanDraft:return compose(payload)
        raise AssertionError('Unexpected role or real model call')
    with patch.object(cp.llm,'complete',AsyncMock(side_effect=fake)):
        t['plan']=asyncio.run(cp.generate(t,w.PLATFORMS[platform],w.BASE))
    if legacy:
        old=compose(cp.shared_context(t,w.PLATFORMS[platform]) | dict(selected_point_ids=t['plan']['selected_point_ids'],ranked_candidates=t['plan']['planning_analysis']['candidates']))
        old['planning_analysis']=t['plan']['planning_analysis'];t['plan']=old
    t.update(status='plan_ready' ,resume_status='plan_ready',document=None,review=None,error=None)
    return db.save(t,'隔离候选已就绪')

class SelectionTests(unittest.TestCase):
    def setUp(self):
        self.client=TestClient(app);self.client.__enter__()
    def tearDown(self):self.client.__exit__(None,None,None)
    def post(self,t,selected,**extra):
        return self.client.post(f"/api/tasks/{t['id']}/replan-points",json=dict(version=t['version'],selected_point_ids=selected,replace_current_plan=True,**extra))
    def test_new_plans_have_no_forced_framework(self):
        t=task();self.assertNotIn('narrative',t['plan']);self.assertTrue(t['plan']['composition_rationale'])
        self.assertNotIn('narrative',P.ContentPlanDraft.model_fields)
        self.assertEqual(t['plan']['planning_analysis']['method_sources'],['content-strategy'])
    def test_ranking_does_not_implicitly_choose_top_k(self):
        t=task();cs=t['plan']['planning_analysis']['candidates']
        self.assertEqual(cs[0]['id'],'C2');self.assertEqual(cs[0]['recommendation'],'alternative')
        self.assertEqual(t['plan']['selected_point_ids'],['C1'])
    def test_moments_count_is_advice_not_a_hard_lock(self):
        t=task(selected=('C1','C2'));w.validate_plan(t,t['plan'])
        self.assertEqual(set(t['plan']['selected_point_ids']),{'C1','C2'})
    def test_success_reuses_candidates_without_model_calls(self):
        t=task();old=copy.deepcopy(t['plan']);package=copy.deepcopy(t['package'])
        async def fake(model,system,payload,schema,**kw):
            self.assertIs(schema,P.ContentPlanDraft);return compose(payload)
        with patch.object(w.llm,'complete',AsyncMock(side_effect=fake)) as model,patch.object(w.ima,'retrieve_for_task',AsyncMock()) as retrieval,patch.object(w,'analyze',AsyncMock()) as brief:
            r=self.post(t,['C2'])
        self.assertEqual(r.status_code,202);self.assertEqual(model.await_count,0);retrieval.assert_not_awaited();brief.assert_not_awaited()
        u=db.get(t['id']);self.assertEqual(u['status'],'plan_ready');self.assertIsNone(u['document'])
        self.assertEqual(u['plan']['selected_point_ids'],['C2']);self.assertEqual(u['package'],package)
        self.assertEqual(db.snapshot(t['id'],t['version'])['plan'],old)
        self.assertEqual(u['plan']['planning_analysis']['candidates'],old['planning_analysis']['candidates'])
    def test_stale_version_rejected_before_model(self):
        t=task()
        with patch.object(w.llm,'complete',AsyncMock()) as model:
            r=self.client.post(f"/api/tasks/{t['id']}/replan-points",json=dict(version=t['version']-1,selected_point_ids=['C2'],replace_current_plan=True))
        self.assertEqual(r.status_code,409);model.assert_not_called()
    def test_replacement_requires_literal_human_boolean(self):
        t=task()
        for value in (False,1,'true',None):
            with self.subTest(value=value):
                with patch.object(w.llm,'complete',AsyncMock()) as model:
                    r=self.client.post(f"/api/tasks/{t['id']}/replan-points",json=dict(version=t['version'],selected_point_ids=['C2'],replace_current_plan=value))
                self.assertEqual(r.status_code,422);model.assert_not_called()
        r=self.client.post(f"/api/tasks/{t['id']}/replan-points",json=dict(version=t['version'],selected_point_ids=['C2']))
        self.assertEqual(r.status_code,422)
    def test_invalid_selection_never_calls_model_or_mutates(self):
        t=task();before=db.get(t['id'])
        for selected,status in (([],422),(['C1','C1'],400),(['unknown'],400),([str(i) for i in range(9)],422)):
            with patch.object(w.llm,'complete',AsyncMock()) as model:r=self.post(t,selected)
            self.assertEqual(r.status_code,status);model.assert_not_called()
            self.assertEqual(db.get(t['id']),before)
    def test_busy_task_cannot_replan(self):
        t=task();t['status']='planning';db.save(t,'隔离运行中')
        with patch.object(w.llm,'complete',AsyncMock()) as model:r=self.post(t,['C2'])
        self.assertEqual(r.status_code,400);model.assert_not_called()
        t['status']='plan_ready';db.save(t,'结束隔离状态')
    def test_missing_candidate_provenance_rejected(self):
        t=task();t['plan']['planning_analysis'].pop('origin');db.save(t,'无候选来源')
        with patch.object(w.llm,'complete',AsyncMock()) as model:r=self.post(t,['C2'])
        self.assertEqual(r.status_code,400);model.assert_not_called()
    def test_changed_evidence_context_invalidates_candidates(self):
        t=task();t['package']['facts'][1]['conditions']='已改变配置';db.save(t,'配置变化')
        with patch.object(w.llm,'complete',AsyncMock()) as model:r=self.post(t,['C2'])
        self.assertEqual(r.status_code,400);model.assert_not_called()
    def failed(self,t,reply=None,error=None):
        old=copy.deepcopy(t['plan'])
        async def fake(model,system,payload,schema,**kwargs):
            if error:raise error
            return reply(payload)
        with patch.object(w.llm,'complete',AsyncMock(side_effect=fake)):r=self.post(t,['C2'])
        self.assertEqual(r.status_code,202);u=db.get(t['id'])
        self.assertEqual(u['status'],'plan_ready');self.assertTrue(u['error']);self.assertEqual(u['plan'],old)
        self.assertIsNone(u['pending_point_replan']);self.assertEqual(u['point_replans'][-1]['status'],'failed')
        return u
    def test_selection_save_ignores_unused_model_reply(self):
        t=task()
        with patch.object(w.llm,'complete',AsyncMock(side_effect=AssertionError('No inference when saving'))) as model:
            r=self.post(t,['C2'])
        model.assert_not_called();self.assertEqual(r.status_code,202)
        u=db.get(t['id']);self.assertEqual(u['plan']['sections'],[])
        self.assertEqual(u['plan']['selected_point_ids'],['C2'])
    def test_selection_save_failure_preserves_manual_legacy_edits(self):
        t=task();t['plan']['sections'][0]['heading']='工作人员已编辑';db.save(t,'已编辑')
        with patch.object(cp,'generate',AsyncMock(side_effect=ServiceError('fixture failure'))):
            r=self.post(t,['C2'])
        self.assertEqual(r.status_code,202);u=db.get(t['id'])
        self.assertEqual(u['plan'],t['plan']);self.assertTrue(u['error'])
    def test_interrupted_request_recovers_without_replanning(self):
        t=task();old=copy.deepcopy(t['plan']);t['status']='planning'
        t['pending_point_replan']=dict(selected_point_ids=['C2']);t['point_replans']=[dict(status='running')]
        db.save(t,'中断请求')
        with patch.object(w.llm,'complete',AsyncMock()) as model:self.assertTrue(w.recover_point_replan(t))
        model.assert_not_called();u=db.get(t['id']);self.assertEqual(u['plan'],old)
        self.assertEqual(u['status'],'plan_ready');self.assertEqual(u['point_replans'][-1]['status'],'interrupted')
    def test_historical_narrative_read_projection_does_not_migrate_database(self):
        t=task();p=t['plan'];p.pop('composition_rationale');p['narrative']=dict(framework='scene_story',reason='旧理由',ordering_rationale='旧排序')
        p['planning_analysis'].pop('candidate_context_hash')
        for c in p['planning_analysis']['candidates']:
            c.pop('recommendation');c.pop('recommendation_reason')
        db.save(t,'历史候选');before=db.get(t['id'])
        r=self.client.get(f"/api/tasks/{t['id']}")
        self.assertEqual(r.json()['plan']['composition_rationale'],'旧排序')
        self.assertEqual(r.json()['plan']['planning_analysis']['candidates'][0]['recommendation'],'alternative')
        self.assertEqual(db.get(t['id']),before)
        self.assertEqual(len(cp.trusted_candidates(t)),2)
    def test_manual_edit_preserves_point_associations(self):
        t=task();p=copy.deepcopy(t['plan']);p['sections'][0].update(heading='新提示',purpose='新目标')
        r=self.client.put(f"/api/tasks/{t['id']}/plan",json=dict(version=t['version'],plan=p))
        self.assertEqual(r.status_code,200);u=db.get(t['id'])
        self.assertEqual(u['plan']['sections'][0]['point_ids'],['C1']);self.assertEqual(u['plan']['selected_point_ids'],['C1'])
    def test_manual_edit_cannot_escape_candidate_fact_scope(self):
        t=task();p=copy.deepcopy(t['plan']);p['sections'][0]['fact_ids']=['F02']
        r=self.client.put(f"/api/tasks/{t['id']}/plan",json=dict(version=t['version'],plan=p));self.assertEqual(r.status_code,400)
        self.assertEqual(db.get(t['id'])['plan'],t['plan'])
    def test_manual_edit_cannot_replace_execution_selection(self):
        t=task();p=copy.deepcopy(t['plan']);p['selected_point_ids']=['C2']
        r=self.client.put(f"/api/tasks/{t['id']}/plan",json=dict(version=t['version'],plan=p));self.assertEqual(r.status_code,400)
    def test_manual_edit_cannot_silently_drop_selected_point(self):
        t=task();p=copy.deepcopy(t['plan']);s=p['sections'][0];s.update(role='opening',point_ids=[],fact_ids=[])
        r=self.client.put(f"/api/tasks/{t['id']}/plan",json=dict(version=t['version'],plan=p));self.assertEqual(r.status_code,400)
    def test_client_cannot_forge_recommendation_or_score(self):
        t=task();p=copy.deepcopy(t['plan']);p['planning_analysis']['candidates'][0].update(total_score=999,recommendation='recommended',recommendation_reason='客户端伪造')
        r=self.client.put(f"/api/tasks/{t['id']}/plan",json=dict(version=t['version'],plan=p))
        self.assertEqual(r.status_code,200);self.assertEqual(db.get(t['id'])['plan']['planning_analysis']['candidates'],t['plan']['planning_analysis']['candidates'])
    def test_missing_required_request_fails_before_model(self):
        t=task(canonical=True)
        with patch.object(w.llm,'complete',AsyncMock()) as model:r=self.post(t,['C2'])
        self.assertEqual(r.status_code,400);self.assertIn('必须内容',r.json()['detail']);model.assert_not_called()
    def test_required_fact_must_actually_be_used_in_outline(self):
        t=task(canonical=True);p=copy.deepcopy(t['plan'])
        t['brief_analysis']['commercial_requests']=[dict(category='price',on_missing='block')]
        t['brief_analysis']['retrieval_plan']['facts'].append(dict(id='PRICE',category='price',question='必须写价格',priority='supporting'))
        t['package']['coverage'].append(dict(request_id='PRICE',status='supported',fact_ids=['F01','F02']))
        p['planning_analysis']['candidates'][1]['fact_ids']=['F01','F02']
        p['planning_analysis']['candidate_context_hash']=cp.candidate_context_hash(t)
        with self.assertRaisesRegex(ValueError,'必须事实'):w.validate_plan(t,p)
    def test_confirm_plan_uses_same_selection_guards(self):
        t=task();p=copy.deepcopy(t['plan']);p['sections'][0]['fact_ids']=['F02']
        with patch.object(w.llm,'complete',AsyncMock()) as model:
            r=self.client.post(f"/api/tasks/{t['id']}/confirm-plan",json=dict(version=t['version'],plan=p))
        self.assertEqual(r.status_code,400);model.assert_not_called()


    def test_retrieval_priority_alone_does_not_lock_user_selection(self):
        t=task(canonical=True)
        from backend import brief_agent as ba
        t['brief_analysis']['requirements']['user_constraints']=dict(value=[],source='unknown',reason='未要求',evidence=[])
        t['brief']=ba.projection(t['brief_analysis']);t['brief_confirmation']['analysis_hash']=ba.digest(t['brief_analysis'])
        t['plan']['planning_analysis']['candidate_context_hash']=cp.candidate_context_hash(t)
        for c in t['plan']['planning_analysis']['candidates']:c['mandatory_need_ids']=[]
        db.save(t,'只有检索required，没有必须写作要求')
        async def fake(model,system,payload,schema,**kwargs):return compose(payload)
        with patch.object(w.llm,'complete',AsyncMock(side_effect=fake)):r=self.post(t,['C2'])
        self.assertEqual(r.status_code,202);self.assertIsNone(db.get(t['id'])['error'])
        self.assertEqual(db.get(t['id'])['plan']['selected_point_ids'],['C2'])

    def test_pending_selection_does_not_pretend_old_outline_has_updated(self):
        t=task()
        with patch.object(w,'job',AsyncMock()) as job:r=self.post(t,['C2'])
        self.assertEqual(r.status_code,202);job.assert_awaited_once_with(t['id'],'replan_points')
        u=self.client.get(f"/api/tasks/{t['id']}").json()
        self.assertEqual(u['status'],'planning');self.assertEqual(u['plan']['selected_point_ids'],['C1'])
        self.assertEqual(u['pending_point_replan']['selected_point_ids'],['C2'])
        w.recover_point_replan(db.get(t['id']))
