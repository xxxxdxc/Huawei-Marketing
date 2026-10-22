"""Brief V2 integration tests: synthetic responses, isolated SQLite, no paid APIs."""
import asyncio
import copy
import unittest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient
from pydantic import ValidationError
# Import isolated data configuration before backend modules.
from backend.test_workflow import prepared, TEST_DATA
from backend.main import app
from backend import storage as db, workflow as w, brief_agent as ba, schemas as S
from backend.clients import ServiceError, Ima
from backend.brief_test_data import parsing, responses, unknown, explicit, STRATEGY

PRODUCTS=[dict(id="test-product",name="测试型号",category="测试",folder="test",path="fixture/测试型号")]

class BriefAgentTests(unittest.TestCase):
    def setUp(self):
        self.client=TestClient(app);self.client.__enter__()
        self.catalog=patch.object(w.ima,"catalog",AsyncMock(return_value=copy.deepcopy(PRODUCTS)))
        self.catalog.start();self.addCleanup(self.catalog.stop)
    def tearDown(self):self.client.__exit__(None,None,None)
    def task(self):return db.create("这是隔离测试营销任务","test-product","moments")
    def analyze(self,t,outputs=None):
        with patch.object(w.llm,"complete",AsyncMock(side_effect=outputs or responses())) as model,patch.object(w.ima,"retrieve",AsyncMock()) as retrieve:
            r=self.client.post(f"/api/tasks/{t['id']}/analyze",json=dict(version=t["version"]))
            self.assertEqual(r.status_code,202)
            updated=db.get(t["id"])
            retrieve.assert_not_awaited()
        return updated,model
    def ready(self):
        t,model=self.analyze(self.task())
        self.assertEqual(t["status"],"brief_ready")
        return t
    def test_natural_language_create_needs_no_selector_or_catalog_connection(self):
        with patch.object(w.ima,"catalog",AsyncMock(side_effect=ServiceError("offline"))) as catalog:
            r=self.client.post("/api/tasks",json=dict(raw="给新生写一篇电脑营销图文"))
        self.assertEqual(r.status_code,201);self.assertIsNone(r.json()["product_id"]);self.assertIsNone(r.json()["platform"]);catalog.assert_not_awaited()
    def test_three_stages_have_versioned_inputs_and_outputs_without_retrieval(self):
        t,model=self.analyze(self.task())
        self.assertEqual(model.await_count,3)
        self.assertEqual([r["stage"] for r in t["brief_runs"]],["parsing","audience","strategy"])
        self.assertTrue(all(r["status"]=="completed" and r["input"] and r["output"] and r["version"]["source_sha256"] for r in t["brief_runs"]))
        self.assertEqual(t["brief_analysis"]["status"],"ready");self.assertIsNone(t["brief_confirmation"])
        self.assertEqual(t["brief_analysis"]["message_strategy"]["priorities"][0]["verification"],"pending")
        self.assertEqual(t["brief"],ba.projection(t["brief_analysis"]))
        with self.assertRaises(ValueError):ba.assert_confirmed(t)
    def test_ready_is_not_published_while_strategy_is_still_running(self):
        t=self.task();outputs=responses();index=0
        async def model(*args,**kwargs):
            nonlocal index
            current=db.get(t["id"])
            self.assertIsNone(current["brief_analysis"])
            answer=outputs[index];index+=1
            return answer
        with patch.object(w.llm,"complete",AsyncMock(side_effect=model)):
            r=self.client.post(f"/api/tasks/{t['id']}/analyze",json=dict(version=t["version"]))
        self.assertEqual(r.status_code,202);u=db.get(t["id"])
        self.assertEqual(u["brief_analysis"]["status"],"ready")
        r=self.client.get(f"/api/tasks/{t['id']}")
        self.assertEqual(r.status_code,200);self.assertEqual(r.json()["brief_analysis_hash"],ba.digest(u["brief_analysis"]))
        self.assertIn("MarketingBrief",app.openapi()["components"]["schemas"])
    def test_official_skill_is_read_and_unrelated_campaign_scope_trimmed(self):
        system,version=ba.instructions("audience")
        self.assertIn("Buying stage",system)
        self.assertNotIn("### 5. Content Calendar",system)
        self.assertTrue(version["source_blob"])
    def test_unknown_model_never_autoselected_from_catalog(self):
        t=db.create("给学生写一篇朋友圈电脑推荐")
        output=parsing();output["requirements"]["product_query"]=unknown();output["requirements"]["product_model"]=dict(value="测试型号",source="inferred",evidence=[],reason="目录里有")
        output["requirements"]["platform"]=explicit("moments","朋友圈","U1")
        u,model=self.analyze(t,[output])
        self.assertEqual(model.await_count,1);self.assertIsNone(u["product_id"])
        self.assertEqual(u["brief_analysis"]["status"],"need_clarification")
        self.assertTrue(any(q["field"]=="product_model" for q in u["brief_analysis"]["questions"]))
    def test_ambiguous_edition_requires_confirmation(self):
        t=db.create("推广 MateBook 14，发朋友圈")
        output=parsing(query="MateBook 14",product_turn="U1");output["requirements"]["platform"]=explicit("moments","朋友圈","U1")
        products=[PRODUCTS[0]|dict(id="a",name="HUAWEI MateBook 14 鸿蒙版"),PRODUCTS[0]|dict(id="b",name="HUAWEI MateBook 14 Windows版")]
        with patch.object(w.ima,"catalog",AsyncMock(return_value=products)):
            u,_=self.analyze(t,[output])
        self.assertEqual(u["brief_analysis"]["product_resolution"]["state"],"ambiguous");self.assertIsNone(u["product_id"])
        self.assertEqual(len(u["brief_analysis"]["product_resolution"]["candidates"]),2)
    def test_bare_family_name_does_not_select_exact_base_over_other_edition(self):
        t=db.create("推广 MateBook 14，发朋友圈")
        output=parsing(query="MateBook 14",product_turn="U1");output["requirements"]["platform"]=explicit("moments","朋友圈","U1")
        products=[PRODUCTS[0]|dict(id="harmony",name="HUAWEI MateBook 14",category="鸿蒙电脑"),PRODUCTS[0]|dict(id="windows",name="MateBook 14 酷睿 Ultra",category="MateBook-Windows")]
        with patch.object(w.ima,"catalog",AsyncMock(return_value=products)):
            u,_=self.analyze(t,[output])
        self.assertEqual(u["brief_analysis"]["product_resolution"]["state"],"ambiguous")
    def test_explicit_model_answer_with_category_resolves_catalog_identity(self):
        products=[PRODUCTS[0]|dict(id="harmony",name="HUAWEI MateBook 14",category="鸿蒙电脑"),PRODUCTS[0]|dict(id="windows",name="MateBook 14 酷睿 Ultra",category="MateBook-Windows")]
        q="HUAWEI MateBook 14（鸿蒙电脑）"
        parsed=parsing(query=q,product_turn="U2")
        turns=[dict(id="U2",kind="user",text=q,question_field="product_model")]
        resolved=ba.resolve_product(parsed["requirements"],products,turns)
        self.assertEqual(resolved["state"],"resolved");self.assertEqual(resolved["product_id"],"harmony")
    def test_restored_analysis_needs_new_confirmation(self):
        t=self.ready();version=t["version"]
        t["brief_confirmation"]={"analysis_hash":ba.digest(t["brief_analysis"])};t=db.save(t,"fixture confirmation")
        r=self.client.post(f"/api/tasks/{t['id']}/restore",json=dict(version=t["version"],target_version=version))
        self.assertEqual(r.status_code,200);self.assertIsNone(r.json()["brief_confirmation"])
        with self.assertRaises(ValueError):ba.assert_confirmed(r.json())
    def test_guessed_platform_is_not_silently_accepted(self):
        output=parsing();output["requirements"]["platform"]=dict(value="xiaohongshu",source="inferred",reason="学生常用",evidence=[])
        u,_=self.analyze(self.task(),[output])
        self.assertIsNone(u["platform"]);self.assertIsNone(u["brief"])
        self.assertTrue(any(q["field"]=="platform" for q in u["brief_analysis"]["questions"]))
    def test_fabricated_user_quote_is_rejected(self):
        output=parsing();output["requirements"]["target_audience"]=explicit("老板","用户根本没有说过这句话","U1")
        u,model=self.analyze(self.task(),[output])
        self.assertEqual(u["status"],"error");self.assertEqual(model.await_count,1);self.assertIsNone(u["brief_analysis"])
    def test_inferred_fields_require_reason_and_explicit_fields_require_evidence(self):
        for field in (dict(value="学生",source="inferred",reason="",evidence=[]),dict(value="学生",source="explicit",reason="",evidence=[])):
            with self.assertRaises(ValidationError):S.TextField.model_validate(field)
    def test_conflict_pauses_before_audience_and_strategy(self):
        output=parsing();output["questions"]=[ba.question("user_constraints","必须同时保留两个互斥要求吗？","用户条件冲突",kind="conflict")]
        u,model=self.analyze(self.task(),[output])
        self.assertEqual(u["brief_analysis"]["status"],"needs_resolution");self.assertEqual(model.await_count,1)
        self.assertIsNone(u["brief_analysis"]["audience_insight"])
    def test_answer_round_preserves_history_and_recomputes_missing_fields(self):
        output=parsing();output["requirements"]["platform"]=unknown()
        u,_=self.analyze(self.task(),[output]);q=next(q for q in u["brief_analysis"]["questions"] if q["field"]=="platform")
        updated=parsing(platform="wechat",platform_turn="U2")
        with patch.object(w.llm,"complete",AsyncMock(side_effect=responses(updated))),patch.object(w.ima,"retrieve",AsyncMock()) as retrieve:
            r=self.client.post(f"/api/tasks/{u['id']}/brief/answers",json=dict(version=u["version"],answers=[dict(question_id=q["id"],answer="公众号")]))
        self.assertEqual(r.status_code,202);retrieve.assert_not_awaited();u=db.get(u["id"])
        self.assertEqual(u["status"],"brief_ready");self.assertEqual(u["platform"],"wechat")
        self.assertEqual(u["dialogue"][-1]["question_id"],q["id"])
        self.assertEqual(u["brief_analysis"]["requirements"]["platform"]["evidence"][0]["turn_id"],"U2")
        self.assertIsNone(u["brief_confirmation"])
    def test_partial_answer_only_resolves_answered_fields(self):
        output=parsing();output["requirements"]["platform"]=unknown();output["requirements"]["product_query"]=unknown()
        t,_=self.analyze(self.task(),[output]);q=next(q for q in t["brief_analysis"]["questions"] if q["field"]=="platform")
        next_parse=parsing(platform="wechat",platform_turn="U2");next_parse["requirements"]["product_query"]=unknown()
        with patch.object(w.llm,"complete",AsyncMock(side_effect=[next_parse])) as model:
            r=self.client.post(f"/api/tasks/{t['id']}/brief/answers",json=dict(version=t["version"],answers=[dict(question_id=q["id"],answer="公众号")]))
        self.assertEqual(r.status_code,202);model.assert_awaited_once()
        u=db.get(t["id"]);self.assertEqual(u["status"],"needs_information");self.assertEqual(u["platform"],"wechat")
        self.assertTrue(any(q["field"]=="product_model" for q in u["brief_analysis"]["questions"]))
    def test_unchanged_legacy_projection_can_confirm_v2(self):
        t=self.ready()
        with patch.object(w,"job",AsyncMock()):
            r=self.client.post(f"/api/tasks/{t['id']}/confirm-brief",json=dict(version=t["version"],brief=t["brief"]))
        self.assertEqual(r.status_code,202);ba.assert_confirmed(db.get(t["id"]))
    def test_unknown_duplicate_or_stale_answers_do_not_change_state(self):
        output=parsing();output["requirements"]["platform"]=unknown()
        t,_=self.analyze(self.task(),[output]);q=t["brief_analysis"]["questions"][0]["id"]
        cases=[(t["version"],[dict(question_id="invalid",answer="公众号")],400),(t["version"],[dict(question_id=q,answer="公众号")]*2,400),(t["version"]-1,[dict(question_id=q,answer="公众号")],409)]
        for version,answers,expected in cases:
            r=self.client.post(f"/api/tasks/{t['id']}/brief/answers",json=dict(version=version,answers=answers))
            self.assertEqual(r.status_code,expected);self.assertEqual(db.get(t["id"])["version"],t["version"])
    def test_cannot_confirm_missing_information(self):
        output=parsing();output["requirements"]["product_query"]=unknown()
        t,_=self.analyze(self.task(),[output])
        with patch.object(w,"job",AsyncMock()) as job:
            r=self.client.post(f"/api/tasks/{t['id']}/confirm-brief",json=dict(version=t["version"]))
        self.assertEqual(r.status_code,400);job.assert_not_awaited()
    def test_clearing_projection_questions_does_not_bypass_canonical_gate(self):
        output=parsing();output["requirements"]["product_query"]=unknown()
        t,_=self.analyze(self.task(),[output]);edited=copy.deepcopy(t["brief"]);edited["questions"]=[]
        r=self.client.post(f"/api/tasks/{t['id']}/confirm-brief",json=dict(version=t["version"],brief=edited))
        self.assertEqual(r.status_code,400);self.assertIsNone(db.get(t["id"])["brief_confirmation"])
    def test_confirmation_records_hash_and_rejects_wrong_hash(self):
        t=self.ready()
        r=self.client.post(f"/api/tasks/{t['id']}/confirm-brief",json=dict(version=t["version"],analysis_hash="obsolete"))
        self.assertEqual(r.status_code,409)
        with patch.object(w,"job",AsyncMock()):
            r=self.client.post(f"/api/tasks/{t['id']}/confirm-brief",json=dict(version=t["version"],analysis_hash=ba.digest(t["brief_analysis"])))
        self.assertEqual(r.status_code,202);u=db.get(t["id"]);ba.assert_confirmed(u)
        self.assertEqual(u["last_confirmed_brief"],u["brief_analysis"])
        u["brief_analysis"]["message_strategy"]["theme"]="changed"
        with self.assertRaises(ValueError):ba.assert_confirmed(u)
    def test_legacy_card_edits_restart_analysis_instead_of_retrieval(self):
        t=self.ready();edited=copy.deepcopy(t["brief"]);edited["tone"]="更正式"
        with patch.object(w,"job",AsyncMock()) as job:
            r=self.client.post(f"/api/tasks/{t['id']}/confirm-brief",json=dict(version=t["version"],brief=edited))
        self.assertEqual(r.status_code,202);self.assertEqual(job.await_args.args[1],"analyze")
        u=db.get(t["id"]);self.assertIsNone(u["brief_analysis"]);self.assertIn("更正式",u["dialogue"][-1]["text"])
    def test_plan_cannot_be_invoked_before_confirmation(self):
        t=self.ready()
        with patch.object(w.ima,"retrieve",AsyncMock()) as retrieve:
            with self.assertRaises(ValueError):asyncio.run(w.plan(t))
        retrieve.assert_not_awaited()
    def test_identity_evidence_gap_stops_before_image_selection(self):
        t=self.ready();t['brief_analysis']['retrieval_plan']['facts'][0]['guardrail']='identity';t["brief_confirmation"]={"analysis_hash":ba.digest(t["brief_analysis"])}
        package=copy.deepcopy(prepared()["package"])
        raw=dict(facts=package["facts"],conflicts=[],coverage=[dict(request_id="R1",status="not_found",fact_ids=[],reason="原文不足以回答指定配置条件")])
        with patch.object(w.ima,"retrieve",AsyncMock(return_value=package)) as retrieve,patch.object(w.llm,"complete",AsyncMock(return_value=raw)) as model:
            asyncio.run(w.plan(t))
        self.assertEqual(model.await_count,1);self.assertEqual(t["status"],"needs_review")
        self.assertTrue(t["package"]["evidence_gaps"]);self.assertIsNone(t["plan"])
        self.assertEqual(retrieve.await_args.args[1]["retrieval_plan"],t["brief_analysis"]["retrieval_plan"])
    def test_no_relevant_facts_reports_human_evidence_gap_instead_of_fabricating(self):
        t=self.ready();t["brief_confirmation"]={"analysis_hash":ba.digest(t["brief_analysis"])}
        package=copy.deepcopy(prepared()["package"])
        raw=dict(facts=[],conflicts=[],coverage=[dict(request_id="R1",status="not_found",fact_ids=[],reason="没有相关证据")])
        S.RetrievalFacts.model_validate(raw)
        with patch.object(w.ima,"retrieve",AsyncMock(return_value=package)),patch.object(w.llm,"complete",AsyncMock(return_value=raw)) as model:
            asyncio.run(w.plan(t))
        self.assertEqual(t["status"],"needs_review");self.assertEqual(t["package"]["facts"],[]);self.assertEqual(model.await_count,1)
    def test_coverage_cannot_claim_support_without_evidence_or_skip_request(self):
        t=self.ready();t["package"]=copy.deepcopy(prepared()["package"])
        for coverage in ([],[dict(request_id="R1",status="supported",fact_ids=[],reason="empty")],[dict(request_id="R1",status="supported",fact_ids=["missing"],reason="invalid")]):
            t["package"]["coverage"]=coverage
            with self.assertRaises(ServiceError):w.verify_coverage(t)
    def test_retrieval_searches_use_confirmed_requests_but_read_verified_directory(self):
        ima=Ima();content="测试型号重量约 1.33 kg，实际因配置而异。"*3
        async def call(route,body):
            self.assertEqual(route,"search_knowledge")
            return {"knowledge_list":[{"media_id":"outside-product"}]}
        with patch.object(ima,"listing",AsyncMock(return_value=[dict(title="产品事实.md",media_id="verified-source")])),patch.object(ima,"knowledge_base",AsyncMock(return_value="fixture-kb")),patch.object(ima,"fetch_media",AsyncMock(return_value=content.encode())) as fetch,patch.object(ima,"call",AsyncMock(side_effect=call)) as search:
            package=asyncio.run(ima.retrieve(PRODUCTS[0],dict(retrieval_plan=STRATEGY["retrieval_plan"])))
        self.assertEqual(search.await_count,2);self.assertIn("重量",search.await_args.args[1]["query"])
        fetch.assert_awaited_once_with("verified-source")
        self.assertEqual(package["request_searches"][1]["request_id"],"R1")
    def test_strategy_cannot_reference_unknown_direction_or_verified_claim(self):
        bad=copy.deepcopy(STRATEGY);bad["retrieval_plan"]["facts"][0]["direction_id"]="unknown"
        with self.assertRaises(ValidationError):S.StrategyResult.model_validate(bad)
        bad=copy.deepcopy(STRATEGY);bad["message_strategy"]["priorities"][0]["verification"]="verified"
        with self.assertRaises(ValidationError):S.StrategyResult.model_validate(bad)

if __name__=="__main__":unittest.main()
