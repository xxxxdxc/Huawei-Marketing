"""Isolated transient retries and prewriting recovery; synthetic evidence only."""
import asyncio,copy,json,unittest
from unittest.mock import patch,AsyncMock as Mock
import httpx
from backend import test_commercial_policy as fixture
from backend.planner_test_data import AsyncMock
from backend import storage as db,workflow as w,prewrite_recovery as pr,brief_agent as ba,clients,schemas as S
from backend.clients import ServiceError
from backend.test_model_output import CONFIG,VALID,envelope

class TransientTests(unittest.TestCase):
    def invoke(self,outputs):
        original=httpx.AsyncClient;self.requests=[]
        def handle(request):
            self.requests.append(json.loads(request.content));item=outputs[min(len(self.requests)-1,len(outputs)-1)]
            if isinstance(item,Exception):raise item
            status,data=item
            return httpx.Response(status,json=data)
        with patch.object(clients,'api_key',return_value='fixture-key'),patch.object(clients,'get_settings',return_value=CONFIG),patch.object(clients.httpx,'AsyncClient',side_effect=lambda **kw:original(transport=httpx.MockTransport(handle),**kw)),patch.object(clients.asyncio,'sleep',new_callable=Mock) as sleep:
            self.sleep=sleep
            return asyncio.run(clients.LLM().complete('fixture-reviewer','fixture',{'fixture':True},S.Review))
    def test_524_retries_identical_request_once(self):
        self.assertEqual(self.invoke([(524,{}),(200,envelope())]),VALID)
        self.assertEqual(len(self.requests),2);self.assertEqual(self.requests[0],self.requests[1]);self.sleep.assert_awaited_once_with(1)
    def test_repeated_524_is_bounded_and_actionable(self):
        with self.assertRaises(ServiceError) as caught:self.invoke([(524,{})])
        self.assertEqual(len(self.requests),2);self.assertIn('当前步骤',str(caught.exception));self.assertNotIn('余额',str(caught.exception))
    def test_timeout_and_connection_failure_retry_once(self):
        for error in (httpx.ReadTimeout('fixture'),httpx.ConnectError('fixture')):
            self.assertEqual(self.invoke([error,(200,envelope())]),VALID);self.assertEqual(len(self.requests),2)
    def test_permission_and_quota_never_retry(self):
        for status,data in ((401,{}),(403,{}),(403,{'error':{'code':'insufficient_quota'}}),(524,{'error':{'code':'insufficient_balance'}})):
            with self.assertRaises(ServiceError):self.invoke([(status,data)])
            self.assertEqual(len(self.requests),1);self.sleep.assert_not_awaited()
    def test_format_retry_counts_toward_total_limit(self):
        with self.assertRaises(ServiceError):self.invoke([(200,envelope(content='invalid')),(524,{})])
        self.assertEqual(len(self.requests),2)

class CheckpointTests(unittest.TestCase):
    setUp=fixture.CommercialPolicyTests.setUp
    tearDown=fixture.CommercialPolicyTests.tearDown
    task=fixture.CommercialPolicyTests.task
    analyze=fixture.CommercialPolicyTests.analyze
    ready=fixture.CommercialPolicyTests.ready
    def paused(self,stage='image_review',legacy=False):
        t=self.ready();t['package']=fixture.priced(t);w.verify_coverage(t)
        t['package']['images'][0].update(visual_checked=False,usable=True,model_verified=True)
        t['brief_confirmation']={'analysis_hash':ba.digest(t['brief_analysis'])}
        t.update(status='error',resume_status='brief_ready',error='模型服务返回 HTTP 524',plan=None,document=None)
        if legacy:t['events'].append(dict(text='事实摘录已核对，正在按策略筛选图片',at=db.now()))
        else:pr.start(t,stage);pr.finish(t,failed=True)
        return db.save(t,'fixture timeout')
    def retry(self,t):return self.client.post(f"/api/tasks/{t['id']}/retry-prewrite",json={'version':t['version']})
    def test_legacy_stage_projection_does_not_mutate_record(self):
        t=self.paused(legacy=True);before=copy.deepcopy(t)
        r=self.client.get(f"/api/tasks/{t['id']}");self.assertEqual(r.status_code,200)
        self.assertEqual(r.json()['prewrite_recovery']['stage'],'image_review');self.assertTrue(r.json()['prewrite_recovery']['resumable'])
        self.assertNotIn('权限',r.json()['error']);self.assertIn('响应超时',r.json()['error'])
        self.assertEqual(db.get(t['id']),before)
    def test_image_retry_preserves_facts_and_stops_before_writer(self):
        t=self.paused(legacy=True);facts=copy.deepcopy(t['package']['facts']);confirmation=copy.deepcopy(t['brief_confirmation'])
        selected={'images':[{'id':'a'*20,'description':'fixture','reason':'fixture','usable':True}]}
        with patch.object(w.ima,'catalog_for_task',AsyncMock(side_effect=AssertionError('no catalog'))),patch.object(w,'extract_facts',AsyncMock(side_effect=AssertionError('no extraction'))),patch.object(w,'analyze',AsyncMock(side_effect=AssertionError('no Brief'))),patch.object(w.llm,'complete',AsyncMock(side_effect=[selected])) as model:
            self.assertEqual(self.retry(t).status_code,202)
        u=db.get(t['id']);self.assertEqual(u['status'],'plan_ready');self.assertIsNone(u['document'])
        self.assertEqual(u['package']['facts'],facts);self.assertEqual(u['brief_confirmation'],confirmation)
        self.assertEqual(model.await_args_list[0].args[3],S.AssetSelection);self.assertEqual(model.await_count,2)
        self.assertTrue(u['package']['images'][0]['visual_checked'])
    def test_failed_retry_preserves_unverified_images(self):
        t=self.paused();facts=copy.deepcopy(t['package']['facts'])
        with patch.object(w.llm,'complete',AsyncMock(side_effect=ServiceError('模型网关 HTTP 524'))):self.assertEqual(self.retry(t).status_code,202)
        u=db.get(t['id']);self.assertEqual(u['status'],'error');self.assertEqual(u['package']['facts'],facts)
        self.assertFalse(u['package']['images'][0]['visual_checked']);self.assertIsNone(u.get('plan'));self.assertTrue(pr.info(u)['resumable'])
    def test_changed_stale_unconfirmed_and_busy_tasks_cannot_resume(self):
        t=self.paused();self.assertEqual(self.client.post(f"/api/tasks/{t['id']}/retry-prewrite",json={'version':t['version']-1}).status_code,409)
        t['package']['facts'][0]['conditions']='changed';db.save(t,'fixture changed');self.assertEqual(self.retry(t).status_code,400)
        t=self.paused();t['brief_confirmation']=None;db.save(t,'fixture unconfirmed');self.assertEqual(self.retry(t).status_code,400)
        t=self.paused();t['status']='planning';db.save(t,'fixture busy');self.assertEqual(self.retry(t).status_code,400)
    def test_fact_retry_does_not_reread_sources(self):
        t=self.paused('fact_extraction');raw={k:copy.deepcopy(t['package'][k]) for k in ('facts','coverage','conflicts')}
        t['package']['facts']=[];t['package']['coverage']=[];pr.start(t,'fact_extraction');pr.finish(t,failed=True);db.save(t,'fixture fact timeout')
        with patch.object(w.ima,'catalog_for_task',AsyncMock(side_effect=AssertionError('no catalog'))),patch.object(w,'extract_facts',AsyncMock(return_value=raw)) as extract,patch.object(w,'finish_prewrite',AsyncMock()) as finish:
            self.assertEqual(self.retry(t).status_code,202)
        extract.assert_awaited_once();finish.assert_awaited_once();self.assertEqual(finish.call_args.args[0]['package']['facts'],raw['facts'])

    def test_source_retry_returns_to_source_reading_only(self):
        t=self.paused('source_retrieval');t['package']=None;pr.start(t,'source_retrieval');pr.finish(t,failed=True);db.save(t,'fixture source timeout')
        with patch.object(w,'plan',AsyncMock()) as plan:
            self.assertEqual(self.retry(t).status_code,202)
        plan.assert_awaited_once()
    def test_selling_point_retry_skips_image_review(self):
        t=self.paused('selling_points');t['package']['images'][0]['visual_checked']=True
        pr.start(t,'selling_points');pr.finish(t,failed=True);db.save(t,'fixture candidate timeout')
        with patch.object(w,'select_images',AsyncMock(side_effect=AssertionError('no image recheck'))),patch.object(w,'extract_facts',AsyncMock(side_effect=AssertionError('no extraction'))),patch.object(w.llm,'complete',AsyncMock()) as model:
            self.assertEqual(self.retry(t).status_code,202)
        u=db.get(t['id']);self.assertEqual(u['status'],'plan_ready');self.assertEqual(model.await_count,1)
    def test_old_failed_planner_history_cannot_mask_new_image_timeout(self):
        t=self.paused(legacy=True);t['planner_runs']=[dict(status='failed',error='候选卖点 JSON 失败')];db.save(t,'fixture old planner history')
        r=self.client.get(f"/api/tasks/{t['id']}")
        self.assertEqual(r.json()['prewrite_recovery']['stage'],'image_review')
