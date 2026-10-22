import copy, io, json, os, re, zipfile
from contextlib import asynccontextmanager
from typing import Literal
from fastapi import BackgroundTasks, FastAPI, HTTPException, Request, Query
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from . import storage as db, schemas as S, workflow as w, brief_agent as ba
from . import platform_change as pc, evidence_resolution as er, content_planner as cp
from .content_layout import effective_layout
from .clients import llm, ServiceError, KB_NAME
from .knowledge import knowledge as ima
from .settings import ROOT, ASSETS, public_settings, save_settings, get_settings
from .request_origin import origin_allowed

@asynccontextmanager
async def lifespan(app):
    db.init()
    for item in db.listing():
        if item["status"] in w.BUSY:
            t=db.get(item["id"])
            if w.recover_point_replan(t):continue
            t["status"]="error";t["error"]="上次运行被中断，中间状态已保存，请重试。";db.save(t,"启动时恢复中断任务")
    yield

app=FastAPI(title="华为 PC 门店图文助手",version="0.6.1",lifespan=lifespan)
app.add_middleware(TrustedHostMiddleware,allowed_hosts=os.getenv("HUAWEI_ALLOWED_HOSTS","127.0.0.1,localhost,testserver").split(","))

@app.middleware("http")
async def local_origin(request:Request,call_next):
    origin=request.headers.get("origin")
    if origin is not None and request.method not in ("GET","HEAD","OPTIONS") and not origin_allowed(origin,request.headers.get("host", ""),request.url.scheme):
        response=Response(json.dumps({"detail":"请求来源与服务配置不匹配，请刷新页面或联系管理员检查部署设置。","code":"origin_not_allowed"},ensure_ascii=False),status_code=403,media_type="application/json")
    else:
        response=await call_next(request)
    if request.url.path.startswith("/api/"):response.headers["Cache-Control"]="no-store"
    response.headers["X-Content-Type-Options"]="nosniff"
    return response

@app.exception_handler(ServiceError)
async def service_error(request,exc):
    return Response(json.dumps({"detail":str(exc)},ensure_ascii=False),status_code=400,media_type="application/json")

@app.exception_handler(ValueError)
async def value_error(request,exc):
    return Response(json.dumps({"detail":str(exc)},ensure_ascii=False),status_code=409 if "已更新" in str(exc) else 400,media_type="application/json")

@app.exception_handler(KeyError)
async def missing(request,exc):return Response('{"detail":"任务或版本不存在"}',status_code=404,media_type="application/json")

@app.get("/api/health")
def health():return {"ok":True,"app":"华为 PC 门店图文助手","brief_schema_version":"2","knowledge_source":get_settings()["knowledge_source"]}

@app.get("/api/settings")
def settings():return public_settings()

@app.put("/api/settings")
def update_settings(body:S.SettingsUpdate):
    d=body.model_dump();key=d.pop("api_key");reviewer_key=d.pop("reviewer_api_key")
    d=get_settings() | {k:v for k,v in d.items() if v is not None}
    if d["knowledge_source"]=="local_zip":ima.source_info("local_zip",d["local_knowledge_path"])
    save_settings(d,key,reviewer_key);return public_settings()

@app.put("/api/settings/knowledge-source")
def update_knowledge_source(body:S.KnowledgeSourceUpdate):
    config=get_settings();config["knowledge_source"]=body.source
    if body.local_knowledge_path is not None:config["local_knowledge_path"]=body.local_knowledge_path
    # Verify local archive before changing preferences; never touch model keys.
    if body.source=="local_zip":ima.source_info(body.source,config["local_knowledge_path"])
    save_settings(config)
    return public_settings()

@app.post("/api/settings/probe")
async def probe():return await llm.probe()

@app.get("/api/catalog")
async def catalog(refresh:bool=False,source:Literal["ima","local_zip"]|None=None):
    chosen=source or get_settings()["knowledge_source"]
    products=await ima.catalog(refresh,source=chosen)
    return {"knowledge_base":KB_NAME,"knowledge_source":chosen,"source_info":ima.source_info(chosen),"products":[{k:v for k,v in p.items() if k!="folder"} for p in products],"connected":True}

@app.get("/api/tasks")
def tasks():return db.listing()

@app.post("/api/tasks",status_code=201)
async def create_task(body:S.NewTask):
    source=body.knowledge_source or get_settings()["knowledge_source"]
    if body.product_id and not any(p["id"]==body.product_id for p in await ima.catalog(source=source)):raise ValueError("请选择当前资料源内的明确产品型号")
    return db.create(body.raw,body.product_id,body.platform,source,get_settings()["local_knowledge_path"] if source=="local_zip" else None)

@app.get("/api/tasks/{tid}",response_model=S.TaskView,response_model_exclude_unset=True)
def get_task(tid:str):
    t=db.get(tid);t["can_export"]=w.can_export(t)
    if t["status"]=="error":
        t["resume_status"]=w.current(t)
        if t["resume_status"]=="needs_review" and t.get("error")=="模型连续两次未返回符合结构要求的完整结果，未采用不完整输出":
            t["error"]="上次内容核验未返回符合结构的结果；初稿已保留，请重新核验，无需重新写稿。"
    t["brief_analysis_hash"]=ba.digest(t["brief_analysis"]) if t.get("brief_analysis") else None
    if t.get("plan"):t["plan"]=cp.public_plan(t["plan"])
    if t.get("plan"):t["render_layout"]=effective_layout(w.effective_plan(t),t["platform"],t.get("document"))
    return t

@app.get("/api/tasks/{tid}/history")
def history(tid:str):db.get(tid);return db.history(tid)

@app.post("/api/tasks/{tid}/restore")
def restore(tid:str,body:S.Restore):
    with db.LOCK:
        current=db.get(tid)
        if current["status"] in w.BUSY:raise ValueError("任务运行中，暂不能恢复版本")
        t=db.snapshot(tid,body.target_version)
        t.pop("can_export",None)
        t.pop("brief_analysis_hash",None)
        t["selection_confirmation"]=None;t["writer_stage"]=None
        t["brief_confirmation"]=None
        t["review"]=None;t["error"]=None
        t["status"]="needs_review" if t.get("document") else "plan_ready" if t.get("plan") else "brief_ready" if t.get("brief") else "draft"
        if not t.get("document") and not t.get("plan") and t.get("brief_analysis"):
            t["status"]="brief_ready" if t["brief_analysis"]["status"]=="ready" else "needs_information"
        t["resume_status"]=t["status"]
        return db.save(t,f"恢复历史版本 {body.target_version}，核验结果已失效",body.version)

def begin(tid,body,states,operation,bg,update=None):
    with db.LOCK:
        t=db.get(tid);w.require(t,states)
        if t["version"]!=body.version:raise ValueError("任务已更新，请刷新后重试")
        if update:update(t)
        t["resume_status"]={"analyze":"draft","plan":"brief_ready","write":"plan_ready","review":"needs_review","resume_plan":"needs_review","replan":"plan_ready","replan_points":"plan_ready","resolve_evidence":"needs_review","refresh_evidence":"needs_review","manual_evidence":"needs_review"}[operation]
        t["status"]={"analyze":"analyzing","plan":"retrieving","write":"writing","review":"reviewing","resume_plan":"planning","replan":"planning","replan_points":"planning","resolve_evidence":"planning","refresh_evidence":"retrieving","manual_evidence":"retrieving"}[operation]
        t["error"]=None;t["review"]=None
        db.save(t,{"analyze":"开始分析需求","plan":"用户已确认策略，开始检索资料","write":"用户已确认卖点或历史规划，开始编排并写稿","review":"重新核验当前稿件","resume_plan":"按当前规则重新评估已保存资料并继续规划","replan":"仅切换平台，复用需求与核心策略，重新规划","replan_points":"保存卖点选择，原版本暂时保留","resolve_evidence":"用户明确确认局部取舍，复用资料继续规划","refresh_evidence":"用户请求刷新原资料源并重新检查","manual_evidence":"用户提交手动原文与来源链接，重新检查"}[operation],body.version)
        bg.add_task(w.job,tid,operation)
        return {"accepted":True,"task_id":tid}

@app.post("/api/tasks/{tid}/analyze",status_code=202)
def analyze(tid:str,body:S.Versioned,bg:BackgroundTasks):
    return begin(tid,body,{"draft","needs_information","brief_ready"},"analyze",bg)

@app.post("/api/tasks/{tid}/brief/answers",status_code=202)
def answer_brief(tid:str,body:S.BriefAnswers,bg:BackgroundTasks):
    def update(t):
        questions={q["id"]:q for q in (t.get("brief_analysis") or {}).get("questions",[])}
        ids=[a.question_id for a in body.answers]
        if len(ids)!=len(set(ids)) or any(i not in questions for i in ids):
            raise ValueError("问题编号重复或已失效，请刷新当前 Brief")
        if any(not a.answer.strip() for a in body.answers):raise ValueError("回答不能为空")
        for answer in body.answers:
            q=questions[answer.question_id]
            ba.add_turn(t,answer.answer,question_id=q["id"],question_field=q["field"],question=q["question"])
        ba.invalidate(t)
    return begin(tid,body,{"needs_information","brief_ready"},"analyze",bg,update)

@app.post("/api/tasks/{tid}/confirm-brief",status_code=202)
def confirm_brief(tid:str,body:S.BriefUpdate,bg:BackgroundTasks):
    # Legacy form edits become explicit feedback and are reanalysed, never silently
    # applied to the canonical analysis or treated as already approved.
    with db.LOCK:
        existing=db.get(tid)
        if existing["version"]!=body.version:raise ValueError("任务已更新，请刷新后重试")
        if existing.get("brief_analysis") and body.brief is not None:
            incoming=body.brief.model_dump()
            expected=ba.projection(existing["brief_analysis"])
            if incoming!=expected:
                if incoming["questions"]!=((expected or {}).get("questions",[])):
                    raise ValueError("待确认问题由后端计算，请通过补充回答解决，不能直接清除")
                def feedback(t):
                    changes={k:v for k,v in incoming.items() if k!="questions" and v!=(expected or {}).get(k)}
                    ba.add_turn(t,"用户修改策略卡："+json.dumps(changes,ensure_ascii=False))
                    ba.invalidate(t)
                return begin(tid,body,{"brief_ready","needs_information","plan_ready","needs_review","approved"},"analyze",bg,feedback)
        def update(t):
            if t.get("brief_analysis"):
                analysis=ba.assert_ready(t)
                h=ba.digest(analysis)
                if body.analysis_hash and body.analysis_hash!=h:raise ValueError("Brief 已更新，请刷新后重新确认")
                t["brief"]=ba.projection(analysis)
                t["brief_confirmation"]=dict(analysis_hash=h,at=db.now(),authorized_version=t["version"]+1)
                t["last_confirmed_brief"]=copy.deepcopy(analysis)
            else:
                if body.brief is None:raise ValueError("旧版任务需要提交完整策略卡")
                b=body.brief.model_dump()
                if b["questions"]:raise ValueError("请先补齐待确认问题")
                if not t.get("product_id"):raise ValueError("请先确认产品型号")
                t["brief"]=b;t["platform"]=b["platform"]
            t["package"]=None;t["plan"]=None;t["document"]=None;t["user_image_overrides"]={}
        return begin(tid,body,{"brief_ready","needs_information","plan_ready","needs_review","approved"},"plan",bg,update)

@app.post("/api/tasks/{tid}/resume-plan",status_code=202)
def resume_plan(tid:str,body:S.Versioned,bg:BackgroundTasks):
    def update(t):
        ba.assert_confirmed(t)
        if t.get("plan") or t.get("document") or not t.get("package") or not t["package"].get("coverage"):
            raise ValueError("只可恢复已有检索资料但尚无规划和文稿的任务")
        if t.get('manual_evidence'):
            t.setdefault('evidence_refreshes',[]).append(dict(kind='saved_manual_recheck',requested_at=db.now(),authorized_version=t['version']+1))
    return begin(tid,body,{"needs_review"},"resume_plan",bg,update)

@app.put("/api/tasks/{tid}/plan")
def save_plan(tid:str,body:S.PlanUpdate):
    with db.LOCK:
        t=db.get(tid);w.require(t,{"plan_ready"})
        p=cp.reconcile(t.get("plan"),body.plan.model_dump(exclude_unset=True),t["platform"]);w.validate_plan(t,p,False)
        t["plan"]=p;t["review"]=None
        return db.save(t,"用户修改内容规划",body.version)

@app.post("/api/tasks/{tid}/confirm-plan",status_code=202)
def confirm_plan(tid:str,body:S.PlanUpdate,bg:BackgroundTasks):
    def update(t):
        incoming=body.plan.model_dump(exclude_unset=True)
        if (t.get('plan') or {}).get('schema_version')=='3':
            # Accept the local selection in one explicit confirmation, ignoring client scores.
            if incoming.get('schema_version')!='3' or incoming.get('product_id')!=t['product_id']:
                raise ValueError('卖点选择版本或型号已变化，请刷新')
            p=cp.selection_plan(t,cp.trusted_candidates(t),incoming.get('selected_point_ids'))
            t['selection_confirmation']=dict(selection_hash=cp.selection_fingerprint(p),
                authorized_version=t['version']+1,at=db.now())
            t['writer_outline']=None;t['writer_stage']=None
        else:
            p=cp.reconcile(t.get("plan"),incoming,t["platform"])
        w.validate_plan(t,p);t["plan"]=p;t["user_image_overrides"]={}
    return begin(tid,body,{"plan_ready"},"write",bg,update)

@app.put("/api/tasks/{tid}/document")
def edit_document(tid:str,body:S.DocumentUpdate):
    with db.LOCK:
        t=db.get(tid);w.require(t,{"approved","needs_review"})
        if t["version"]!=body.version:raise ValueError("任务已更新，请刷新后重试")
        document=body.document.model_dump()
        t["user_image_overrides"]=w.record_user_image_edits(t,document)
        t["document"]=document;t["review"]=None;t["status"]="needs_review";t["resume_status"]="needs_review"
        return db.save(t,"用户编辑成稿，旧核验结果已失效",body.version)

@app.post("/api/tasks/{tid}/review",status_code=202)
def review(tid:str,body:S.Versioned,bg:BackgroundTasks):
    t=db.get(tid)
    if not t.get("document"):raise ValueError("尚无成稿可核验")
    return begin(tid,body,{"approved","needs_review"},"review",bg)

@app.get("/api/tasks/{tid}/evidence-review")
def evidence_review(tid:str):
    return er.review_summary(db.get(tid))


@app.post("/api/tasks/{tid}/evidence-resolution/preview")
def preview_evidence_resolution(tid:str,body:S.EvidenceResolutionPreview):
    t=db.get(tid)
    if t["version"]!=body.version:raise ValueError("任务已更新，请刷新后重新预览")
    if t["status"] in w.BUSY:raise ValueError("任务运行中，请完成后再预览")
    return er.preview(t,body.drop_request_ids,body.drop_direction_ids)


@app.post("/api/tasks/{tid}/evidence-resolution/confirm",status_code=202)
def confirm_evidence_resolution(tid:str,body:S.EvidenceResolutionConfirm,bg:BackgroundTasks):
    return begin(tid,body,{"needs_review","plan_ready"},"resolve_evidence",bg,lambda t:er.confirm(t,body))


@app.post("/api/tasks/{tid}/manual-evidence",status_code=202)
def add_manual_evidence(tid:str,body:S.ManualEvidenceInput,bg:BackgroundTasks):
    return begin(tid,body,{"plan_ready","needs_review","approved"},"manual_evidence",bg,
                 lambda t:w.me.prepare(t,body))


@app.post("/api/tasks/{tid}/refresh-evidence",status_code=202)
def refresh_evidence(tid:str,body:S.Versioned,bg:BackgroundTasks):
    def update(t):
        ba.assert_confirmed(t)
        if not t.get("brief_analysis"):raise ValueError("请先确认结构化 Brief")
        t.setdefault("evidence_refreshes",[]).append(dict(requested_at=db.now(),authorized_version=t["version"]+1,
            from_snapshot=copy.deepcopy(t.get("knowledge_snapshot")),original_package_hash=er.digest(er.raw_package(t)),
            knowledge_source=t.get("knowledge_source","ima"),scope_id=(t.get("execution_scope") or {}).get("id")))
        t["plan"]=None;t["document"]=None;t["repair_before"]=None;t["user_image_overrides"]={}
    return begin(tid,body,{"brief_ready","plan_ready","needs_review","approved"},"refresh_evidence",bg,update)



@app.post("/api/tasks/{tid}/replan-points",status_code=202)
def replan_points(tid:str,body:S.ReplanPoints,bg:BackgroundTasks):
    def update(t):
        ba.assert_confirmed(t)
        candidates=cp.trusted_candidates(t)
        selected=cp.validate_selection(t,candidates,body.selected_point_ids)
        pending=dict(selected_point_ids=selected,original_plan_hash=cp.content_fingerprint(t["plan"]),
            candidate_hash=cp.digest(candidates),authorized_version=t["version"]+1,requested_at=db.now())
        t["pending_point_replan"]=pending
        t.setdefault("point_replans",[]).append(dict(pending,status="running"))
    return begin(tid,body,{"plan_ready"},"replan_points",bg,update)


@app.post("/api/tasks/{tid}/replan",status_code=202)
def retry_replan(tid:str,body:S.Versioned,bg:BackgroundTasks):
    def update(t):
        ba.assert_confirmed(t)
        if not t.get("platform_changes") or t["platform_changes"][-1]["analysis_hash"]!=ba.digest(t["brief_analysis"]) or t.get("document"):
            raise ValueError("仅可重试已授权的平台重规划；已有文稿请明确更换平台")
        t["plan"]=None;t["review"]=None
    return begin(tid,body,{"plan_ready","needs_review"},"replan",bg,update)


@app.post("/api/tasks/{tid}/change-platform",status_code=202)
def change_platform(tid:str,body:S.PlatformChange,bg:BackgroundTasks):
    return begin(tid,body,{"brief_ready","plan_ready","approved","needs_review"},"replan",bg,
        lambda t:pc.apply(t,body.platform))


@app.post("/api/tasks/{tid}/modify",status_code=202)
def modify(tid:str,body:S.Modify,bg:BackgroundTasks):
    # Compatibility with the existing frontend button and exact natural-language commands.
    with db.LOCK:
        existing=db.get(tid)
        platform=pc.detect_platform(body.instruction)
        if platform and pc.eligible(existing):
            return begin(tid,body,{"brief_ready","plan_ready","approved","needs_review"},"replan",bg,
                lambda t:pc.apply(t,platform,body.instruction))
    def update(t):
        ba.add_turn(t,body.instruction)
        t["raw"]+="\n用户新增修改要求："+body.instruction
        t["latest_instruction"]=body.instruction
        ba.invalidate(t);t["resume_status"]="draft"
    return begin(tid,body,{"draft","brief_ready","needs_information","plan_ready","approved","needs_review"},"analyze",bg,update)

@app.get("/api/assets/{iid}")
def asset(iid:str):
    if not re.fullmatch(r"[a-f0-9]{20}",iid) or not (ASSETS/iid).is_file():raise HTTPException(404,"图片不存在")
    from PIL import Image
    with Image.open(ASSETS/iid) as im:mime={"PNG":"image/png","JPEG":"image/jpeg","WEBP":"image/webp"}.get(im.format,"application/octet-stream")
    return FileResponse(ASSETS/iid,media_type=mime)

@app.get("/api/tasks/{tid}/export")
def export(tid:str,bundle:bool=False):
    t=db.get(tid);text=w.markdown(t)
    if not bundle:return Response(text,media_type="text/markdown; charset=utf-8",headers={"Content-Disposition":'attachment; filename="marketing.md"'})
    out=io.BytesIO()
    with zipfile.ZipFile(out,"w",zipfile.ZIP_DEFLATED) as z:
        z.writestr("marketing.md",text)
        z.writestr("evidence.md",w.markdown(t,include_evidence=True))
        z.writestr("review.json",json.dumps(t["review"],ensure_ascii=False,indent=2))
        z.writestr("layout.json",json.dumps(effective_layout(w.effective_plan(t),t["platform"],t["document"]),ensure_ascii=False,indent=2))
        used={p["image_id"] for p in t["document"]["paragraphs"] if p["image_id"]}
        for im in t["package"]["images"]:
            if im["id"] in used:z.write(ASSETS/im["id"],f"assets/{im['id']}.{im['mime'].split('/')[-1]}")
    return Response(out.getvalue(),media_type="application/zip",headers={"Content-Disposition":'attachment; filename="marketing-bundle.zip"'})

# WeChat is an export adapter: no Writer/Planner/review calls or task mutations.
def wechat_current(tid, version):
    t = db.get(tid)
    if t["version"] != version:
        raise ValueError("任务已更新，请返回工作台重新打开公众号排版")
    if t["platform"] != "wechat":
        raise ValueError("公众号排版仅适用于微信公众号")
    if not w.can_export(t):
        raise ValueError("当前版本尚未通过核验，不能复制或导出公众号排版")
    return t


def wechat_rendered(tid, version, theme, offline=False):
    from . import wechat_export as wx
    t = wechat_current(tid, version)
    return wx.render(t, effective_layout(w.effective_plan(t), t["platform"], t["document"]),
                     db.digest(t), ASSETS, theme, offline=offline)


@app.get("/api/tasks/{tid}/wechat/render")
def wechat_render(tid: str, version: int = Query(ge=1), theme: Literal["moyu-green", "moyu-ticket"] = "moyu-green"):
    return wechat_rendered(tid, version, theme)[0]


@app.get("/api/tasks/{tid}/wechat/preview")
def wechat_preview(tid: str, version: int = Query(ge=1), theme: Literal["moyu-green", "moyu-ticket"] = "moyu-green"):
    from . import wechat_export as wx
    page, nonce = wx.preview_page(wechat_rendered(tid, version, theme)[0])
    return Response(page, media_type="text/html; charset=utf-8",
                    headers={"Content-Security-Policy": "default-src 'none'; script-src 'nonce-" + nonce +
                             "'; style-src 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; base-uri 'none'; frame-ancestors 'self'",
                             "Referrer-Policy": "no-referrer"})


@app.get("/api/tasks/{tid}/wechat/export")
def wechat_export(tid: str, version: int = Query(ge=1), theme: Literal["moyu-green", "moyu-ticket"] = "moyu-green", bundle: bool = False):
    from . import wechat_export as wx
    result, images = wechat_rendered(tid, version, theme, offline=True)
    if bundle:
        return Response(wx.bundle(result, images), media_type="application/zip",
                        headers={"Content-Disposition": 'attachment; filename="wechat-images-and-layout.zip"'})
    # A standalone HTML fragment embeds the exact verified image bytes for local viewing.
    html = result["html"]
    import base64
    for image in result["assets"]:
        uri = "data:" + image["mime"] + ";base64," + base64.b64encode(images[image["filename"]]).decode("ascii")
        html = html.replace('src="' + image["filename"] + '"', 'src="' + uri + '"')
    return Response(html, media_type="text/html; charset=utf-8",
                    headers={"Content-Disposition": 'attachment; filename="wechat-article.html"'})


@app.get("/api/wechat/layout-source")
def wechat_layout_source():
    from . import wechat_export as wx
    return Response(wx.source_bundle(), media_type="application/zip",
                    headers={"Content-Disposition": 'attachment; filename="wechat-layout-source.zip"'})


DIST=ROOT/"frontend/dist"
if DIST.is_dir():
    app.mount("/assets",StaticFiles(directory=DIST/"assets"),name="frontend-assets")
    @app.get("/")
    def index():return FileResponse(DIST/"index.html")
