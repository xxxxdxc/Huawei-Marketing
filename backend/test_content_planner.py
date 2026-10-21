"""Planner-specific gates/compatibility/layout tests. Synthetic evidence only."""
import asyncio,copy,unittest
from unittest.mock import patch
from pydantic import ValidationError
from backend.test_workflow import prepared,PLAN,DOC
from backend import content_planner as cp,workflow as w,schemas as S
from backend.content_layout import effective_layout,default_position
from backend.planner_test_data import AsyncMock

def valid(platform='moments'):
    t=prepared();t['platform']=platform;t['brief']['platform']=platform
    n={'moments':1,'wechat':2,'xiaohongshu':3}[platform]
    t['package']['images']=[dict(id=chr(97+i)*20,model_verified=True,visual_checked=True,usable=True) for i in range(n)]
    old=copy.deepcopy(PLAN);old['sections']=[dict(old['sections'][0],id=f'P{i+1}',purpose=f'解答问题{i+1}',image_id=chr(97+i)*20) for i in range(n)]
    model=AsyncMock(return_value=old)
    with patch.object(cp.llm,'complete',model):plan=asyncio.run(cp.generate(t,w.PLATFORMS[platform],w.BASE))
    from backend.test_point_selection import compose
    payload=cp.shared_context(t,w.PLATFORMS[platform]) | dict(selected_point_ids=plan['selected_point_ids'],ranked_candidates=plan['planning_analysis']['candidates'])
    legacy=compose(payload);legacy['planning_analysis']=plan['planning_analysis']
    return t,legacy

class PlannerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from backend import storage as db
        db.init()
    def test_two_calls_and_no_document(self):
        t,p=valid();self.assertEqual(p['schema_version'],'2');self.assertEqual(t['planner_runs'][-1]['status'],'complete');self.assertNotIn('document',p)
    def test_weighted_score_is_server_computed(self):
        t,p=valid();c=p['planning_analysis']['candidates'][0];self.assertEqual(c['total_score'],75);self.assertEqual(c['rank'],1)
    def test_evidence_conditions_are_merged(self):
        t,p=valid();self.assertIn('实际因配置而异',p['planning_analysis']['candidates'][0]['conditions'])
    def test_unknown_candidate_fact_rejected(self):
        t,p=valid();c=copy.deepcopy(p['planning_analysis']['candidates'][0]);c.pop('total_score');c.pop('rank');c['fact_ids']=['F999']
        with self.assertRaises(ValueError):cp.rank_candidates(t,dict(product_id=t['product_id'],candidates=[c]))
    def test_unknown_candidate_image_rejected(self):
        t,p=valid();c=copy.deepcopy(p['planning_analysis']['candidates'][0]);c.pop('total_score');c.pop('rank');c['image_ids']=['unknown']
        with self.assertRaises(ValueError):cp.rank_candidates(t,dict(product_id=t['product_id'],candidates=[c]))
    def test_score_range_is_strict(self):
        from backend.planner_schemas import Score
        for value in (5,-1,'4',True):
            with self.assertRaises(ValidationError):Score(value=value,reason='fixture')
    def test_wrong_product_input(self):
        t,p=valid();t['package']['product']['id']='other'
        with self.assertRaises(ValueError):cp.check_input(t)
    def test_wrong_fact_product(self):
        t,p=valid();t['package']['facts'][0]['product_id']='other'
        with self.assertRaises(ValueError):cp.check_input(t)
    def test_unchecked_image_input(self):
        t,p=valid();t['package']['images'][0]['visual_checked']=False
        with self.assertRaises(ValueError):cp.check_input(t)
    def test_empty_quote_rejected(self):
        t,p=valid();t['package']['facts'][0]['quote']=''
        with self.assertRaises(ValueError):cp.check_input(t)
    def test_unknown_section_fact(self):
        t,p=valid();p['sections'][0]['fact_ids']=['F999']
        with self.assertRaises(ValueError):w.validate_plan(t,p)
    def test_unknown_selected_point(self):
        t,p=valid();p['selected_point_ids']=['C999']
        with self.assertRaises(ValueError):w.validate_plan(t,p)
    def test_argument_without_evidence(self):
        t,p=valid();p['sections'][0]['fact_ids']=[]
        with self.assertRaises(ValueError):w.validate_plan(t,p)
    def test_duplicate_reader_question(self):
        t,p=valid('wechat');p['sections'][1]['reader_question']=p['sections'][0]['reader_question']
        with self.assertRaises(ValueError):w.validate_plan(t,p)
    def test_duplicate_image(self):
        t,p=valid('wechat');p['sections'][1]['image_id']=p['sections'][0]['image_id']
        with self.assertRaises(ValueError):w.validate_plan(t,p)
    def test_invalid_platform_layout(self):
        t,p=valid('wechat');p['sections'][0]['image_position']=dict(kind='carousel',order=1)
        with self.assertRaises(ValueError):w.validate_plan(t,p)
    def test_non_contiguous_carousel(self):
        t,p=valid('xiaohongshu');p['sections'][1]['image_position']['order']=9
        with self.assertRaises(ValueError):w.validate_plan(t,p)
    def test_budget_guard(self):
        t,p=valid();p['sections'][0]['target_chars']=900
        with self.assertRaises(ValueError):w.validate_plan(t,p)
    def test_insufficient_images(self):
        t,p=valid('wechat');p['sections'][1]['image_id']=None;p['sections'][1]['image_position']=dict(kind='none',order=None)
        with self.assertRaises(ValueError):w.validate_plan(t,p)
    def test_old_body_preserves_v2_and_marks_stale(self):
        t,p=valid();incoming=copy.deepcopy(PLAN);incoming['angle']='用户新角度'
        changed=cp.reconcile(p,incoming,'moments');w.validate_plan(t,changed)
        self.assertEqual(changed['schema_version'],'2');self.assertEqual(changed['planning_analysis']['status'],'user_modified')
    def test_unchanged_save_keeps_analysis(self):
        t,p=valid();incoming=S.Plan.model_validate(p).model_dump(exclude_unset=True)
        self.assertEqual(cp.reconcile(p,incoming,'moments')['planning_analysis'],p['planning_analysis'])
    def test_client_cannot_forge_scores(self):
        t,p=valid();incoming=copy.deepcopy(p);incoming['planning_analysis']['candidates'][0]['total_score']=999
        self.assertEqual(cp.reconcile(p,incoming,'moments')['planning_analysis']['candidates'][0]['total_score'],75)
    def test_reorder_legacy_client_resequences(self):
        t,p=valid('xiaohongshu');incoming=copy.deepcopy(p);incoming['sections'].reverse();new=cp.reconcile(p,incoming,'xiaohongshu');w.validate_plan(t,new)
        self.assertEqual([s['image_position']['order'] for s in new['sections']],[1,2,3])
    def test_layout_respects_cover_swap(self):
        t,p=valid('xiaohongshu');p['sections'][0]['image_position']['order']=3;p['sections'][2]['image_position']['order']=1
        w.validate_plan(t,p);self.assertEqual(effective_layout(p,'xiaohongshu')['cover_section_id'],'P3')
    def test_document_image_override_uses_same_slot(self):
        t,p=valid();d=copy.deepcopy(DOC);d['paragraphs'][0]['image_id']='new-image'
        self.assertEqual(effective_layout(p,'moments',d)['slots'][0]['image_id'],'new-image')
    def test_legacy_plan_stays_legacy(self):
        self.assertNotIn('schema_version',cp.reconcile(PLAN,PLAN,'moments'))
    def test_writer_does_not_receive_candidate_scores(self):
        t,p=valid();self.assertNotIn('planning_analysis',cp.execution_plan(p));self.assertIn('composition_rationale',cp.execution_plan(p))
    def test_markdown_position_matches_wechat(self):
        from backend import storage as db
        t,p=valid('wechat');t['plan']=p;t['document']=copy.deepcopy(DOC);d=t['document'];d['paragraphs']=[dict(d['paragraphs'][0],section_id=s['id'],heading='段'+s['id'],text='文'+s['id'],image_id=s['image_id']) for s in p['sections']]
        for image in t['package']['images']:image.update(mime='image/png',source='synthetic')
        p['sections'][0]['image_position']=dict(kind='before_section',order=None);t['status']='approved';t['review']=dict(passed=True,summary='synthetic',issues=[],document_hash=db.digest(t))
        text=w.markdown(t);self.assertLess(text.index('assets/'+p['sections'][0]['image_id']),text.index('文P1'));self.assertGreater(text.index('assets/'+p['sections'][1]['image_id']),text.index('文P2'))

    def test_explicit_null_version_cannot_bypass_layout_checks(self):
        t,p=valid('wechat');incoming=copy.deepcopy(p);incoming['schema_version']=None
        incoming['sections'][0]['image_position']=dict(kind='carousel',order=1)
        changed=cp.reconcile(p,incoming,'wechat');self.assertEqual(changed['schema_version'],'2')
        with self.assertRaises(ValueError):w.validate_plan(t,changed)

    def test_legacy_plan_with_explicit_bad_layout_is_rejected(self):
        t=prepared();p=copy.deepcopy(PLAN);p['sections'][0]['image_position']=dict(kind='carousel',order=1)
        with self.assertRaises(ValueError):w.validate_plan(t,p)
