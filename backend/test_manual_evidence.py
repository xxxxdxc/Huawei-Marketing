"""Synthetic task-local excerpts; provider and KB calls mocked, no link fetches."""
import asyncio,copy,unittest
from unittest.mock import patch,AsyncMock
from fastapi.testclient import TestClient
from pydantic import ValidationError
from backend.test_evidence_resolution import paused
from backend import manual_evidence as me,workflow as w,storage as db,schemas as S,evidence_resolution as er
from backend.main import app

TEXT='测试型号的隔离资料原文：在指定测试配置下进行课程播放测量；测试场景、亮度与系统版本均有明确说明。这里仅为自动化测试资料，不是实际产品参数。'
def body(t,**changes):
    return dict(version=t['version'],product_id=t['product_id'],request_ids=['R1','R3'],text=TEXT,source_url='https://example.com/specs',source_title='隔离测试资料',conditions='测试配置',confirmed=True)|changes

def extraction(t,conflict=False,missing=False):
    facts=copy.deepcopy(t['package']['facts']);sid=t['manual_evidence'][-1]['id']
    facts.append(dict(id='FM1',category='product',claim='测试课程续航资料',quote=TEXT,source_id=sid,conditions='测试配置'))
    return dict(facts=facts,conflicts=[dict(category='product',request_ids=['R1'],source_ids=['S1',sid],detail='同配置数据相互冲突')] if conflict else [],coverage=[dict(request_id=rid,status='not_found' if missing and rid!='R2' else 'supported',fact_ids=[] if missing and rid!='R2' else ['F01'] if rid=='R2' else ['FM1'],reason='隔离检查') for rid in ('R1','R2','R3')])

class ManualEvidenceTests(unittest.TestCase):
    def setUp(self):db.init()
    def prepared(self):
        t=paused();me.prepare(t,S.ManualEvidenceInput(**body(t)));return t
    def test_validation_rejects_invalid_links_and_thin_data(self):
        t=paused()
        for url in ('javascript:alert(1)','file:///tmp/x','https://a:b@example.com','https://example.com/a b','bad-link'):
            with self.subTest(url=url),self.assertRaises(ValidationError):S.ManualEvidenceInput(**body(t,source_url=url))
        for text in ('70 Wh',' '*40):
            with self.assertRaises(ValidationError):S.ManualEvidenceInput(**body(t,text=text))
        with self.assertRaises(ValidationError):S.ManualEvidenceInput(**body(t,confirmed=False))
    def test_wrong_product_unknown_request_and_duplicates_rejected(self):
        for change in ({'product_id':'other'},{'request_ids':['unknown']}):
            t=paused()
            with self.assertRaises(ValueError):me.prepare(t,S.ManualEvidenceInput(**body(t,**change)))
        t=self.prepared()
        with self.assertRaisesRegex(ValueError,'重复提交'):me.prepare(t,S.ManualEvidenceInput(**body(t)))
    def test_source_stored_verbatim_with_unverified_provenance(self):
        t=self.prepared();source=t['package']['sources'][-1]
        self.assertEqual(source['text'],TEXT);self.assertFalse(source['link_verified'])
        self.assertEqual(source['source_type'],'user_manual');self.assertEqual(source['path'],'https://example.com/specs')
        self.assertFalse(me.provenance(t)[0]['link_verified'])
    def test_supplement_does_not_approve_without_extracting(self):
        t=paused();before=copy.deepcopy(t['package']['coverage']);me.prepare(t,S.ManualEvidenceInput(**body(t)))
        self.assertEqual(t['package']['coverage'],before);self.assertIsNone(t['plan']);self.assertIsNone(t['review'])
    def test_success_only_rechecks_saved_materials_and_returns_to_selection(self):
        t=self.prepared();original=copy.deepcopy(t['brief_analysis']);raw=extraction(t)
        async def plan(task,*a,**k):task.update(status='plan_ready',resume_status='plan_ready');w.event(task,'测试卖点待确认')
        with patch.object(w,'extract_facts',AsyncMock(return_value=raw)) as extract,patch.object(w,'build_content_plan',AsyncMock(side_effect=plan)) as planner,patch.object(w.ima,'retrieve_for_task',AsyncMock()) as kb,patch.object(w.ima,'catalog_for_task',AsyncMock()) as catalog,patch.object(w,'analyze',AsyncMock()) as brief,patch.object(w,'write',AsyncMock()) as writer:
            asyncio.run(me.run(t))
        extract.assert_awaited_once();planner.assert_awaited_once();kb.assert_not_awaited();catalog.assert_not_awaited();brief.assert_not_awaited();writer.assert_not_awaited()
        self.assertEqual(t['status'],'plan_ready');self.assertEqual(t['brief_analysis'],original);self.assertEqual(t['manual_evidence'][0]['status'],'checked')
        self.assertEqual(t['evidence_refreshes'][-1]['status'],'plan_ready')
    def test_missing_and_conflicting_sources_still_pause(self):
        for flags in ({'missing':True},{'conflict':True}):
            with self.subTest(flags=flags):
                t=self.prepared()
                if flags.get('missing'):t['brief_analysis']['retrieval_plan']['facts'][0]['guardrail']='identity';t['brief_confirmation']['analysis_hash']=w.ba.digest(t['brief_analysis'])
                with patch.object(w,'extract_facts',AsyncMock(return_value=extraction(t,**flags))),patch.object(w,'build_content_plan',AsyncMock()) as planner:
                    asyncio.run(me.run(t))
                self.assertEqual(t['status'],'needs_review');planner.assert_not_awaited()
                self.assertGreaterEqual(len(t['package']['sources']),2)
    def test_forged_quote_rejected_and_original_input_preserved(self):
        t=self.prepared();raw=extraction(t);raw['facts'][-1]['quote']='这段原文从未出现在任何提供的来源之中'
        with patch.object(w,'extract_facts',AsyncMock(return_value=raw)),patch.object(w.llm,'complete',AsyncMock(return_value={'facts':[]})),patch.object(w,'build_content_plan',AsyncMock()):asyncio.run(me.run(t))
        self.assertEqual(t['manual_evidence'][0]['text'],TEXT);self.assertTrue(t['package']['rejected_facts'])
        self.assertNotIn('FM1',{f['id'] for f in t['package']['facts']})
    def test_attach_retains_supplement_after_original_source_refresh(self):
        t=self.prepared();fresh={'sources':[]};me.attach(t,fresh);me.attach(t,fresh)
        self.assertEqual(len(fresh['sources']),1)
        t['product_id']='other';fresh={'sources':[]};me.attach(t,fresh);self.assertEqual(fresh['sources'],[])
    def test_versions_http_validation_and_history(self):
        client=TestClient(app);t=paused();old=copy.deepcopy(t)
        with patch.object(w,'job',AsyncMock()) as job:
            self.assertEqual(client.post(f"/api/tasks/{t['id']}/manual-evidence",json=body(t,version=t['version']-1)).status_code,409)
            self.assertEqual(client.post(f"/api/tasks/{t['id']}/manual-evidence",json=body(t,product_id='wrong')).status_code,400)
            self.assertEqual(client.post(f"/api/tasks/{t['id']}/manual-evidence",json=body(t)).status_code,202)
        job.assert_awaited_once_with(t['id'],'manual_evidence')
        saved=db.get(t['id']);self.assertEqual(saved['manual_evidence'][0]['text'],TEXT)
        self.assertEqual(db.snapshot(t['id'],old['version']),old)
    def test_manual_source_changes_invalidate_review_digest(self):
        t=self.prepared();a=db.digest(t);t['manual_evidence'][0]['source_url']='https://example.com/changed';self.assertNotEqual(a,db.digest(t))

    def test_existing_omission_scope_is_not_restored(self):
        t=paused();preview=er.preview(t,['R1'],[])
        confirm=S.EvidenceResolutionConfirm(version=t['version'],preview_id=preview['preview_id'],drop_request_ids=preview['selected_request_ids'],drop_direction_ids=preview['selected_direction_ids'],confirmed=True,acknowledged_constraint_ids=[])
        er.confirm(t,confirm);scope=copy.deepcopy(t['execution_scope'])
        me.prepare(t,S.ManualEvidenceInput(**body(t)))
        with patch.object(w,'extract_facts',AsyncMock(return_value=extraction(t))),patch.object(w,'build_content_plan',AsyncMock()):asyncio.run(me.run(t))
        self.assertEqual(t['execution_scope'],scope)
        self.assertIn('R1',t['execution_scope']['omitted_request_ids'])
        self.assertFalse(any('FM1'==f['id'] for f in t['package']['facts']))

    def test_failed_extract_retries_saved_entry_without_duplicate_sources(self):
        t=self.prepared();original=copy.deepcopy(t['package']['facts'])
        with patch.object(w,'extract_facts',AsyncMock(side_effect=ValueError('provider failed'))),self.assertRaises(ValueError):asyncio.run(me.run(t))
        me.prepare(t,S.ManualEvidenceInput(**body(t)))
        self.assertEqual(len(t['manual_evidence']),1)
        self.assertEqual(t['package']['facts'],original)
        self.assertEqual(len([s for s in t['package']['sources'] if s.get('source_type')=='user_manual']),1)

    def test_final_review_retains_unverified_source_notice(self):
        from backend.test_platform_change import task
        t=task();plan=copy.deepcopy(t['plan']);document=copy.deepcopy(t['document'])
        data=body(t,request_ids=[t['brief_analysis']['retrieval_plan']['facts'][0]['id']])
        me.prepare(t,S.ManualEvidenceInput(**data));t.update(plan=plan,document=document)
        with patch.object(w,'deterministic_review',return_value=[]),patch.object(w.llm,'complete',AsyncMock(return_value=dict(summary='测试：与提供资料一致',issues=[]))):asyncio.run(w.review(t))
        self.assertTrue(t['review']['passed']);self.assertFalse(t['review']['source_verification'][0]['link_verified'])
        self.assertEqual(db.get(t['id'])['review']['source_verification'],t['review']['source_verification'])
