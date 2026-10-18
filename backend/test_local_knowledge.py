"""Local ZIP routing tests. Synthetic archive, no external APIs."""
import asyncio,hashlib,io,json,tempfile,unittest,zipfile
from pathlib import Path
from unittest.mock import AsyncMock,patch
from PIL import Image
from fastapi.testclient import TestClient
from backend.test_workflow import TEST_DATA
from backend.main import app
from backend import storage as db,settings as settings_module
from backend import main as api
from backend.clients import ima as cloud,ServiceError,short_id
from backend.local_knowledge import LocalZip
from backend.knowledge import Knowledge

ROOT="fixture-v7/"
MODEL="P1-产品参数库/01-鸿蒙电脑/HUAWEI MateBook 14"

def make_archive(path):
    image=io.BytesIO();Image.new("RGB",(8,8),"white").save(image,format="PNG")
    with zipfile.ZipFile(path,"w",zipfile.ZIP_DEFLATED) as z:
        z.writestr(ROOT+MODEL+"/产品事实.md","测试型号重量约 1.33 kg，实际因配置而异。"*3)
        z.writestr(ROOT+MODEL+"/卖点与限制.md","这是隔离测试资料，不是实际产品证据。"*3)
        z.writestr(ROOT+MODEL+"/图片索引.csv","文件名,产品型号,官网图片说明,建议用途\nimage.png,HUAWEI MateBook 14（鸿蒙版）,测试图,测试用途\nwrong.png,HUAWEI MateBook Pro,别的型号,不能混用\n")
        z.writestr(ROOT+MODEL+"/images/image.png",image.getvalue())
        z.writestr(ROOT+MODEL+"/images/wrong.png",image.getvalue())
        z.writestr(ROOT+"P1-产品参数库/08-官方公开价格快照/官方价格快照.csv","规范产品名称,精确款式,核验时间,官方URL,页面金额（元）\nHUAWEI MateBook 14（鸿蒙版）,16GB/512GB,2026-10-17,https://item.vmall.com/test,5999\nMateBook 14 酷睿 Ultra,16GB/1TB,2026-10-17,https://item.vmall.com/other,6999\n")

class LocalKnowledgeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix="huawei-local-zip-");self.addCleanup(self.temp.cleanup)
        self.archive=Path(self.temp.name)/"fixture.zip";make_archive(self.archive)
    def local(self):return LocalZip(self.archive)
    def test_local_catalog_reads_metadata_without_ima_or_fact_download(self):
        local=self.local()
        with patch.object(cloud,"call",AsyncMock(side_effect=AssertionError("no cloud"))) as call,patch.object(local,"fetch_media",AsyncMock(side_effect=AssertionError("metadata only"))):
            products=asyncio.run(local.catalog())
        call.assert_not_awaited();self.assertEqual(len(products),1)
        self.assertEqual(products[0]["id"],short_id(MODEL));self.assertEqual(local.snapshot()["archive_root"],"fixture-v7")
    def test_local_retrieval_verifies_images_and_uses_no_network(self):
        local=self.local();product=asyncio.run(local.catalog())[0]
        with patch("backend.clients.httpx.AsyncClient",side_effect=AssertionError("no network")):
            p=asyncio.run(local.retrieve(product,{}))
        self.assertEqual(len(p["sources"]),2);self.assertEqual(len(p["images"]),1)
        self.assertEqual(p["images"][0]["name"],"image.png");self.assertTrue(p["images"][0]["model_verified"])
        self.assertEqual(p["knowledge_source"],"local_zip")
        self.assertTrue(all(s["archive_sha256"]==local.sha256 for s in p["sources"]))
    def test_local_public_price_is_exact_model_scoped(self):
        local=self.local();product=asyncio.run(local.catalog())[0]
        sources=asyncio.run(local.public_price_sources(product))
        self.assertEqual(sources[0]["record_count"],1);self.assertIn("5999",sources[0]["text"]);self.assertNotIn("6999",sources[0]["text"])
    def test_local_retrieval_does_not_change_archive(self):
        before=self.archive.read_bytes();local=self.local();product=asyncio.run(local.catalog())[0]
        asyncio.run(local.retrieve(product,{}))
        self.assertEqual(before,self.archive.read_bytes())
    def test_task_pinned_local_survives_global_cloud_switch(self):
        router=Knowledge();t=dict(knowledge_source="local_zip",knowledge_zip_path=str(self.archive))
        products=asyncio.run(router.catalog_for_task(t))
        with patch("backend.knowledge.get_settings",return_value=dict(knowledge_source="ima",local_knowledge_path="missing.zip")),patch.object(cloud,"call",AsyncMock(side_effect=AssertionError("no cloud"))):
            p=asyncio.run(router.retrieve_for_task(t,products[0],{}))
        self.assertEqual(p["knowledge_source"],"local_zip")
    def test_legacy_task_remains_cloud_when_default_is_local(self):
        router=Knowledge();task={}
        with patch("backend.knowledge.get_settings",return_value=dict(knowledge_source="local_zip",local_knowledge_path=str(self.archive))),patch.object(router,"catalog",AsyncMock(return_value=[])) as catalog:
            asyncio.run(router.catalog_for_task(task))
        self.assertEqual(catalog.await_args.kwargs["source"],"ima");self.assertEqual(task["knowledge_snapshot"]["kind"],"ima")
    def test_archive_replacement_rejected_after_snapshot(self):
        router=Knowledge();task=dict(knowledge_source="local_zip",knowledge_zip_path=str(self.archive))
        asyncio.run(router.catalog_for_task(task))
        with zipfile.ZipFile(self.archive,"a") as z:z.writestr(ROOT+"new.md","new version")
        with self.assertRaises(ServiceError):asyncio.run(router.catalog_for_task(task,verify_snapshot=True))
    def test_held_adapter_detects_archive_change(self):
        local=self.local()
        with zipfile.ZipFile(self.archive,"a") as z:z.writestr(ROOT+"new.md","new version")
        with self.assertRaises(ServiceError):asyncio.run(local.catalog())
    def test_missing_local_archive_never_falls_back_to_cloud(self):
        router=Knowledge()
        with patch.object(cloud,"catalog",AsyncMock(side_effect=AssertionError("no fallback"))) as catalog:
            with self.assertRaises(ServiceError):asyncio.run(router.catalog(source="local_zip",archive_path=str(self.archive)+"missing"))
        catalog.assert_not_awaited()
    def test_unsafe_zip_paths_rejected_without_extraction(self):
        bad=Path(self.temp.name)/"bad.zip"
        with zipfile.ZipFile(bad,"w") as z:z.writestr("../escape.txt","bad")
        with self.assertRaises(ServiceError):LocalZip(bad)
        self.assertFalse((Path(self.temp.name).parent/"escape.txt").exists())
    def test_old_settings_request_preserves_selected_local_source(self):
        data=Path(self.temp.name)/"settings";data.mkdir()
        conf=settings_module.DEFAULTS | dict(knowledge_source="local_zip",local_knowledge_path=str(self.archive))
        with patch.object(settings_module,"DATA",data),patch.object(settings_module,"user_env",return_value=""):
            settings_module.save_settings(conf)
            with TestClient(app) as c:
                r=c.put("/api/settings",json={k:conf[k] for k in ("base_url","writer_model","reviewer_model","vision")})
            self.assertEqual(r.status_code,200);self.assertEqual(r.json()["knowledge_source"],"local_zip")
            self.assertEqual(json.loads((data/"settings.json").read_text(encoding="utf-8"))["local_knowledge_path"],str(self.archive))
    def test_full_local_workflow_uses_real_zip_with_fixture_models(self):
        from backend import workflow as w,brief_agent as ba
        from backend.brief_test_data import parsing,responses
        from backend.test_workflow import DOC,PLAN
        import copy
        local=self.local();product=asyncio.run(local.catalog())[0]
        conf=settings_module.DEFAULTS | dict(knowledge_source="local_zip",local_knowledge_path=str(self.archive))
        iid=short_id(product["id"]+local.prefix+MODEL+"/images/image.png")
        parsed=parsing(query="HUAWEI MateBook 14")
        fact=dict(id="F01",category="product",claim="测试型号约 1.33 kg",quote="测试型号重量约 1.33 kg，实际因配置而异。",source_id="S1",conditions="实际因配置而异")
        plan=copy.deepcopy(PLAN);plan["sections"][0]["image_id"]=iid
        doc=copy.deepcopy(DOC);doc["paragraphs"][0]["image_id"]=iid
        outputs=responses(parsed)+[dict(facts=[fact],conflicts=[],coverage=[dict(request_id="R1",status="supported",fact_ids=["F01"],reason="原文支持")]),dict(images=[dict(id=iid,description="fixture",reason="fixture",usable=True)]),plan,doc,dict(summary="fixture",issues=[])]
        with patch.object(api,"get_settings",return_value=conf),patch("backend.knowledge.get_settings",return_value=conf),patch.object(w.llm,"complete",AsyncMock(side_effect=outputs)) as model,patch.object(cloud,"call",AsyncMock(side_effect=AssertionError("local task must not call ima"))) as cloud_call,TestClient(app) as c:
            t=c.post("/api/tasks",json=dict(raw="这是本地隔离测试任务",product_id=product["id"],platform="moments")).json()
            self.assertEqual(c.post(f"/api/tasks/{t['id']}/analyze",json=dict(version=t["version"])).status_code,202)
            t=c.get(f"/api/tasks/{t['id']}").json();self.assertEqual(t["status"],"brief_ready")
            self.assertEqual(c.post(f"/api/tasks/{t['id']}/confirm-brief",json=dict(version=t["version"],analysis_hash=t["brief_analysis_hash"])).status_code,202)
            t=c.get(f"/api/tasks/{t['id']}").json();self.assertEqual(t["status"],"plan_ready")
            self.assertEqual(t["package"]["knowledge_source"],"local_zip")
            self.assertEqual(c.post(f"/api/tasks/{t['id']}/confirm-plan",json=dict(version=t["version"],plan=t["plan"])).status_code,202)
            t=c.get(f"/api/tasks/{t['id']}").json();self.assertTrue(t["can_export"])
            self.assertEqual(c.get(f"/api/tasks/{t['id']}/export").status_code,200)
        cloud_call.assert_not_awaited();self.assertEqual(model.await_count,8)
    def test_source_only_switch_preserves_model_configuration(self):
        data=Path(self.temp.name)/"source-settings";data.mkdir()
        conf=settings_module.DEFAULTS | dict(local_knowledge_path=str(self.archive))
        with patch.object(settings_module,"DATA",data),patch.object(settings_module,"user_env",return_value=""),TestClient(app) as c:
            settings_module.save_settings(conf)
            r=c.put("/api/settings/knowledge-source",json=dict(source="local_zip"))
            self.assertEqual(r.status_code,200);self.assertEqual(r.json()["knowledge_source"],"local_zip")
            self.assertEqual(r.json()["writer_model"],conf["writer_model"])
            r=c.put("/api/settings/knowledge-source",json=dict(source="ima"))
            self.assertEqual(r.status_code,200);self.assertEqual(r.json()["knowledge_source"],"ima")
            r=c.put("/api/settings/knowledge-source",json=dict(source="local_zip",local_knowledge_path=str(self.archive)+"missing"))
            self.assertEqual(r.status_code,400);self.assertEqual(settings_module.get_settings()["knowledge_source"],"ima")
    def test_invalid_zip_in_full_settings_request_does_not_change_config(self):
        bad=Path(self.temp.name)/"broken.zip";bad.write_bytes(b"not a zip")
        data=Path(self.temp.name)/"invalid-settings";data.mkdir()
        conf=settings_module.DEFAULTS.copy()
        with patch.object(settings_module,"DATA",data),patch.object(settings_module,"user_env",return_value=""),TestClient(app) as c:
            settings_module.save_settings(conf)
            r=c.put("/api/settings",json={k:conf[k] for k in ("base_url","writer_model","reviewer_model","vision")}|dict(knowledge_source="local_zip",local_knowledge_path=str(bad)))
            self.assertEqual(r.status_code,400);self.assertEqual(settings_module.get_settings()["knowledge_source"],"ima")
    def test_new_task_pins_current_source_and_archive_path(self):
        conf=settings_module.DEFAULTS | dict(knowledge_source="local_zip",local_knowledge_path=str(self.archive))
        with patch.object(api,"get_settings",return_value=conf),TestClient(app) as c:
            r=c.post("/api/tasks",json=dict(raw="给大学新生写电脑图文"))
        self.assertEqual(r.status_code,201);task=db.get(r.json()["id"])
        self.assertEqual(task["knowledge_source"],"local_zip");self.assertEqual(task["knowledge_zip_path"],str(self.archive))

if __name__=="__main__":unittest.main()
