"""First-run official supplementation, stable IDs and optional gap behavior."""
import asyncio,copy,unittest
from unittest.mock import patch
from backend import test_platform_change as fixture,workflow as w,vmall,brief_agent as ba,evidence_policy as ep,storage as db
from backend.planner_test_data import AsyncMock

class IngestionTests(unittest.TestCase):
    def setUp(self):db.init()
    def sample(self):
        t=fixture.task(images=1);t.update(status='retrieving',plan=None,document=None,review=None)
        t['brief_analysis']['retrieval_plan']['facts'].append(dict(id='R2',direction_id='D1',category='product',question='屏幕相关事实',conditions=[],priority='required',guardrail='none'))
        t['brief_confirmation']['analysis_hash']=ba.digest(t['brief_analysis'])
        t['package']['coverage'].append(dict(request_id='R2',status='not_found',fact_ids=[],reason='原库没有'))
        return t
    def test_first_run_supplements_missing_direction_and_preserves_old_fact_id(self):
        t=self.sample();original=copy.deepcopy(t['package']['facts'][0])
        source=dict(id='V1',text='该配置具有独立的屏幕参数，本条仅为合成测试资料。',title='商城',path='fixture')
        result=fixture.empty_supplement();result['sources']=[source]
        extracted=dict(facts=[dict(id='F01',category='product',claim='合成屏幕参数',quote=source['text'],source_id='V1',conditions='合成版本')],conflicts=[],coverage=[dict(request_id='R1',status='not_found',fact_ids=[],reason='增量来源未涉及'),dict(request_id='R2',status='supported',fact_ids=['F01'],reason='新增来源支持')])
        with patch.object(vmall,'supplement',AsyncMock(return_value=result)) as supplier,patch.object(w.llm,'complete',AsyncMock(side_effect=[extracted])) as model:
            asyncio.run(w.finish_prewrite(t,{},reuse_images=True))
        self.assertEqual(t['status'],'plan_ready');self.assertIsNone(t['document']);self.assertEqual(t['package']['facts'][0],original)
        new=t['package']['facts'][1];self.assertTrue(new['id'].startswith('VM'));self.assertEqual(new['source_id'],'V1')
        self.assertEqual(t['package']['coverage'][0]['fact_ids'],['F01']);self.assertEqual(t['package']['coverage'][1]['fact_ids'],[new['id']])
        supplier.assert_awaited_once();self.assertEqual(model.await_count,2)
    def test_ordinary_required_search_gap_omits_but_explicit_guardrail_blocks(self):
        t=self.sample();self.assertEqual(w.verify_coverage(t),[]);self.assertTrue(t['package']['omitted_product_requests'])
        t['brief_analysis']['retrieval_plan']['facts'][1]['guardrail']='identity'
        self.assertTrue(w.verify_coverage(t))
    def test_failed_optional_supplement_keeps_original_facts(self):
        t=self.sample();facts=copy.deepcopy(t['package']['facts'])
        with patch.object(vmall,'supplement',AsyncMock(side_effect=w.ServiceError('offline'))),patch.object(w.llm,'complete',AsyncMock()):
            asyncio.run(w.finish_prewrite(t,{},reuse_images=True))
        self.assertEqual(t['status'],'plan_ready');self.assertEqual(t['package']['facts'],facts)
    def test_zero_product_facts_still_blocks(self):
        t=self.sample();t['package']['facts']=[]
        for row in t['package']['coverage']:row.update(status='not_found',fact_ids=[])
        self.assertTrue(w.verify_coverage(t))
    def test_official_text_view_retains_decoded_values_and_source_fields(self):
        value={'name':'测试型号','detail':'第一行\n第二行包含"条件"','capacity':'70 Wh'}
        text=vmall.evidence_text(value)
        self.assertIn(value['detail'],text);self.assertIn('70 Wh',text)
    def test_registry_does_not_mix_systems_or_unknown_products(self):
        urls=vmall.registry_urls({'name':'HUAWEI MateBook 14','category':'鸿蒙电脑'})
        self.assertTrue(any('10086097339191' in u for u in urls))
        self.assertFalse(vmall.registry_urls({'name':'未知型号','category':'鸿蒙电脑'}))
        self.assertFalse(vmall.model_matches({'name':'MateBook D 14','category':'Windows'},{'name':'HUAWEI MateBook D 14 2024','attrViewList':[]}))

    def test_model_source_view_avoids_duplicate_raw_json(self):
        source=dict(id='V1',text='可追溯正文',raw_json='审计原始JSON',sku='SKU1',knowledge_source='vmall')
        view=w.source_views([source])[0]
        self.assertEqual(view['text'],source['text']);self.assertEqual(view['sku'],'SKU1');self.assertNotIn('raw_json',view)
