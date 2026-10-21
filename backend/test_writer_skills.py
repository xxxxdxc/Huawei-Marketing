"""Stage-specific skill routing and bounded copy editing; no provider calls."""
import asyncio,copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import AsyncMock,patch
from backend.test_workflow import prepared,DOC,PLAN
from backend import marketing_methods as mm,platform_writer as pw,workflow as w,schemas as S

class WriterSkillTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from backend import storage as db
        db.init()
    def test_route_by_platform_and_stage(self):
        for platform in ('moments','xiaohongshu','wechat'):
            extra='content-creation' if platform=='wechat' else 'social'
            for stage,expected in [('outline',['copywriting',extra]),('draft',['copywriting',extra,'copy-editing']),('repair',['copy-editing'])]:
                with self.subTest(platform=platform,stage=stage):
                    bundle=mm.writer_bundle(platform,stage)
                    self.assertEqual(bundle['method_sources'],expected)
                    self.assertEqual([r['skill'] for r in bundle['sources']],expected)
                    self.assertEqual(len(bundle['adapter_sha256']),64)
                    self.assertIn('不放进正文',bundle['text'])
    def test_sources_are_pinned_and_actual_excerpts(self):
        b=mm.writer_bundle('wechat','draft')
        for s in b['sources']:
            self.assertEqual(len(s['commit']),40);self.assertEqual(len(s['sha256']),64)
            for heading in s['headings']:self.assertIn(heading,b['text'])
        self.assertIn('Front-load key information',b['text'])
        self.assertNotIn('### Sweep 7: Zero Risk',b['text'])
    def test_social_is_not_loaded_for_wechat(self):
        self.assertNotIn('<method name="social">',mm.writer_bundle('wechat','outline')['text'])
    def test_long_form_is_not_loaded_for_social_platforms(self):
        for platform in ('moments','xiaohongshu'):
            self.assertNotIn('<method name="content-creation">',mm.writer_bundle(platform,'draft')['text'])
    def test_repair_only_uses_point_edit_methods(self):
        b=mm.writer_bundle('moments','repair')
        self.assertIn('A point edit skips the Seven Sweeps',b['text'])
        self.assertNotIn('### Sweep 6: Heightened Emotion',b['text'])
        self.assertNotIn('### Sweep 7: Zero Risk',b['text'])
        self.assertNotIn('Publishing From Your Agent',b['text'])
    def test_bad_route_is_not_silently_fallback(self):
        for platform,stage in [('unknown','draft'),('wechat','unknown')]:
            with self.assertRaises(ValueError):mm.writer_bundle(platform,stage)
    def test_unknown_optional_skill_is_disabled(self):
        with self.assertRaises(ValueError):mm.sections('wechat-article-writing',['# Writing'])
    def test_missing_heading_fails_explicitly(self):
        with self.assertRaisesRegex(ValueError,'Missing pinned Skill section'):mm.sections('copywriting',['## nonexistent'])
    def test_source_tampering_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'vendor/example').mkdir(parents=True)
            (root/'vendor/example/SKILL.md').write_text('changed',encoding='utf-8')
            (root/'planner_sources.json').write_text(json.dumps(dict(skill_sources={'sample':dict(path='vendor/example/SKILL.md',sha256='0'*64)})),encoding='utf-8')
            with patch.object(mm,'ROOT',root):
                with self.assertRaisesRegex(ValueError,'checksum mismatch'):mm.sections('sample',['# Writing'])
    def test_source_path_must_remain_vendored(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'planner_sources.json').write_text(json.dumps(dict(skill_sources={'sample':dict(path='../outside',sha256='0'*64)})),encoding='utf-8')
            with patch.object(mm,'ROOT',root):
                with self.assertRaisesRegex(ValueError,'vendored'):mm.source_record('sample')
    def payload(self):
        return dict(plan=copy.deepcopy(PLAN),document=copy.deepcopy(DOC),issues=[w.issue('fact','携带','修正措辞')])
    def test_valid_point_edit_preserves_untouched_fields(self):
        payload=self.payload();d=copy.deepcopy(DOC);d['paragraphs'][0]['text']='机身约1.33 kg。'
        self.assertEqual(pw.validate_repair(payload,d),d)
    def test_repair_cannot_change_structure_images_or_scope(self):
        for key,value in [('section_id','unknown'),('image_id',None),('fact_ids',['unknown'])]:
            with self.subTest(key=key):
                d=copy.deepcopy(DOC);d['paragraphs'][0][key]=value
                with self.assertRaises(ValueError):pw.validate_repair(self.payload(),d)
    def test_local_edit_cannot_change_unrelated_title(self):
        d=copy.deepcopy(DOC);d['title']='擅自改标题'
        with self.assertRaisesRegex(ValueError,'无关字段'):pw.validate_repair(self.payload(),d)
    def test_title_edit_cannot_rewrite_unrelated_paragraph(self):
        payload=self.payload();payload['issues']=[w.issue('platform','标题','标题重复')]
        d=copy.deepcopy(DOC);d['paragraphs'][0]['text']='擅自改正文'
        with self.assertRaisesRegex(ValueError,'无关段落'):pw.validate_repair(payload,d)
    def test_repair_failure_is_recorded_and_original_kept(self):
        t=prepared();payload=self.payload();changed=copy.deepcopy(DOC);changed['paragraphs'][0]['image_id']=None
        with patch.object(pw.llm,'complete',AsyncMock(return_value=changed)):
            with self.assertRaises(ValueError):asyncio.run(pw.repair(t,w.BASE,payload,S.Document))
        self.assertEqual(t['document'],DOC);self.assertEqual(t['writer_runs'][-1]['status'],'failed')
        self.assertEqual(t['writer_runs'][-1]['method_sources'],['copy-editing'])
        self.assertTrue(t['writer_runs'][-1]['skill_sources'])
        self.assertEqual(t['writer_runs'][-1]['revision_issues'],payload['issues'])
    def test_existing_repair_path_then_full_review(self):
        t=prepared();bad=copy.deepcopy(DOC);bad['paragraphs'][0]['text']+='重量会因配置而异。'
        outputs=[bad,dict(summary='synthetic',issues=[]),copy.deepcopy(DOC),dict(summary='synthetic',issues=[])]
        with patch.object(w.llm,'complete',AsyncMock(side_effect=outputs)) as model:asyncio.run(w.write(t))
        self.assertEqual(model.await_count,4)
        self.assertEqual([r['stage'] for r in t['writer_runs']],['draft','repair'])
        self.assertEqual(t['writer_runs'][0]['method_sources'],['copywriting','social','copy-editing'])
        self.assertEqual(t['writer_runs'][1]['method_sources'],['copy-editing'])
        self.assertTrue(w.can_export(t));self.assertEqual(t['repair_before'],bad)
        self.assertNotIn('Sweep 7: Zero Risk',model.call_args_list[2].args[1])
