"""Numeric quote evidence regression. No provider calls; isolated workflow fixture."""
import asyncio,copy,unittest
from unittest.mock import AsyncMock,patch
from backend.test_workflow import prepared,DOC,TEST_DATA
from backend import numeric_evidence as ne,workflow as w,storage as db
from pathlib import Path

class NumericEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not db.DB.is_relative_to(Path(TEST_DATA.name)):
            raise RuntimeError('Numeric tests must use the temporary fixture database')
        db.init()
    def values(self,text):return {(x['value'],x['unit']) for x in ne.atoms(text)}
    def case(self,quote='展开厚度左右约7.6/7.3 mm，闭合厚度14.9 mm。',text='左半屏厚约7.6 mm，右半屏厚约7.3 mm。'):
        t=prepared();f=t['package']['facts'][0];f.update(claim='未核验的卖点描述',quote=quote,conditions='左指摄像头所在的左半屏，右指另一半屏。')
        t['package']['sources'][0]['text']=quote
        t['document']['paragraphs'][0].update(text=text,caption='实物图')
        return t
    def test_shared_unit_regression(self):
        t=self.case();self.assertFalse(w.deterministic_review(t));r=ne.audit(t)
        self.assertEqual(len(r['checks']),2);self.assertTrue(all(c['matched_fact_ids']==['F01'] for c in r['checks']))
    def test_three_value_dimensions(self):
        self.assertEqual(self.values('尺寸310×222×13.5 mm'),{('310','mm'),('222','mm'),('13.5','mm')})
    def test_ascii_dimensions(self):
        self.assertEqual(self.values('310 x 222 x 13.5 mm'),{('310','mm'),('222','mm'),('13.5','mm')})
    def test_fullwidth_values_units_and_punctuation(self):
        t=self.case('展开厚度左右约７．６／７．３ ｍｍ。')
        self.assertFalse(ne.audit(t)['issues'])
    def test_unicode_space(self):
        self.assertEqual(self.values('约7.6\u00a0mm，7.3\u202fmm'),{('7.6','mm'),('7.3','mm')})
    def test_unicode_unit_symbol(self):
        self.assertEqual(self.values('7.6㎜'),{('7.6','mm')})
    def test_decimal_equivalence(self):
        self.assertFalse(ne.audit(self.case('左厚度7.60 mm，右厚度7.30 mm。'))['issues'])
    def test_no_rounding(self):
        self.assertTrue(ne.audit(self.case('厚度7.64 mm。','厚度7.6 mm。'))['issues'])
    def test_no_unit_conversion(self):
        self.assertTrue(ne.audit(self.case('重量1.16 kg。','重量1160 g。'))['issues'])
    def test_known_unit_spelling_aliases(self):
        self.assertFalse(ne.audit(self.case('厚度7.6毫米。','厚度7.6 mm。'))['issues'])
    def test_changed_number_rejected(self):
        self.assertTrue(ne.audit(self.case(text='左半屏厚7.8 mm。'))['issues'])
    def test_changed_unit_rejected(self):
        self.assertTrue(ne.audit(self.case(text='左半屏厚7.6 kg。'))['issues'])
    def test_substring_numeric_value_not_accepted(self):
        self.assertTrue(ne.audit(self.case('厚17.6 mm。','厚7.6 mm。'))['issues'])
    def test_decimal_suffix_not_split(self):
        self.assertEqual(self.values('17.6 mm'),{('17.6','mm')})
        self.assertEqual(self.values('0.76 mm'),{('0.76','mm')})
    def test_sign_preserved(self):
        self.assertTrue(ne.audit(self.case('厚度-7.6 mm。','厚度7.6 mm。'))['issues'])
    def test_fractions_are_not_expanded(self):
        self.assertNotIn(('1','mm'),self.values('厚度1/2 mm'))
        self.assertTrue(ne.audit(self.case('厚度1/2 mm。','厚度1 mm。'))['issues'])
    def test_arithmetic_not_evaluated(self):
        self.assertTrue(ne.audit(self.case('计算2×3 mm。','厚度6 mm。'))['issues'])
        self.assertNotIn(('2','mm'),self.values('计算2×3 mm'))
    def test_no_unit_borrowed_across_sentence(self):
        self.assertTrue(ne.audit(self.case('左7.6。右7.3 mm。','左7.6 mm。'))['issues'])
    def test_no_unit_borrowed_across_facts(self):
        t=self.case('左7.6/','左7.6 mm。')
        f=copy.deepcopy(t['package']['facts'][0]);f.update(id='F02',quote='右7.3 mm。')
        t['package']['facts'].append(f);t['document']['paragraphs'][0]['fact_ids'].append('F02')
        self.assertTrue(ne.audit(t)['issues'])
    def test_claim_is_not_quote_evidence(self):
        t=self.case('厚度7.3 mm。','厚度7.6 mm。');t['package']['facts'][0]['claim']='厚度7.6 mm'
        self.assertTrue(ne.audit(t)['issues'])
    def test_conditions_do_not_invent_quote_evidence(self):
        t=self.case('厚度7.3 mm。','厚度7.6 mm。');t['package']['facts'][0]['conditions']='7.6 mm'
        self.assertTrue(ne.audit(t)['issues'])
    def test_paragraph_cannot_borrow_another_fact(self):
        t=self.case('厚度7.3 mm。','厚度7.6 mm。')
        f=copy.deepcopy(t['package']['facts'][0]);f.update(id='F02',quote='厚度7.6 mm。');t['package']['facts'].append(f)
        self.assertTrue(ne.audit(t)['issues'])
    def test_paragraph_with_correct_reference_passes(self):
        t=self.case();t['document']['paragraphs'][0]['fact_ids']=[]
        self.assertTrue(ne.audit(t)['issues']);t['document']['paragraphs'][0]['fact_ids']=['F01']
        self.assertFalse(ne.audit(t)['issues'])
    def test_root_fields_use_authorized_declared_facts(self):
        t=self.case();t['document']['title']='厚约7.6 mm'
        self.assertFalse(ne.audit(t)['issues'])
        t['document']['paragraphs'][0]['fact_ids']=[]
        self.assertTrue(any(i['location']=='标题' for i in ne.audit(t)['issues']))
    def test_unplanned_root_fact_rejected(self):
        t=self.case();t['document']['title']='厚度19 mm'
        f=copy.deepcopy(t['package']['facts'][0]);f.update(id='F02',quote='厚度19 mm。');t['package']['facts'].append(f)
        t['document']['paragraphs'][0]['fact_ids'].append('F02')
        self.assertTrue(any(i['location']=='标题' for i in ne.audit(t)['issues']))
    def test_each_public_field_is_checked(self):
        for field in ('title','lead','cta','tags','caption'):
            t=self.case()
            if field=='caption':t['document']['paragraphs'][0][field]='7.8 mm'
            else:t['document'][field]=['7.8 mm'] if field=='tags' else '7.8 mm'
            self.assertTrue(ne.audit(t)['issues'])
    def test_internal_heading_not_checked(self):
        t=self.case();t['document']['paragraphs'][0]['heading']='内部7.8 mm'
        self.assertFalse(ne.audit(t)['issues'])
    def test_issues_locate_section_and_cited_facts(self):
        r=ne.audit(self.case(text='厚度7.8 mm。'));i=r['issues'][0]
        self.assertEqual(i['location'],'正文 P1');self.assertIn('F01',i['detail']);self.assertIn('7.8',i['detail'])
    def test_audit_has_verbatim_source_quote(self):
        t=self.case();r=ne.audit(t)
        self.assertEqual(r['checks'][0]['evidence'][0]['quote'],t['package']['facts'][0]['quote'])
    def test_audit_does_not_change_any_task_content(self):
        t=self.case();before=copy.deepcopy(t);ne.audit(t);self.assertEqual(t,before)
    def test_sides_swapped_still_requires_semantic_review(self):
        t=self.case(text='左半屏厚约7.3 mm，右半屏厚约7.6 mm。')
        self.assertFalse(ne.audit(t)['issues'])
        result=dict(summary='左右互换',issues=[w.issue('fact','正文 P1','左右厚度与原文不符')])
        with patch.object(w.llm,'complete',AsyncMock(return_value=result)) as model:asyncio.run(w.review(t))
        self.assertEqual(model.await_count,1);self.assertEqual(t['status'],'needs_review')
        self.assertIn('左右互换',model.call_args.args[1]);self.assertTrue(t['review']['issues'])
    def test_review_records_checks_and_does_not_call_writer(self):
        t=self.case();before=copy.deepcopy(t['document'])
        with patch.object(w.llm,'complete',AsyncMock(return_value=dict(summary='synthetic',issues=[]))) as model,patch.object(w.pw,'repair',AsyncMock()) as repair:
            asyncio.run(w.review(t,allow_repair=False))
        self.assertEqual(model.await_count,1);repair.assert_not_called();self.assertEqual(t['document'],before)
        self.assertTrue(t['review']['numeric_checks']['checks'][0]['supported'])

    def test_decimal_precision_never_rounds_into_a_match(self):
        quote='厚度7.600000000000000000000000000001 mm。'
        text='厚度7.600000000000000000000000000002 mm。'
        self.assertTrue(ne.audit(self.case(quote,text))['issues'])
