"""Four approved references: routing, integrity, boundaries and actual Writer wiring."""
import asyncio,copy,hashlib,json,shutil,tempfile,unittest
from pathlib import Path
from unittest.mock import AsyncMock,patch
from backend import writer_cases as wc,marketing_methods as mm,platform_writer as pw,workflow as w,schemas as S
from backend.test_workflow import prepared,DOC,PLAN
from backend import test_writer_responsibilities as fixtures

class WriterCaseTests(unittest.TestCase):
    def test_exact_user_allowlist(self):
        manifest=json.loads((wc.ROOT/'cases.json').read_text(encoding='utf-8'))
        self.assertEqual(len(manifest['cases']),4)
        self.assertEqual({r['case_id']:r['source_url'] for r in manifest['cases']},wc.APPROVED)
        self.assertTrue(all(r['selection_status']=='user_approved_reference' for r in manifest['cases']))

    def test_platform_stage_routes_and_distinct_excerpts(self):
        expected={'wechat':['C019','C020','C021'],'xiaohongshu':['C019','C020','C021','C022'],'moments':['C021','C022']}
        for platform,ids in expected.items():
            stage_hashes=[]
            for stage in wc.STAGES:
                with self.subTest(platform=platform,stage=stage):
                    b=wc.bundle(platform,stage)
                    self.assertEqual([s['case_id'] for s in b['sources']],ids)
                    self.assertEqual({s['heading'] for s in b['sources']},{wc.STAGES[stage]})
                    stage_hashes.append(tuple(s['excerpt_sha256'] for s in b['sources']))
                    for s in b['sources']:self.assertIn(f'<case-method id="{s["case_id"]}" stage="{stage}">',b['text'])
            self.assertEqual(len(set(stage_hashes)),3)

    def test_metadata_and_obsolete_claims_are_not_model_excerpts(self):
        manifest=json.loads((wc.ROOT/'cases.json').read_text(encoding='utf-8'))
        for stage in wc.STAGES:
            b=wc.bundle('xiaohongshu',stage)
            for r in manifest['cases']:
                self.assertNotIn(r['title'],b['text'])
                self.assertNotIn(r['source_url'],b['text'])
                self.assertNotIn(r['publish_date'],b['text'])
            self.assertNotIn('2000元',b['text'])
            self.assertNotIn('烟台微星',b['text'])
            self.assertNotIn('70 Wh',b['text'])
            self.assertNotIn('140 W',b['text'])

    def test_bad_route_arguments(self):
        for platform,stage in [('other','outline'),('wechat','other')]:
            with self.assertRaises(ValueError):wc.bundle(platform,stage)

    def mutate(self,change,expected):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'references';shutil.copytree(wc.ROOT,root)
            manifest=json.loads((root/'cases.json').read_text(encoding='utf-8'))
            change(root,manifest)
            (root/'cases.json').write_text(json.dumps(manifest),encoding='utf-8')
            with patch.object(wc,'ROOT',root):
                with self.assertRaisesRegex(ValueError,expected):wc.bundle('xiaohongshu','draft')

    def test_tamper_rejected(self):
        def change(root,m):(root/m['cases'][0]['path']).write_text('changed',encoding='utf-8')
        self.mutate(change,'checksum mismatch')

    def test_path_escape_rejected(self):
        self.mutate(lambda root,m:m['cases'][0].update(path='../outside.md'),'outside reference library')

    def test_unapproved_case_or_url_rejected(self):
        self.mutate(lambda root,m:m['cases'].append(dict(m['cases'][0],case_id='C001')),'allowlist mismatch')
        self.mutate(lambda root,m:m['cases'][0].update(source_url='https://example.com'),'source mismatch')

    def test_missing_stage_rejected_even_with_updated_checksum(self):
        def change(root,m):
            r=m['cases'][0];p=root/r['path']
            p.write_text(p.read_text(encoding='utf-8').replace('## Draft principles','## Unavailable'),encoding='utf-8')
            r['sha256']=hashlib.sha256(p.read_bytes()).hexdigest()
        self.mutate(change,'Missing or duplicate case stage')

    def test_outline_and_draft_receive_actual_methods_and_audit_sources(self):
        fixture=fixtures.WriterResponsibilitiesTests();t=fixture.selected('moments')
        with patch.object(w.llm,'complete',AsyncMock(side_effect=fixture.fake)) as model:
            asyncio.run(w.write(t))
        self.assertEqual(model.await_count,3) # two Writer calls plus unchanged independent review
        self.assertEqual([r['stage'] for r in t['writer_runs']],['outline','draft'])
        for call,run in zip(model.call_args_list,t['writer_runs']):
            self.assertEqual([s['case_id'] for s in run['case_sources']],['C021','C022'])
            for s in run['case_sources']:
                self.assertIn(f'<case-method id="{s["case_id"]}" stage="{run["stage"]}">',call.args[1])
                self.assertEqual(len(s['sha256']),64)
                self.assertEqual(len(s['excerpt_sha256']),64)
        self.assertEqual(t['writer_runs'][0]['method_sources'],['copywriting','social'])
        self.assertTrue(w.can_export(t))

    def test_repair_receives_repair_only_and_preserves_existing_contract(self):
        t=prepared();payload=dict(plan=copy.deepcopy(PLAN),document=copy.deepcopy(DOC),issues=[w.issue('fact','携带','修正措辞')])
        with patch.object(pw.llm,'complete',AsyncMock(return_value=copy.deepcopy(DOC))) as model:
            asyncio.run(pw.repair(t,w.BASE,payload,S.Document))
        self.assertEqual(model.await_count,1)
        run=t['writer_runs'][-1]
        self.assertEqual(run['method_sources'],['copy-editing'])
        self.assertEqual([s['case_id'] for s in run['case_sources']],['C021','C022'])
        self.assertIn('stage="repair"',model.call_args.args[1])
        self.assertNotIn('stage="outline"',model.call_args.args[1])
        self.assertEqual(run['revision_issues'],payload['issues'])

    def test_adapter_manifest_hash_matches(self):
        manifest=json.loads((mm.ROOT/'planner_sources.json').read_text(encoding='utf-8-sig'))
        self.assertEqual(mm.writer_bundle('wechat','draft')['adapter_sha256'],manifest['writer_adapter_sha256'])
