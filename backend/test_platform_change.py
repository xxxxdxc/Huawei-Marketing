"""Platform-only migration and Vmall boundary tests. Synthetic models/HTTP."""
import asyncio
import copy
import hashlib
import io
import json
import unittest
from unittest.mock import patch
from backend.planner_test_data import AsyncMock
import httpx
from PIL import Image
from fastapi.testclient import TestClient
from backend.test_workflow import prepared,PLAN
from backend.brief_test_data import parsing,AUDIENCE,STRATEGY
from backend.main import app
from backend import storage as db,brief_agent as ba,workflow as w,platform_change as pc,vmall
from backend.clients import ServiceError
from backend.settings import ASSETS


def task(images=2):
    t=prepared("approved")
    requirements=parsing()["requirements"]
    requirements["product_model"]=dict(value="测试型号",source="inferred",evidence=[],reason="目录已确认")
    t["brief_analysis"]=dict(schema_version="2",status="ready",requirements=requirements,commercial_requests=[],
        product_resolution=dict(state="resolved",product_id="test-product",product_model="测试型号",candidates=[]),
        questions=[],audience_insight=copy.deepcopy(AUDIENCE),**copy.deepcopy(STRATEGY))
    t["brief"]=ba.projection(t["brief_analysis"])
    t["brief_confirmation"]=dict(analysis_hash=ba.digest(t["brief_analysis"]),authorized_version=t["version"])
    t["brief_runs"]=[]
    t["package"]["coverage"]=[dict(request_id="R1",status="supported",fact_ids=["F01"],reason="原文有依据")]
    t["package"]["images"]=[]
    for i,color in enumerate(("white","black","red")[:images]):
        iid=chr(97+i)*20;out=io.BytesIO();Image.new("RGB",(220,220),color).save(out,format="PNG")
        body=out.getvalue();(ASSETS/iid).write_bytes(body)
        t["package"]["images"].append(dict(id=iid,model_verified=True,visual_checked=True,usable=True,
            sha256=hashlib.sha256(body).hexdigest(),mime="image/png",description="测试图",source="fixture",selection_reason="已核验"))
    t["package"]["asset_candidates"]=copy.deepcopy(t["package"]["images"])
    t["review"]=dict(passed=True,document_hash=db.digest(t))
    return db.save(t,"已确认的隔离迁移样例")


def plan_two():
    p=copy.deepcopy(PLAN)
    p["sections"].append(p["sections"][0]|dict(id="P2",image_id="b"*20))
    return p


def empty_supplement():
    return dict(sources=[],images=[],audit=dict(source="vmall",status="unavailable"))


class PlatformChangeTests(unittest.TestCase):
    def setUp(self):
        self.client=TestClient(app);self.client.__enter__()
    def tearDown(self):self.client.__exit__(None,None,None)

    def test_platform_route_calls_only_planner_and_preserves_history(self):
        t=task();old=copy.deepcopy(t["brief_analysis"])
        with patch.object(w.llm,"complete",AsyncMock(return_value=plan_two())) as llm,patch.object(w.ima,"retrieve_for_task",AsyncMock()) as retrieve,patch.object(vmall,"supplement",AsyncMock()) as supplement:
            r=self.client.post(f"/api/tasks/{t['id']}/change-platform",json=dict(version=t["version"],platform="wechat"))
        self.assertEqual(r.status_code,202)
        u=db.get(t["id"]);self.assertEqual(u["status"],"plan_ready")
        self.assertEqual(llm.call_count,1);retrieve.assert_not_called();supplement.assert_not_called()
        self.assertIn("Content Planner",llm.call_args.args[1])
        self.assertEqual(llm.call_args.args[2]["policy"]["name"],"公众号")
        self.assertEqual(u["brief_analysis"]["audience_insight"],old["audience_insight"])
        self.assertEqual(u["brief_analysis"]["message_strategy"],old["message_strategy"])
        self.assertEqual(u["brief_analysis"]["retrieval_plan"],old["retrieval_plan"])
        self.assertEqual(u["brief_runs"],[])
        self.assertIsNone(u["document"]);self.assertIsNone(u["review"]);self.assertFalse(w.can_export(u))
        self.assertEqual(u["brief_confirmation"]["analysis_hash"],ba.digest(u["brief_analysis"]))
        self.assertEqual(u["platform_changes"][0]["original_confirmation"],t["brief_confirmation"])
        self.assertIsNotNone(db.snapshot(t["id"],t["version"])["document"])
        ba.assert_confirmed(u)
        self.assertEqual(u["brief_analysis"]["requirements"]["user_constraints"],old["requirements"]["user_constraints"])

    def test_existing_frontend_instruction_uses_fast_branch(self):
        t=task()
        text="将目标发布平台改为微信公众号，保留产品型号、人群和营销目标，重新应用该平台的内容与配图规则。"
        with patch.object(w.llm,"complete",AsyncMock(return_value=plan_two())) as model:
            r=self.client.post(f"/api/tasks/{t['id']}/modify",json=dict(version=t["version"],instruction=text))
        self.assertEqual(r.status_code,202);self.assertEqual(model.call_count,1)
        self.assertEqual(db.get(t["id"])["status"],"plan_ready")

    def test_short_command_supported_but_mixed_edits_not_classified(self):
        self.assertEqual(pc.detect_platform("改成公众号"),"wechat")
        self.assertIsNone(pc.detect_platform("改成公众号，人群改成程序员"))
        self.assertIsNone(pc.detect_platform("改成公众号并删除优惠"))
        self.assertIsNone(pc.detect_platform("改成公众号或者小红书"))
        self.assertIsNone(pc.detect_platform("不要改成公众号"))

    def test_mixed_edit_still_runs_brief_and_invalidates_package(self):
        t=task()
        with patch.object(w,"job",AsyncMock()) as job:
            r=self.client.post(f"/api/tasks/{t['id']}/modify",json=dict(version=t["version"],instruction="改成公众号，人群改成程序员"))
        self.assertEqual(r.status_code,202);self.assertEqual(job.call_args.args[1],"analyze")
        u=db.get(t["id"]);self.assertIsNone(u["brief_analysis"]);self.assertIsNone(u["package"])

    def test_unconfirmed_brief_cannot_be_migrated(self):
        t=task();t["brief_confirmation"]=None;db.save(t,"未确认")
        r=self.client.post(f"/api/tasks/{t['id']}/change-platform",json=dict(version=t["version"],platform="wechat"))
        self.assertEqual(r.status_code,400);self.assertEqual(db.get(t["id"])["platform"],"moments")

    def test_stale_busy_same_or_invalid_platform_rejected(self):
        t=task()
        for body,expected in ((dict(version=t["version"]-1,platform="wechat"),409),
                (dict(version=t["version"],platform="moments"),400),
                (dict(version=t["version"],platform="unknown"),422)):
            self.assertEqual(self.client.post(f"/api/tasks/{t['id']}/change-platform",json=body).status_code,expected)
        t["status"]="writing";db.save(t,"运行中")
        self.assertEqual(self.client.post(f"/api/tasks/{t['id']}/change-platform",json=dict(version=t["version"],platform="wechat")).status_code,400)
        t["status"]="approved";db.save(t,"结束隔离状态")

    def test_image_shortage_tries_vmall_then_pauses_without_brief_or_planner(self):
        t=task(images=1)
        with patch.object(vmall,"supplement",AsyncMock(return_value=empty_supplement())) as supplement,patch.object(w.llm,"complete",AsyncMock()) as llm:
            self.client.post(f"/api/tasks/{t['id']}/change-platform",json=dict(version=t["version"],platform="wechat"))
        u=db.get(t["id"]);self.assertEqual(u["status"],"needs_review")
        supplement.assert_awaited_once();llm.assert_not_called()
        self.assertIn("至少需要2张",u["error"]);self.assertIsNone(u["document"])

    def test_new_vmall_image_is_visually_checked_before_planning(self):
        t=task(images=1)
        extra=copy.deepcopy(task()["package"]["images"][1]);extra.update(visual_checked=False,knowledge_source="vmall")
        response=empty_supplement();response["images"]=[extra]
        visual=dict(images=[dict(id=extra["id"],description="新增图",reason="可用",usable=True)])
        with patch.object(vmall,"supplement",AsyncMock(return_value=response)),patch.object(w.llm,"complete",AsyncMock(side_effect=[visual,plan_two()])) as model:
            self.client.post(f"/api/tasks/{t['id']}/change-platform",json=dict(version=t["version"],platform="wechat"))
        u=db.get(t["id"]);self.assertEqual(u["status"],"plan_ready");self.assertEqual(model.call_count,2)
        self.assertIn("Asset Selector",model.call_args_list[0].args[1])
        self.assertTrue(any(i["id"]==extra["id"] and i["visual_checked"] for i in u["package"]["images"]))

    def test_product_evidence_gap_cannot_be_bypassed(self):
        t=task();t["package"]["coverage"][0].update(status="not_found",fact_ids=[]);db.save(t,"缺少产品事实")
        with patch.object(vmall,"supplement",AsyncMock(return_value=empty_supplement())),patch.object(w.llm,"complete",AsyncMock()) as model:
            self.client.post(f"/api/tasks/{t['id']}/change-platform",json=dict(version=t["version"],platform="wechat"))
        self.assertEqual(db.get(t["id"])["status"],"needs_review");model.assert_not_called()

    def test_changed_model_package_rejected(self):
        t=task();t["package"]["product"]["id"]="wrong";db.save(t,"错误型号")
        with patch.object(w.llm,"complete",AsyncMock()) as llm,patch.object(vmall,"supplement",AsyncMock()) as supplement:
            self.client.post(f"/api/tasks/{t['id']}/change-platform",json=dict(version=t["version"],platform="wechat"))
        self.assertEqual(db.get(t["id"])["status"],"error");llm.assert_not_called();supplement.assert_not_called()

    def test_tampered_image_must_be_rechecked(self):
        t=task();(ASSETS/("a"*20)).write_bytes(b"changed")
        visual=dict(images=[dict(id="a"*20,description="测试",reason="测试",usable=True)])
        with patch.object(w.llm,"complete",AsyncMock(side_effect=[visual,plan_two()])) as model:
            self.client.post(f"/api/tasks/{t['id']}/change-platform",json=dict(version=t["version"],platform="wechat"))
        self.assertEqual(model.call_count,2);self.assertIn("Asset Selector",model.call_args_list[0].args[1])

    def test_retry_after_shortage_preserves_platform_authorization(self):
        t=task(images=1)
        with patch.object(vmall,"supplement",AsyncMock(return_value=empty_supplement())):
            self.client.post(f"/api/tasks/{t['id']}/change-platform",json=dict(version=t["version"],platform="wechat"))
        u=db.get(t["id"]);extra=task()["package"]["images"][1]
        u["package"]["images"].append(extra);u["package"]["asset_candidates"].append(extra);db.save(u,"补充隔离素材")
        with patch.object(w.llm,"complete",AsyncMock(return_value=plan_two())) as model:
            r=self.client.post(f"/api/tasks/{t['id']}/replan",json=dict(version=u["version"]))
        self.assertEqual(r.status_code,202);self.assertEqual(db.get(t["id"])["status"],"plan_ready");self.assertEqual(model.call_count,1)

    def test_selection_does_not_preassign_image_slots(self):
        t=task()
        with patch.object(w.llm,"complete",AsyncMock(return_value=copy.deepcopy(PLAN))):
            self.client.post(f"/api/tasks/{t['id']}/change-platform",json=dict(version=t["version"],platform="wechat"))
        self.assertEqual(db.get(t["id"])["status"],"plan_ready")
        self.assertEqual(db.get(t["id"])["plan"]["sections"],[])
        self.assertFalse(w.can_export(db.get(t["id"])))

    def test_vmall_failure_does_not_erase_existing_product_facts(self):
        t=task(images=1);facts=copy.deepcopy(t["package"]["facts"])
        with patch.object(vmall,"supplement",AsyncMock(side_effect=ServiceError("暂不可用"))):
            self.client.post(f"/api/tasks/{t['id']}/change-platform",json=dict(version=t["version"],platform="wechat"))
        u=db.get(t["id"]);self.assertEqual(u["package"]["facts"],facts);self.assertEqual(u["status"],"needs_review")
        self.assertEqual(u["package"]["supplement_attempts"][0]["status"],"unavailable")


    def add_commercial(self,t,block=False):
        t["brief_analysis"]["commercial_requests"]=[dict(category="price",request="写价格",
            evidence=[dict(turn_id="U1",quote="价格")],on_missing="block" if block else "omit",
            blocking_evidence=[dict(turn_id="U1",quote="没有价格就不生成")] if block else [])]
        t["dialogue"]=[dict(id="U1",kind="user",text="没有价格就不生成" if block else "请写价格")]
        t["brief_analysis"]["retrieval_plan"]["facts"].append(dict(id="R2",direction_id="D1",category="price",question="价格",conditions=["配置与渠道"],priority="supporting"))
        t["package"]["coverage"].append(dict(request_id="R2",status="not_found",fact_ids=[],reason="无可用价格"))
        t["brief_confirmation"]["analysis_hash"]=ba.digest(t["brief_analysis"])
        return db.save(t,"明确价格需求")

    def test_optional_price_missing_after_vmall_does_not_block(self):
        t=self.add_commercial(task())
        with patch.object(vmall,"supplement",AsyncMock(return_value=empty_supplement())) as supplement,patch.object(w.llm,"complete",AsyncMock(return_value=plan_two())) as model:
            self.client.post(f"/api/tasks/{t['id']}/change-platform",json=dict(version=t["version"],platform="wechat"))
        u=db.get(t["id"]);self.assertEqual(u["status"],"plan_ready")
        supplement.assert_awaited_once();self.assertTrue(supplement.call_args.kwargs["need_facts"])
        self.assertEqual(model.call_count,1);self.assertIn("price",u["package"]["content_policy"]["omitted_categories"])

    def test_user_refusal_to_generate_still_blocks_after_vmall(self):
        t=self.add_commercial(task(),block=True)
        with patch.object(vmall,"supplement",AsyncMock(return_value=empty_supplement())),patch.object(w.llm,"complete",AsyncMock()) as model:
            self.client.post(f"/api/tasks/{t['id']}/change-platform",json=dict(version=t["version"],platform="wechat"))
        u=db.get(t["id"]);self.assertEqual(u["status"],"needs_review");model.assert_not_called()
        self.assertTrue(u["package"]["content_policy"]["blocked_requests"])

    def test_supplemental_fact_reextract_then_check_then_plan(self):
        t=task();t["package"]["coverage"][0].update(status="not_found",fact_ids=[]);db.save(t,"待补证据")
        source=dict(id="V1",title="商城证据",path="https://item.vmall.com/",text="此配置产品重量约1.33kg，因配置而异。")
        result=empty_supplement();result["sources"]=[source]
        extracted=dict(facts=[dict(id="F02",category="product",claim="约1.33kg",quote=source["text"],source_id="V1",conditions="因配置而异")],
            conflicts=[],coverage=[dict(request_id="R1",status="supported",fact_ids=["F02"],reason="补充原文")])
        plan=plan_two()
        for sec in plan["sections"]:sec["fact_ids"]=["F02"]
        with patch.object(vmall,"supplement",AsyncMock(return_value=result)),patch.object(w.llm,"complete",AsyncMock(side_effect=[extracted,plan])) as model:
            self.client.post(f"/api/tasks/{t['id']}/change-platform",json=dict(version=t["version"],platform="wechat"))
        u=db.get(t["id"]);self.assertEqual(u["status"],"plan_ready");self.assertEqual(model.call_count,2)
        self.assertEqual(u["package"]["facts"][0]["source_id"],"V1")
        self.assertEqual(u["package"]["sources"][0]["id"],"S1")

    def test_conflicting_vmall_product_fact_is_not_preferred_over_original(self):
        t=task();t["package"]["coverage"][0].update(status="not_found",fact_ids=[]);db.save(t,"待核对")
        result=empty_supplement();result["sources"]=[dict(id="V1",title="商城",path="fixture",text="产品资料存在需要核对的配置差异。")]
        extracted=dict(facts=t["package"]["facts"],coverage=[dict(request_id="R1",status="conflict",fact_ids=["F01"],reason="同配置冲突")],
            conflicts=[dict(category="product",request_ids=["R1"],source_ids=["S1","V1"],detail="同配置冲突")])
        with patch.object(vmall,"supplement",AsyncMock(return_value=result)),patch.object(w.llm,"complete",AsyncMock(return_value=extracted)) as model:
            self.client.post(f"/api/tasks/{t['id']}/change-platform",json=dict(version=t["version"],platform="wechat"))
        self.assertEqual(db.get(t["id"])["status"],"needs_review");self.assertEqual(model.call_count,1)

    def test_local_source_snapshot_is_preserved_without_catalog_read(self):
        t=task();snapshot=dict(kind="local_zip",sha256="original")
        t.update(knowledge_source="local_zip",knowledge_snapshot=snapshot)
        t["package"].update(knowledge_source="local_zip",knowledge_snapshot=copy.deepcopy(snapshot));db.save(t,"固定本地快照")
        with patch.object(w.ima,"catalog_for_task",AsyncMock()) as catalog,patch.object(w.llm,"complete",AsyncMock(return_value=plan_two())):
            self.client.post(f"/api/tasks/{t['id']}/change-platform",json=dict(version=t["version"],platform="wechat"))
        u=db.get(t["id"]);self.assertEqual(u["status"],"plan_ready");self.assertEqual(u["knowledge_snapshot"],snapshot);catalog.assert_not_called()

    def test_cached_rejected_images_do_not_reenter_usable_pool(self):
        t=task()
        bad=copy.deepcopy(t["package"]["images"][0]);bad["id"]="c"*20;bad["usable"]=False
        (ASSETS/bad["id"]).write_bytes((ASSETS/("a"*20)).read_bytes())
        t["package"]["asset_candidates"].append(bad);db.save(t,"已拒绝图片")
        with patch.object(w.llm,"complete",AsyncMock(return_value=plan_two())) as model:
            self.client.post(f"/api/tasks/{t['id']}/change-platform",json=dict(version=t["version"],platform="wechat"))
        u=db.get(t["id"]);self.assertEqual(model.call_count,1)
        self.assertNotIn("c"*20,{i["id"] for i in u["package"]["images"]})
        self.assertIn("c"*20,{i["id"] for i in u["package"]["asset_candidates"]})


    def test_invalid_supplemental_quote_cannot_replace_original_facts(self):
        t=task();t["package"]["coverage"][0].update(status="not_found",fact_ids=[]);db.save(t,"待补")
        original=copy.deepcopy(t["package"]["facts"])
        result=empty_supplement();result["sources"]=[dict(id="V1",title="商城",path="fixture",text="真实原文与模型错误输出不一致。")]
        bad=dict(facts=[dict(id="F02",category="product",claim="错误",quote="这是来源中并不存在的引文。",source_id="V1",conditions="")],
            conflicts=[],coverage=[dict(request_id="R1",status="supported",fact_ids=["F02"],reason="错误支持")])
        with patch.object(vmall,"supplement",AsyncMock(return_value=result)),patch.object(w.llm,"complete",AsyncMock(return_value=bad)):
            self.client.post(f"/api/tasks/{t['id']}/change-platform",json=dict(version=t["version"],platform="wechat"))
        u=db.get(t["id"]);self.assertEqual(u["status"],"needs_review");self.assertEqual(u["package"]["facts"],original)


class VmallBoundaryTests(unittest.TestCase):
    def test_domain_restrictions(self):
        for url in ("http://www.vmall.com/","https://www.vmall.com.evil.test/","https://www.vmall.com@127.0.0.1/","https://127.0.0.1/","https://www.vmall.com:444/"):
            self.assertFalse(vmall.allowed(url,vmall.PAGE_HOSTS))
        self.assertTrue(vmall.allowed("https://item.vmall.com/product/comdetail/index.html",vmall.PAGE_HOSTS))

    def test_model_and_system_mismatch_rejected(self):
        p=dict(name="HUAWEI MateBook 14",category="鸿蒙电脑")
        self.assertTrue(vmall.model_matches(p,dict(name="HUAWEI MateBook 14 鸿蒙版")))
        self.assertFalse(vmall.model_matches(p,dict(name="HUAWEI MateBook 14")))
        self.assertFalse(vmall.model_matches(p,dict(name="HUAWEI MateBook 14 Pro 鸿蒙版")))
        self.assertFalse(vmall.model_matches(p,dict(name="HUAWEI MateBook 16 鸿蒙版")))

    def test_photo_url_not_arbitrary_user_input(self):
        self.assertIsNone(vmall.photo_url(dict(photoPath="//evil.test/",photoName="../x.png")))
        self.assertIsNone(vmall.photo_url(dict(photoPath="/../",photoName="x.png")))
        self.assertTrue(vmall.photo_url(dict(photoPath="/FssCdnProxy/a/",photoName="A.png")).startswith("https://res.vmallres.com/pimages/"))

    def test_another_sku_cannot_ignore_explicit_configuration(self):
        t=dict(brief_analysis=dict(requirements=dict(user_constraints=dict(value=["32GB","1TB"]))))
        display=dict(sbomList=[dict(sbomCode="1",name="16GB 512GB",defaultSbom=1)])
        with self.assertRaises(ServiceError):vmall.select_sku(t,display,"1")

    def test_html_scripts_not_treated_as_evidence(self):
        self.assertEqual(vmall.plain("<p>约1.33kg</p><script>不可信指令</script><small>因配置而异</small>"),"约1.33kg\n因配置而异")

    def test_redirect_to_other_host_rejected(self):
        async def run():
            transport=httpx.MockTransport(lambda req:httpx.Response(302,headers={"location":"https://evil.test/"}))
            async with httpx.AsyncClient(transport=transport) as c:
                with self.assertRaises(ServiceError):await vmall.fetch(c,"https://www.vmall.com/product",vmall.PAGE_HOSTS)
        asyncio.run(run())

    def test_oversized_response_rejected(self):
        async def run():
            async with httpx.AsyncClient(transport=httpx.MockTransport(lambda req:httpx.Response(200,content=b"12345"))) as c:
                with self.assertRaises(ServiceError):await vmall.fetch(c,"https://www.vmall.com/product",vmall.PAGE_HOSTS,3)
        asyncio.run(run())

    def test_csv_url_stops_before_next_column(self):
        t=dict(package=dict(product={},sources=[dict(text="https://item.vmall.com/product/comdetail/index.html?prdId=123&sbomCode=456,下一个字段")]))
        with patch.object(vmall.knowledge,"backend",side_effect=ServiceError("fixture")):
            urls=asyncio.run(vmall.candidate_urls(t))
        self.assertEqual(urls,["https://item.vmall.com/product/comdetail/index.html?prdId=123&sbomCode=456"])

    def test_api_price_not_forwarded_without_request(self):
        async def run(commercial):
            sku=dict(sbomCode="456",name="HUAWEI MateBook 14 鸿蒙版 16GB 512GB",defaultSbom=1,price=5999,gbomAttrList=[],groupPhotoList=[])
            display=dict(disPrdId="123",name="HUAWEI MateBook 14 鸿蒙版",sbomList=[sku])
            async def fake_fetch(client,url,hosts,limit=3_000_000):
                if "openapi" in url:return json.dumps(dict(code="0",displayPrdVo=display)).encode(),url
                return b"<html></html>",url
            t=dict(package=dict(product=dict(name="HUAWEI MateBook 14",category="鸿蒙电脑")),brief_analysis=dict(requirements={},commercial_requests=commercial))
            with patch.object(vmall,"fetch",side_effect=fake_fetch):
                return await vmall.read_product(None,"https://item.vmall.com/product/comdetail/index.html?prdId=123&sbomCode=456",t)
        plain=asyncio.run(run([]));self.assertNotIn("commercial_snapshot",plain["facts"])
        price=asyncio.run(run([dict(category="price")]))
        self.assertEqual(price["facts"]["commercial_snapshot"]["price"]["price"],5999)
        self.assertIn("未验证用户资格",price["facts"]["commercial_conditions"]["eligibility"])
