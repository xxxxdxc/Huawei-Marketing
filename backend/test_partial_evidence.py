"""Bounded partial claims, no real model calls or network."""
import asyncio,copy,unittest
from unittest.mock import patch,AsyncMock
from backend.test_evidence_resolution import paused
from backend.test_manual_evidence import body,extraction
from backend import evidence_policy as ep,evidence_resolution as er,manual_evidence as me,workflow as w,schemas as S,brief_agent as ba,storage as db

class PartialEvidenceTests(unittest.TestCase):
    def setUp(self):db.init()
    def task(self):
        t=paused();me.prepare(t,S.ManualEvidenceInput(**body(t)));raw=extraction(t)
        for c in raw['coverage']:
            if c['request_id']!='R2':c.update(status='partial',reason='有原文数据，额外测试条件未提供；仅保留原文限定',missing_details=['额外测试脚注'],usage_limits=['不得推断全天办公续航'])
        t['package'].update(raw);return t
    def test_partial_required_uses_existing_facts_without_claiming_completeness(self):
        t=self.task();self.assertEqual(w.verify_coverage(t),[])
        c=t['package']['coverage'][0];self.assertEqual(c['status'],'partial');self.assertEqual(c['fact_ids'],['FM1'])
        self.assertIn('FM1',{f['id'] for f in t['package']['facts']})
        summary=er.review_summary(t);item=next(u for u in summary['unmet_requirements'] if u['request']['id']=='R1')
        self.assertTrue(item['found']);self.assertFalse(item['blocking'])
    def test_link_verification_flag_is_not_a_blocker(self):
        t=self.task();self.assertFalse(t['package']['sources'][-1]['link_verified']);self.assertEqual(w.verify_coverage(t),[])
    def test_partial_empty_references_rejected(self):
        t=self.task();t['package']['coverage'][0]['fact_ids']=[]
        with self.assertRaises(Exception):w.verify_coverage(t)
    def test_partial_unknown_references_rejected(self):
        t=self.task();t['package']['coverage'][0]['fact_ids']=['FAKE']
        with self.assertRaises(Exception):w.verify_coverage(t)
    def test_real_guardrails_continue_to_block_partial(self):
        for guardrail in ('identity','safety','compatibility'):
            with self.subTest(guardrail=guardrail):
                t=self.task();t['brief_analysis']['retrieval_plan']['facts'][0]['guardrail']=guardrail
                self.assertTrue(w.verify_coverage(t));self.assertIsNotNone(er.protected_reason(t,t['brief_analysis']['retrieval_plan']['facts'][0]))
    def test_explicit_complete_test_conditions_remain_a_gate(self):
        t=self.task();t['dialogue']=[dict(id='U99',kind='user',text='必须包含续航的完整测试条件，否则不生成')]
        self.assertTrue(w.verify_coverage(t))
    def test_preference_is_not_a_gate_even_if_strategy_said_nonwaivable(self):
        t=self.task();r=t['brief_analysis']['retrieval_plan']['facts'][0];r.update(waivable=False,guardrail='none')
        t['dialogue']=[dict(id='U99',kind='user',text='更侧重高续航，上课找不到充电口')]
        self.assertIsNone(er.protected_reason(t,r));self.assertEqual(w.verify_coverage(t),[])
    def test_required_does_not_normalize_into_nonwaivable(self):
        t=self.task();strategy={k:copy.deepcopy(t['brief_analysis'][k]) for k in ('message_strategy','retrieval_plan')}
        strategy['retrieval_plan']['facts'][0].update(waivable=False,guardrail='none')
        normalized=ep.normalize_strategy(strategy,[])
        self.assertTrue(normalized['retrieval_plan']['facts'][0]['waivable'])
    def test_same_condition_conflicts_still_pause(self):
        t=self.task();t['package']['conflicts']=[dict(category='product',source_ids=['S1'],request_ids=['R1'],detail='同配置出现不同数值')]
        w.verify_coverage(t);self.assertTrue(t['package']['conflicts'])
    def test_boundary_notes_stay_traceable_but_are_not_product_points(self):
        t=self.task();f=dict(id='RULE',category='product',claim='不得未经核验承诺全天续航',quote='不得未经核验承诺全天续航，也不能直接换成课堂续航。',source_id='S1',conditions='内部规则')
        t['package']['sources'][0]['text']+=' '+f['quote'];t['package']['facts'].append(f)
        w.verify_coverage(t)
        self.assertNotIn('RULE',{x['id'] for x in t['package']['facts']})
        self.assertIn('RULE',{x['id'] for x in t['package']['all_facts']})
        self.assertEqual(t['package']['writing_boundaries'][0]['id'],'RULE')
    def test_saved_fact_recheck_does_not_reextract_or_fetch(self):
        t=self.task();facts=copy.deepcopy(t['package']['facts']);sources=copy.deepcopy(t['package']['sources']);brief=copy.deepcopy(t['brief_analysis'])
        async def plan(task,*args,**kwargs):task['status']='plan_ready'
        with patch.object(w.llm,'complete',AsyncMock(return_value=dict(coverage=copy.deepcopy(t['package']['coverage'])))) as model,patch.object(w,'extract_facts',AsyncMock()) as extract,patch.object(w.ima,'catalog_for_task',AsyncMock()) as catalog,patch.object(w.ima,'retrieve_for_task',AsyncMock()) as fetch,patch.object(w,'build_content_plan',AsyncMock(side_effect=plan)),patch.object(w,'write',AsyncMock()) as writer:
            asyncio.run(w.plan(t,reuse_package=True))
        model.assert_awaited_once();extract.assert_not_awaited();catalog.assert_not_awaited();fetch.assert_not_awaited();writer.assert_not_awaited()
        self.assertEqual(t['package']['all_facts'],facts);self.assertEqual(t['package']['sources'],sources);self.assertEqual(t['brief_analysis'],brief);self.assertEqual(t['status'],'plan_ready')
    def test_recheck_cannot_forge_a_fact_id(self):
        t=self.task();coverage=copy.deepcopy(t['package']['coverage']);coverage[0]['fact_ids']=['FAKE']
        with patch.object(w.llm,'complete',AsyncMock(return_value=dict(coverage=coverage))),self.assertRaises(Exception):asyncio.run(me.run(t,reuse_facts=True))
    def test_partial_model_schema_preserves_unknown_details(self):
        c=S.FactCoverage(request_id='f1',status='partial',fact_ids=['F04','F05'],reason='只有原文限定',missing_details=['亮度未提供'],usage_limits=['不能写办公18小时'])
        self.assertEqual(c.status,'partial');self.assertEqual(c.fact_ids,['F04','F05'])

    def test_planner_and_writer_context_get_partial_use_limits(self):
        from backend import content_planner as cp
        t=self.task();w.verify_coverage(t)
        context=cp.shared_context(t,w.PLATFORMS[t['platform']])
        self.assertTrue(context['evidence_usage'])
        self.assertIn('不得推断全天办公续航',context['evidence_usage'][0]['usage_limits'])

    def test_prefixed_source_cautions_are_boundaries_not_specs(self):
        from backend import evidence_usage as usage
        self.assertTrue(usage.guidance_fact({'claim':'知识库明确提示电池容量不能等同于固定续航。'}))
        self.assertTrue(usage.guidance_fact({'claim':'知识库列出的限制：不经核验不得承诺全天续航。'}))
        self.assertFalse(usage.guidance_fact({'claim':'Windows版支持十点触控，Linux版仅五点触控'}))
        self.assertFalse(usage.guidance_fact({'claim':'屏幕不支持手写笔'}))
        self.assertFalse(usage.guidance_fact({'claim':'不能运行该Windows软件'}))
        self.assertFalse(usage.guidance_fact({'claim':'不得连接高于指定电压的电源'}))

    def test_explicit_global_condition_requirement_is_respected(self):
        t=self.task();t['dialogue']=[dict(id='U99',kind='user',text='文案必须包含完整测试条件')]
        self.assertTrue(w.verify_coverage(t))
        t=self.task();t['dialogue']=[dict(id='U99',kind='user',text='无需完整测试条件，按原文写即可')]
        self.assertEqual(w.verify_coverage(t),[])
