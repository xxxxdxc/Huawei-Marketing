"""WeChat-only layout adapter, derived from gzh-design-skill.
SPDX-License-Identifier: AGPL-3.0-or-later
Copyright (C) 2026 甲木 (Jiamu) × 摸鱼小李 (Moyu Xiaoli)
Adaptation: Huawei-Marketing, 2026-10-21. Only visual components are reused.
No writing, retrieval, model calls, account credentials, or publishing.
"""
import hashlib
import importlib.util
import io
import json
import re
import zipfile
from html import escape
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENDOR = ROOT / "vendor/gzh-design-skill"
MANIFEST = ROOT / "wechat_sources.json"
VERSION = "wechat_layout_v1"
THEMES = {"moyu-green": "摸鱼绿", "moyu-ticket": "摸鱼票据"}
IMAGE_NOTE = "图片使用本机或当前应用地址，粘贴到公众号后可能丢失；请按图片包内的顺序补插。"
FORMAT = {"PNG": ("image/png", "png"), "JPEG": ("image/jpeg", "jpg"), "WEBP": ("image/webp", "webp")}


def source_info():
    meta = json.loads(MANIFEST.read_text(encoding="utf-8"))
    for relative, expected in meta["sha256"].items():
        path = VENDOR / relative
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError("公众号排版 Skill 源文件与固定版本不一致，请检查安装")
    return meta


def _snippet(text, heading):
    start = text.index(heading)
    block = re.search(r"\x60\x60\x60html\s*\n(.*?)\x60\x60\x60", text[start:], re.S)
    if not block:
        raise ValueError("公众号主题缺少已登记的组件")
    return block[1]


def _styles(snippet, tag):
    return re.findall(r"<" + tag + r'\s+style="([^"]*)"', snippet)


def theme_styles(theme):
    if theme not in THEMES:
        raise ValueError("未知公众号排版主题")
    source_info()
    raw = (VENDOR / f"references/theme-{theme}.md").read_text(encoding="utf-8")
    result = dict(
        root=_styles(_snippet(raw, "## 组件 1 全局容器"), "section")[0],
        paragraph=_styles(_snippet(raw, "## 组件 5 正文段落"), "p")[0],
    )
    if theme == "moyu-green":
        result.update(
            card=_styles(_snippet(raw, "### 11e. tool-card"), "section")[0],
            image=_styles(_snippet(raw, "### 12a. image"), "section")[0],
            emphasis=_styles(_snippet(raw, "### 6e. 绿色下划线"), "span")[0],
        )
    else:
        result.update(
            card=_styles(_snippet(raw, "## 组件 11 核心观点卡片"), "section")[1],
            image=_styles(_snippet(raw, "## 组件 8 图片容器"), "section")[1],
            emphasis=_styles(_snippet(raw, "### 6c. 绿色下划线"), "span")[0],
        )
    return result


def _leaf(text):
    return '<span leaf="">' + escape(text, quote=False).replace("\r\n", "\n").replace("\r", "\n").replace("\n", "<br>") + "</span>"


# Emphasis selects existing substrings only. It never computes or adds a claim.
NUMERIC = re.compile(r"\d+(?:\.\d+)?\s*(?:kg|mm|cm|Wh|Hz|GB|TB|W|g|英寸|点触控)", re.I)


def _inline(text, style):
    matches = list(NUMERIC.finditer(text))[:2]
    parts = []
    start = 0
    for match in matches:
        parts.extend((_leaf(text[start:match.start()]),
                      '<span style="' + style + '">' + _leaf(match[0]) + "</span>"))
        start = match.end()
    parts.append(_leaf(text[start:]))
    return "".join(parts)


class ArticleCheck(HTMLParser):
    """Check generated structure, exact visible blocks, and exact image order."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.blocks = []
        self.current = None
        self.images = []

    def handle_starttag(self, tag, attrs):
        allowed = {"section": {"style"}, "p": {"style"}, "span": {"style", "leaf"},
                   "br": set(), "img": {"style", "src", "alt"}}
        if tag not in allowed or len(attrs) != len(dict(attrs)) or set(dict(attrs)) - allowed[tag]:
            raise ValueError("公众号 HTML 含未授权的标签或属性")
        attrs = dict(attrs)
        style = attrs.get("style", "")
        if re.search(r"url\s*\(|expression|@|position\s*:|display\s*:\s*none|visibility\s*:|opacity\s*:", style, re.I):
            raise ValueError("公众号 HTML 含不允许的样式")
        if tag == "p":
            if self.current is not None:
                raise ValueError("公众号 HTML 段落结构错误")
            self.current = []
        if tag == "br":
            if self.current is None:
                raise ValueError("公众号换行缺少正文段落")
            self.current.append("\n")
        elif tag == "img":
            self.images.append(attrs.get("src"))
            if "alt" not in attrs:
                raise ValueError("公众号图片缺少说明属性")
        else:
            self.stack.append((tag, attrs))

    def handle_endtag(self, tag):
        if not self.stack or self.stack[-1][0] != tag:
            raise ValueError("公众号 HTML 标签未正确闭合")
        self.stack.pop()
        if tag == "p":
            self.blocks.append("".join(self.current))
            self.current = None

    def handle_data(self, data):
        if data and (self.current is None or not any(t == "span" and "leaf" in a for t, a in self.stack)):
            raise ValueError("公众号正文必须在 leaf 文本节点内")
        if self.current is not None:
            self.current.append(data)

    def handle_comment(self, data):
        raise ValueError("公众号正文不能包含模板注释")

    def handle_decl(self, decl):
        raise ValueError("公众号正文必须是 HTML 片段")


def validate_html(html, expected_blocks, expected_images):
    parser = ArticleCheck()
    parser.feed(html)
    parser.close()
    if parser.stack or parser.current is not None or parser.blocks != expected_blocks or parser.images != expected_images:
        raise ValueError("公众号排版改变了已核验的正文或图片顺序")
    spec = importlib.util.spec_from_file_location("pinned_gzh_validator", VENDOR / "scripts/validate_gzh_html.py")
    validator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(validator)
    errors, warnings, leaves = validator.validate(html)
    if errors:
        raise ValueError("公众号 HTML 兼容性校验失败：" + "；".join(errors))
    return dict(passed=True, content_identical=True, image_order_identical=True,
                leaf_count=leaves, upstream_errors=errors, upstream_warnings=warnings)


def render(task, layout, document_hash, asset_dir, theme="moyu-green", offline=False):
    """Pure rendering; the HTTP caller must first enforce the current review gate."""
    if task["platform"] != "wechat" or layout["platform"] != "wechat":
        raise ValueError("公众号排版仅适用于微信公众号")
    styles = theme_styles(theme)
    document = task["document"]
    paragraphs = document["paragraphs"]
    section_ids = [p["section_id"] for p in paragraphs]
    if len(section_ids) != len(set(section_ids)):
        raise ValueError("公众号段落编号重复")
    slots = {s["section_id"]: s for s in layout["slots"]}
    if len(slots) != len(layout["slots"]) or set(slots) - set(section_ids):
        raise ValueError("公众号配图布局与当前正文不一致")
    images = {im["id"]: im for im in task["package"]["images"]}
    expected = []
    expected_images = []
    asset_bytes = {}
    asset_manifest = []
    used = set()
    output = ['<section style="' + styles["root"] + '">']
    normalise = lambda text: text.replace("\r\n", "\n").replace("\r", "\n")

    def text_block(text, card=False):
        if not text:
            return
        text = normalise(text)
        expected.append(text)
        p = '<p style="' + styles["paragraph"] + '">' + _inline(text, styles["emphasis"]) + "</p>"
        if card:
            p = '<section style="' + styles["card"] + '">' + p + "</section>"
        output.append(p)

    def picture(p, slot):
        iid = slot["image_id"]
        im = images.get(iid)
        if not re.fullmatch(r"[a-f0-9]{20}", iid or "") or iid in used or not im or im.get("model_verified") is not True or im.get("usable") is False:
            raise ValueError("公众号导出只能使用本型号已核验且不重复的图片")
        if im.get("visual_checked") is not True:
            raise ValueError("当前图片尚未完成画面核验，请先核验图片")
        if slot["kind"] not in ("before_section", "after_section"):
            raise ValueError("公众号图片位置必须为段前或段后")
        path = Path(asset_dir) / iid
        if not path.is_file():
            raise ValueError("公众号配图文件缺失，请恢复素材后重新核验")
        data = path.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        if im.get("sha256") and im["sha256"] != digest:
            raise ValueError("公众号配图字节已改变，请重新核验")
        from PIL import Image, UnidentifiedImageError
        try:
            with Image.open(io.BytesIO(data)) as image:
                fmt = image.format
                image.verify()
        except (OSError, UnidentifiedImageError):
            raise ValueError("公众号配图文件无法读取") from None
        if fmt not in FORMAT:
            raise ValueError("公众号导出暂不支持此图片格式")
        mime, extension = FORMAT[fmt]
        filename = f"images/{len(asset_manifest) + 1:02d}-{iid}.{extension}"
        src = filename if offline else "/api/assets/" + iid
        caption = normalise(p["caption"])
        used.add(iid)
        expected_images.append(src)
        output.append('<section style="' + styles["image"] + '"><span leaf=""><img src="' + src +
                      '" alt="' + escape(caption, quote=True) +
                      '" style="max-width:100%;height:auto;display:block;margin:0 auto;"></span></section>')
        if caption:
            expected.append(caption)
            output.append('<p style="font-size:12px;color:#596273;text-align:center;margin:0 0 24px;">' + _leaf(caption) + "</p>")
        asset_bytes[filename] = data
        asset_manifest.append(dict(order=len(asset_manifest) + 1, section_id=p["section_id"],
                                   image_id=iid, position=slot["kind"], filename=filename,
                                   caption=caption, sha256=digest, mime=mime))

    text_block(document["lead"], card=True)
    for index, paragraph in enumerate(paragraphs):
        slot = slots.get(paragraph["section_id"])
        if bool(slot) != bool(paragraph["image_id"]) or slot and slot["image_id"] != paragraph["image_id"]:
            raise ValueError("公众号配图与当前已核验段落不一致")
        if slot and slot["kind"] not in ("before_section", "after_section"):
            raise ValueError("公众号图片位置必须为段前或段后")
        if slot and slot["kind"] == "before_section":
            picture(paragraph, slot)
        text_block(paragraph["text"], card=index == 0 and not document["lead"])
        if slot and slot["kind"] == "after_section":
            picture(paragraph, slot)
    text_block(document["cta"])
    text_block(" ".join(document["tags"]))
    output.append("</section>")
    html = "".join(output)
    checks = validate_html(html, expected, expected_images)
    meta = source_info()
    warnings = [IMAGE_NOTE]
    # The approved document wins over upstream's cosmetic punctuation conversion.
    if checks["upstream_warnings"]:
        warnings.append("上游格式提示已记录；为保持核验原文，未自动替换标点，请在预览中检查。")
    result = dict(schema_version=1, renderer_version=VERSION, task_id=task["id"], version=task["version"],
                  document_hash=document_hash, theme=theme, theme_name=THEMES[theme],
                  title=document["title"], html=html, plain_text="\n\n".join(expected),
                  html_sha256=hashlib.sha256(html.encode()).hexdigest(), assets=asset_manifest,
                  checks=checks, warnings=warnings,
                  source=dict(repository=meta["repository"], commit=meta["commit"], license=meta["license"]))
    return result, asset_bytes


def preview_page(result, offline=False):
    template = (ROOT / "wechat_preview.html").read_text(encoding="utf-8")
    config = {k: result[k] for k in ("task_id", "version", "theme", "title", "html", "plain_text", "document_hash", "warnings")}
    config["offline"] = offline
    config_json = json.dumps(config, ensure_ascii=False).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    import secrets
    nonce = secrets.token_urlsafe(20)
    page = template.replace("__NONCE__", nonce).replace("__CONFIG__", config_json)
    return page, nonce


def bundle(result, image_bytes):
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("article.html", result["html"])
        z.writestr("title.txt", result["title"])
        z.writestr("preview.html", preview_page(result, offline=True)[0])
        z.writestr("manifest.json", json.dumps({k: v for k, v in result.items() if k not in ("html", "plain_text")}, ensure_ascii=False, indent=2))
        lines = ["公众号图片插入顺序（先粘贴正文，缺图时再补插）："]
        lines += [f'{a["order"]:02d} {a["filename"]} → {a["section_id"]} 段{"前" if a["position"] == "before_section" else "后"}；图片说明：{a["caption"]}' for a in result["assets"]]
        z.writestr("图片顺序.txt", "\n".join(lines))
        z.writestr("使用说明.txt", "打开 preview.html 预览；标题单独粘贴到公众号标题栏，正文使用“复制公众号排版”。\n"
                   + IMAGE_NOTE + "\narticle.html 为带内联样式的正文片段，图片为相对路径。\n"
                   "本包是导出时的已核验快照；修改文字或配图后应回软件重新核验。\n"
                   "排版来源：" + result["source"]["repository"] + " @ " + result["source"]["commit"]
                   + "\n许可证：" + result["source"]["license"] + "，版权与组件源码见应用中的“排版组件源码”。\n")
        for filename, data in image_bytes.items():
            z.writestr(filename, data)
    return out.getvalue()


def source_bundle():
    """Allowlisted corresponding layout sources; never task data, keys or .local."""
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for name in ("wechat_export.py", "wechat_preview.html", "wechat_sources.json"):
            z.write(ROOT / name, "adapter/" + name)
        for relative in source_info()["installed_files"]:
            path = VENDOR / relative
            if not path.resolve().is_relative_to(VENDOR.resolve()) or not path.is_file():
                raise ValueError("排版组件源码清单不完整或路径无效")
            z.write(path, "upstream/" + relative)
        z.writestr("README.txt", "公众号排版适配组件源码，AGPL-3.0-or-later。\n"
                   "上游版权：2026 甲木 (Jiamu) × 摸鱼小李 (Moyu Xiaoli)。\n"
                   "修改：2026-10-21 Huawei-Marketing，仅产品测评／工具盘点视觉组件；移除标题标签、评分和尾注。\n"
                   "render(task, layout, document_hash, asset_dir, theme) 接收已核验的结构化输入，调用方必须先核对审核指纹。\n"
                   "运行依赖：Python 3.11+，Pillow 11.2.1；不调用模型或公众号API。\n"
                   "上游完整许可位于 upstream/LICENSE。主项目其余文件的许可证不因此被自动改写。\n")
    return out.getvalue()
