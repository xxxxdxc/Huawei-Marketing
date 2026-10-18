"""Isolated fixture tests; no provider calls and no competition evidence."""
import copy, os, tempfile, unittest
from unittest.mock import AsyncMock, patch
TEST_DATA=tempfile.TemporaryDirectory(prefix="huawei-tests-")
os.environ["HUAWEI_DATA_DIR"]=TEST_DATA.name
from fastapi.testclient import TestClient
from backend.main import app
from backend import storage as db, workflow as w
from backend.clients import ServiceError
from backend.schemas import BriefUpdate
from backend import brief_agent as ba
from backend.brief_test_data import parsing, responses
from pydantic import ValidationError

BRIEF=dict(audience="测试人群",scenario="测试场景",platform="moments",goal="咨询",purchase_stage="了解",pain_points=["测试"],strategy="测试策略",tone="自然",emphasis=["重量"],questions=[])
DOC=dict(title="测试标题",lead="",paragraphs=[dict(section_id="P1",heading="携带",text="约 1.33 kg。",fact_ids=["F01"],image_id="a"*20,caption="测试产品图")],cta="欢迎咨询",tags=[])
PLAN=dict(angle="测试角度",title_direction="场景",sections=[dict(id="P1",heading="携带",purpose="介绍重量",fact_ids=["F01"],image_id="a"*20,image_reason="测试")],cta="欢迎咨询")
def prepared(status="plan_ready"):
    t=db.create("这是隔离测试任务","test-product","moments")
    t.update(brief=copy.deepcopy(BRIEF),status=status,resume_status=status,plan=copy.deepcopy(PLAN),document=copy.deepcopy(DOC),package=dict(product=dict(id="test-product",name="测试型号"),facts=[dict(id="F01",claim="约 1.33 kg",quote="测试型号重量约 1.33 kg，实际因配置而异。",source_id="S1",conditions="实际因配置而异")],sources=[dict(id="S1",title="测试资料",text="测试型号重量约 1.33 kg，实际因配置而异。",path="fixture")],images=[dict(id="a"*20,model_verified=True)],conflicts=[]))
    return db.save(t,"隔离测试资料")

class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.client=TestClient(app);self.client.__enter__()
    def tearDown(self):self.client.__exit__(None,None,None)
    def test_confirmation_cannot_be_skipped(self):
        t=db.create("这是隔离测试任务","test","moments")
        r=self.client.post(f"/api/tasks/{t['id']}/confirm-plan",json=dict(version=t["version"],plan=PLAN))
        self.assertEqual(r.status_code,400)
    def test_stale_version_rejected(self):
        t=prepared()
        r=self.client.put(f"/api/tasks/{t['id']}/plan",json=dict(version=t["version"]-1,plan=PLAN))
        self.assertEqual(r.status_code,409)
    def test_unknown_fact_rejected(self):
        t=prepared();plan=copy.deepcopy(PLAN);plan["sections"][0]["fact_ids"]=["MISSING"]
        r=self.client.put(f"/api/tasks/{t['id']}/plan",json=dict(version=t["version"],plan=plan))
        self.assertEqual(r.status_code,400)
    def test_wrong_model_image_rejected(self):
        t=prepared();plan=copy.deepcopy(PLAN);plan["sections"][0]["image_id"]="b"*20
        with self.assertRaises(ValueError):w.validate_plan(t,plan)
    def test_duplicate_image_and_platform_shortage(self):
        t=prepared();t["brief"]["platform"]="xiaohongshu"
        with self.assertRaises(ValueError):w.validate_plan(t,t["plan"])
        t["brief"]["platform"]="moments";plan=copy.deepcopy(PLAN);plan["sections"].append(plan["sections"][0]|{"id":"P2"})
        with self.assertRaises(ValueError):w.validate_plan(t,plan)
    def test_fact_quote_must_match_original(self):
        t=prepared();w.verify_facts(t["package"])
        t["package"]["facts"][0]["quote"]="这句话并不存在于原始资料中。"
        with self.assertRaises(ServiceError):w.verify_facts(t["package"])
    def test_unreferenced_number_in_title_is_detected(self):
        t=prepared();t["document"]["title"]="只要 999 元"
        self.assertTrue(any(i["category"]=="fact" for i in w.deterministic_review(t)))
    def test_document_edit_invalidates_export(self):
        t=prepared("approved");t["review"]={"passed":True,"document_hash":db.digest(t),"summary":"fixture","issues":[]};db.save(t,"隔离测试通过")
        t=db.get(t["id"]);self.assertTrue(w.can_export(t))
        r=self.client.put(f"/api/tasks/{t['id']}/document",json=dict(version=t["version"],document=DOC|{"title":"用户修改"}))
        self.assertEqual(r.status_code,200);updated=r.json();self.assertIsNone(updated["review"]);self.assertFalse(w.can_export(updated))
        self.assertEqual(self.client.get(f"/api/tasks/{t['id']}/export").status_code,400)
    def test_hash_prevents_stale_approval(self):
        t=prepared("approved");t["review"]={"passed":True,"document_hash":db.digest(t)};self.assertTrue(w.can_export(t));t["plan"]["angle"]="改变";self.assertFalse(w.can_export(t))
    def test_restore_creates_version_and_invalidates_review(self):
        t=prepared("approved");old=t["version"];t["review"]={"passed":True,"document_hash":db.digest(t)};db.save(t,"保存核验")
        t=db.get(t["id"]);r=self.client.post(f"/api/tasks/{t['id']}/restore",json=dict(version=t["version"],target_version=old))
        self.assertEqual(r.status_code,200);self.assertGreater(r.json()["version"],t["version"]);self.assertIsNone(r.json()["review"])
    def test_strict_schema_rejects_coercion(self):
        with self.assertRaises(ValidationError):BriefUpdate.model_validate(dict(version="1",brief=BRIEF))
    def test_cross_origin_write_rejected(self):
        r=self.client.post("/api/settings/probe",headers={"origin":"https://unrelated.example"})
        self.assertEqual(r.status_code,403)
    def test_busy_task_cannot_reconfirm(self):
        t=prepared("writing")
        r=self.client.post(f"/api/tasks/{t['id']}/confirm-brief",json=dict(version=t["version"],brief=BRIEF))
        self.assertEqual(r.status_code,400)
    def test_dpapi_roundtrip(self):
        from backend.settings import protect
        value=b"isolated-test-secret"
        self.assertEqual(protect(protect(value),decrypt=True),value)
    def test_full_workflow_with_explicit_fixture_models(self):
        import asyncio
        t=prepared("draft");t["brief"]=None;t["document"]=None;t["plan"]=None
        package=prepared()["package"]
        package["images"][0].update(name="fixture.png",model="测试型号",source="fixture",description="测试图片",mime="image/png")
        outputs=responses()+[dict(facts=copy.deepcopy(package["facts"]),conflicts=[],coverage=[dict(request_id="R1",status="supported",fact_ids=["F01"],reason="原文提供重量与条件")]),dict(images=[dict(id="a"*20,description="测试图片",reason="场景匹配",usable=True)]),copy.deepcopy(PLAN),copy.deepcopy(DOC),dict(summary="隔离测试核验",issues=[])]
        with patch.object(w.ima,"catalog",AsyncMock(return_value=[dict(id="test-product",name="测试型号",category="测试",folder="test")])),patch.object(w.ima,"retrieve",AsyncMock(return_value=package)),patch.object(w.llm,"complete",AsyncMock(side_effect=outputs)),patch.object(w,"get_settings",return_value=dict(writer_model="fixture-writer",reviewer_model="fixture-reviewer",vision=True)):
            asyncio.run(w.analyze(t));self.assertEqual(t["status"],"brief_ready")
            t["brief_confirmation"]={"analysis_hash":ba.digest(t["brief_analysis"])}
            asyncio.run(w.plan(t));self.assertEqual(t["status"],"plan_ready");self.assertIsNone(t["document"])
            asyncio.run(w.write(t));self.assertTrue(w.can_export(t));self.assertEqual(w.llm.complete.call_count,8)
    def test_natural_language_platform_change_restarts_confirmation(self):
        t=prepared("approved")
        output=parsing(platform="wechat",platform_turn="U2");output["requirements"]["platform"]["evidence"][0]["quote"]="公众号"
        with patch.object(w.ima,"catalog",AsyncMock(return_value=[dict(id="test-product",name="测试型号",category="测试")])),patch.object(w.llm,"complete",AsyncMock(side_effect=responses(output))):
            r=self.client.post(f"/api/tasks/{t['id']}/modify",json=dict(version=t["version"],instruction="改成公众号"))
        self.assertEqual(r.status_code,202)
        updated=db.get(t["id"]);self.assertEqual(updated["platform"],"wechat");self.assertEqual(updated["status"],"brief_ready");self.assertIsNone(updated["review"])
    def test_failed_analysis_can_be_retried_from_draft_gate(self):
        t=db.create("这是隔离测试任务","test-product","moments")
        with patch.object(w.ima,"catalog",AsyncMock(return_value=[dict(id="test-product",name="测试型号",category="测试")])),patch.object(w.llm,"complete",AsyncMock(side_effect=ServiceError("模型不可用"))):
            self.client.post(f"/api/tasks/{t['id']}/analyze",json=dict(version=t["version"]))
        updated=db.get(t["id"]);self.assertEqual(updated["status"],"error");self.assertEqual(updated["resume_status"],"draft")
    def test_writer_and_reviewer_secrets_are_independent(self):
        from backend import settings
        from pathlib import Path
        with tempfile.TemporaryDirectory(prefix="huawei-role-keys-") as directory,patch.object(settings,"DATA",Path(directory)),patch.object(settings,"user_env",return_value=""):
            conf=settings.DEFAULTS.copy()
            settings.save_settings(conf,"fixture-writer-key","fixture-reviewer-key")
            self.assertEqual(settings.api_key(),"fixture-writer-key")
            self.assertEqual(settings.api_key("reviewer"),"fixture-reviewer-key")
            settings.save_settings(conf,"fixture-writer-updated")
            self.assertEqual(settings.api_key("reviewer"),"fixture-reviewer-key")
            self.assertNotIn("fixture-writer",(Path(directory)/"settings.json").read_text(encoding="utf-8"))
            self.assertNotEqual((Path(directory)/"reviewer_credential.bin").read_bytes(),b"fixture-reviewer-key")
    def test_legacy_key_is_reviewer_fallback_only_when_no_dedicated_key(self):
        from backend import settings
        from pathlib import Path
        with tempfile.TemporaryDirectory(prefix="huawei-key-fallback-") as directory,patch.object(settings,"DATA",Path(directory)),patch.object(settings,"user_env",return_value=""):
            settings.save_settings(settings.DEFAULTS.copy(),"fixture-shared-key")
            self.assertEqual(settings.api_key("reviewer"),"fixture-shared-key")
            self.assertTrue(settings.public_settings()["reviewer_uses_writer_key"])
    def test_reviewer_request_uses_reviewer_authorization(self):
        import asyncio,httpx
        from backend import clients
        from backend.schemas import Review
        wire=AsyncMock();wire.__aenter__.return_value=wire
        wire.post.return_value=httpx.Response(200,json={"choices":[{"message":{"content":'{"summary":"fixture","issues":[]}'},"finish_reason":"stop"}]})
        with patch.object(clients,"api_key",side_effect=lambda role: {"writer":"fixture-writer","reviewer":"fixture-reviewer"}[role]),patch.object(clients.httpx,"AsyncClient",return_value=wire):
            asyncio.run(clients.llm.complete("gpt-6.1-sol","fixture",{},Review,role="reviewer"))
        self.assertEqual(wire.post.call_args.kwargs["headers"]["Authorization"],"Bearer fixture-reviewer")
    def image_swap_task(self):
        t=prepared("approved")
        t["package"]["images"].append(dict(id="b"*20,model_verified=True))
        t["review"]={"passed":True,"document_hash":db.digest(t),"summary":"fixture","issues":[]}
        return db.save(t,"隔离测试配图候选")
    def swap_document(self,t,image_id):
        d=copy.deepcopy(t["document"]);d["paragraphs"][0]["image_id"]=image_id
        return self.client.put(f"/api/tasks/{t['id']}/document",json=dict(version=t["version"],document=d))
    def test_user_image_swap_is_recorded_and_needs_review(self):
        t=self.image_swap_task();r=self.swap_document(t,"b"*20)
        self.assertEqual(r.status_code,200);u=r.json()
        self.assertEqual(u["status"],"needs_review");self.assertIsNone(u["review"]);self.assertFalse(w.can_export(u))
        self.assertEqual(u["plan"]["sections"][0]["image_id"],"a"*20)
        self.assertEqual(u["user_image_overrides"]["P1"]["origin"],"user_document_edit")
        self.assertEqual(w.effective_plan(u)["sections"][0]["image_id"],"b"*20)
        self.assertFalse(any(i["category"]=="image" for i in w.deterministic_review(u)))
    def test_model_image_swap_without_user_record_still_fails(self):
        t=self.image_swap_task();t["document"]["paragraphs"][0]["image_id"]="b"*20
        self.assertTrue(any(i["category"]=="image" and "没有对应" in i["detail"] for i in w.deterministic_review(t)))
    def test_text_edit_does_not_authorize_existing_model_image_swap(self):
        t=self.image_swap_task();t["document"]["paragraphs"][0]["image_id"]="b"*20;t=db.save(t,"隔离模拟模型擅自换图")
        d=copy.deepcopy(t["document"]);d["title"]="用户只改标题"
        r=self.client.put(f"/api/tasks/{t['id']}/document",json=dict(version=t["version"],document=d))
        self.assertEqual(r.status_code,200);self.assertFalse(r.json().get("user_image_overrides"))
        self.assertTrue(any(i["category"]=="image" for i in w.deterministic_review(r.json())))
    def test_foreign_and_unverified_user_images_rejected(self):
        for image_id,verified in [("c"*20,True),("b"*20,False)]:
            with self.subTest(image_id=image_id,verified=verified):
                t=self.image_swap_task();t["package"]["images"][1]["model_verified"]=verified;t=db.save(t,"候选校验状态")
                r=self.swap_document(t,image_id);self.assertEqual(r.status_code,400)
                self.assertEqual(db.get(t["id"])["version"],t["version"])
    def test_duplicate_images_rejected_on_document_save(self):
        t=self.image_swap_task();t["plan"]["sections"].append(t["plan"]["sections"][0]|dict(id="P2",image_id="b"*20))
        t["document"]["paragraphs"].append(t["document"]["paragraphs"][0]|dict(section_id="P2",image_id="b"*20));t=db.save(t,"两段隔离图文")
        d=copy.deepcopy(t["document"]);d["paragraphs"][1]["image_id"]="a"*20
        r=self.client.put(f"/api/tasks/{t['id']}/document",json=dict(version=t["version"],document=d));self.assertEqual(r.status_code,400)
    def test_image_removal_cannot_bypass_platform_minimum(self):
        t=self.image_swap_task();self.assertEqual(self.swap_document(t,None).status_code,400)
    def test_revert_to_original_image_clears_override(self):
        t=self.image_swap_task();u=self.swap_document(t,"b"*20).json()
        r=self.swap_document(u,"a"*20);self.assertEqual(r.status_code,200);self.assertFalse(r.json()["user_image_overrides"])
    def test_reviewer_receives_effective_plan_and_current_images(self):
        import asyncio
        t=self.image_swap_task();u=self.swap_document(t,"b"*20).json()
        with patch.object(w.llm,"complete",AsyncMock(return_value=dict(summary="隔离复核",issues=[]))):
            asyncio.run(w.review(u));args=w.llm.complete.await_args
            self.assertEqual(args.args[2]["plan"]["sections"][0]["image_id"],"b"*20)
            self.assertEqual([x["id"] for x in args.kwargs["images"]],["b"*20])
        self.assertTrue(w.can_export(u))
    def test_reconfirming_strategy_clears_image_authorizations(self):
        t=self.image_swap_task();u=self.swap_document(t,"b"*20).json()
        with patch.object(w,"job",AsyncMock()):
            r=self.client.post(f"/api/tasks/{u['id']}/confirm-brief",json=dict(version=u["version"],brief=BRIEF))
        self.assertEqual(r.status_code,202);self.assertFalse(db.get(u["id"])["user_image_overrides"])
    def test_settings_never_return_key(self):
        r=self.client.get("/api/settings");self.assertEqual(r.status_code,200);self.assertNotIn("api_key",r.json());self.assertNotIn("reviewer_api_key",r.json())

if __name__=="__main__":unittest.main()
