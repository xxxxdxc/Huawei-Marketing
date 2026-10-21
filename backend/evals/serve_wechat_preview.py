"""Serve a visibly synthetic preview fixture in a TEMP database; never production."""
import argparse
import hashlib
import io
import json
import os
import tempfile
from pathlib import Path

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8767)
    parser.add_argument("--info", required=True)
    args = parser.parse_args()
    directory = Path(tempfile.mkdtemp(prefix="huawei-wechat-preview-qa-"))
    os.environ["HUAWEI_DATA_DIR"] = str(directory)
    from backend import storage as db, workflow as w
    from backend.main import app
    from backend.settings import ASSETS
    from PIL import Image, ImageDraw
    import uvicorn
    if not db.DB.is_relative_to(directory):
        raise RuntimeError("Fixture must never use production storage")
    db.init()
    async def no_model(*args, **kwargs):
        raise RuntimeError("Isolated preview fixture must not call a model")
    w.llm.complete = no_model
    images = []
    for n, iid in enumerate(("c"*20, "d"*20)):
        im = Image.new("RGB", (900, 550), ("#e6f0e9", "#f5efdf")[n])
        draw = ImageDraw.Draw(im)
        draw.rounded_rectangle((160, 70, 740, 440), 20, fill="#304d42")
        draw.rectangle((180, 90, 720, 418), fill=("#a2cfb1", "#dcd0aa")[n])
        draw.polygon([(160, 440), (740, 440), (830, 490), (70, 490)], fill="#c7d0cb")
        draw.text((40, 25), "ISOLATED QA FIXTURE - NOT A REAL PRODUCT IMAGE", fill="#304d42")
        buffer = io.BytesIO()
        im.save(buffer, "PNG")
        raw = buffer.getvalue()
        (ASSETS / iid).write_bytes(raw)
        images.append(dict(id=iid, mime="image/png", model_verified=True, visual_checked=True,
                           usable=True, sha256=hashlib.sha256(raw).hexdigest(), source="isolated QA"))
    t = db.create("这是隔离测试任务，不能作为产品宣传资料", "qa-product", "wechat")
    t.update(status="approved", brief=dict(platform="wechat"),
             plan=dict(sections=[dict(id="S1", image_id=images[0]["id"]),
                                 dict(id="S2", image_id=images[1]["id"], image_position=dict(kind="before_section", order=None))]),
             package=dict(images=images, facts=[], sources=[], product=dict(id="qa-product", name="隔离测试型号")),
             document=dict(title="轻装出发，留一点从容给工作日",
                           lead="这是一篇仅用于验证排版和复制的隔离示例，参数及图片均不作为真实产品资料。",
                           paragraphs=[
                               dict(section_id="S1", heading="INTERNAL_STAFF_ONLY_1", text="在教室与图书馆之间切换，给随行的电脑留一个轻巧的位置。测试文字中的 1.31 kg 和 14.5 mm，只用于检查数字强调与复制一致性。", fact_ids=[], image_id=images[0]["id"], caption="隔离测试图片一"),
                               dict(section_id="S2", heading="INTERNAL_STAFF_ONLY_2", text="让阅读回到内容本身。段落顺序、图片位置和文字保持原样，留白与卡片为视线留下自然的停顿。\n这里另起一行，检查换行是否被完整保留。", fact_ids=[], image_id=images[1]["id"], caption="隔离测试图片二")
                           ], cta="", tags=[]))
    t["review"] = dict(passed=True, document_hash=db.digest(t), summary="仅隔离测试，不代表真实核验", issues=[])
    db.save(t, "隔离排版预览")
    info = dict(task_id=t["id"], version=t["version"], data_dir=str(directory), port=args.port,
                preview=f"http://127.0.0.1:{args.port}/api/tasks/{t['id']}/wechat/preview?version={t['version']}")
    Path(args.info).write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")

if __name__ == "__main__":
    main()
