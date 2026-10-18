"""Explicit evidence scope preview/confirmation/refresh. Isolated fixture models only."""
import asyncio
import copy
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import AsyncMock,patch
from fastapi.testclient import TestClient
from backend.test_platform_change import task
from backend.test_workflow import PLAN,DOC
from backend.main import app
from backend import evidence_resolution as er,brief_agent as ba,workflow as w,storage as db,schemas as S
from backend.clients import ServiceError


def paused():
    t=task()
    t.update(status="needs_review",resume_status="needs_review",plan=None,document=None,review=None)
    a=t["brief_analysis"]
    a["message_strategy"]["theme"]="待验证课程续航与携带需求"
    a["message_strategy"]["priorities"]=[
        dict(id="D1",direction="核实课程续航",reason="课程需求",customer_needs=["课程使用"],verification="pending"),
        dict(id="D2",direction="核实携带重量",reason="携带需求",customer_needs=["携带方便"],verification="pending"),
        dict(id="D3",direction="轻便和续航兼顾",reason="组合论证",customer_needs=["兼顾"],verification="pending")]
    a["retrieval_plan"]["facts"]=[
        dict(id="R1",direction_id="D1",category="product",question="续航是否满足课程需要",conditions=["具体配置"],priority="required"),
        dict(id="R2",direction_id="D2",category="product",question="具体配置重量及携带负担",conditions=["配置和测量条件"],priority="required"),
        dict(id="R3",direction_id="D3",category="product",question="能否兼顾续航和重量",conditions=["同配置"],priority="required",depends_on=["R1","R2"])]
    a["retrieval_plan"]["images"]=[dict(id="I1",direction_id="D2",description="机身图",reason="展示机身")]
    t["brief"]=ba.projection(a);t["brief_confirmation"]["analysis_hash"]=ba.digest(a)
    t["package"]["coverage"]=[
        dict(request_id="R1",status="not_found",fact_ids=[],reason="无课程续航测量资料"),
        dict(request_id="R2",status="supported",fact_ids=["F01"],reason="原文提供重量"),
        dict(request_id="R3",status="not_found",fact_ids=[],reason="缺同配置续航依据")]
    return db.save(t,"资料审查暂停隔离案例")


class EvidenceResolutionTests(unittest.TestCase):
    def setUp(self):
        self.client=TestClient(app);self.client.__enter__()
    def tearDown(self):self.client.__exit__(None,None,None)
    def preview(self,t,requests=None,directions=None):
        r=self.client.post(f"/api/tasks/{t['id']}/evidence-resolution/preview",
            json=dict(version=t["version"],drop_request_ids=["R1"] if requests is None else requests,drop_direction_ids=directions or []))
        self.assertEqual(r.status_code,200,r.text);return r.json()
    def confirm(self,t,p,**extra):
        return self.client.post(f"/api/tasks/{t['id']}/evidence-resolution/confirm",
            json=dict(version=t["version"],drop_request_ids=p["selected_request_ids"],drop_direction_ids=p["selected_direction_ids"],
                preview_id=p["preview_id"],confirmed=True,acknowledged_constraint_ids=[],**extra))
    def resolved(self):
        t=paused();p=self.preview(t)
        with patch.object(w.llm,"complete",AsyncMock(return_value=copy.deepcopy(PLAN))):
            self.assertEqual(self.confirm(t,p).status_code,202)
        return db.get(t["id"])

    def grouped_requests(self):
        t=paused();a=t['brief_analysis']
        a['retrieval_plan']['facts'].insert(0,dict(id='RID',direction_id='D1',category='product',question='确认产品型号和配置版本',conditions=[],priority='required',guardrail='identity',waivable=False,depends_on=[]))
        for r in a['retrieval_plan']['facts'][1:]:
            if r['id'] != 'R3':r['depends_on']=['RID']
        a['message_strategy']['priorities'].append(dict(id='D4',direction='核实触屏和手写笔的课堂用途',reason='课堂需求',customer_needs=['触屏'],verification='pending'))
        a['retrieval_plan']['facts'].extend([
            dict(id='RTOUCH',direction_id='D4',category='product',question='是否配备触控屏及版本限制',conditions=[],priority='required',depends_on=['RID']),
            dict(id='RPEN',direction_id='D4',category='product',question='是否支持手写笔用于课堂批注',conditions=[],priority='supporting',depends_on=['RTOUCH'])])
        t['package']['coverage'].extend([
            dict(request_id='RID',status='supported',fact_ids=['F01'],reason='型号资料已确认'),
            dict(request_id='RTOUCH',status='supported',fact_ids=['F01'],reason='隔离用有效引用'),
            dict(request_id='RPEN',status='not_found',fact_ids=[],reason='缺少手写笔依据')])
        t['brief']=ba.projection(a);t['brief_confirmation']['analysis_hash']=ba.digest(a)
        return db.save(t,'同方向包含独立请求与身份前置核查')

    def test_omissions_preserve_identity_and_independent_siblings(self):
        t=self.grouped_requests();original=copy.deepcopy(t)
        p=self.preview(t,requests=['R1','RPEN','R3'])
        self.assertTrue(p['can_apply'],p['remaining_blockers'])
        self.assertEqual(p['omitted_request_ids'],['R1','R3','RPEN'])
        self.assertEqual({r['request']['id'] for r in p['retained']},{'RID','R2','RTOUCH'})
        self.assertNotIn('portability',p['prohibited_topics'])
        self.assertNotIn('non_waivable',{b['code'] for b in p['remaining_blockers']})
        self.assertEqual(db.get(t['id']),original)
        view,_=er.project(t,set(p['omitted_request_ids']),set(p['omitted_direction_ids']))
        d=next(d for d in view['brief_analysis']['message_strategy']['priorities'] if d['id']=='D4')
        self.assertIn('触控屏',d['direction']);self.assertNotIn('手写笔',d['direction'])
        with patch.object(w.llm,'complete',AsyncMock(return_value=copy.deepcopy(PLAN))) as model:
            self.assertEqual(self.confirm(t,p).status_code,202)
        u=db.get(t['id']);self.assertEqual(u['status'],'plan_ready');self.assertIsNone(u['document'])
        self.assertEqual(u['brief_analysis'],original['brief_analysis']);self.assertEqual(model.call_count,1)

    def test_shared_direction_does_not_reverse_dependency_edges(self):
        t=self.grouped_requests();p=self.preview(t,requests=['RPEN'])
        self.assertNotIn('RTOUCH',p['omitted_request_ids'])
        self.assertNotIn('RID',p['omitted_request_ids'])
        p=self.preview(t,requests=['RTOUCH'])
        self.assertIn('RPEN',p['omitted_request_ids'])
        self.assertNotIn('RID',p['omitted_request_ids'])

    def test_direct_identity_omission_still_blocks(self):
        t=self.grouped_requests();p=self.preview(t,requests=['RID'])
        self.assertFalse(p['can_apply'])
        self.assertIn('non_waivable',{b['code'] for b in p['remaining_blockers']})

    def test_preview_read_only_and_lists_dependency_impact(self):
        t=paused();original=copy.deepcopy(db.get(t["id"]))
        with patch.object(w.llm,"complete",AsyncMock()) as model,patch.object(w.ima,"retrieve_for_task",AsyncMock()) as retrieve:
            p=self.preview(t)
        self.assertEqual(p["omitted_request_ids"],["R1","R3"])
        self.assertEqual(p["omitted_direction_ids"],["D1","D3"])
        self.assertEqual([d["id"] for d in p["retained_directions"]],["D2"])
        self.assertEqual(p["retained_fact_ids"],["F01"]);self.assertTrue(p["can_apply"])
        self.assertEqual(db.get(t["id"]),original);model.assert_not_called();retrieve.assert_not_called()
        self.assertEqual(self.preview(t)["preview_id"],p["preview_id"])

    def test_confirm_keeps_original_hash_coverage_and_stops_at_plan_confirmation(self):
        t=paused();p=self.preview(t);original=copy.deepcopy(t)
        with patch.object(w.llm,"complete",AsyncMock(return_value=copy.deepcopy(PLAN))) as model,patch.object(w.ima,"retrieve_for_task",AsyncMock()) as retrieve:
            r=self.confirm(t,p)
        self.assertEqual(r.status_code,202,r.text);u=db.get(t["id"])
        self.assertEqual(u["status"],"plan_ready");self.assertIsNone(u["document"])
        self.assertEqual(u["brief_analysis"],original["brief_analysis"])
        self.assertEqual(u["brief_confirmation"],original["brief_confirmation"])
        self.assertEqual(u["package"]["coverage"],original["package"]["coverage"])
        self.assertEqual([r["request_id"] for r in u["package"]["execution_coverage"]],["R2"])
        self.assertEqual(u["resolution_history"][0]["preview"],p)
        self.assertEqual(model.call_count,1);retrieve.assert_not_called()
        self.assertEqual([f["id"] for f in u["package"]["facts"]],["F01"])
        context=model.call_args.args[2]["brief"]
        self.assertEqual([r["id"] for r in context["retrieval_plan"]["facts"]],["R2"])
        self.assertNotIn("续航",context["message_strategy"]["theme"])
        self.assertEqual(context["execution_scope"]["prohibited_topics"],["battery"])
        self.assertIsNone(db.snapshot(t["id"],t["version"]).get("execution_scope"))

    def test_missing_explicit_confirmation_not_executed(self):
        t=paused();p=self.preview(t)
        body=dict(version=t["version"],drop_request_ids=["R1"],preview_id=p["preview_id"],confirmed=False)
        with patch.object(w.llm,"complete",AsyncMock()) as model:
            r=self.client.post(f"/api/tasks/{t['id']}/evidence-resolution/confirm",json=body)
        self.assertEqual(r.status_code,400);self.assertEqual(db.get(t["id"])["version"],t["version"]);model.assert_not_called()

    def test_stale_version_and_preview_rejected_with_409(self):
        t=paused();p=self.preview(t)
        r=self.client.post(f"/api/tasks/{t['id']}/evidence-resolution/preview",json=dict(version=t["version"]-1,drop_request_ids=["R1"]))
        self.assertEqual(r.status_code,409)
        r=self.confirm(t,p|dict(preview_id="wrong"));self.assertEqual(r.status_code,409)
        p2=p|dict(selected_request_ids=["R2"])
        self.assertEqual(self.confirm(t,p2).status_code,409)
        db.save(t,"别人修改")
        old=copy.deepcopy(t);old["version"]-=1
        self.assertEqual(self.confirm(old,p).status_code,409)
        self.assertIsNone(db.get(t["id"]).get("execution_scope"))

    def test_required_remaining_gap_prevents_confirm(self):
        t=paused();p=self.preview(t,requests=["R3"])
        self.assertFalse(p["can_apply"])
        self.assertTrue(any(b["request_id"]=="R1" for b in p["remaining_blockers"] if b.get("request_id")))
        self.assertEqual(self.confirm(t,p).status_code,400)

    def test_all_directions_cannot_be_dropped(self):
        t=paused();p=self.preview(t,requests=[],directions=["D1","D2","D3"])
        self.assertFalse(p["can_apply"]);self.assertIn("empty_content",[b["code"] for b in p["remaining_blockers"]])
        self.assertEqual(self.confirm(t,p).status_code,400)

    def test_nonwaivable_safety_cannot_be_dropped(self):
        t=paused();t["brief_analysis"]["retrieval_plan"]["facts"][0].update(guardrail="safety",waivable=False)
        t["brief_confirmation"]["analysis_hash"]=ba.digest(t["brief_analysis"]);db.save(t,"必要安全条件")
        p=self.preview(t)
        self.assertFalse(p["can_apply"]);self.assertIn("non_waivable",[b["code"] for b in p["remaining_blockers"]])

    def test_product_identity_unclear_is_not_bypassed(self):
        t=paused();t["brief_analysis"]["product_resolution"]["state"]="ambiguous";db.save(t,"型号歧义")
        p=self.preview(t);self.assertFalse(p["can_apply"])
        self.assertIn("identity_or_brief",[b["code"] for b in p["remaining_blockers"]])

    def test_wrong_product_package_not_bypassed(self):
        t=paused();t["package"]["product"]["id"]="another";db.save(t,"型号错配")
        p=self.preview(t);self.assertFalse(p["can_apply"])
        self.assertIn("product_identity",[b["code"] for b in p["remaining_blockers"]])

    def test_unsupported_original_quote_is_not_bypassed(self):
        t=paused();t["package"]["facts"][0]["quote"]="这不是原始资料提供的连续原文。";db.save(t,"错误引文")
        p=self.preview(t);self.assertFalse(p["can_apply"])
        self.assertIn("evidence_integrity",[b["code"] for b in p["remaining_blockers"]])

    def test_selected_conflict_quarantined_and_raw_preserved(self):
        t=paused()
        fact=dict(id="FB",category="product",claim="续航待核实",quote="测试型号重量约 1.33 kg，实际因配置而异。",source_id="S1",conditions="测试")
        t["package"]["facts"].append(fact)
        t["package"]["coverage"][0].update(status="conflict",fact_ids=["FB"])
        conflict=dict(category="product",request_ids=["R1"],source_ids=["S1"],detail="同配置续航冲突")
        t["package"]["conflicts"]=[conflict];db.save(t,"结构化冲突")
        p=self.preview(t);self.assertTrue(p["can_apply"]);self.assertIn("FB",p["excluded_fact_ids"])
        with patch.object(w.llm,"complete",AsyncMock(return_value=copy.deepcopy(PLAN))):
            self.assertEqual(self.confirm(t,p).status_code,202)
        u=db.get(t["id"]);self.assertEqual(u["package"]["conflicts"],[])
        self.assertEqual(u["package"]["all_conflicts"],[conflict])
        self.assertEqual(u["package"]["coverage"][0]["status"],"conflict")
        self.assertNotIn("FB",{f["id"] for f in u["package"]["facts"]})

    def test_remaining_conflict_and_unscoped_conflicts_block(self):
        for conflict in (dict(category="product",request_ids=["R2"],source_ids=["S1"],detail="重量冲突"),"旧版无关联冲突"):
            t=paused();t["package"]["conflicts"]=[conflict];db.save(t,"冲突")
            p=self.preview(t);self.assertFalse(p["can_apply"])
            self.assertTrue(any(b["code"] in ("active_conflict","product_evidence","empty_content") for b in p["remaining_blockers"]))

    def test_product_refusal_constraint_requires_explicit_ack(self):
        t=paused();t["dialogue"]=[dict(id="U1",kind="user",text="没有续航依据就不生成")];db.save(t,"拒绝降级")
        p=self.preview(t);self.assertTrue(p["can_apply"]);self.assertTrue(p["required_constraint_acks"])
        self.assertEqual(self.confirm(t,p).status_code,400)
        body=dict(version=t["version"],drop_request_ids=["R1"],preview_id=p["preview_id"],confirmed=True,
            acknowledged_constraint_ids=[c["id"] for c in p["required_constraint_acks"] if c["requires_ack"]])
        with patch.object(w.llm,"complete",AsyncMock(return_value=copy.deepcopy(PLAN))):
            r=self.client.post(f"/api/tasks/{t['id']}/evidence-resolution/confirm",json=body)
        self.assertEqual(r.status_code,202,r.text)
        u=db.get(t["id"]);self.assertEqual(u["dialogue"],t["dialogue"])
        self.assertTrue(u["resolution_history"][0]["acknowledged_constraint_ids"])
        self.assertEqual(ba.context(u)["execution_scope"]["relaxed_constraints"][0]["request_id"],"R1")

    def test_unknown_duplicate_scopes_rejected(self):
        t=paused()
        for ids in (["unknown"],["R1","R1"]):
            r=self.client.post(f"/api/tasks/{t['id']}/evidence-resolution/preview",json=dict(version=t["version"],drop_request_ids=ids))
            self.assertEqual(r.status_code,400)

    def test_preview_does_not_generate_or_mark_review_as_passed(self):
        t=paused();self.preview(t)
        u=db.get(t["id"]);self.assertEqual(u["status"],"needs_review");self.assertIsNone(u["review"]);self.assertFalse(w.can_export(u))

    def test_boundary_reaches_writer_reviewer_and_repair(self):
        t=self.resolved()
        bad=copy.deepcopy(DOC);bad["title"]="一天课程不用找插座，续航超长"
        outputs=[bad,dict(summary="fixture没有发现",issues=[]),copy.deepcopy(DOC),dict(summary="fixture通过",issues=[])]
        with patch.object(w.llm,"complete",AsyncMock(side_effect=outputs)) as model:
            r=self.client.post(f"/api/tasks/{t['id']}/confirm-plan",json=dict(version=t["version"],plan=t["plan"]))
        self.assertEqual(r.status_code,202);u=db.get(t["id"])
        self.assertEqual(u["status"],"approved");self.assertEqual(model.call_count,4)
        for call in model.call_args_list:
            self.assertIn("execution_scope",call.args[1])
            self.assertIn("battery",call.args[2]["brief"]["execution_scope"]["prohibited_topics"])
            self.assertNotIn("all_facts",call.args[2]["package"])
        self.assertIsNotNone(u["repair_before"]);self.assertNotIn("续航",u["document"]["title"])

    def test_manual_edit_reintroducing_omitted_claim_fails_review(self):
        t=self.resolved()
        with patch.object(w.llm,"complete",AsyncMock(side_effect=[copy.deepcopy(DOC),dict(summary="fixture通过",issues=[])])):
            self.client.post(f"/api/tasks/{t['id']}/confirm-plan",json=dict(version=t["version"],plan=t["plan"]))
        t=db.get(t["id"]);bad=copy.deepcopy(DOC);bad["title"]="从早用到晚的电池"
        r=self.client.put(f"/api/tasks/{t['id']}/document",json=dict(version=t["version"],document=bad));self.assertEqual(r.status_code,200)
        t=db.get(t["id"])
        with patch.object(w.llm,"complete",AsyncMock(return_value=dict(summary="fixture未发现",issues=[]))):
            self.client.post(f"/api/tasks/{t['id']}/review",json=dict(version=t["version"]))
        u=db.get(t["id"]);self.assertEqual(u["status"],"needs_review");self.assertFalse(w.can_export(u))
        self.assertTrue(any("舍弃" in i["detail"] for i in u["review"]["issues"]))

    def test_planner_reintroducing_omitted_direction_is_rejected(self):
        t=paused();p=self.preview(t);bad=copy.deepcopy(PLAN);bad["angle"]="续航一天"
        with patch.object(w.llm,"complete",AsyncMock(return_value=bad)):
            self.assertEqual(self.confirm(t,p).status_code,202)
        u=db.get(t["id"]);self.assertEqual(u["status"],"error");self.assertFalse(w.can_export(u))

    def test_summary_reports_actual_source_missing_conditions_and_paths(self):
        t=paused();r=self.client.get(f"/api/tasks/{t['id']}/evidence-review");self.assertEqual(r.status_code,200)
        body=r.json();self.assertEqual(body["knowledge_source"],t.get("knowledge_source","ima"))
        self.assertEqual([u["request"]["id"] for u in body["unmet_requirements"]],["R1","R3"])
        self.assertFalse(body["task_upload_supported"]);self.assertEqual(len(body["actions"]),3)
        self.assertEqual(body["material_requirements"][0]["conditions"],["具体配置"])

    def test_overall_modify_clears_execution_scope(self):
        t=self.resolved()
        with patch.object(w,"job",AsyncMock()):
            self.client.post(f"/api/tasks/{t['id']}/modify",json=dict(version=t["version"],instruction="产品改为另一型号，人群改为设计师"))
        u=db.get(t["id"]);self.assertIsNone(u.get("execution_scope"));self.assertIsNone(u["package"]);self.assertTrue(u["resolution_history"])

    def test_scope_hash_tampering_invalidates_export(self):
        t=self.resolved();t["document"]=copy.deepcopy(DOC);t["status"]="approved"
        t["review"]=dict(passed=True,document_hash=db.digest(t))
        self.assertTrue(w.can_export(t));t["execution_scope"]["omitted_request_ids"]=[]
        self.assertFalse(w.can_export(t))

    def test_scope_survives_pure_platform_change_and_rebinding(self):
        from backend import platform_change as pc
        t=self.resolved();oldscope=copy.deepcopy(t["execution_scope"])
        pc.apply(t,"wechat")
        self.assertEqual(t["execution_scope"]["omitted_request_ids"],oldscope["omitted_request_ids"])
        self.assertEqual(t["execution_scope"]["brief_hash"],ba.digest(t["brief_analysis"]))
        self.assertEqual(t["execution_scope"]["source_brief_hash"],oldscope["source_brief_hash"])
        er.apply(t);self.assertEqual([f["id"] for f in t["package"]["facts"]],["F01"])

    def test_refresh_reads_new_source_and_preserves_scope_and_approval(self):
        t=self.resolved();t["knowledge_source"]="local_zip";t["knowledge_snapshot"]=dict(kind="local_zip",sha256="old")
        t["package"].update(knowledge_source="local_zip",knowledge_snapshot=copy.deepcopy(t["knowledge_snapshot"]));db.save(t,"固定旧快照")
        package=er.raw_package(t);package.update(knowledge_source="local_zip",knowledge_snapshot=dict(kind="local_zip",sha256="new"))
        package.pop("all_facts",None);package.pop("all_conflicts",None)
        outputs=[dict(facts=package["facts"],conflicts=[],coverage=copy.deepcopy(t["package"]["coverage"])),
            dict(images=[dict(id=i["id"],description="新核验",reason="适用",usable=True) for i in package["images"]]),copy.deepcopy(PLAN)]
        async def catalog(current,verify_snapshot=False,refresh=False):
            self.assertFalse(verify_snapshot);self.assertTrue(refresh)
            current["knowledge_snapshot"]=dict(kind="local_zip",sha256="new")
            return [dict(id="test-product",name="测试型号",category="测试")]
        with patch.object(w.ima,"catalog_for_task",side_effect=catalog),patch.object(w.ima,"retrieve_for_task",AsyncMock(return_value=package)) as retrieve,patch.object(w.llm,"complete",AsyncMock(side_effect=outputs)) as model:
            r=self.client.post(f"/api/tasks/{t['id']}/refresh-evidence",json=dict(version=t["version"]))
        self.assertEqual(r.status_code,202,r.text);u=db.get(t["id"])
        self.assertEqual(u["status"],"plan_ready");self.assertEqual(u["brief_confirmation"],t["brief_confirmation"])
        self.assertEqual(u["execution_scope"]["id"],t["execution_scope"]["id"])
        self.assertEqual(u["knowledge_snapshot"]["sha256"],"new")
        self.assertEqual(u["evidence_refreshes"][-1]["from_snapshot"]["sha256"],"old")
        self.assertEqual(u["evidence_refreshes"][-1]["to_snapshot"]["sha256"],"new")
        self.assertEqual(model.call_count,3);self.assertTrue(retrieve.call_args.args[2]["_refresh_assets"])
        self.assertEqual(u["package"]["coverage"],t["package"]["coverage"])
        self.assertIsNone(u["document"])

    def test_refresh_cannot_run_with_unconfirmed_brief(self):
        t=paused();t["brief_confirmation"]=None;db.save(t,"未确认")
        with patch.object(w.ima,"retrieve_for_task",AsyncMock()) as retrieve:
            r=self.client.post(f"/api/tasks/{t['id']}/refresh-evidence",json=dict(version=t["version"]))
        self.assertEqual(r.status_code,400);retrieve.assert_not_called()

    def test_local_zip_snapshot_refresh_does_not_force_brief_reanalysis(self):
        from backend.test_local_knowledge import make_archive
        from backend.knowledge import Knowledge
        async def run(path):
            router=Knowledge();products=await router.catalog(source="local_zip",archive_path=str(path))
            t=dict(knowledge_source="local_zip",knowledge_zip_path=str(path),knowledge_snapshot=router.source_info("local_zip",str(path)))
            old=t["knowledge_snapshot"]["sha256"]
            with zipfile.ZipFile(path,"a") as z:z.writestr("fixture-v7/version.txt","updated")
            await router.catalog_for_task(t,verify_snapshot=False,refresh=True)
            self.assertNotEqual(t["knowledge_snapshot"]["sha256"],old)
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/"fixture.zip";make_archive(path);asyncio.run(run(path))

    def test_shared_independent_fact_survives_composite_direction_drop(self):
        t=paused();t["package"]["coverage"][2].update(status="supported",fact_ids=["F01"])
        db.save(t,"组合方向共享独立重量事实")
        p=self.preview(t)
        self.assertTrue(p["can_apply"]);self.assertEqual(p["retained_fact_ids"],["F01"])

    def test_visible_omitted_claim_in_cached_image_listed_and_excluded(self):
        t=paused();t["package"]["images"][0]["visual_description"]="图上写着超长续航"
        t["package"]["asset_candidates"]=copy.deepcopy(t["package"]["images"]);db.save(t,"已知画面")
        p=self.preview(t);self.assertTrue(p["can_apply"])
        self.assertEqual(p["excluded_image_ids"],["a"*20])
        plan=copy.deepcopy(PLAN);plan["sections"][0]["image_id"]="b"*20
        with patch.object(w.llm,"complete",AsyncMock(return_value=plan)) as model:
            self.assertEqual(self.confirm(t,p).status_code,202)
        u=db.get(t["id"]);self.assertEqual(u["status"],"plan_ready");self.assertEqual(model.call_count,1)
        self.assertNotIn("a"*20,{im["id"] for im in u["package"]["images"]})

    def test_deleted_cache_file_blocks_resolution(self):
        from backend.settings import ASSETS
        t=paused();(ASSETS/("a"*20)).unlink()
        p=self.preview(t);self.assertFalse(p["can_apply"])
        self.assertIn("image_integrity",[b["code"] for b in p["remaining_blockers"]])

    def test_protection_for_explicit_compatibility_need(self):
        t=paused()
        r=t["brief_analysis"]["retrieval_plan"]["facts"][0];r["question"]="兼容性是否满足软件需求"
        t["brief_analysis"]["requirements"]["customer_needs"]=dict(value=["软件兼容性必须确认"],source="explicit",evidence=[dict(turn_id="U1",quote="软件兼容性必须确认")],reason="用户明确提出")
        t["brief_confirmation"]["analysis_hash"]=ba.digest(t["brief_analysis"]);db.save(t,"明确兼容需求")
        p=self.preview(t);self.assertFalse(p["can_apply"])
        self.assertTrue(any(b["code"]=="non_waivable" for b in p["remaining_blockers"]))

    def test_refresh_assets_preserves_old_image_bytes_and_reloads_media(self):
        from backend.test_local_knowledge import make_archive
        from backend.local_knowledge import LocalZip
        from backend.settings import ASSETS
        from PIL import Image
        import io
        async def run(path):
            local=LocalZip(path);product=(await local.catalog())[0]
            original=await local.retrieve(product,{})
            old_id=original["images"][0]["id"];before=(ASSETS/old_id).read_bytes()
            out=io.BytesIO();Image.new("RGB",(8,8),"black").save(out,format="PNG");new_bytes=out.getvalue()
            real_fetch=local.fetch_media
            async def fresh(media_id):
                if media_id.endswith("/images/image.png"):return new_bytes
                return await real_fetch(media_id)
            with patch.object(local,"fetch_media",side_effect=fresh) as fetch:
                refreshed=await local.retrieve(product,{"_refresh_assets":True})
            self.assertNotEqual(refreshed["images"][0]["id"],old_id)
            self.assertEqual((ASSETS/old_id).read_bytes(),before)
            self.assertEqual((ASSETS/refreshed["images"][0]["id"]).read_bytes(),new_bytes)
            self.assertTrue(any(c.args[0].endswith("/images/image.png") for c in fetch.call_args_list))
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/"fixture.zip";make_archive(path);asyncio.run(run(path))

    def test_cloud_refresh_bypasses_catalog_cache(self):
        from backend.knowledge import Knowledge
        router=Knowledge();t=dict(knowledge_source="ima")
        with patch.object(router,"catalog",AsyncMock(return_value=[])) as catalog:
            asyncio.run(router.catalog_for_task(t,verify_snapshot=False,refresh=True))
        self.assertTrue(catalog.call_args.kwargs["refresh"])
        self.assertEqual(t["knowledge_snapshot"]["kind"],"ima")

    def test_optional_compatibility_interest_is_not_nonwaivable(self):
        t=paused()
        t["brief_analysis"]["retrieval_plan"]["facts"][0]["question"]="核实兼容性"
        t["brief_analysis"]["requirements"]["customer_needs"]=dict(value=["想了解软件兼容性"],source="explicit",evidence=[dict(turn_id="U1",quote="想了解软件兼容性")],reason="用户兴趣")
        t["brief_confirmation"]["analysis_hash"]=ba.digest(t["brief_analysis"]);db.save(t,"普通兼容兴趣")
        p=self.preview(t);self.assertTrue(p["can_apply"])
        self.assertNotIn("non_waivable",[b["code"] for b in p["remaining_blockers"]])

    def test_endurance_omission_keeps_independent_battery_capacity_evidence(self):
        self.assertIn("battery_capacity",er.topics("容量70 Wh"))
        t=paused();a=t["brief_analysis"]
        a["message_strategy"]["priorities"].append(dict(id="D4",direction="核实电池容量",reason="容量事实",customer_needs=["了解配置"],verification="pending"))
        a["retrieval_plan"]["facts"].append(dict(id="R4",direction_id="D4",category="product",question="电池容量是多少Wh",conditions=["同配置"],priority="supporting"))
        quote="此配置的电池容量为70 Wh，实际容量以具体配置为准。"
        t["package"]["sources"].append(dict(id="S2",title="容量",path="fixture",text=quote))
        t["package"]["facts"].append(dict(id="FCAP",category="product",claim="电池容量70 Wh",quote=quote,source_id="S2",conditions="具体配置"))
        t["package"]["coverage"].append(dict(request_id="R4",status="supported",fact_ids=["FCAP"],reason="容量原文"))
        t["brief_confirmation"]["analysis_hash"]=ba.digest(a);db.save(t,"独立容量依据")
        p=self.preview(t);self.assertTrue(p["can_apply"])
        self.assertEqual(p["omitted_request_ids"],["R1","R3"])
        self.assertIn("FCAP",p["retained_fact_ids"]);self.assertNotIn("battery_capacity",p["prohibited_topics"])
        with patch.object(w.llm,"complete",AsyncMock(return_value=copy.deepcopy(PLAN))):
            self.assertEqual(self.confirm(t,p).status_code,202)
        u=db.get(t["id"]);self.assertEqual(er.text_issues(u,"电池容量70 Wh","正文"),[])
        self.assertTrue(er.text_issues(u,"一天课程不用充电","正文"))

    def test_legacy_raw_refusal_is_in_authorization_preview(self):
        t=paused();t.pop("dialogue",None);t["raw"]="没有续航依据就不生成";db.save(t,"旧格式拒绝条件")
        p=self.preview(t);self.assertTrue(p["required_constraint_acks"])
        self.assertEqual(self.confirm(t,p).status_code,400)

    def test_financial_card_cannot_serve_as_last_remaining_product_fact(self):
        t=paused()
        t["brief_analysis"]["retrieval_plan"]["facts"][1]["priority"]="supporting"
        quote="此配置官方快照售价5999元，受具体渠道限制。"
        t["package"]["sources"][0]["text"]=quote
        t["package"]["facts"][0].update(category="price",claim="售价5999元",quote=quote)
        t["brief_confirmation"]["analysis_hash"]=ba.digest(t["brief_analysis"]);db.save(t,"错误产品事实")
        p=self.preview(t);self.assertFalse(p["can_apply"])
        self.assertIn("empty_content",[b["code"] for b in p["remaining_blockers"]])

    def test_refresh_failure_keeps_previous_evidence_and_records_attempt(self):
        t=paused();before=copy.deepcopy(t["package"])
        with patch.object(w.ima,"catalog_for_task",AsyncMock(side_effect=ServiceError("资料暂不可读"))),patch.object(w.llm,"complete",AsyncMock()) as model:
            self.assertEqual(self.client.post(f"/api/tasks/{t['id']}/refresh-evidence",json=dict(version=t["version"])).status_code,202)
        u=db.get(t["id"]);self.assertEqual(u["status"],"error")
        self.assertEqual(u["package"],before);self.assertEqual(u["evidence_refreshes"][-1]["status"],"error")
        self.assertIn("completed_at",u["evidence_refreshes"][-1]);model.assert_not_called()

    def test_new_dependency_ids_validated(self):
        from backend.brief_test_data import STRATEGY
        from pydantic import ValidationError
        bad=copy.deepcopy(STRATEGY);bad["retrieval_plan"]["facts"][0]["depends_on"]=["unknown"]
        with self.assertRaises(ValidationError):S.StrategyResult.model_validate(bad)
