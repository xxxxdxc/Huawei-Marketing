"""Provider protocol failures are synthetic; no live requests or coercion."""
import asyncio,copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import AsyncMock,patch
import httpx
from fastapi.testclient import TestClient
from backend.test_workflow import prepared,DOC,PLAN
from backend import clients,model_output as mo,schemas as S,storage as db,workflow as w
from backend.main import app
from backend.clients import ServiceError

VALID=dict(summary="合成核验结果",issues=[])
CONFIG=dict(base_url="https://fixture.invalid/v1",writer_model="fixture-writer",reviewer_model="fixture-reviewer")

def envelope(value=None,finish="stop",content=None):
    return dict(choices=[dict(finish_reason=finish,message=dict(content=json.dumps(value or VALID,ensure_ascii=False) if content is None else content))],usage=dict(completion_tokens=20))


class ModelOutputTests(unittest.TestCase):
    def call(self,outputs,schema=S.Review):
        requests=[];original=httpx.AsyncClient
        def handle(request):
            requests.append(json.loads(request.content))
            return httpx.Response(200,json=outputs[min(len(requests)-1,len(outputs)-1)])
        transport=httpx.MockTransport(handle)
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.folder=Path(temp.name)
        with patch.object(clients,"api_key",return_value="fixture-private-key"),patch.object(clients,"get_settings",return_value=CONFIG),patch.object(mo,"DATA",self.folder),patch.object(clients.httpx,"AsyncClient",side_effect=lambda **kw:original(transport=transport,**kw)):
            try:
                result=asyncio.run(clients.LLM().complete("fixture-reviewer","合成协议测试",{"synthetic_secret_input":"never-log-input"},schema))
                return result,requests
            finally:self.requests=requests

    def test_specific_enum_error_and_failed_answer_are_given_to_retry(self):
        bad=dict(summary="x",issues=[dict(category="structure",location="正文",detail="测试",severity="error",repairable=True)])
        result,requests=self.call([envelope(bad),envelope()])
        self.assertEqual(result,VALID);self.assertEqual(len(requests),2)
        retry=requests[1]["messages"];self.assertEqual(retry[-2]["role"],"assistant")
        self.assertIn("structure",retry[-2]["content"])
        self.assertIn("literal_error",retry[-1]["content"]);self.assertIn("category",retry[-1]["content"])

    def test_truncation_is_not_accepted_even_if_json_looks_complete(self):
        result,requests=self.call([envelope(finish="length"),envelope()])
        self.assertEqual(len(requests),2);self.assertEqual(requests[0]["max_tokens"],6000)
        self.assertEqual(requests[1]["max_tokens"],12000);self.assertEqual(result,VALID)

    def test_gateway_max_tokens_finish_reason_detected(self):
        _,requests=self.call([envelope(finish="max_tokens"),envelope()])
        self.assertEqual(requests[1]["max_tokens"],12000)

    def test_empty_final_content_retries_with_more_budget(self):
        result,requests=self.call([envelope(content=""),envelope()])
        self.assertEqual(result,VALID);self.assertEqual(requests[1]["max_tokens"],12000)

    def test_output_text_blocks_supported_without_reasoning(self):
        data=envelope()
        data["choices"][0]["message"]["content"]=[dict(type="reasoning",text="not JSON"),dict(type="output_text",text=json.dumps(VALID))]
        self.assertEqual(mo.decode(data,S.Review),VALID)

    def test_complete_code_fence_is_allowed(self):
        fence=chr(96)*3
        self.assertEqual(mo.decode(envelope(content=fence+"json\n"+json.dumps(VALID)+"\n"+fence),S.Review),VALID)

    def test_explanation_without_a_complete_json_object_is_rejected(self):
        with self.assertRaises(mo.InvalidOutput):
            mo.decode(envelope(content="请看这里：只有说明，没有完整对象。"),S.Review)

    def test_string_boolean_is_not_coerced(self):
        bad=dict(summary="x",issues=[dict(category="fact",location="正文",detail="测试",severity="error",repairable="false")])
        with self.assertRaises(mo.InvalidOutput) as caught:mo.decode(envelope(bad),S.Review)
        self.assertEqual(caught.exception.kind,"schema")
        self.assertEqual(caught.exception.detail[0]["type"],"bool_type")

    def test_two_invalid_outputs_remain_blocked_and_diagnostics_private(self):
        bad=dict(summary="x",issues=[dict(category="wrong",location="正文",detail="测试",severity="error",repairable=True)])
        with self.assertRaises(ServiceError) as caught:self.call([envelope(bad),envelope(bad)])
        self.assertIn("内容核验失败",str(caught.exception));self.assertIn("issues.0.category",str(caught.exception))
        files=list((self.folder/"llm_diagnostics").glob("*.json"))
        self.assertEqual(len(files),2)
        records=[json.loads(p.read_text(encoding="utf-8")) for p in files]
        record=next(r for r in records if len(r["attempts"])==2)
        self.assertTrue(all(a["kind"]=="schema" for a in record["attempts"]))
        text=" ".join(p.read_text(encoding="utf-8") for p in files)
        self.assertNotIn("fixture-private-key",text);self.assertNotIn("never-log-input",text)
        self.assertNotIn("Authorization",text);self.assertIn("response_content",text)

    def test_invalid_json_diagnostic_has_line_and_column(self):
        with self.assertRaises(mo.InvalidOutput) as caught:mo.decode(envelope(content='{"summary":'),S.Review)
        self.assertEqual(caught.exception.kind,"invalid_json");self.assertEqual(caught.exception.detail["line"],1)

    def test_wrapped_json_and_invalid_type_example_are_accepted(self):
        text='Explanation {"value": int, "reason": str}\n```json\n'+json.dumps(VALID)+'\n```\nEnd.'
        self.assertEqual(mo.decode(envelope(content=text),S.Review),VALID)

    def test_wrapper_preserves_escaped_quotes_and_braces_in_strings(self):
        value=dict(summary='A "quote" and {braces} with \\ slash',issues=[])
        self.assertEqual(mo.decode(envelope(content='Result: '+json.dumps(value)+' Done.'),S.Review),value)

    def test_multiple_complete_json_objects_are_rejected(self):
        for text in (json.dumps(VALID)+'\n'+json.dumps(VALID),'{}\n'+json.dumps(VALID)):
            with self.subTest(text=text),self.assertRaises(mo.InvalidOutput) as caught:
                mo.decode(envelope(content=text),S.Review)
            self.assertEqual(caught.exception.kind,'invalid_json')

    def test_truncated_outer_object_cannot_expose_nested_valid_object(self):
        for text in ('Explanation {"nested":'+json.dumps(VALID),'Explanation '+json.dumps(VALID)+' {"unfinished":'):
            with self.subTest(text=text),self.assertRaises(mo.InvalidOutput):
                mo.decode(envelope(content=text),S.Review)

    def test_wrapped_array_is_not_unwrapped_to_inner_object(self):
        with self.assertRaises(mo.InvalidOutput):mo.decode(envelope(content='Result: ['+json.dumps(VALID)+']'),S.Review)

    def test_wrapped_json_keeps_strict_schema_and_finish_checks(self):
        with self.assertRaises(mo.InvalidOutput) as caught:
            mo.decode(envelope(content='Result: '+json.dumps(dict(summary='x',issues=[],passed='true'))),S.Review)
        self.assertEqual(caught.exception.kind,'schema')
        with self.assertRaises(mo.InvalidOutput) as caught:
            mo.decode(envelope(content='Result: '+json.dumps(VALID),finish='length'),S.Review)
        self.assertEqual(caught.exception.kind,'truncated')

    def test_missing_envelope_fields_are_reported(self):
        with self.assertRaises(mo.InvalidOutput) as caught:mo.decode({"error":{"code":"fixture"}},S.Review)
        self.assertEqual(caught.exception.kind,"envelope")

    def test_refusal_does_not_retry_blindly(self):
        with self.assertRaises(ServiceError):self.call([envelope(finish="content_filter")])
        self.assertEqual(len(self.requests),1)

    def test_truncated_twice_never_returns_partial_result(self):
        with self.assertRaises(ServiceError) as caught:self.call([envelope(finish="length"),envelope(finish="length")])
        self.assertIn("输出上限",str(caught.exception));self.assertEqual(len(self.requests),2)

    def test_non_reviewer_schema_keeps_original_budget(self):
        result,requests=self.call([envelope({"images":[]})],schema=S.AssetSelection)
        self.assertEqual(result,{"images":[]});self.assertEqual(requests[0]["max_tokens"],6000)

    def test_quota_error_is_actionable_without_leaking_key_or_retrying(self):
        original=httpx.AsyncClient;calls=[]
        def handle(request):
            calls.append(request)
            return httpx.Response(403,json={"error":{"code":"pre_consume_token_quota_failed","message":"令牌[fixture-private-key]额度不足"}})
        with patch.object(clients,"api_key",return_value="fixture-private-key"),patch.object(clients,"get_settings",return_value=CONFIG),patch.object(clients.httpx,"AsyncClient",side_effect=lambda **kw:original(transport=httpx.MockTransport(handle),**kw)):
            with self.assertRaises(ServiceError) as caught:
                asyncio.run(clients.LLM().complete("fixture-reviewer","合成测试",{"synthetic":True},S.Review))
        self.assertIn("核验模型 API 预扣额度不足",str(caught.exception))
        self.assertNotIn("fixture-private-key",str(caught.exception));self.assertEqual(len(calls),1)

    def test_new_diagnostic_write_failure_does_not_hide_model_error(self):
        error=mo.InvalidOutput("schema",[dict(loc=("issues",0,"category"),msg="wrong")])
        with patch.object(Path,"mkdir",side_effect=OSError("fixture")):
            self.assertIsNone(mo.save_failure("fixture",S.Review,[dict(kind="schema")]))
        self.assertIn("issues.0.category",mo.describe(error,S.Review,None))


class ReviewerResumeTests(unittest.TestCase):
    def setUp(self):
        self.client=TestClient(app);self.client.__enter__()
    def tearDown(self):self.client.__exit__(None,None,None)
    def legacy_failed_review(self):
        t=prepared("error");t["resume_status"]="plan_ready";t["review"]=None
        t["error"]="模型连续两次未返回符合结构要求的完整结果，未采用不完整输出"
        t["events"]=[dict(text="正在核对全文、图片与证据",at=db.now()),dict(text="处理已暂停："+t["error"],at=db.now())]
        return db.save(t,"旧核验错误")

    def test_legacy_failed_review_projects_correct_resume_without_rewriting_record(self):
        t=self.legacy_failed_review();before=copy.deepcopy(db.get(t["id"]))
        r=self.client.get(f"/api/tasks/{t['id']}");self.assertEqual(r.status_code,200)
        self.assertEqual(r.json()["resume_status"],"needs_review")
        self.assertIn("无需重新写稿",r.json()["error"])
        self.assertEqual(db.get(t["id"]),before)

    def test_legacy_failed_review_retries_only_reviewer(self):
        t=self.legacy_failed_review();original=copy.deepcopy(t["document"])
        with patch.object(w.llm,"complete",AsyncMock(return_value=VALID)) as model:
            r=self.client.post(f"/api/tasks/{t['id']}/review",json=dict(version=t["version"]))
        self.assertEqual(r.status_code,202);u=db.get(t["id"])
        self.assertEqual(u["document"],original);self.assertEqual(model.call_count,1)
        self.assertIn("Fact Reviewer",model.call_args.args[1]);self.assertEqual(u["status"],"approved")

    def test_new_reviewer_failure_preserves_draft_and_correct_stage(self):
        t=prepared("needs_review")
        with patch.object(w.llm,"complete",AsyncMock(side_effect=ServiceError("合成核验失败"))):
            self.client.post(f"/api/tasks/{t['id']}/review",json=dict(version=t["version"]))
        u=db.get(t["id"]);self.assertEqual(u["status"],"error")
        self.assertEqual(u["resume_status"],"needs_review");self.assertEqual(u["document"],DOC)

    def test_failed_writer_without_document_stays_at_plan(self):
        t=prepared("error");t["document"]=None;t["resume_status"]="plan_ready";db.save(t,"写稿失败")
        self.assertEqual(self.client.get(f"/api/tasks/{t['id']}").json()["resume_status"],"plan_ready")
        self.assertEqual(self.client.post(f"/api/tasks/{t['id']}/review",json=dict(version=t["version"])).status_code,400)

    def test_review_error_cannot_silently_trigger_writer(self):
        t=self.legacy_failed_review()
        with patch.object(w.llm,"complete",AsyncMock()) as model:
            r=self.client.post(f"/api/tasks/{t['id']}/confirm-plan",json=dict(version=t["version"],plan=PLAN))
        self.assertEqual(r.status_code,400);model.assert_not_called()
