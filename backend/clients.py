import asyncio, base64, csv, hashlib, io, json, os, re, time
from pathlib import Path
from urllib.parse import urlparse
import httpx
from PIL import Image
from pydantic import ValidationError
from . import storage as db, model_output as mo
from .settings import ROOT, ASSETS, DATA, get_settings, api_key, user_env

KB_NAME = "任德耀新建华为PC知识库"
SCRIPT = ROOT / "backend/vendor/ima-skill/ima_api.cjs"

class ServiceError(Exception): pass

def short_id(value): return hashlib.sha256(value.encode()).hexdigest()[:20]
def compact(s): return re.sub(r"\s+", "", s)

class Ima:
    def __init__(self): self.kb = None
    async def call(self, route, body):
        env=os.environ.copy()
        env.update(IMA_OPENAPI_CLIENTID=user_env("IMA_OPENAPI_CLIENTID"), IMA_OPENAPI_APIKEY=user_env("IMA_OPENAPI_APIKEY"), IMA_BASE_URL="https://ima.qq.com", IMA_LAST_CHECK_FILE=str(DATA / "ima_last_check"))
        # Avoid unrelated legacy variables taking priority over the selected account.
        env.pop("IMA_CLIENT_ID", None); env.pop("IMA_API_KEY", None)
        if not env["IMA_OPENAPI_CLIENTID"] or not env["IMA_OPENAPI_APIKEY"]: raise ServiceError("尚未配置 ima 凭证，请设置 IMA_OPENAPI_CLIENTID 和 IMA_OPENAPI_APIKEY")
        proc=await asyncio.create_subprocess_exec("node",str(SCRIPT),"openapi/wiki/v1/"+route,json.dumps(body,ensure_ascii=False),env=env,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
        try: out,err=await asyncio.wait_for(proc.communicate(),35)
        except asyncio.TimeoutError:
            proc.kill();await proc.communicate();raise ServiceError("ima 请求超时，请稍后重试")
        if proc.returncode:
            try: code=json.loads(err).get("code")
            except Exception: code=None
            if code == -200: raise ServiceError("官方 ima Skill 提示有新版本，请先更新调用脚本")
            raise ServiceError("ima 调用失败，请检查账号凭证和网络连接")
        try: data=json.loads(out)
        except Exception: raise ServiceError("ima 返回了无法识别的响应")
        if data.get("code") != 0: raise ServiceError("ima："+str(data.get("msg","接口调用失败"))[:300])
        return data.get("data",{})
    async def knowledge_base(self):
        if self.kb:return self.kb
        d=await self.call("search_knowledge_base",dict(query=KB_NAME,cursor="",limit=20))
        for k in d.get("info_list",[]):
            if (k.get("kb_name") or k.get("name"))==KB_NAME:
                self.kb=k.get("kb_id") or k.get("id");return self.kb
        raise ServiceError("当前 ima 账号未找到指定比赛知识库，请确认已加入共享知识库")
    async def listing(self, folder=None):
        kb=await self.knowledge_base();cursor="";items=[]
        for _ in range(30):
            body=dict(knowledge_base_id=kb,cursor=cursor,limit=50)
            if folder:body["folder_id"]=folder
            d=await self.call("get_knowledge_list",body);items.extend(d.get("knowledge_list",[]))
            if d.get("is_end",True):return items
            nxt=d.get("next_cursor","")
            if not nxt or nxt==cursor:raise ServiceError("ima 目录分页异常")
            cursor=nxt
        raise ServiceError("ima 目录页数超过限制，请缩小范围")
    async def fetch_media(self, media_id):
        d=await self.call("get_media_info",dict(media_id=media_id))
        u=d.get("url_info") or {};url=u.get("url","");p=urlparse(url)
        allowed=("qq.com","myqcloud.com","qpic.cn","huawei.com","tencentcos.cn","tencentcloudapi.com")
        if p.scheme!="https" or not any(p.hostname==h or (p.hostname or "").endswith("."+h) for h in allowed):
            raise ServiceError("ima 未返回可安全读取的原文链接，请使用 ima 客户端检查该资料")
        async with httpx.AsyncClient(timeout=35,trust_env=False) as c:
            async with c.stream("GET",url,headers=u.get("headers") or {}) as res:
                if res.status_code!=200:raise ServiceError("无法读取 ima 原文或图片，请刷新资料权限后重试")
                chunks=[];size=0
                async for chunk in res.aiter_bytes():
                    size+=len(chunk)
                    if size>20*1024*1024:raise ServiceError("单项资料超过 20 MB，已停止读取")
                    chunks.append(chunk)
                return b"".join(chunks)
    async def catalog(self, refresh=False):
        cached=db.cache_get("catalog")
        if cached and not refresh and time.time()-cached["at"]<3600:return cached["products"]
        root=await self.listing()
        wrapper=next((x for x in root if x.get("title")==KB_NAME and x.get("media_type")==99),None)
        if wrapper:root=await self.listing(wrapper["media_id"])
        p1=next((x for x in root if x.get("title","").startswith("P1-")),None)
        if not p1:raise ServiceError("未找到 P1 产品参数目录")
        cats=await self.listing(p1["media_id"]);products=[]
        for cat in cats:
            if not cat.get("title","").startswith(("01-","02-","03-")):continue
            children=await self.listing(cat["media_id"])
            for x in children:
                if x.get("media_type")!=99:continue
                path=f"P1-产品参数库/{cat['title']}/{x['title']}"
                products.append(dict(id=short_id(path),name=x["title"],category=cat["title"].split("-",1)[-1],path=path,folder=x["media_id"]))
        if not products:raise ServiceError("产品目录为空")
        db.cache_set("catalog",dict(at=time.time(),products=products));return products
    async def public_price_sources(self, product):
        """Only verified public P1/08 rows; never use P4 controlled templates."""
        root=await self.listing()
        wrapper=next((x for x in root if x.get("title")==KB_NAME and x.get("media_type")==99),None)
        if wrapper:root=await self.listing(wrapper["media_id"])
        p1=next((x for x in root if x.get("title","").startswith("P1-") and x.get("media_type")==99),None)
        if not p1:return []
        folder=next((x for x in await self.listing(p1["media_id"]) if x.get("title","").startswith("08-官方公开价格快照") and x.get("media_type")==99),None)
        if not folder:return []
        item=next((x for x in await self.listing(folder["media_id"]) if x.get("title")=="官方价格快照.csv"),None)
        if not item:return []
        text=(await self.fetch_media(item["media_id"])).decode("utf-8-sig")
        reader=csv.DictReader(io.StringIO(text))
        if not {"规范产品名称","精确款式","核验时间","官方URL"}<=set(reader.fieldnames or []):raise ServiceError("公开价格快照字段不完整，请核对知识库")
        def norm(name):
            name=name.lower().replace("huawei","").replace("华为","")
            return re.sub(r"[^a-z0-9\u4e00-\u9fff]","",name)
        lines=text.splitlines(keepends=True);header=reader.line_num;previous=header;selected=[]
        for row in reader:
            original="".join(lines[previous:reader.line_num]);previous=reader.line_num
            name=row.get("规范产品名称","");key=norm(name)
            harmony="鸿蒙" in name or "harmonyos" in name.lower()
            if harmony!=("鸿蒙" in product["category"]):continue
            key=key.replace("鸿蒙版","").replace("harmonyos","")
            if key!=norm(product["name"]):continue
            # Include empty-amount states: absence of a usable quote is evidence too.
            selected.append(original)
        if not selected:return []
        return [dict(title="官方价格快照.csv",path="P1-产品参数库/08-官方公开价格快照/官方价格快照.csv",text="".join(lines[:header]+selected),scope="public_price_snapshot",record_count=len(selected),usage_limitations="仅为指定型号的配置、时间、渠道及资格条件快照；无统一现价，不是今天的门店报价或结算实付；空金额与模板不能推测金额。",retrieved_at=db.now())]

    async def retrieve(self, product, brief):
        entries=await self.listing(product["folder"])
        # Search is attempted first. Empty search explicitly falls back to the verified product directory.
        kb=await self.knowledge_base()
        requests=(brief.get("retrieval_plan") or {}).get("facts",[])
        queries=[dict(request_id=None,query=product["name"])]
        ordered=sorted(requests,key=lambda r:r.get("category","product") not in ("price","promotion"))
        queries.extend(dict(request_id=r["id"],query=product["name"]+" "+r["question"][:180]) for r in ordered[:2])
        searches=[]
        for item in queries:
            search=await self.call("search_knowledge",dict(knowledge_base_id=kb,query=item["query"],cursor=""))
            searches.append(item | dict(hits=len(search.get("knowledge_list") or search.get("info_list") or [])))
        search_hits=sum(x["hits"] for x in searches)
        sources=[];index=[]
        for entry in entries:
            title=entry.get("title","")
            if title in ("产品事实.md","卖点与限制.md","article.md"):
                content=(await self.fetch_media(entry["media_id"])).decode("utf-8-sig")
                if len(content.strip())<40:continue
                sources.append(dict(id=f"S{len(sources)+1}",title=title,path=product["path"]+"/"+title,text=content[:45000],retrieved_at=db.now()))
            elif title=="图片索引.csv":
                text=(await self.fetch_media(entry["media_id"])).decode("utf-8-sig")
                index=list(csv.DictReader(io.StringIO(text)))
        if not sources:raise ServiceError("指定型号没有可读取的产品原文，不能生成无依据文案")
        if brief.get("commercial_requests") or any(r.get("category") in ("price","promotion") for r in requests):
            for source in await self.public_price_sources(product):
                source["id"]="S"+str(len(sources)+1);sources.append(source)
        candidates=[]
        for folder in [x for x in entries if x.get("media_type")==99 and ("图" in x.get("title","") or x.get("title")=="images")]:
            for entry in await self.listing(folder["media_id"]):
                if entry.get("media_type")==9 or re.search(r"\.(png|jpe?g|webp)$",entry.get("title",""),re.I):
                    candidates.append((folder,entry))
        images=[]
        # Prefer index-backed assets, then source-specific names; no external image fallback.
        byname={x.get("文件名"):x for x in index}
        image_requests=(brief.get("retrieval_plan") or {}).get("images",[])
        keywords=set(re.findall(r"[a-zA-Z]{3,}|[\u4e00-\u9fff]{2,4}"," ".join(r["description"] for r in image_requests)))
        def image_rank(pair):
            row=byname.get(pair[1].get("title"),{})
            text=" ".join(str(v) for v in row.values())
            return (not bool(row),-sum(word in text for word in keywords))
        candidates.sort(key=image_rank)
        for folder,entry in candidates[:12]:
            name=entry.get("title","");row=byname.get(name)
            if not row:continue
            m=row.get("产品型号","")
            if compact(product["name"]).lower() not in compact(m).lower():continue
            # A model/category mismatch is never repaired by appearance alone.
            if "鸿蒙" in product["category"] and ("Windows" in m or "酷睿" in m):continue
            iid=short_id(product["id"]+entry["media_id"]);dest=ASSETS/iid
            try:
                if brief.get("_refresh_assets") or not dest.exists():
                    data=await self.fetch_media(entry["media_id"])
                    if brief.get("_refresh_assets"):
                        iid=short_id(product["id"]+entry["media_id"]+hashlib.sha256(data).hexdigest())
                        dest=ASSETS/iid
                    dest.write_bytes(data)
                with Image.open(dest) as im:
                    w,h=im.size;fmt=im.format
                    if w*h>40_000_000:raise ValueError("Image too large")
                    im.verify()
            except (ServiceError,OSError,ValueError):continue
            mime={"PNG":"image/png","JPEG":"image/jpeg","WEBP":"image/webp"}.get(fmt)
            if not mime:continue
            images.append(dict(id=iid,name=name,model=m,source=product["path"]+"/"+folder["title"]+"/"+name,description=row.get("官网图片说明") or name,purpose=row.get("建议用途",""),width=w,height=h,mime=mime,sha256=hashlib.sha256(dest.read_bytes()).hexdigest(),url="/api/assets/"+iid,model_verified=True))
        return dict(product={k:v for k,v in product.items() if k!="folder"},sources=sources,images=images,facts=[],conflicts=[],search_hits=search_hits,request_searches=searches,retrieval_plan=brief.get("retrieval_plan"),retrieved_at=db.now())

ima=Ima()

class LLM:
    async def complete(self, model, system, payload, schema, images=None, role=None):
        s=get_settings()
        selected_role=role or ("reviewer" if model==s["reviewer_model"] and model!=s["writer_model"] else "writer")
        key=api_key(selected_role)
        if not key:raise ServiceError("请先在设置中填写模型 API Key 并测试连接")
        s=get_settings()
        body={"model":model,"messages":[{"role":"system","content":system+"\n只返回一个完整的 JSON 对象，不要 Markdown。严格遵守以下 JSON Schema：\n"+json.dumps(schema.model_json_schema(),ensure_ascii=False)},{"role":"user","content":json.dumps(payload,ensure_ascii=False)}],"max_tokens":6000}
        if images:
            content=[{"type":"text","text":body["messages"][1]["content"]}]
            for image in images[:6]:
                data=(ASSETS/image["id"]).read_bytes()
                content.append({"type":"text","text":"图片编号："+image["id"]+"；资料说明："+image["description"]})
                content.append({"type":"image_url","image_url":{"url":"data:"+image["mime"]+";base64,"+base64.b64encode(data).decode()}})
            body["messages"][1]["content"]=content
        # Prompt JSON + local validation is compatible with the gateway's documented minimum protocol.
        attempts=[]
        async with httpx.AsyncClient(timeout=150,trust_env=False) as c:
            for attempt in range(2):
                try:res=await c.post(s["base_url"].rstrip("/")+"/chat/completions",headers={"Authorization":"Bearer "+key},json=body)
                except httpx.TimeoutException:raise ServiceError("模型响应超时，请保留当前任务后重试")
                except httpx.HTTPError:raise ServiceError("无法连接模型服务，请检查 API 地址和网络")
                if res.status_code!=200:
                    try:
                        provider_error=res.json().get("error",{})
                        error_code=provider_error.get("code") if isinstance(provider_error,dict) else None
                    except (ValueError,AttributeError):error_code=None
                    if error_code in ("pre_consume_token_quota_failed","insufficient_quota","insufficient_balance"):
                        label="核验" if selected_role=="reviewer" else "写作"
                        raise ServiceError(label+"模型 API 预扣额度不足，请检查该密钥额度或更换可用密钥后重试；已有稿件和资料已保留。")
                    raise ServiceError(f"模型服务返回 HTTP {res.status_code}，请检查模型权限、余额和接口兼容性")
                try:
                    try:data=res.json()
                    except ValueError as exc:raise mo.InvalidOutput("envelope","模型服务没有返回 JSON") from exc
                    return mo.decode(data,schema)
                except mo.InvalidOutput as error:
                    attempts.append(dict(attempt=attempt+1,kind=error.kind,finish_reason=error.finish_reason,
                        max_tokens=body["max_tokens"],usage=error.usage,detail=error.detail,
                        response_content=error.content[:60000]))
                    identifier=mo.save_failure(model,schema,attempts)
                    if attempt or error.kind=="refusal":
                        raise ServiceError(mo.describe(error,schema,identifier)) from error
                    # Include the actual failed answer and field errors so retry
                    # can correct it rather than repeat an ungrounded generic request.
                    if error.content and error.kind not in ("truncated","empty_content"):
                        body["messages"].append({"role":"assistant","content":error.content[:16000]})
                    if error.kind in ("truncated","empty_content"):
                        body["max_tokens"]=min(body["max_tokens"]*2,24000)
                    body["messages"].append({"role":"user","content":mo.feedback(error,schema)})
        raise ServiceError("模型调用未完成")
    async def probe(self):
        s=get_settings();available={};seen={};counts=[]
        async with httpx.AsyncClient(timeout=25,trust_env=False) as c:
            for role,field in (("writer","writer_model"),("reviewer","reviewer_model")):
                key=api_key(role)
                if not key:raise ServiceError("尚未配置"+("写作" if role=="writer" else "核验")+"模型密钥")
                if key not in seen:
                    try:r=await c.get(s["base_url"].rstrip("/")+"/models",headers={"Authorization":"Bearer "+key})
                    except httpx.HTTPError:raise ServiceError("无法连接模型服务")
                    if r.status_code!=200:raise ServiceError(("写作" if role=="writer" else "核验")+f"模型列表请求返回 HTTP {r.status_code}")
                    seen[key]={x["id"] for x in r.json().get("data",[])}
                ids=seen[key];available[role]=s[field] in ids;counts.append(len(ids))
        return dict(connected=True,writer_available=available["writer"],reviewer_available=available["reviewer"],model_count=max(counts),note="已分别使用写作与核验凭证读取模型列表；实际推理能力需单独验证")

llm=LLM()
