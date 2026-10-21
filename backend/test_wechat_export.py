"""Isolated WeChat export regression; no model calls or production database."""
import copy
import hashlib
import io
import json
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch
from backend.test_workflow import prepared, TEST_DATA  # Must precede backend imports.
from backend import storage as db, workflow as w, wechat_export as wx
from backend.settings import ASSETS
from backend.main import app
from fastapi.testclient import TestClient
from PIL import Image

class WechatExportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not db.DB.is_relative_to(Path(TEST_DATA.name)):
            raise RuntimeError("WeChat tests must use temporary database")
        db.init()

    def approved(self, two=False):
        t = prepared("approved")
        t["platform"] = t["brief"]["platform"] = "wechat"
        t["document"].update(title="测试标题，不复制进正文", lead="轻装出发，准备新的工作日。", cta="", tags=[])
        t["document"]["paragraphs"][0]["heading"] = "STAFF_ONLY_GUIDE"
        if two:
            t["plan"]["sections"].append(dict(t["plan"]["sections"][0], id="P2", image_id="b"*20,
                image_position=dict(kind="before_section", order=None)))
            t["document"]["paragraphs"].append(dict(t["document"]["paragraphs"][0], section_id="P2",
                image_id="b"*20, text="屏幕用于呈现文档。", caption="第二张产品图"))
            t["package"]["images"].append(dict(id="b"*20, model_verified=True))
        for index, im in enumerate(t["package"]["images"]):
            output = io.BytesIO()
            Image.new("RGB", (40, 30), ["white", "green"][index]).save(output, "PNG")
            raw = output.getvalue()
            (ASSETS / im["id"]).write_bytes(raw)
            im.update(mime="image/png", visual_checked=True, usable=True,
                      sha256=hashlib.sha256(raw).hexdigest())
        t["review"] = dict(passed=True, document_hash=db.digest(t), summary="隔离测试", issues=[])
        return db.save(t, "隔离公众号测试")

    def render(self, t, theme="moyu-green", offline=False):
        from backend.content_layout import effective_layout
        return wx.render(t, effective_layout(w.effective_plan(t), t["platform"], t["document"]),
                         db.digest(t), ASSETS, theme, offline)

    def test_both_themes_preserve_text_and_hide_staff_headings(self):
        t = self.approved(True)
        original = copy.deepcopy(t)
        for theme in wx.THEMES:
            result, _ = self.render(t, theme)
            self.assertNotIn("STAFF_ONLY_GUIDE", result["html"])
            self.assertNotIn(t["document"]["title"], result["html"])
            self.assertNotIn("★★★★★", result["html"])
            self.assertNotIn("GRADE", result["html"])
            self.assertNotIn("TOOL", result["html"])
            self.assertTrue(result["checks"]["content_identical"])
            self.assertTrue(result["checks"]["image_order_identical"])
            self.assertEqual(result["checks"]["upstream_errors"], [])
        self.assertEqual(t, original)

    def test_before_and_after_images_keep_order_and_captions(self):
        result, _ = self.render(self.approved(True))
        html = result["html"]
        self.assertLess(html.index("/api/assets/"+"a"*20), html.index("/api/assets/"+"b"*20))
        self.assertLess(html.index("/api/assets/"+"b"*20), html.index("屏幕用于呈现文档"))
        self.assertEqual([a["position"] for a in result["assets"]], ["after_section", "before_section"])
        self.assertEqual([a["order"] for a in result["assets"]], [1, 2])

    def test_escaped_user_text_cannot_inject_tags_attributes_or_scripts(self):
        t = self.approved()
        t["document"]["paragraphs"][0]["text"] = '正文<script>alert("x")</script> & <img src=x onerror=alert(1)>\n下一行。'
        result, _ = self.render(t)
        self.assertNotIn("<script>", result["html"])
        self.assertIn("&lt;script&gt;", result["html"])
        page, _ = wx.preview_page(result)
        self.assertNotIn('正文<script>', page)
        self.assertIn("\\u003cscript\\u003e", page)

    def test_styles_cannot_change_text_or_contain_active_content(self):
        with self.assertRaises(ValueError):
            wx.validate_html('<section><p><span leaf="">改了</span></p></section>', ["原文"], [])
        with self.assertRaises(ValueError):
            wx.validate_html('<section><p><span leaf="" onclick="x()">原文</span></p></section>', ["原文"], [])
        with self.assertRaises(ValueError):
            wx.validate_html('<section><p style="background:url(https://example.com)"><span leaf="">原文</span></p></section>', ["原文"], [])

    def test_empty_caption_and_cta_do_not_get_invented(self):
        t = self.approved()
        t["document"]["paragraphs"][0]["caption"] = ""
        result, _ = self.render(t)
        self.assertNotIn("图片说明", result["plain_text"])
        self.assertNotIn("欢迎", result["plain_text"])
        self.assertEqual(result["assets"][0]["caption"], "")

    def test_bytes_changed_since_review_rejected(self):
        t = self.approved()
        (ASSETS / ("a"*20)).write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "字节已改变"):
            self.render(t)

    def test_missing_image_rejected(self):
        t = self.approved()
        (ASSETS / ("a"*20)).unlink()
        with self.assertRaisesRegex(ValueError, "文件缺失"):
            self.render(t)

    def test_invalid_image_not_trusted_by_filename_or_declared_mime(self):
        t = self.approved()
        raw = b"<svg onload='alert(1)'></svg>"
        (ASSETS / ("a"*20)).write_bytes(raw)
        t["package"]["images"][0]["sha256"] = hashlib.sha256(raw).hexdigest()
        with self.assertRaisesRegex(ValueError, "无法读取"):
            self.render(t)

    def test_unverified_or_rejected_image_rejected(self):
        for change in (dict(model_verified=False), dict(visual_checked=False), dict(usable=False)):
            t = self.approved()
            t["package"]["images"][0].update(change)
            with self.assertRaises(ValueError):
                self.render(t)

    def test_duplicate_image_rejected(self):
        t = self.approved(True)
        t["document"]["paragraphs"][1]["image_id"] = "a"*20
        t["plan"]["sections"][1]["image_id"] = "a"*20
        with self.assertRaisesRegex(ValueError, "不重复"):
            self.render(t)

    def test_bundle_has_ordered_original_image_bytes_and_portable_preview(self):
        t = self.approved(True)
        result, images = self.render(t, offline=True)
        with zipfile.ZipFile(io.BytesIO(wx.bundle(result, images))) as z:
            self.assertIn("preview.html", z.namelist())
            self.assertEqual(z.read("title.txt").decode(), t["document"]["title"])
            self.assertIn("段前", z.read("图片顺序.txt").decode())
            self.assertNotIn("/api/assets/", z.read("article.html").decode())
            for im in result["assets"]:
                self.assertEqual(z.read(im["filename"]), (ASSETS / im["image_id"]).read_bytes())
                self.assertEqual(hashlib.sha256(z.read(im["filename"])).hexdigest(), im["sha256"])

    def test_export_routes_require_current_passed_version(self):
        with TestClient(app) as client:
            t = self.approved()
            for suffix in ("render", "preview", "export", "export?bundle=true"):
                sep = "&" if "?" in suffix else "?"
                url = f"/api/tasks/{t['id']}/wechat/{suffix}{sep}version={t['version']}"
                self.assertEqual(client.get(url).status_code, 200)
                self.assertEqual(client.get(url.replace(f"version={t['version']}", "version=999")).status_code, 409)
            t["document"]["title"] = "审核后修改"
            db.save(t, "隔离未核验修改")
            response = client.get(f"/api/tasks/{t['id']}/wechat/render?version={t['version']}")
            self.assertEqual(response.status_code, 400)
            self.assertIn("尚未通过核验", response.json()["detail"])

    def test_other_platforms_never_use_wechat_route(self):
        for platform in ("moments", "xiaohongshu"):
            t = self.approved()
            t["platform"] = t["brief"]["platform"] = platform
            t["review"]["document_hash"] = db.digest(t)
            db.save(t, "隔离其他平台")
            with TestClient(app) as client:
                response = client.get(f"/api/tasks/{t['id']}/wechat/render?version={t['version']}")
                self.assertEqual(response.status_code, 400)

    def test_route_rejects_missing_version_and_unknown_theme(self):
        t = self.approved()
        with TestClient(app) as client:
            base = f"/api/tasks/{t['id']}/wechat/render"
            self.assertEqual(client.get(base).status_code, 422)
            self.assertEqual(client.get(base, params=dict(version=t["version"], theme="other")).status_code, 422)

    def test_gets_do_not_call_models_or_save_task_or_versions(self):
        t = self.approved()
        before = db.get(t["id"])
        history = db.history(t["id"])
        with patch.object(w.llm, "complete", side_effect=AssertionError("No models allowed")):
            with TestClient(app) as client:
                for name in ("render", "preview", "export"):
                    response = client.get(f"/api/tasks/{t['id']}/wechat/{name}?version={t['version']}")
                    self.assertEqual(response.status_code, 200)
                self.assertEqual(client.get(f"/api/tasks/{t['id']}/export").status_code, 200)
        self.assertEqual(db.get(t["id"]), before)
        self.assertEqual(db.history(t["id"]), history)

    def test_html_download_embeds_exact_image_and_omits_wrapper(self):
        import base64
        t = self.approved()
        with TestClient(app) as client:
            response = client.get(f"/api/tasks/{t['id']}/wechat/export?version={t['version']}")
        self.assertTrue(response.text.startswith("<section"))
        self.assertNotIn("<script", response.text)
        data = response.text.split("base64,", 1)[1].split('"', 1)[0]
        self.assertEqual(base64.b64decode(data), (ASSETS / ("a"*20)).read_bytes())

    def test_preview_uses_nonce_csp_and_no_internal_content(self):
        t = self.approved()
        with TestClient(app) as client:
            response = client.get(f"/api/tasks/{t['id']}/wechat/preview?version={t['version']}")
        self.assertIn("script-src 'nonce-", response.headers["content-security-policy"])
        self.assertIn("复制公众号排版", response.text)
        self.assertNotIn("STAFF_ONLY_GUIDE", response.text)
        self.assertNotIn("__CONFIG__", response.text)

    def test_pinned_upstream_hash_checked(self):
        meta = json.loads(wx.MANIFEST.read_text(encoding="utf-8"))
        meta["sha256"]["SKILL.md"] = "0"*64
        with patch.object(wx.json, "loads", return_value=meta):
            with self.assertRaisesRegex(ValueError, "固定版本"):
                wx.theme_styles("moyu-green")

    def test_upstream_punctuation_warning_retained_without_rewriting_approved_copy(self):
        t = self.approved()
        t["document"]["lead"] = '中文, "原样"'
        result, _ = self.render(t)
        self.assertEqual(result["plain_text"].split("\n\n")[0], '中文, "原样"')
        self.assertTrue(result["checks"]["upstream_warnings"])

    def test_source_zip_allowlists_only_layout_source_not_tasks_or_secrets(self):
        with zipfile.ZipFile(io.BytesIO(wx.source_bundle())) as z:
            self.assertIn("upstream/LICENSE", z.namelist())
            self.assertIn("adapter/wechat_export.py", z.namelist())
            self.assertFalse(any(".local" in name or ".env" in name or "credential" in name for name in z.namelist()))

    def test_invalid_slot_kind_cannot_silently_drop_image(self):
        t = self.approved()
        from backend.content_layout import effective_layout
        layout = effective_layout(w.effective_plan(t), "wechat", t["document"])
        layout["slots"][0]["kind"] = "carousel"
        with self.assertRaisesRegex(ValueError, "段前或段后"):
            wx.render(t, layout, db.digest(t), ASSETS)

    def test_template_markers_in_approved_title_are_not_replaced(self):
        t = self.approved()
        t["document"]["title"] = "__NONCE__ __CONFIG__"
        result, _ = self.render(t)
        page, nonce = wx.preview_page(result)
        self.assertIn('"title": "__NONCE__ __CONFIG__"', page)
        self.assertIn('nonce="' + nonce + '"', page)
