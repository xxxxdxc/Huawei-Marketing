"""Platform-specific store marketing; real orchestration, synthetic model responses."""
import asyncio,copy,unittest
from unittest.mock import AsyncMock,patch
from pydantic import ValidationError
from backend.test_workflow import prepared,DOC
from backend.test_writer_responsibilities import outline,document
from backend.test_point_selection import task
from backend import store_marketing as sm,platform_writer as pw,workflow as w,planner_schemas as P,schemas as S,storage as db,content_planner as cp,platform_change as pc

TEXT='我的门店名称是杭州湖滨店，地址是杭州市湖滨路10号，电话是0571-12345678，提供选购咨询。'

def simple(platform='wechat',text=TEXT):
    return dict(platform=platform,dialogue=[dict(id='U1',kind='user',text=text)])

def context():
    return dict(details=[dict(field=k,value=v,evidence=dict(turn_id='U1',quote=TEXT)) for k,v in [('name','杭州湖滨店'),('location','杭州市湖滨路10号'),('contact','0571-12345678'),('service','选购咨询')]],wechat_exception=None)

class StoreMarketingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):db.init()
    def test_defaults_for_all_platforms(self):
        for platform,enabled in [('wechat',False),('xiaohongshu',True),('moments',True)]:
            with self.subTest(platform=platform):
                p=sm.policy(simple(platform));self.assertEqual(p['enabled'],enabled)
                self.assertEqual(p['allow_empty_cta'],not enabled)
    def test_store_data_is_not_wechat_exception(self):
        self.assertFalse(sm.policy(simple(),context())['enabled'])
    def test_store_values_remain_user_business_data(self):
        out=sm.payload(simple('moments')|dict(store_marketing_context=context()))
        self.assertNotIn('facts',out);self.assertEqual(out['store_marketing_context'],context())
        self.assertEqual(out['store_user_evidence'][0]['text'],TEXT)
    def test_value_must_be_verbatim(self):
        c=context();c['details'][0]['value']='杭州西湖旗舰店'
        with self.assertRaisesRegex(ValueError,'逐字'):sm.checked_context(simple(),c)
    def test_quote_must_be_real_user_turn(self):
        for change in ({'turn_id':'unknown'},{'quote':'我们有现货'}):
            c=context();c['details'][0]['evidence'].update(change)
            with self.assertRaisesRegex(ValueError,'用户原话'):sm.checked_context(simple(),c)
    def test_duplicate_details_rejected(self):
        c=context();c['details'].append(copy.deepcopy(c['details'][0]))
        with self.assertRaisesRegex(ValueError,'重复'):sm.checked_context(simple(),c)
    def test_product_or_system_turn_cannot_source_store_data(self):
        t=simple();t['dialogue'][0]['kind']='assistant'
        with self.assertRaises(ValueError):sm.checked_context(t,context())
    def test_explicit_wechat_exception(self):
        text='这篇公众号也要加入我们门店的营销。';t=simple(text=text)
        c=dict(details=[],wechat_exception=dict(turn_id='U1',quote=text))
        self.assertTrue(sm.policy(t,c)['enabled'])
    def test_negative_wechat_request_is_not_exception(self):
        text='公众号不要写门店。';t=simple(text=text)
        with self.assertRaises(ValueError):sm.checked_context(t,dict(wechat_exception=dict(turn_id='U1',quote=text)))
    def test_asking_store_marketing_for_other_platform_is_not_exception(self):
        text='公众号不写门店，小红书要加入门店营销。';t=simple('wechat',text)
        with self.assertRaises(ValueError):sm.checked_context(t,dict(wechat_exception=dict(turn_id='U1',quote=text)))
    def test_platform_only_command_is_not_new_authorization(self):
        t=simple();t['dialogue'].append(dict(id='U2',kind='user',change_kind='platform_only',text='改为公众号，保留到店目标'))
        with self.assertRaises(ValueError):sm.checked_context(t,dict(wechat_exception=dict(turn_id='U2',quote='改为公众号，保留到店目标')))
    def test_generic_inherited_goal_is_not_exception(self):
        text='要引导到店。';t=simple('wechat',text)
        t['platform_changes']=[dict(from_platform='xiaohongshu',to_platform='wechat',turn_id='U2')]
        t['dialogue'].append(dict(id='U2',kind='user',change_kind='platform_only',text='切换到公众号'))
        with self.assertRaises(ValueError):sm.checked_context(t,dict(wechat_exception=dict(turn_id='U1',quote=text)))
    def test_fresh_wechat_direct_store_request_is_valid(self):
        text='请加入我们门店的介绍。';t=simple('wechat',text)
        self.assertTrue(sm.policy(t,dict(wechat_exception=dict(turn_id='U1',quote=text)))['enabled'])
    def test_later_explicit_revoke_does_not_block(self):
        text='公众号也要写门店。';t=simple(text=text)
        t['dialogue'].append(dict(id='U2',kind='user',text='公众号不要写门店。'))
        self.assertFalse(sm.policy(t,dict(wechat_exception=dict(turn_id='U1',quote=text)))['enabled'])
    def test_store_info_survives_switch_but_mode_changes(self):
        t=simple('xiaohongshu');t['store_marketing_context']=context();before=copy.deepcopy(t)
        self.assertTrue(sm.policy(t)['enabled']);t['platform']='wechat'
        self.assertFalse(sm.policy(t)['enabled']);self.assertEqual(t['store_marketing_context'],before['store_marketing_context'])
        t['platform']='moments';self.assertTrue(sm.policy(t)['enabled'])
    def test_user_turn_platform_scope_survives_roundtrip(self):
        text='请加入我们门店的介绍。';t=simple('moments',text)
        t['platform_changes']=[dict(from_platform='wechat',to_platform='moments',turn_id='U2')]
        t['dialogue'].append(dict(id='U2',kind='user',text='切换到朋友圈',change_kind='platform_only'))
        c=dict(wechat_exception=dict(turn_id='U1',quote=text))
        self.assertTrue(sm.checked_context(t,c)['wechat_exception'])
    def test_missing_details_never_blocks(self):
        for platform in ('xiaohongshu','moments'):
            p=sm.policy(simple(platform,''));self.assertEqual(p['details'],[])
            d=copy.deepcopy(DOC);d['cta']='欢迎私信了解我们的门店。'
            self.assertFalse(sm.document_issues(simple(platform,''),d))
    def test_wechat_empty_cta_and_natural_ending_allowed(self):
        for cta in ('','愿每一个工作日，都有自己的节奏。'):
            d=copy.deepcopy(DOC);d['cta']=cta
            self.assertFalse(sm.document_issues(simple(),d))
    def test_product_meeting_booking_is_not_store_advertisement(self):
        d=copy.deepcopy(DOC);d['cta']='';d['paragraphs'][0]['text']='支持预约会议。'
        self.assertFalse(sm.document_issues(simple(),d))
    def test_wechat_store_leaks_in_all_public_fields(self):
        for field in ('title','lead','text','caption','cta','tags'):
            d=copy.deepcopy(DOC);d['cta']=''
            if field in ('text','caption'):d['paragraphs'][0][field]='欢迎到店体验'
            else:d[field]=['门店体验'] if field=='tags' else '欢迎到店体验'
            self.assertTrue(sm.document_issues(simple(),d))
    def test_known_store_name_and_contact_are_detected_without_store_word(self):
        for value in ('杭州湖滨店','0571-12345678'):
            d=copy.deepcopy(DOC);d['cta']=value
            self.assertTrue(sm.document_issues(simple(),d,context()))
    def test_enabled_store_closing_can_use_true_name(self):
        d=copy.deepcopy(DOC);d['cta']='欢迎联系杭州湖滨店。'
        self.assertFalse(sm.document_issues(simple('moments'),d,context()))
    def test_social_missing_store_closing_is_repairable(self):
        d=copy.deepcopy(DOC);d['cta']='欢迎咨询'
        issues=sm.document_issues(simple('moments'),d)
        self.assertTrue(issues);self.assertTrue(all(x['repairable'] for x in issues))
    def test_store_details_cannot_leak_into_product_body(self):
        d=copy.deepcopy(DOC);d['paragraphs'][0]['text']='杭州湖滨店提供咨询。'
        self.assertTrue(sm.document_issues(simple('moments'),d,context()))
    def test_internal_heading_is_not_public_store_promotion(self):
        d=copy.deepcopy(DOC);d['paragraphs'][0]['heading']='门店内部提示';d['cta']=''
        self.assertFalse(sm.document_issues(simple(),d))
    def test_old_saved_document_is_not_retroactively_blocked(self):
        t=prepared();t['platform']='wechat';t['brief']['platform']='wechat'
        # Use direct store checker gate separately: platform image policy remains unchanged.
        t['platform']='moments';t['brief']['platform']='moments';t['document']['cta']='欢迎咨询'
        self.assertFalse(w.deterministic_review(t))
        t['store_marketing_version']=sm.VERSION
        self.assertTrue(any('所在门店' in i['detail'] for i in w.deterministic_review(t)))
    def test_business_musts_not_product_fact_constraints(self):
        for text in ('必须写门店名称','务必写门店地址和联系电话','必须介绍我们的门店'):
            self.assertTrue(sm.is_store_request(text))
        for text in ('必须写门店优惠','必须写门店及屏幕参数','必须写触控功能','必须写门店和跨端协同'):
            self.assertFalse(sm.is_store_request(text))
    def test_writer_outline_allows_empty_cta_without_relaxing_other_schema(self):
        # Existing outline fixture is obtained through actual confirmed candidate data.
        t=task(legacy=False);payload=cp.shared_context(t,w.PLATFORMS[t['platform']])|dict(selected_points=t['plan']['planning_analysis']['candidates'],selected_point_ids=t['plan']['selected_point_ids'])
        r=outline(payload);r['cta']='';self.assertEqual(P.WriterOutline.model_validate(r).cta,'')
        r['selected_point_ids']=[]
        with self.assertRaises(ValidationError):P.WriterOutline.model_validate(r)
    def test_repair_always_receives_current_policy(self):
        t=prepared();t['platform']='wechat';t['brief']['platform']='wechat'
        payload=dict(brief=t['brief'],plan=t['plan'],document=copy.deepcopy(DOC),issues=[w.issue('platform','行动引导','去掉门店')])
        d=copy.deepcopy(DOC);d['cta']=''
        with patch.object(pw.llm,'complete',AsyncMock(return_value=d)) as model:asyncio.run(pw.repair(t,w.BASE,payload,S.Document))
        self.assertEqual(model.call_args.args[2]['store_marketing_policy']['mode'],'product_only')
        self.assertIn('公众号默认只做产品宣传',model.call_args.args[1])
    def selected(self):
        t=task(legacy=False);t['selection_confirmation']=dict(selection_hash=cp.selection_fingerprint(t['plan']))
        return t
    def test_store_extraction_uses_existing_outline_call_and_is_persisted(self):
        t=self.selected();t['dialogue']=[dict(id='U1',kind='user',text=TEXT)]
        calls=[]
        async def fake(model,system,payload,schema,**kw):
            calls.append((schema,payload))
            if schema is P.WriterOutline:
                r=outline(payload);r['store_context']=context();r['cta']='欢迎私信杭州湖滨店了解门店详情。';return r
            if schema is S.Document:return document(payload['plan'])
            return dict(summary='synthetic',issues=[])
        with patch.object(w.llm,'complete',AsyncMock(side_effect=fake)):asyncio.run(w.write(t))
        self.assertEqual([x[0] for x in calls],[P.WriterOutline,S.Document,S.Review])
        self.assertEqual(t['store_marketing_context'],context());self.assertTrue(w.can_export(t))
        self.assertTrue(calls[1][1]['store_marketing_policy']['enabled'])
        self.assertEqual(calls[2][1]['store_marketing']['store_marketing_context'],context())
    def test_empty_outline_cta_recovers_only_enabled_generic_closing(self):
        for platform in ('moments','xiaohongshu','wechat'):
            for empty in ('','   '):
                with self.subTest(platform=platform,empty=empty):
                    t=task(platform=platform,legacy=False)
                    payload=cp.shared_context(t,w.PLATFORMS[platform])|dict(selected_points=t['plan']['planning_analysis']['candidates'],selected_point_ids=t['plan']['selected_point_ids'])
                    raw=outline(payload);raw['cta']=empty
                    fixed,_=pw.validate_outline(t,t['plan'],raw)
                    self.assertEqual(fixed['cta'],empty if platform=='wechat' else '欢迎私信了解我们的门店。')
                    self.assertEqual(raw['cta'],empty)
    def test_empty_cta_does_not_replace_provided_store_identity(self):
        t=self.selected();t['dialogue']=[dict(id='U1',kind='user',text=TEXT)]
        payload=cp.shared_context(t,w.PLATFORMS[t['platform']])|dict(selected_points=t['plan']['planning_analysis']['candidates'],selected_point_ids=t['plan']['selected_point_ids'])
        raw=outline(payload);raw['store_context']=context();raw['cta']=''
        with self.assertRaisesRegex(ValueError,'所在门店'):pw.validate_outline(t,t['plan'],raw)
    def test_nonempty_invalid_cta_is_not_silently_replaced(self):
        t=self.selected()
        payload=cp.shared_context(t,w.PLATFORMS[t['platform']])|dict(selected_points=t['plan']['planning_analysis']['candidates'],selected_point_ids=t['plan']['selected_point_ids'])
        raw=outline(payload);raw['cta']='明天更精彩。'
        with self.assertRaisesRegex(ValueError,'所在门店'):pw.validate_outline(t,t['plan'],raw)
    def test_generic_cta_recovery_continues_through_draft_and_review(self):
        t=self.selected();calls=[]
        async def fake(model,system,payload,schema,**kw):
            calls.append(schema)
            if schema is P.WriterOutline:
                r=outline(payload);r['cta']='';return r
            if schema is S.Document:
                d=document(payload['plan']);d['cta']='';return d
            return dict(summary='synthetic',issues=[])
        with patch.object(w.llm,'complete',AsyncMock(side_effect=fake)):asyncio.run(w.write(t))
        self.assertEqual(calls,[P.WriterOutline,S.Document,S.Review])
        self.assertEqual(t['writer_runs'][1]['recoveries'][0]['kind'],'generic_store_cta')
        self.assertEqual(t['writer_runs'][0]['recoveries'][0]['kind'],'generic_store_cta')
        self.assertEqual(t['document']['cta'],'欢迎私信了解我们的门店。')
        self.assertTrue(w.can_export(t))

    def test_hallucinated_store_context_stops_before_draft(self):
        t=self.selected();t['dialogue']=[dict(id='U1',kind='user',text=TEXT)]
        async def fake(model,system,payload,schema,**kw):
            r=outline(payload);c=context();c['details'][0]['value']='不存在的店';r['store_context']=c;return r
        with patch.object(w.llm,'complete',AsyncMock(side_effect=fake)) as model:
            with self.assertRaisesRegex(ValueError,'逐字'):asyncio.run(w.write(t))
        self.assertEqual(model.await_count,1);self.assertIsNone(t['document'])

    def test_mandatory_store_identity_does_not_require_product_fact_ids(self):
        from backend.test_platform_change import task as canonical_task
        t=canonical_task()
        t['brief_analysis']['requirements']['user_constraints']=dict(value=['必须写门店名称','必须包含屏幕触控'],source='explicit',
            evidence=[dict(turn_id='U1',quote='必须写门店名称，必须包含屏幕触控')],reason='用户要求')
        needs=cp.mandatory_needs(t)
        self.assertEqual([n['text'] for n in needs],['必须包含屏幕触控'])
    def test_api_platform_roundtrip_recomputes_policy_without_brief_or_planner(self):
        from backend.test_writer_responsibilities import WriterResponsibilitiesTests
        from fastapi.testclient import TestClient
        from backend.main import app
        t=WriterResponsibilitiesTests().platform_task()
        t['dialogue'].append(dict(id='Store1',kind='user',text=TEXT))
        c=context()
        for detail in c['details']:detail['evidence']['turn_id']='Store1'
        t['store_marketing_context']=c;db.save(t,'synthetic store metadata')
        chosen=copy.deepcopy(t['plan']['selected_point_ids']);before_runs=copy.deepcopy(t.get('brief_runs',[]))
        seen=[]
        async def fake(model,system,payload,schema,**kw):
            seen.append((schema,payload))
            if schema is P.WriterOutline:
                r=outline(payload);r['store_context']=payload['store_marketing_context']
                if payload['store_marketing_policy']['enabled']:r['cta']='欢迎私信杭州湖滨店了解我们的门店。'
                return r
            if schema is S.Document:return document(payload['plan'])
            return dict(summary='synthetic',issues=[])
        with TestClient(app) as client,patch.object(w.llm,'complete',AsyncMock(side_effect=fake)) as model,patch.object(w,'analyze',AsyncMock()) as brief,patch.object(cp,'generate',AsyncMock()) as planner:
            for platform in ('wechat','moments'):
                response=client.post(f"/api/tasks/{t['id']}/change-platform",json=dict(version=t['version'],platform=platform))
                self.assertEqual(response.status_code,202);t=db.get(t['id'])
                self.assertTrue(w.can_export(t),t.get('error'))
                self.assertEqual(t['plan']['selected_point_ids'],chosen)
                self.assertEqual(t['store_marketing_context']['details'],c['details'])
                self.assertEqual(t['document']['cta']== '',platform=='wechat')
            brief.assert_not_called();planner.assert_not_called();self.assertEqual(model.await_count,6)
        self.assertEqual(t.get('brief_runs',[]),before_runs)
        self.assertEqual([x[1]['store_marketing_policy']['mode'] for x in seen if x[0] is P.WriterOutline],['product_only','store_closing'])
    def test_wechat_repair_cannot_restore_store_marketing(self):
        from backend.test_writer_responsibilities import WriterResponsibilitiesTests
        from fastapi.testclient import TestClient
        from backend.main import app
        t=WriterResponsibilitiesTests().platform_task()
        async def fake(model,system,payload,schema,**kw):
            if schema is P.WriterOutline:return outline(payload)
            if schema is S.TextRepair:
                self.assertEqual(payload['store_marketing_policy']['mode'],'product_only')
                return dict(root_changes=dict(cta=''),paragraph_changes=[])
            if schema is S.Document:
                if 'issues' in payload:
                    self.assertEqual(payload['store_marketing_policy']['mode'],'product_only')
                    d=copy.deepcopy(payload['document']);d['cta']='';return d
                d=document(payload['plan']);d['cta']='欢迎到店体验。';return d
            return dict(summary='synthetic',issues=[])
        with TestClient(app) as client,patch.object(w.llm,'complete',AsyncMock(side_effect=fake)) as model:
            response=client.post(f"/api/tasks/{t['id']}/change-platform",json=dict(version=t['version'],platform='wechat'))
        self.assertEqual(response.status_code,202);t=db.get(t['id'])
        self.assertTrue(w.can_export(t),t.get('error'));self.assertEqual(t['document']['cta'],'')
        self.assertEqual(t['repair_before']['cta'],'欢迎到店体验。');self.assertEqual(model.await_count,5)

    def test_known_store_name_should_personalize_closing(self):
        d=copy.deepcopy(DOC)
        self.assertTrue(any('真实门店名称' in i['detail'] for i in sm.document_issues(simple('moments'),d,context())))

    def test_store_context_change_invalidates_new_review_hash(self):
        t=prepared('approved');t['store_marketing_version']=sm.VERSION
        t['store_marketing_context']=dict(details=[],wechat_exception=None)
        t['review']=dict(passed=True,document_hash=db.digest(t))
        self.assertTrue(w.can_export(t))
        t['store_marketing_context']=context()
        self.assertFalse(w.can_export(t))
    def test_legacy_review_hash_unchanged_by_unpublished_store_metadata(self):
        t=prepared('approved');before=db.digest(t);t['store_marketing_context']=context()
        self.assertEqual(before,db.digest(t))
