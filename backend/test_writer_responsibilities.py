"""Responsibilities, actual method loading, two-stage writing and migration. No live models."""
import asyncio,copy,unittest
from unittest.mock import AsyncMock,patch
from fastapi.testclient import TestClient
from backend.test_point_selection import task,compose
from backend import content_planner as cp,platform_writer as pw,workflow as w,planner_schemas as P,storage as db,schemas as S
from backend.main import app
from backend.clients import ServiceError


def outline(payload):
    points=payload['selected_points']
    result=compose(payload | dict(ranked_candidates=points))
    result['cta']='' if payload.get('store_marketing_policy',{}).get('platform')=='wechat' else '欢迎私信了解我们的门店'
    result.pop('schema_version');result['main_takeaway']='围绕本次需求形成有依据的选购判断'
    for i,s in enumerate(result['sections']):
        s.update(connection_to_previous='从需求进入事实' if i==0 else '在上一段理解上解释下一个问题'+str(i),reader_progress='形成具体理解'+str(i))
    return result


def document(plan):
    return dict(title='测试标题',lead='',paragraphs=[dict(section_id=s['id'],heading=s['heading'],text='说明本段已核验产品资料。',fact_ids=s['fact_ids'],image_id=s['image_id'],caption='产品图片') for s in plan['sections']],cta=plan['cta'],tags=[])


class WriterResponsibilitiesTests(unittest.TestCase):
    def setUp(self):
        self.client=TestClient(app);self.client.__enter__()
    def tearDown(self):self.client.__exit__(None,None,None)
    def selected(self,platform='moments'):
        t=task(platform=platform,legacy=False)
        t['selection_confirmation']=dict(selection_hash=cp.selection_fingerprint(t['plan']))
        return t
    def fake(self,model,system,payload,schema,**kw):
        if schema is P.WriterOutline:return outline(payload)
        if schema is S.Document:return document(payload['plan'])
        if schema is S.Review:return dict(summary='隔离测试通过',issues=[])
        raise AssertionError('Unexpected model call')
    def test_planner_only_calls_candidate_stage(self):
        t=task(legacy=False)
        self.assertEqual(t['plan']['schema_version'],'3');self.assertEqual(t['plan']['phase'],'selection')
        self.assertEqual(t['plan']['sections'],[])
        self.assertEqual(t['planner_runs'][-1]['method_sources'],['content-strategy'])
        self.assertNotIn('composition_rationale',t['plan'])
    def test_no_writing_without_user_selection_confirmation(self):
        t=task(legacy=False)
        with patch.object(w.llm,'complete',AsyncMock()) as model:
            with self.assertRaisesRegex(ValueError,'确认核心卖点'):asyncio.run(w.write(t))
        model.assert_not_called()
    def test_writer_then_draft_then_independent_review(self):
        t=self.selected()
        with patch.object(w.llm,'complete',AsyncMock(side_effect=self.fake)) as model:asyncio.run(w.write(t))
        self.assertEqual([c.args[3] for c in model.call_args_list],[P.WriterOutline,S.Document,S.Review])
        self.assertEqual(t['plan']['phase'],'composed');self.assertTrue(t['writer_outline']['main_takeaway'])
        self.assertTrue(w.can_export(t));self.assertEqual(t['writer_stage'],'complete')
        self.assertIn('## Drafting Protocol',model.call_args_list[0].args[1])
        self.assertIn('### One Idea Per Section',model.call_args_list[1].args[1])
    def test_confirm_accepts_local_selection_and_ignores_forged_scores(self):
        t=task(legacy=False);incoming=copy.deepcopy(t['plan']);incoming['selected_point_ids']=['C2']
        incoming['planning_analysis']['candidates'][0]['total_score']=999
        with patch.object(w.llm,'complete',AsyncMock(side_effect=self.fake)) as model:
            r=self.client.post(f"/api/tasks/{t['id']}/confirm-plan",json=dict(version=t['version'],plan=incoming))
        self.assertEqual(r.status_code,202);u=db.get(t['id']);self.assertTrue(w.can_export(u))
        self.assertEqual(u['plan']['selected_point_ids'],['C2'])
        self.assertEqual(u['plan']['planning_analysis']['candidates'],t['plan']['planning_analysis']['candidates'])
        self.assertEqual({f['id'] for f in model.call_args_list[0].args[2]['facts']},{'F02'})
        self.assertEqual({f['id'] for f in model.call_args_list[1].args[2]['package']['facts']},{'F02'})
    def test_unknown_selection_rejected_before_writer(self):
        t=task(legacy=False);p=copy.deepcopy(t['plan']);p['selected_point_ids']=['missing']
        with patch.object(w.llm,'complete',AsyncMock()) as model:
            r=self.client.post(f"/api/tasks/{t['id']}/confirm-plan",json=dict(version=t['version'],plan=p))
        self.assertEqual(r.status_code,400);model.assert_not_called()
    def test_stale_confirmation_rejected(self):
        t=task(legacy=False)
        with patch.object(w.llm,'complete',AsyncMock()) as model:
            r=self.client.post(f"/api/tasks/{t['id']}/confirm-plan",json=dict(version=t['version']-1,plan=t['plan']))
        self.assertEqual(r.status_code,409);model.assert_not_called()
    def test_structural_errors_stop_before_drafting(self):
        mutations={
            'missing_point':lambda r:r.update(selected_point_ids=['C2']),
            'unknown_fact':lambda r:r['sections'][0].update(fact_ids=['missing']),
            'wrong_product':lambda r:r.update(product_id='other'),
            'unknown_image':lambda r:r['sections'][0].update(image_id='missing'),
            'out_of_scope_fact':lambda r:r['sections'][0].update(fact_ids=['F02']),
            'unselected_point':lambda r:r['sections'][0].update(point_ids=['C2']),
            'no_evidence':lambda r:r['sections'][0].update(fact_ids=[]),
            'wrong_platform_layout':lambda r:r['sections'][0].update(image_position=dict(kind='carousel',order=1)),
            'bad_budget':lambda r:r['sections'][0].update(target_chars=900),
            'duplicate_cta_section':lambda r:r['sections'][0].update(role='cta'),
        }
        for name,change in mutations.items():
            with self.subTest(name=name):
                t=self.selected();old=copy.deepcopy(t['plan'])
                async def bad(model,system,payload,schema,**kw):
                    result=outline(payload);change(result);return result
                with patch.object(w.llm,'complete',AsyncMock(side_effect=bad)) as model:
                    with self.assertRaises(ValueError):asyncio.run(w.write(t))
                self.assertEqual(model.await_count,1);self.assertEqual(t['plan'],old);self.assertIsNone(t['document'])
                self.assertIn('rejected_outline',t['writer_runs'][-1])
    def test_repeated_progress_rejected(self):
        t=self.selected('wechat')
        async def bad(model,system,payload,schema,**kw):
            r=outline(payload);r['sections'][1]['reader_progress']=r['sections'][0]['reader_progress'];return r
        with patch.object(w.llm,'complete',AsyncMock(side_effect=bad)):
            with self.assertRaisesRegex(ValueError,'信息增量'):asyncio.run(w.write(t))
    def test_missing_connection_is_rejected(self):
        t=self.selected()
        async def bad(model,system,payload,schema,**kw):
            r=outline(payload);r['sections'][0].pop('connection_to_previous');return r
        with patch.object(w.llm,'complete',AsyncMock(side_effect=bad)):
            with self.assertRaises(ValueError):asyncio.run(w.write(t))
    def test_structure_can_merge_multiple_selected_points(self):
        t=self.selected();t['plan']['selected_point_ids']=['C1','C2']
        t['selection_confirmation']['selection_hash']=cp.selection_fingerprint(t['plan'])
        async def merged(model,system,payload,schema,**kw):
            if schema is P.WriterOutline:
                r=outline(payload);r['sections']=r['sections'][:1]
                r['sections'][0].update(point_ids=['C1','C2'],fact_ids=['F01','F02'],target_chars=100)
                return r
            return self.fake(model,system,payload,schema,**kw)
        with patch.object(w.llm,'complete',AsyncMock(side_effect=merged)):asyncio.run(w.write(t))
        self.assertEqual(len(t['plan']['sections']),1);self.assertEqual(t['plan']['sections'][0]['point_ids'],['C1','C2'])
    def test_structure_failure_keeps_selection_and_retries(self):
        t=task(legacy=False)
        with patch.object(w.llm,'complete',AsyncMock(side_effect=ServiceError('fixture timeout'))):
            self.client.post(f"/api/tasks/{t['id']}/confirm-plan",json=dict(version=t['version'],plan=t['plan']))
        u=db.get(t['id']);self.assertEqual(u['status'],'error');self.assertEqual(u['resume_status'],'plan_ready')
        self.assertEqual(u['plan']['phase'],'selection');self.assertIsNone(u['document'])
        self.assertEqual(u['writer_runs'][-1]['status'],'failed');self.assertIn('seconds',u['writer_runs'][-1])
        with patch.object(w.llm,'complete',AsyncMock(side_effect=self.fake)):
            r=self.client.post(f"/api/tasks/{t['id']}/confirm-plan",json=dict(version=u['version'],plan=u['plan']))
        self.assertEqual(r.status_code,202);self.assertTrue(w.can_export(db.get(t['id'])))
    def test_draft_failure_retains_internal_outline(self):
        t=self.selected()
        async def bad(model,system,payload,schema,**kw):
            if schema is P.WriterOutline:return outline(payload)
            raise ServiceError('fixture draft timeout')
        with patch.object(w.llm,'complete',AsyncMock(side_effect=bad)):
            with self.assertRaises(ServiceError):asyncio.run(w.write(t))
        self.assertTrue(t['writer_outline']);self.assertEqual(t['plan']['phase'],'composed');self.assertIsNone(t['document'])
    def test_user_edits_invalidate_review_and_keep_section_ids(self):
        t=self.selected()
        with patch.object(w.llm,'complete',AsyncMock(side_effect=self.fake)):asyncio.run(w.write(t))
        d=copy.deepcopy(t['document']);d['title']='用户改后的标题'
        r=self.client.put(f"/api/tasks/{t['id']}/document",json=dict(version=t['version'],document=d))
        self.assertEqual(r.status_code,200);self.assertFalse(w.can_export(db.get(t['id'])))
        d['paragraphs'][0]['section_id']='unknown'
        u=db.get(t['id']);r=self.client.put(f"/api/tasks/{t['id']}/document",json=dict(version=u['version'],document=d))
        self.assertEqual(r.status_code,400)
    def test_phase_schema_cannot_fake_outline(self):
        p=task(legacy=False)['plan'];p['sections']=[dict(id='P1')]
        with self.assertRaises(ValueError):S.Plan.model_validate(p)
    def platform_task(self,confirmed=True):
        from backend.test_platform_change import task as platform_task
        t=task(canonical=True,legacy=False)
        extra=platform_task()['package']['images'][1]
        t['package']['images'].append(extra)
        t['package']['asset_candidates']=copy.deepcopy(t['package']['images'])
        # Package context legitimately extended before selection confirmation.
        t['plan']['planning_analysis']['candidate_context_hash']=cp.candidate_context_hash(t)
        if confirmed:t['selection_confirmation']=dict(selection_hash=cp.selection_fingerprint(t['plan']))
        return db.save(t,'平台迁移前隔离状态')
    def test_platform_change_keeps_confirmed_points_and_skips_planner(self):
        t=self.platform_task();before=copy.deepcopy(t)
        with patch.object(w.llm,'complete',AsyncMock(side_effect=self.fake)) as model,patch.object(w,'analyze',AsyncMock()) as brief:
            r=self.client.post(f"/api/tasks/{t['id']}/change-platform",json=dict(version=t['version'],platform='wechat'))
        self.assertEqual(r.status_code,202);u=db.get(t['id']);self.assertTrue(w.can_export(u),u.get('error'))
        self.assertEqual([x.args[3] for x in model.call_args_list],[P.WriterOutline,S.Document,S.Review]);brief.assert_not_called()
        self.assertEqual(u['plan']['selected_point_ids'],before['plan']['selected_point_ids'])
        self.assertEqual(u['selection_confirmation']['authorization'],'platform_only')
        self.assertEqual(db.snapshot(t['id'],t['version'])['platform'],'moments')
    def test_unconfirmed_platform_selection_waits_without_model(self):
        t=self.platform_task(False)
        with patch.object(w.llm,'complete',AsyncMock()) as model:
            self.client.post(f"/api/tasks/{t['id']}/change-platform",json=dict(version=t['version'],platform='wechat'))
        u=db.get(t['id']);self.assertEqual(u['status'],'plan_ready');self.assertIsNone(u['selection_confirmation']);model.assert_not_called()
    def test_saved_selection_clears_confirmation_without_model(self):
        t=self.selected();t=db.save(t,'已有确认记录')
        with patch.object(w.llm,'complete',AsyncMock()) as model:
            r=self.client.post(f"/api/tasks/{t['id']}/replan-points",json=dict(version=t['version'],selected_point_ids=['C2'],replace_current_plan=True))
        self.assertEqual(r.status_code,202);u=db.get(t['id']);model.assert_not_called()
        self.assertEqual(u['plan']['sections'],[]);self.assertIsNone(u['selection_confirmation'])
    def test_source_methods_are_actual_excerpt_and_stage_specific(self):
        self.assertIn('### 1. Customer Impact (40%)',cp.ADAPTER)
        self.assertNotIn('## Drafting Protocol',cp.ADAPTER)
        self.assertIn('## Drafting Protocol',pw.WRITER_METHOD)
        from backend.marketing_methods import sections
        self.assertIn('Build a logical flow',sections('copywriting',['### One Idea Per Section']))
    def test_final_markdown_has_no_internal_structure_labels(self):
        t=self.selected();t['package']['images'][0].update(mime='image/png',source='fixture')
        with patch.object(w.llm,'complete',AsyncMock(side_effect=self.fake)):asyncio.run(w.write(t))
        text=w.markdown(t)
        self.assertNotIn(t['writer_outline']['sections'][0]['heading'],text)
        self.assertNotIn('reader_progress',text);self.assertNotIn('connection_to_previous',text)

    def test_draft_failure_via_job_preserves_failed_run_and_outline(self):
        t=task(legacy=False)
        async def fail(model,system,payload,schema,**kw):
            if schema is P.WriterOutline:return outline(payload)
            raise ServiceError('fixture draft failure')
        with patch.object(w.llm,'complete',AsyncMock(side_effect=fail)):
            self.client.post(f"/api/tasks/{t['id']}/confirm-plan",json=dict(version=t['version'],plan=t['plan']))
        u=db.get(t['id']);self.assertEqual(u['status'],'error');self.assertIsNone(u['document'])
        self.assertTrue(u['writer_outline']);self.assertEqual(u['plan']['phase'],'composed')
        self.assertEqual([r['status'] for r in u['writer_runs']],['complete','failed'])
        self.assertEqual(u['writer_runs'][-1]['stage'],'draft')
    def test_final_document_must_cover_confirmed_points(self):
        t=self.selected()
        with patch.object(w.llm,'complete',AsyncMock(side_effect=self.fake)):asyncio.run(w.write(t))
        t['document']['paragraphs'][0]['fact_ids']=[]
        self.assertTrue(any('遗漏了已确认卖点' in i['detail'] for i in w.deterministic_review(t)))
