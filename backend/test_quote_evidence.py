"""Bounded formatting repair never substitutes numerical or semantic claims."""
import asyncio,copy,unittest
from unittest.mock import patch,AsyncMock
from backend.test_workflow import prepared
from backend import quote_evidence as qe,workflow as w

def package(text='重量约1.33 kg；屏幕支持触控，具体以该配置为准。',quote='重量约1.33 kg;屏幕支持触控,具体以该配置为准。'):
    return dict(product=dict(id='test',name='测试型号'),sources=[dict(id='S1',text=text)],facts=[dict(id='F1',source_id='S1',quote=quote,claim='示例事实',conditions='该配置')],coverage=[dict(request_id='R1',status='supported',fact_ids=['F1'],reason='原文支持')])

class QuoteTests(unittest.TestCase):
    def setUp(self):
        from backend import storage as db
        db.init()
    def test_punctuation_restores_real_contiguous_source(self):
        p=package();self.assertEqual(qe.reconcile(p),[]);w.verify_facts(p)
        self.assertEqual(p['facts'][0]['quote'],p['sources'][0]['text']);a=p['quote_repairs'][0]
        self.assertEqual(p['sources'][0]['text'][a['start']:a['end']],a['quote']);self.assertNotEqual(a['original_quote'],a['quote'])
    def test_digits_units_negative_sign_and_sentence_gaps_are_not_ignored(self):
        for quote in ('重量约1.34 kg','重量约1.33 g','重量约-1.33 kg','重量约1.33 kg具体以该配置为准。'):
            with self.subTest(quote=quote):
                p=package(quote=quote);self.assertEqual(len(qe.reconcile(p)),1);self.assertEqual(p['facts'],[])
                self.assertEqual(p['coverage'][0]['status'],'not_found')
    def test_full_width_and_whitespace_only_are_equivalent(self):
        p=package(text='重量约１.３３ kg；屏幕支持触控。',quote='重量约1.33kg; 屏幕支持触控。')
        self.assertEqual(qe.reconcile(p),[]);w.verify_facts(p)
    def test_one_bad_card_does_not_remove_good_card_or_dangle_references(self):
        p=package();p['facts'].append(dict(p['facts'][0],id='F2',quote='原文里根本没有这一句'))
        p['coverage'][0]['fact_ids']=['F1','F2'];qe.reconcile(p)
        self.assertEqual([f['id'] for f in p['facts']],['F1']);self.assertEqual(p['coverage'][0]['status'],'partial')
        self.assertEqual(p['coverage'][0]['fact_ids'],['F1']);self.assertEqual(p['unresolved_fact_ids'],['F2'])
    def test_missing_source_and_duplicate_ids_are_quarantined(self):
        p=package();p['facts'][0]['source_id']='missing';qe.reconcile(p);self.assertFalse(p['facts'])
        p=package();p['facts'].append(copy.deepcopy(p['facts'][0]));qe.reconcile(p);self.assertFalse(p['facts'])
    def test_targeted_correction_restores_coverage_without_new_ids(self):
        t=prepared();t['package']=package(quote='模型改写了这句原文')
        fixed=dict(t['package']['facts'][0],quote=t['package']['sources'][0]['text'])
        with patch.object(w.llm,'complete',AsyncMock(return_value={'facts':[fixed]})) as model:asyncio.run(w.reconcile_extracted(t))
        self.assertEqual(model.await_count,1);self.assertEqual(t['package']['coverage'][0]['status'],'supported')
        self.assertEqual(t['package']['coverage'][0]['fact_ids'],['F1']);w.verify_facts(t['package'])
    def test_unknown_corrected_id_is_not_adopted(self):
        t=prepared();t['package']=package(quote='模型改写了这句原文')
        fixed=dict(t['package']['facts'][0],id='NEW',quote=t['package']['sources'][0]['text'])
        with patch.object(w.llm,'complete',AsyncMock(return_value={'facts':[fixed]})):asyncio.run(w.reconcile_extracted(t))
        self.assertFalse(t['package']['facts'])
