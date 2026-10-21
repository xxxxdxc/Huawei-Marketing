"""Reader-facing publication boundaries; synthetic evidence, isolated DB, no provider."""
import asyncio,copy,io,json,unittest,zipfile
from unittest.mock import AsyncMock,patch
from backend.test_workflow import prepared,DOC,PLAN
from backend import workflow as w,storage as db,publication_rules as pub
from backend.main import app
from backend.settings import ASSETS
from fastapi.testclient import TestClient
from PIL import Image

NOTE="实际尺寸和重量会因配置、制造工艺和测量方法有所差异。"

class PublicationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):db.init()
    def test_generic_note_is_not_a_required_fact_qualifier(self):
        facts=[dict(id='F1',conditions=NOTE+'；Windows版支持十点触控')]
        before=copy.deepcopy(facts);g=pub.condition_guidance(facts)[0]
        self.assertEqual(facts,before);self.assertEqual(g['internal_notes'],[NOTE])
        self.assertEqual(g['meaningful_conditions'],['Windows版支持十点触控'])
    def test_mixed_and_unknown_conditions_remain_required(self):
        text="仅限特定配置，重量因配置、制造工艺和测量方法有所差异"
        self.assertEqual(pub.condition_guidance([dict(id='F1',conditions=text)])[0]['meaningful_conditions'],[text])
    def test_approximate_value_and_version_are_natural_public_copy(self):
        d=copy.deepcopy(DOC);d['paragraphs'][0]['text']='Windows版支持十点触控，机身约1.33 kg。'
        self.assertFalse(pub.generic_notes(pub.reader_text(d)))
    def test_generic_variants_are_detected(self):
        for text in (NOTE,'重量会因配置而异。','具体以实际购买的版本为准。','以实际配置为准。'):
            with self.subTest(text=text):self.assertTrue(pub.generic_notes(text))
    def test_headings_are_internal_to_consumer_checks(self):
        t=prepared();t['document']['paragraphs'][0]['heading']='内部排查：全网最低 999 元'
        self.assertFalse(w.deterministic_review(t))
    def test_real_consumer_claim_still_checked(self):
        t=prepared();t['document']['paragraphs'][0]['text']='全网最低 999 元'
        self.assertTrue(w.deterministic_review(t))
    def test_new_generic_copy_requires_repair(self):
        t=prepared();t['publication_policy_version']=pub.VERSION;t['document']['paragraphs'][0]['text']+=NOTE
        self.assertTrue(any('通用证据说明' in i['detail'] and i['repairable'] for i in w.deterministic_review(t)))
    def test_legacy_body_not_rewritten_or_new_style_blocked(self):
        t=prepared();t['document']['paragraphs'][0]['text']+=NOTE
        t['document']['paragraphs'][0]['text']+=t['document']['cta']
        before=copy.deepcopy(t)
        self.assertFalse(w.deterministic_review(t));self.assertEqual(t,before)
    def test_duplicate_cta_detected_without_erasing_anchors(self):
        d=copy.deepcopy(DOC);d['paragraphs'][0]['text']+='欢迎，咨询我们的门店！'
        before=copy.deepcopy(d);issues=pub.style_issues(d)
        self.assertTrue(any('cta重复' in i['detail'] for i in issues));self.assertEqual(d,before)
    def test_new_writer_repair_reviewer_cycle_does_not_restore_disclaimers(self):
        t=prepared();t['document']=None
        bad=copy.deepcopy(DOC);bad['paragraphs'][0]['text']+=NOTE+bad['cta']
        clean=copy.deepcopy(DOC)
        replies=[bad,dict(summary='synthetic',issues=[]),clean,dict(summary='synthetic',issues=[])]
        with patch.object(w.llm,'complete',AsyncMock(side_effect=replies)) as model,patch.object(w,'get_settings',return_value=dict(writer_model='fixture-writer',reviewer_model='fixture-reviewer',vision=True)):
            asyncio.run(w.write(t))
        self.assertEqual(model.await_count,4);self.assertEqual(t['publication_policy_version'],pub.VERSION)
        self.assertEqual(t['status'],'approved');self.assertEqual(t['document'],clean)
        self.assertEqual(t['repair_before'],bad)
        self.assertIn('不恢复通用免责声明',model.call_args_list[2].args[1])
        self.assertIn('完整保留在内部',model.call_args_list[0].args[1])
    def approved(self):
        t=prepared('approved');t['document']['paragraphs'][0]['heading']='STAFF_ONLY_GUIDE'
        t['package']['facts'][0]['conditions']=NOTE
        t['package']['images'][0].update(source='private/fixture-path',mime='image/png')
        buffer=io.BytesIO();Image.new('RGB',(2,2),'white').save(buffer,format='PNG')
        (ASSETS/t['package']['images'][0]['id']).write_bytes(buffer.getvalue())
        t['review']=dict(passed=True,summary='synthetic',issues=[],document_hash=db.digest(t))
        return db.save(t,'synthetic approved')
    def test_clean_markdown_and_separate_evidence(self):
        t=self.approved();before=copy.deepcopy(t)
        text=w.markdown(t);evidence=w.markdown(t,include_evidence=True)
        self.assertNotIn('STAFF_ONLY_GUIDE',text);self.assertNotIn('知识库依据',text)
        self.assertNotIn(NOTE,text);self.assertNotIn('private/fixture-path',text)
        self.assertIn(NOTE,evidence);self.assertIn('知识库依据',evidence);self.assertEqual(t,before)
    def test_export_zip_preserves_evidence_and_legacy_database_body(self):
        t=self.approved();body=copy.deepcopy(t['document'])
        with TestClient(app) as c:
            result=c.get(f"/api/tasks/{t['id']}/export?bundle=true")
            self.assertEqual(result.status_code,200)
            with zipfile.ZipFile(io.BytesIO(result.content)) as z:
                self.assertIn('evidence.md',z.namelist())
                self.assertNotIn('STAFF_ONLY_GUIDE',z.read('marketing.md').decode())
                self.assertIn(NOTE,z.read('evidence.md').decode())
            self.assertEqual(db.get(t['id'])['document'],body)


    def test_internal_heading_repeated_as_body_label_is_repairable(self):
        d=copy.deepcopy(DOC);d['paragraphs'][0]['text']=d['paragraphs'][0]['heading']+'：\n'+d['paragraphs'][0]['text']
        self.assertTrue(any('内部阅读提示' in i['detail'] for i in pub.style_issues(d)))
