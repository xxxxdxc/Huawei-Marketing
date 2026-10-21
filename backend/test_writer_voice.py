"""Writer voice regression: screenshot failures, evidence boundaries and legacy isolation."""
import asyncio,copy,hashlib,json,unittest
from unittest.mock import AsyncMock,patch
from backend.test_workflow import prepared,DOC
from backend import platform_writer as pw,publication_rules as pub,marketing_methods as mm,workflow as w,schemas as S

class WriterVoiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from backend import storage
        storage.init()
    def test_five_screenshot_failures_are_detected(self):
        examples=[
            '下面按这个顺序看HUAWEI MateBook Pro。',
            '这是机身本身的规格，到店时可以把充电器一起拿上手，感受一下整套分量。',
            '目前能确认的是电池额定容量70 Wh。实际能用多久，这项值得到店当面问清楚。',
            '3:2是什么感觉，触控顺不顺手，适合在店里用自己的材料试一试。',
            '资料里列有无线投屏，建议带上常用设备到店确认。',
        ]
        for text in examples:
            with self.subTest(text=text):
                d=copy.deepcopy(DOC);d['paragraphs'][0]['text']=text
                self.assertTrue(pub.voice_issues(d))
    def test_generic_purchased_version_patch_detected(self):
        self.assertTrue(pub.generic_notes('具体以所购版本为准。'))
    def test_natural_facts_and_specific_scope_not_flagged(self):
        for text in ('机身重量约970 g，厚度13.5 mm。','Windows版支持十点触控。','电池额定容量70 Wh。','屏幕采用3:2比例，支持最多十点触控。','旅途中的工作，也有自己的节奏。','包装清单之外不添加赠品。'):
            with self.subTest(text=text):
                d=copy.deepcopy(DOC);d['paragraphs'][0]['text']=text
                self.assertFalse(pub.voice_issues(d))
    def test_root_cta_only_can_invite_visit(self):
        d=copy.deepcopy(DOC);d['cta']='欢迎到店体验，也可咨询适合你的版本。'
        self.assertFalse(pub.voice_issues(d))
        d['paragraphs'][0]['text']=d['cta']
        self.assertTrue(pub.voice_issues(d))
    def test_title_lead_caption_and_tags_are_checked(self):
        for field in ('title','lead','caption','tags'):
            with self.subTest(field=field):
                d=copy.deepcopy(DOC);text='资料里列有投屏功能'
                if field=='caption':d['paragraphs'][0][field]=text
                else:d[field]=[text] if field=='tags' else text
                self.assertTrue(pub.voice_issues(d))
    def test_cta_cannot_broadcast_evidence(self):
        d=copy.deepcopy(DOC);d['cta']='目前能确认的是70 Wh。'
        self.assertTrue(pub.voice_issues(d))
    def test_internal_heading_ignored(self):
        d=copy.deepcopy(DOC);d['paragraphs'][0]['heading']='资料里列有/到店问清楚'
        self.assertFalse(pub.voice_issues(d))
    def test_style_check_does_not_mutate_copy(self):
        d=copy.deepcopy(DOC);d['lead']='下面按这个顺序看';before=copy.deepcopy(d)
        self.assertTrue(pub.style_issues(d,voice=True));self.assertEqual(d,before)
    def test_existing_natural_copy_is_not_retroactively_voice_blocked(self):
        t=prepared();t['publication_policy_version']=pub.VERSION;t['document']['lead']='下面按这个顺序看产品。'
        self.assertFalse(any('编排旁白' in i['detail'] for i in w.deterministic_review(t)))
        t['writer_voice_version']=pw.VOICE_VERSION
        self.assertTrue(any('编排旁白' in i['detail'] for i in w.deterministic_review(t)))
    def test_writer_projection_excludes_generated_workflow_advice(self):
        payload=dict(brief=dict(goal='引导咨询和到店体验',audience='职场',strategy='每段到店核对',
            message_strategy=dict(theme='轻装随行',angle='每段到店核对'),retrieval_plan=dict(facts=['问清续航']),
            requirements=dict(user_constraints=dict(value='保留70 Wh',source='explicit'))),
            selected_points=[dict(id='C4',fact_ids=['F03'],conditions=['额定容量'],recommendation_reason='到店问续航',scores={})],
            retrieval_requests=['未知兼容'],mandatory_requests=[dict(fact_ids=['F03'])])
        before=copy.deepcopy(payload);out=pw.writing_payload(payload)
        self.assertEqual(payload,before)
        self.assertNotIn('strategy',out['brief']);self.assertNotIn('message_strategy',out['brief'])
        self.assertNotIn('retrieval_plan',out['brief']);self.assertNotIn('retrieval_requests',out)
        self.assertNotIn('recommendation_reason',out['selected_points'][0])
        self.assertEqual(out['brief']['requirements'],payload['brief']['requirements'])
        self.assertEqual(out['mandatory_requests'],payload['mandatory_requests'])
        self.assertEqual(out['selected_points'][0]['fact_ids'],['F03'])
        self.assertEqual(out['brief']['core_theme'],'轻装随行')
    def test_explicit_goal_wins_over_projection(self):
        out=pw.writing_payload(dict(brief=dict(goal='模型添加到店',requirements=dict(marketing_goal=dict(value='介绍产品',source='explicit')))))
        self.assertEqual(out['writer_contract']['marketing_goal'],'介绍产品')
    def test_repair_keeps_original_diagnostic_for_audit_but_not_as_instruction(self):
        t=prepared();payload=dict(brief=dict(strategy='到店问'),plan=copy.deepcopy(t['plan']),document=copy.deepcopy(DOC),
            issues=[w.issue('platform','全文','建议改成资料里列有')])
        with patch.object(pw.llm,'complete',AsyncMock(return_value=copy.deepcopy(DOC))) as model:
            asyncio.run(pw.repair(t,w.BASE,payload,S.Document))
        self.assertEqual(t['writer_runs'][-1]['revision_issues'],payload['issues'])
        self.assertNotIn('strategy',model.call_args.args[2]['brief'])
        self.assertIn('不照搬建议措辞',model.call_args.args[2]['writer_contract']['reviewer_suggestions'])
        self.assertIn('Reviewer建议仅用于识别风险',model.call_args.args[1])
    def test_all_nine_bundles_load_voice_experience(self):
        for platform in ('moments','xiaohongshu','wechat'):
            for stage in ('outline','draft','repair'):
                with self.subTest(platform=platform,stage=stage):
                    bundle=mm.writer_bundle(platform,stage)
                    self.assertIn('brand_promotion_v1',bundle['text'])
                    self.assertIn('五类反例',bundle['text'])
                    self.assertIn('无忧使用',bundle['text'])
    def test_manifest_matches_adapter_and_pinned_sources(self):
        manifest=json.loads((mm.ROOT/'planner_sources.json').read_text(encoding='utf-8-sig'))
        self.assertEqual(manifest['writer_adapter_sha256'],mm.writer_bundle('wechat','repair')['adapter_sha256'])
        for name in manifest['skill_sources']:mm.source_record(name)
    def test_new_write_uses_profile_and_repair_removes_leak(self):
        t=prepared();bad=copy.deepcopy(DOC);bad['paragraphs'][0]['text']+='资料里列有投屏。'
        clean=copy.deepcopy(DOC)
        with patch.object(w.llm,'complete',AsyncMock(side_effect=[bad,dict(summary='fixture',issues=[]),clean,dict(summary='fixture',issues=[])])) as model:
            asyncio.run(w.write(t))
        self.assertEqual(model.await_count,4);self.assertEqual(t['writer_voice_version'],pw.VOICE_VERSION)
        self.assertEqual(t['status'],'approved');self.assertEqual(t['repair_before'],bad)
        self.assertEqual(t['document'],clean)
        self.assertIn('成熟品牌宣传口吻',model.call_args_list[1].args[1])
