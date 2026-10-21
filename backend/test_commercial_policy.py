"""Price/offer fallback and generic CTA behavior, isolated fixtures only."""
import asyncio
import copy
import csv
import io
import unittest
from unittest.mock import patch
from backend.planner_test_data import AsyncMock
from backend.test_brief_agent import BriefAgentTests, PRODUCTS
from backend.test_workflow import prepared, PLAN
from backend.brief_test_data import parsing,responses,STRATEGY
from backend import workflow as w,brief_agent as ba,evidence_policy as ep,schemas as S,storage as db
from backend.clients import Ima,ServiceError

# A distinct base avoids importing a TestCase into this module's discovery scope.
Base=BriefAgentTests
del BriefAgentTests

def need(category="price"):
    return dict(category=category,request="查询价格" if category=="price" else "查询教育优惠",evidence=[dict(turn_id="U1",quote="隔离测试")])

def priced(t,status="not_found",category="price"):
    a=t["brief_analysis"];a["commercial_requests"]=[need(category)]
    a["retrieval_plan"]["facts"].append(dict(id="PRICE",category=category,direction_id="D1",question="查询价格" if category=="price" else "查询教育优惠",conditions=["配置和时间"],priority="required"))
    package=copy.deepcopy(prepared()["package"])
    package["coverage"]=[dict(request_id="R1",status="supported",fact_ids=["F01"],reason="原文支持重量"),dict(request_id="PRICE",status=status,fact_ids=[],reason="没有资料或存在冲突")]
    return package

class CommercialPolicyTests(unittest.TestCase):
    setUp=Base.setUp
    tearDown=Base.tearDown
    task=Base.task
    analyze=Base.analyze
    ready=Base.ready

    def test_generic_store_cta_does_not_force_store_or_city_question(self):
        output=parsing();output["questions"]=[ba.question("user_constraints","请提供具体门店和城市","要引导到店体验"),ba.question("user_constraints","请提供预约或体验安排","到店体验需要安排")]
        t,_=self.analyze(self.task(),responses(output))
        self.assertEqual(t["status"],"brief_ready");self.assertEqual(t["brief_analysis"]["questions"],[])
    def test_explicit_address_request_still_asks_missing_address(self):
        t=self.task();t["dialogue"][0]["text"]="隔离测试，请文案写上具体门店地址";db.save(t,"fixture input")
        output=parsing();output["detail_requests"]=[dict(category="address",request="文案写上具体地址",evidence=[dict(turn_id="U1",quote="请文案写上具体门店地址")])]
        output["questions"]=[ba.question("user_constraints","请提供具体门店地址","用户要求文案包含地址")]
        u,model=self.analyze(t,[output]);self.assertEqual(model.await_count,1);self.assertEqual(u["status"],"needs_information")
    def test_price_evidence_is_not_a_brief_question(self):
        output=parsing();output["commercial_requests"]=[need()];output["questions"]=[ba.question("user_constraints","请提供价格或优惠政策","缺少具体金额")]
        t,_=self.analyze(self.task(),responses(output))
        self.assertEqual(t["status"],"brief_ready")
        self.assertTrue(any(r["category"]=="price" for r in t["brief_analysis"]["retrieval_plan"]["facts"]))
    def test_unrequested_price_task_is_removed(self):
        strategy=copy.deepcopy(STRATEGY);strategy["retrieval_plan"]["facts"].append(dict(id="BAD",direction_id="D1",question="查询价格和优惠",conditions=[],priority="required"))
        result=ep.normalize_strategy(strategy,[])
        self.assertEqual([r["id"] for r in result["retrieval_plan"]["facts"]],["R1"])
    def test_price_required_but_missing_continues_and_records_unmet_requirement(self):
        t=self.ready();t["package"]=priced(t)
        self.assertEqual(w.verify_coverage(t),[])
        policy=t["package"]["content_policy"]
        self.assertTrue(policy["omit_commercial"]);self.assertFalse(policy["approval_required"])
        self.assertFalse(policy["omitted_requests"][0]["requirement_satisfied"])
        self.assertEqual(t["package"]["coverage"][1]["status"],"not_found")
        self.assertTrue(ba.context(t)["content_policy"]["notices"])
    def test_price_conflict_is_omitted_without_blocking_product_facts(self):
        t=self.ready();t["package"]=priced(t,"conflict")
        t["package"]["conflicts"]=[dict(category="price",request_ids=["PRICE"],source_ids=["S1"],detail="同一配置同一时点金额冲突")]
        self.assertEqual(w.verify_coverage(t),[])
        self.assertEqual(t["package"]["conflicts"],[]);self.assertTrue(t["package"]["all_conflicts"])
        self.assertIn("冲突",t["package"]["content_policy"]["notices"][0])
    def test_product_conflict_still_blocks(self):
        t=self.ready();t["package"]=priced(t)
        t["package"]["conflicts"]=[dict(category="product",request_ids=["R1"],source_ids=["S1"],detail="同配置重量冲突")]
        w.verify_coverage(t)
        self.assertEqual(t["package"]["conflicts"],["同配置重量冲突"])
    def test_price_conflict_cannot_hide_product_request(self):
        t=self.ready();t["package"]=priced(t)
        t["package"]["conflicts"]=[dict(category="price",request_ids=["R1"],source_ids=["S1"],detail="伪装产品冲突")]
        with self.assertRaises(ServiceError):w.verify_coverage(t)
    def test_unsupported_offer_drops_financial_cards_and_writer_cannot_restore_amount(self):
        t=self.ready();t["package"]=priced(t,category="promotion")
        t["package"]["facts"].append(dict(id="F02",category="price",claim="价格3999元",quote="这是测试价格3999元，不是实际报价。",source_id="S1",conditions="fixture"))
        w.verify_coverage(t)
        self.assertEqual([f["id"] for f in t["package"]["facts"]],["F01"])
        self.assertIn("F02",t["package"]["content_policy"]["omitted_fact_ids"])
        t["plan"]=copy.deepcopy(PLAN);t["document"]=copy.deepcopy(prepared()["document"]);t["document"]["title"]="到手价3999元"
        self.assertTrue(any("已省略" in i["detail"] for i in w.deterministic_review(t)))
    def test_missing_price_continues_to_content_plan_without_extra_approval(self):
        t=self.ready();package=priced(t);t["brief_confirmation"]={"analysis_hash":ba.digest(t["brief_analysis"])}
        package["images"][0].update(description="fixture",name="fixture",mime="image/png")
        raw=dict(facts=copy.deepcopy(package["facts"]),conflicts=[],coverage=package["coverage"])
        outputs=[raw,dict(images=[dict(id="a"*20,description="图片",reason="适用",usable=True)]),copy.deepcopy(PLAN)]
        with patch.object(w.ima,"retrieve",AsyncMock(return_value=package)),patch.object(w.llm,"complete",AsyncMock(side_effect=outputs)) as model:
            asyncio.run(w.plan(t))
        self.assertEqual(t["status"],"plan_ready");self.assertEqual(model.await_count,3)
        self.assertTrue(model.await_args.args[2]["brief"]["content_policy"]["omit_commercial"])
    def test_supported_price_is_kept_when_offer_is_missing(self):
        t=self.ready();p=priced(t,category="promotion");t["brief_analysis"]["commercial_requests"].append(need("price"))
        t["brief_analysis"]["retrieval_plan"]["facts"].append(dict(id="VALID-PRICE",category="price",direction_id="D1",question="查询页面价格",conditions=[],priority="supporting"))
        p["facts"].append(dict(id="FPRICE",category="price",claim="测试快照价格5999元",quote="测试配置页面价格5999元，仅为隔离夹具。",source_id="S1",conditions="测试快照"))
        p["coverage"].append(dict(request_id="VALID-PRICE",status="supported",fact_ids=["FPRICE"],reason="测试快照"));t["package"]=p
        self.assertEqual(w.verify_coverage(t),[])
        self.assertIn("FPRICE",[f["id"] for f in p["facts"]]);self.assertFalse(p["content_policy"]["omit_commercial"])
        self.assertEqual(p["content_policy"]["allowed_categories"],["price"]);self.assertIn("promotion",p["content_policy"]["omitted_categories"])
        t["plan"]=copy.deepcopy(PLAN);t["document"]=copy.deepcopy(prepared()["document"]);t["document"]["title"]="测试快照5999元"
        self.assertFalse(any("已省略价格" in i["detail"] for i in w.deterministic_review(t)))
        t["document"]["title"]="学生优惠"
        self.assertTrue(any("已省略优惠" in i["detail"] for i in w.deterministic_review(t)))
    def test_only_explicit_refusal_to_generate_blocks_offer_gap(self):
        for text,blocked in [("需要优惠",False),("必须写优惠",False),("必须包含优惠，否则不生成",True),("没有优惠就不要生成",True)]:
            with self.subTest(text=text):
                t=self.ready();t["dialogue"].append(dict(id="U2",kind="user",text=text));t["package"]=priced(t,category="promotion")
                gaps=w.verify_coverage(t)
                self.assertEqual(bool(gaps),blocked)
                if blocked:
                    self.assertEqual(gaps[0]["blocking_reason"],"user_refuses_generation")
                    self.assertEqual(gaps[0]["blocking_evidence"][0]["turn_id"],"U2")
    def test_product_fact_cannot_satisfy_refused_missing_offer(self):
        t=self.ready();t["dialogue"].append(dict(id="U2",kind="user",text="必须包含优惠，否则不生成"));p=priced(t,"supported",category="promotion")
        p["coverage"][1]["fact_ids"]=["F01"];t["package"]=p
        gaps=w.verify_coverage(t)
        self.assertEqual(gaps[0]["blocking_reason"],"user_refuses_generation")
        self.assertEqual(p["content_policy"]["blocked_requests"][0]["status"],"not_usable")
    def test_one_missing_price_does_not_remove_other_supported_price_same_category(self):
        t=self.ready();p=priced(t)
        t["brief_analysis"]["retrieval_plan"]["facts"].append(dict(id="OTHER",category="price",direction_id="D1",question="另一配置价格",conditions=[],priority="supporting"))
        p["facts"].append(dict(id="FPRICE",category="price",claim="另一配置快照价格5999元",quote="另一测试配置页面价格5999元，仅为隔离夹具。",source_id="S1",conditions="fixture"))
        p["coverage"].append(dict(request_id="OTHER",status="supported",fact_ids=["FPRICE"],reason="fixture"));t["package"]=p
        self.assertEqual(w.verify_coverage(t),[]);self.assertIn("FPRICE",[f["id"] for f in p["facts"]])
        self.assertNotIn("price",p["content_policy"]["omitted_categories"])
    def test_model_required_or_block_flag_cannot_invent_user_refusal(self):
        t=self.ready();t["package"]=priced(t)
        t["brief_analysis"]["commercial_requests"][0].update(on_missing="block",blocking_evidence=[dict(turn_id="U1",quote="隔离测试")])
        self.assertEqual(w.verify_coverage(t),[])
    def test_explicit_refusal_applies_only_to_named_item(self):
        turns=[dict(id="U1",kind="user",text="价格可以省略，优惠必须有，否则不生成")]
        self.assertFalse(ep.hard_rule("price",turns));self.assertTrue(ep.hard_rule("promotion",turns))
    def test_latest_explicit_relaxation_removes_previous_refusal(self):
        original=dict(id="U1",kind="user",text="优惠必须有，否则不生成")
        for instruction in ("优惠找不到可以省略", "允许省略，继续生成", "取消优惠没有就不生成的要求，找不到就不写"):
            self.assertFalse(ep.hard_rule("promotion",[original,dict(id="U2",kind="user",text=instruction)]))
    def test_block_schema_requires_user_refusal_evidence(self):
        with self.assertRaises(ValueError):S.CommercialNeed.model_validate(need()|dict(on_missing="block"))
        need_obj=S.CommercialNeed.model_validate(need());self.assertEqual(need_obj.on_missing,"omit")
    def test_optional_product_request_citing_only_omitted_policy_does_not_block(self):
        t=self.ready();p=priced(t)
        p["facts"].append(dict(id="POLICY",claim="知识库不固定价格优惠",quote="本知识库不固定价格与优惠等动态信息。",source_id="S1",conditions="fixture"))
        t["brief_analysis"]["retrieval_plan"]["facts"].append(dict(id="OPTIONAL",direction_id="D1",category="product",question="通用到店说明",conditions=[],priority="supporting"))
        p["coverage"].append(dict(request_id="OPTIONAL",status="supported",fact_ids=["POLICY"],reason="非产品卖点"));t["package"]=p
        self.assertEqual(w.verify_coverage(t),[]);self.assertNotIn("POLICY",[f["id"] for f in p["facts"]])
    def test_resume_plan_reuses_cached_evidence_and_keeps_confirmation(self):
        t=self.ready();t["package"]=priced(t);t["brief_confirmation"]={"analysis_hash":ba.digest(t["brief_analysis"])}
        t["status"]="needs_review";t["resume_status"]="needs_review";t=db.save(t,"fixture old blocked task")
        outputs=[dict(images=[dict(id="a"*20,description="图片",reason="适用",usable=True)]),copy.deepcopy(PLAN)]
        with patch.object(w.ima,"retrieve",AsyncMock(side_effect=AssertionError("cached resume must not retrieve"))) as retrieve,patch.object(w.llm,"complete",AsyncMock(side_effect=outputs)) as model:
            r=self.client.post(f"/api/tasks/{t['id']}/resume-plan",json=dict(version=t["version"]))
        self.assertEqual(r.status_code,202);retrieve.assert_not_awaited();self.assertEqual(model.await_count,2)
        u=db.get(t["id"]);self.assertEqual(u["status"],"plan_ready");ba.assert_confirmed(u)
    def test_old_brief_roundtrips_without_injected_defaults_changing_hash(self):
        t=self.ready();t["brief_analysis"].pop("commercial_requests",None)
        for r in t["brief_analysis"]["retrieval_plan"]["facts"]:r.pop("category",None)
        t["brief_confirmation"]={"analysis_hash":ba.digest(t["brief_analysis"])};t=db.save(t,"fixture old schema")
        r=self.client.get(f"/api/tasks/{t['id']}");self.assertEqual(r.status_code,200)
        self.assertEqual(ba.digest(r.json()["brief_analysis"]),r.json()["brief_analysis_hash"])
    def test_old_categoryless_blocked_task_can_resume_under_current_policy(self):
        t=self.ready();t["package"]=priced(t);t["brief_analysis"].pop("commercial_requests",None)
        for request in t["brief_analysis"]["retrieval_plan"]["facts"]:request.pop("category",None)
        t["brief_confirmation"]={"analysis_hash":ba.digest(t["brief_analysis"])};t["status"]="needs_review";t=db.save(t,"fixture old blocked schema")
        outputs=[dict(images=[dict(id="a"*20,description="图片",reason="适用",usable=True)]),copy.deepcopy(PLAN)]
        with patch.object(w.ima,"retrieve",AsyncMock(side_effect=AssertionError("must reuse"))),patch.object(w.llm,"complete",AsyncMock(side_effect=outputs)):
            r=self.client.post(f"/api/tasks/{t['id']}/resume-plan",json=dict(version=t["version"]))
        self.assertEqual(r.status_code,202);self.assertEqual(db.get(t["id"])["status"],"plan_ready")
    def test_resume_rejects_stale_or_unconfirmed_task(self):
        t=self.ready();t["package"]=priced(t);t["status"]="needs_review";t=db.save(t,"fixture no confirmation")
        r=self.client.post(f"/api/tasks/{t['id']}/resume-plan",json=dict(version=t["version"]-1));self.assertEqual(r.status_code,409)
        r=self.client.post(f"/api/tasks/{t['id']}/resume-plan",json=dict(version=t["version"]));self.assertEqual(r.status_code,400)
    def test_public_price_rows_are_model_scoped_and_preserve_original_csv(self):
        ima=Ima();fields=["规范产品名称","精确款式","核验时间","官方URL","页面金额（元）"]
        stream=io.StringIO(newline="");writer=csv.writer(stream);writer.writerow(fields)
        writer.writerow(["HUAWEI MateBook 14（鸿蒙版）","16GB/512GB","2026-10-17","https://item.vmall.com/test","5999"])
        writer.writerow(["MateBook 14 酷睿 Ultra","16GB/1TB","2026-10-17","https://item.vmall.com/other","6999"])
        text=stream.getvalue()
        async def listing(folder=None):
            return {None:[dict(title="P1-产品参数库",media_type=99,media_id="p1")],"p1":[dict(title="08-官方公开价格快照",media_type=99,media_id="public")],"public":[dict(title="官方价格快照.csv",media_id="csv")]}[folder]
        with patch.object(ima,"listing",AsyncMock(side_effect=listing)),patch.object(ima,"fetch_media",AsyncMock(return_value=text.encode())):
            found=asyncio.run(ima.public_price_sources(dict(name="HUAWEI MateBook 14",category="鸿蒙电脑")))
        self.assertEqual(found[0]["record_count"],1);self.assertIn("5999",found[0]["text"]);self.assertNotIn("6999",found[0]["text"])
        self.assertIn(found[0]["text"].splitlines()[1],text)
    def test_no_price_request_does_not_read_public_price_layer(self):
        ima=Ima();content="测试型号重量约 1.33 kg，实际因配置而异。"*3
        with patch.object(ima,"listing",AsyncMock(return_value=[dict(title="产品事实.md",media_id="s")])),patch.object(ima,"knowledge_base",AsyncMock(return_value="kb")),patch.object(ima,"fetch_media",AsyncMock(return_value=content.encode())),patch.object(ima,"call",AsyncMock(return_value={"info_list":[]})),patch.object(ima,"public_price_sources",AsyncMock()) as public:
            asyncio.run(ima.retrieve(PRODUCTS[0],dict(retrieval_plan=STRATEGY["retrieval_plan"])))
        public.assert_not_awaited()

del Base

if __name__=="__main__":unittest.main()
