"""Scope-review and text-only repair regression; all models/DB are isolated."""
import asyncio
import copy
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch
from backend.test_workflow import prepared, DOC, PLAN, TEST_DATA
from backend import review_guard as rg, workflow as w, storage as db, schemas as S, platform_writer as pw, brief_agent as ba
from backend.clients import ServiceError

class ReviewGuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not db.DB.is_relative_to(Path(TEST_DATA.name)):
            raise RuntimeError("Review-guard tests must use temporary DB")
        db.init()

    def scoped(self):
        t = prepared("needs_review")
        t["brief_analysis"] = dict(retrieval_plan=dict(facts=[
            dict(id="f3", direction_id="d3", question="该产品电池容量和续航数据是什么？"),
            dict(id="f4", direction_id="d4", question="屏幕用于会议材料处理")]),
            message_strategy=dict(priorities=[]))
        t["execution_scope"] = dict(id="test-scope", brief_hash=ba.digest(t["brief_analysis"]),
            omitted_request_ids=["f3"], omitted_direction_ids=[], prohibited_topics=["battery", "battery_capacity"])
        t["package"]["images"][0].update(visual_checked=True, visual_description="电脑显示WPS演示文稿编辑界面，含普通柱状图和技术架构说明。")
        return t

    def problem(self, **changes):
        return dict(category="image", location="P1配图", detail="图表和分析内容触及已舍弃主题，应移除或替换该图。",
                    repairable=True, severity="error") | changes

    def evidence(self, **changes):
        return dict(topic="battery", request_ids=["f3"], direction_ids=[], field="paragraph",
                    section_id="P1", image_id=None, quote="续航") | changes

    def review(self, t, outputs, allow_repair=True):
        with patch.object(w, "verify_coverage"), patch.object(w, "deterministic_review", return_value=[]), \
             patch.object(w.ba, "context", return_value=t["brief"]), \
             patch.object(w, "get_settings", return_value=dict(writer_model="fixture", reviewer_model="fixture", vision=True)), \
             patch.object(w.llm, "complete", AsyncMock(side_effect=outputs)) as model:
            asyncio.run(w.review(t, allow_repair=allow_repair))
            return model

    def test_actual_omission_context_has_no_chart_or_analysis_topic(self):
        context = rg.context(self.scoped())
        self.assertEqual({r["topic"] for r in context["prohibited_topics"]}, {"battery", "battery_capacity"})
        self.assertTrue(all(r["request_ids"] == ["f3"] for r in context["prohibited_topics"]))

    def test_screenshot_opinion_without_binding_is_rejected_not_approved(self):
        t = self.scoped()
        issues, audit, errors = rg.check(t, [self.problem()])
        self.assertEqual(issues, [])
        self.assertFalse(audit[0]["accepted"])
        self.assertTrue(errors)
        original = copy.deepcopy(t["document"])
        model = self.review(t, [dict(summary="fixture", issues=[self.problem()])])
        self.assertEqual(model.await_count, 1)
        self.assertFalse(t["review"]["passed"])
        self.assertTrue(t["review"]["validation_errors"])
        self.assertEqual(t["status"], "needs_review")
        self.assertEqual(t["document"], original)
        self.assertEqual(t["review"]["raw_model_issues"], [self.problem()])
        self.assertFalse(w.can_export(t))

    def test_wrong_topic_or_request_id_cannot_authorize_removal(self):
        t = self.scoped()
        for evidence in [self.evidence(topic="analysis"), self.evidence(request_ids=["f4"]),
                         self.evidence(direction_ids=["unknown"])]:
            with self.subTest(evidence=evidence):
                self.assertTrue(rg.check(t, [self.problem(scope_evidence=evidence)])[2])

    def test_generic_ppt_description_is_not_battery_evidence(self):
        t = self.scoped()
        evidence = self.evidence(field="image", image_id="a"*20, quote="普通柱状图")
        self.assertTrue(rg.check(t, [self.problem(scope_evidence=evidence)])[2])

    def test_nonexistent_visual_quote_is_rejected(self):
        t = self.scoped()
        evidence = self.evidence(field="image", image_id="a"*20, quote="续航20小时")
        self.assertTrue(rg.check(t, [self.problem(scope_evidence=evidence)])[2])

    def test_valid_text_violation_is_preserved(self):
        t = self.scoped()
        t["document"]["paragraphs"][0]["text"] = "产品续航20小时"
        issue = self.problem(category="compliance", scope_evidence=self.evidence(quote="产品续航20小时"))
        accepted, audit, errors = rg.check(t, [issue])
        self.assertEqual(accepted, [issue])
        self.assertFalse(errors)
        self.assertTrue(audit[0]["accepted"])

    def test_valid_image_violation_routes_to_image_editor(self):
        t = self.scoped()
        t["package"]["images"][0]["visual_description"] = "产品宣传图写有续航20小时"
        evidence = self.evidence(field="image", image_id="a"*20, quote="续航20小时")
        accepted, _, errors = rg.check(t, [self.problem(scope_evidence=evidence)])
        self.assertFalse(errors)
        self.assertFalse(accepted[0]["repairable"])
        t["package"]["images"][0]["visual_description"] = "真实产品宣传图"
        model = self.review(t, [dict(summary="需要核对图片", issues=[self.problem(detail="画面与该型号外观不符，需要换图")])])
        self.assertEqual(model.await_count, 1)
        self.assertEqual(t["review"]["repair_decision"], "image_editor")
        self.assertEqual(t["status"], "needs_review")

    def test_no_scope_cannot_invent_omitted_directions(self):
        t = prepared()
        self.assertTrue(rg.check(t, [self.problem(scope_evidence=self.evidence())])[2])

    def test_metadata_filename_is_not_visible_image_evidence(self):
        t = self.scoped()
        t["package"]["images"][0]["source"] = "续航20小时.png"
        e = self.evidence(field="image", image_id="a"*20, quote="续航20小时")
        self.assertTrue(rg.check(t, [self.problem(scope_evidence=e)])[2])

    def test_ordinary_review_still_passes_and_includes_explicit_scope(self):
        t = self.scoped()
        model = self.review(t, [dict(summary="fixture clear", issues=[])])
        self.assertTrue(w.can_export(t))
        payload = model.call_args.args[2]
        self.assertEqual(payload["review_scope"]["omitted_request_ids"], ["f3"])
        self.assertIn("普通PPT", model.call_args.args[1])

    def payload(self):
        return dict(plan=copy.deepcopy(PLAN), document=copy.deepcopy(DOC),
                    issues=[w.issue("fact", "携带", "请自然修正本段措辞")])

    def test_text_patch_preserves_images_facts_heading_and_order(self):
        p = self.payload()
        result = pw.apply_text_repair(p, dict(root_changes={}, paragraph_changes=[dict(section_id="P1", text="机身约1.33 kg。")]))
        before = p["document"]["paragraphs"][0]
        after = result["paragraphs"][0]
        for key in ("image_id", "fact_ids", "heading", "section_id"):
            self.assertEqual(after[key], before[key])
        self.assertEqual(p["document"], DOC)

    def test_patch_schema_forbids_image_and_fact_changes(self):
        for field, value in (("image_id", None), ("fact_ids", []), ("heading", "changed")):
            with self.subTest(field=field):
                with self.assertRaises(ValueError):
                    S.TextRepair.model_validate(dict(root_changes={}, paragraph_changes=[dict(section_id="P1", **{field: value})]))

    def test_patch_unknown_duplicate_and_unrelated_changes_rejected(self):
        for patch_data in (
            dict(root_changes={}, paragraph_changes=[dict(section_id="unknown", text="x")]),
            dict(root_changes={}, paragraph_changes=[dict(section_id="P1", text="x"), dict(section_id="P1", text="y")]),
            dict(root_changes=dict(title="unrelated"), paragraph_changes=[])):
            with self.subTest(patch=patch_data):
                with self.assertRaises(ValueError):
                    pw.apply_text_repair(self.payload(), patch_data)

    def test_real_transport_schema_is_text_patch_but_output_remains_document(self):
        t = prepared()
        p = self.payload()
        with patch.object(pw.llm, "complete", AsyncMock(return_value=dict(root_changes={}, paragraph_changes=[dict(section_id="P1", text="机身约1.33 kg。")]))) as model:
            result = asyncio.run(pw.repair(t, w.BASE, p, S.Document))
        self.assertIs(model.call_args.args[3], S.TextRepair)
        S.Document.model_validate(result)
        self.assertEqual(result["paragraphs"][0]["image_id"], DOC["paragraphs"][0]["image_id"])

    def test_failed_repair_preserves_first_report_and_rejected_output(self):
        t = prepared("needs_review")
        original = copy.deepcopy(t["document"])
        finding = w.issue("fact", "携带", "修正一处文字")
        invalid = dict(root_changes={}, paragraph_changes=[dict(section_id="P1", text="changed", image_id=None)])
        async def repairing(task):
            await w.review(task, allow_repair=True)
        with patch.object(w, "write", new=repairing), patch.object(w, "deterministic_review", return_value=[]), \
             patch.object(w.llm, "complete", AsyncMock(side_effect=[dict(summary="first report", issues=[finding]), invalid])):
            asyncio.run(w.job(t["id"], "write"))
        current = db.get(t["id"])
        self.assertEqual(current["document"], original)
        self.assertEqual(current["review"]["issues"], [finding])
        self.assertEqual(current["status"], "error")
        self.assertEqual(current["writer_runs"][-1]["rejected_output"], invalid)
        self.assertEqual(current["writer_runs"][-1]["before_review"]["summary"], "first report")

    def test_text_repair_then_independent_full_review(self):
        t = prepared("needs_review")
        finding = w.issue("fact", "携带", "修正一处文字")
        outputs = [dict(summary="first report", issues=[finding]),
                   dict(root_changes={}, paragraph_changes=[dict(section_id="P1", text="机身约1.33 kg。")]),
                   dict(summary="complete review", issues=[])]
        with patch.object(w, "deterministic_review", return_value=[]), patch.object(w.llm, "complete", AsyncMock(side_effect=outputs)) as model:
            asyncio.run(w.review(t, allow_repair=True))
        self.assertEqual(model.await_count, 3)
        self.assertEqual([c.args[3] for c in model.call_args_list], [S.Review, S.TextRepair, S.Review])
        self.assertTrue(w.can_export(t))
        self.assertEqual(t["writer_runs"][-1]["before_review"]["summary"], "first report")


    def test_review_coverage_recomputes_on_copy_without_mutating_package(self):
        t=self.scoped();before=copy.deepcopy(t["package"])
        def recompute(checked):
            checked["package"].setdefault("content_policy",{})["execution_scope"]={"rules":"new reviewer rules"}
        with patch.object(w,"verify_coverage",side_effect=recompute),patch.object(w,"deterministic_review",return_value=[]), \
             patch.object(w.ba,"context",return_value=t["brief"]),patch.object(w.llm,"complete",AsyncMock(return_value=dict(summary="clear",issues=[]))):
            asyncio.run(w.review(t))
        self.assertEqual(t["package"],before)

    def test_changed_execution_facts_require_evidence_check_before_model(self):
        t=self.scoped()
        def recompute(checked):
            checked["package"]["facts"]=[]
        with patch.object(w,"verify_coverage",side_effect=recompute),patch.object(w.llm,"complete",AsyncMock()) as model:
            with self.assertRaisesRegex(ServiceError,"已保存资料与当前取舍范围不一致"):
                asyncio.run(w.review(t))
        model.assert_not_called()

    def dimension_case(self):
        t=prepared()
        t["document"]["paragraphs"][0]["text"]="机身尺寸约 312.6 × 226.8 × 14.5 mm。"
        t["package"]["facts"][0]["quote"]="机身约 312.6 × 226.8 × 14.5 mm，圆/方键盘版本约1.33/1.32kg。"
        issue=self.problem(category="fact",location="正文 P1",detail="尺寸写成确定数值“机身尺寸约 312.6 × 226.8 × 14.5 mm”，但“约”只修饰厚度，长度和宽度没有保留近似限定，需覆盖完整尺寸。")
        return t,issue

    def test_exact_cited_dimension_prefix_resolves_only_this_false_positive(self):
        t,issue=self.dimension_case()
        accepted,audit,errors=rg.check(t,[issue])
        self.assertEqual(accepted,[]);self.assertFalse(errors)
        self.assertEqual(audit[0]["resolved_by"],"dimension_approximation_prefix")
        self.assertEqual(audit[0]["proof"]["fact_ids"],["F01"])

    def test_dimension_proof_does_not_hide_missing_qualifier_or_wrong_numbers(self):
        for body in ("机身312.6 × 226.8 × 14.5 mm。","机身约312.6 × 226.8 × 15.5 mm。"):
            t,issue=self.dimension_case();t["document"]["paragraphs"][0]["text"]=body
            self.assertEqual(rg.check(t,[issue])[0],[issue])

    def test_dimension_proof_requires_bound_fact_and_approximate_original(self):
        t,issue=self.dimension_case();t["document"]["paragraphs"][0]["fact_ids"]=[]
        self.assertEqual(rg.check(t,[issue])[0],[issue])
        t,issue=self.dimension_case();t["package"]["facts"][0]["quote"]="机身312.6 × 226.8 × 14.5 mm"
        self.assertEqual(rg.check(t,[issue])[0],[issue])

    def test_dimension_proof_does_not_resolve_mixed_real_objections(self):
        t,issue=self.dimension_case();issue["detail"]+="；还混淆了Windows与鸿蒙版本。"
        self.assertEqual(rg.check(t,[issue])[0],[issue])
        t,issue=self.dimension_case();issue["location"]="正文 unknown"
        self.assertEqual(rg.check(t,[issue])[0],[issue])

    def test_two_dimension_chains_cannot_cross_authorize_each_other(self):
        t,issue=self.dimension_case()
        t["document"]["paragraphs"][0]["text"]+="另一型号机身310 × 220 × 15 mm。"
        self.assertEqual(rg.check(t,[issue])[0],[issue])

    def test_dimension_proof_never_rounds_long_decimal_values(self):
        t,issue=self.dimension_case()
        t["package"]["facts"][0]["quote"]="机身约312.6 × 226.8 × 14.5000000000000000000000000000001 mm"
        self.assertEqual(rg.check(t,[issue])[0],[issue])
