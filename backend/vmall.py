"""Bounded, anonymous official Vmall supplementation. No search snippets or login."""
import asyncio
import hashlib
import io
import json
import re
from pathlib import Path
from html.parser import HTMLParser
from urllib.parse import parse_qs, urlencode, urljoin, urlparse
import httpx
from PIL import Image
from . import storage as db
from .clients import ServiceError, short_id
from .knowledge import knowledge
from .settings import ASSETS

PAGE_HOSTS = {"www.vmall.com", "item.vmall.com", "m.vmall.com"}
API_HOSTS = {"openapi.vmall.com"}
IMAGE_HOSTS = {"res.vmallres.com"}
API = "https://openapi.vmall.com/mcp/product/queryDisplayProductByVersion"


def allowed(url, hosts):
    p=urlparse(url)
    return p.scheme=="https" and p.hostname in hosts and p.port in (None,443) and not p.username and not p.password


async def fetch(client, url, hosts, limit=3_000_000):
    for _ in range(4):
        if not allowed(url,hosts):raise ServiceError("商城来源地址不在已核对的官方域名内")
        async with client.stream("GET",url) as r:
            if r.status_code in (301,302,303,307,308):
                url=urljoin(url,r.headers.get("location",""))
                continue
            if r.status_code!=200:raise ServiceError(f"商城公开资料返回 HTTP {r.status_code}")
            parts=[];size=0
            async for part in r.aiter_bytes():
                size+=len(part)
                if size>limit:raise ServiceError("商城资料超过读取上限")
                parts.append(part)
            return b"".join(parts),str(r.url)
    raise ServiceError("商城页面跳转次数过多")


class Text(HTMLParser):
    def __init__(self):
        super().__init__();self.parts=[];self.skip=0
    def handle_starttag(self,tag,attrs):
        if tag in ("script","style"):self.skip+=1
    def handle_endtag(self,tag):
        if tag in ("script","style"):self.skip=max(0,self.skip-1)
    def handle_data(self,data):
        if not self.skip and data.strip():self.parts.append(data.strip())


def plain(value):
    p=Text();p.feed(str(value));return "\n".join(p.parts)


def norm(value):
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]","",value.lower().replace("huawei","").replace("华为",""))


def model_matches(product, display):
    actual=str(display.get("name",""))
    base=re.sub(r'^(?:huawei|华为)','',norm(product["name"])).replace("鸿蒙版","").replace("harmonyos","")
    other=re.sub(r'^(?:huawei|华为)','',norm(actual)).replace("鸿蒙版","").replace("harmonyos","")
    # Catalog aliases may include CPU family, but never merge display sizes or Pro/GT.
    base=base.replace("酷睿ultra","")
    if base!=other:return False
    attrs=json.dumps(display.get("attrViewList",[]),ensure_ascii=False).lower()
    harmony="鸿蒙" in actual or "harmonyos" in actual.lower() or "harmonyos" in attrs
    if harmony!=("鸿蒙" in product.get("category","")):return False
    if "酷睿" in product["name"] and "ultra" not in (attrs+actual.lower()):return False
    return bool(actual)


def registry_urls(product):
    rows=json.loads((Path(__file__).parent/'vmall_products.json').read_text(encoding='utf-8'))
    return [r['url'] for r in rows if re.sub(r'^(?:huawei|华为)','',norm(r['product_name']))==re.sub(r'^(?:huawei|华为)','',norm(product.get('name',''))) and r['system']==('harmony' if '鸿蒙' in product.get('category','') else 'windows')]


def evidence_text(value,path='商品'):
    if isinstance(value,dict):return '\n'.join(evidence_text(v,path+'.'+k) for k,v in value.items())
    if isinstance(value,list):return '\n'.join(evidence_text(v,path+f'[{i}]') for i,v in enumerate(value))
    return path+'：'+str(value)


def source_urls(texts):
    urls=[]
    for text in texts:
        for raw in re.findall(r'https://[^\s<>"，）,;]+',text):
            url=raw.rstrip('.,;）');parsed=urlparse(url);qs=parse_qs(parsed.query)
            if allowed(url,PAGE_HOSTS) and parsed.path=='/product/comdetail/index.html' and re.fullmatch(r'\d+',qs.get('prdId',[''])[0]):
                if url not in urls:urls.append(url)
    return urls


async def candidate_urls(task):
    """Reuse saved links and exact registry seeds before requesting any old catalog."""
    p=task['package'];urls=source_urls([s['text'] for s in p['sources']])
    for url in registry_urls(p['product']):
        if url not in urls:urls.append(url)
    if urls:return urls[:5]
    try:
        backend=knowledge.backend(task.get('knowledge_source','ima'),task.get('knowledge_zip_path'))
        return source_urls([s['text'] for s in await backend.public_price_sources(p['product'])])[:5]
    except (ServiceError,KeyError,OSError,httpx.HTTPError,TimeoutError):return []


def photo_url(photo):
    name=photo.get("photoName","");path=photo.get("photoPath","")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+\.(?:png|jpe?g|webp)",name,re.I):return None
    url="https://res.vmallres.com/pimages"+path+name
    if not path.startswith("/") or ".." in path or not allowed(url,IMAGE_HOSTS):return None
    return url


def select_sku(task,display,requested):
    skus=display.get("sbomList",[])
    requirements=(task.get("brief_analysis") or {}).get("requirements",{})
    explicit=" ".join(str(requirements.get(k,{}).get("value") or "") for k in ("product_query","product_model","user_constraints"))
    tokens=re.findall(r"(?i)\b(?:16|24|32|64)GB\b|\b(?:512GB|1TB|2TB)\b|圆键盘|方键盘",explicit)
    candidates=[s for s in skus if all(norm(t) in norm(s.get("name","")) for t in tokens)]
    selected=next((s for s in candidates if str(s.get("sbomCode"))==requested),None)
    if not selected and tokens:selected=next(iter(candidates),None)
    if not selected and not requested:selected=next((s for s in candidates if s.get("defaultSbom")),None)
    if not selected:raise ServiceError("商城商品无法匹配指定 SKU 或用户配置约束")
    return selected


async def read_product(client,url,task):
    qs=parse_qs(urlparse(url).query);pid=qs["prdId"][0];sku=qs.get("sbomCode",[""])[0]
    page={};method="api";retrieved_url=None
    try:
        body,final=await fetch(client,url,PAGE_HOSTS)
        match=re.search(r'<script[^>]+id=["\x27]__NEXT_DATA__["\x27][^>]*>(.*?)</script>',body.decode("utf-8"),re.S)
        if match:
            page=json.loads(match[1])["props"]["pageProps"];method="ssr";retrieved_url=final
    except (ServiceError,ValueError,KeyError,UnicodeError,httpx.HTTPError):
        pass
    current=(page.get("mainData") or {}).get("current",{})
    display=current.get("displayPrdVo")
    api_url=API+"?"+urlencode(dict(portal=1,lang="zh_CN",country="CN",version=6,prdId=pid,sbomCode=sku,isCacheDisplayProduct=1))
    if not isinstance(display,dict):
        raw,retrieved_url=await fetch(client,api_url,API_HOSTS)
        method="api"
        data=json.loads(raw)
        if str(data.get("code"))!="0":raise ServiceError("商城未返回可用商品数据")
        display=data.get("displayPrdVo",{})
    if str(display.get("disPrdId"))!=pid or not model_matches(task["package"]["product"],display):
        raise ServiceError("商城商品型号或系统版本与任务不一致，未采用")
    if not display.get("sbomList") and isinstance(current.get("base"),dict):
        display=dict(display,sbomList=list(current["base"].values()))
    selected=select_sku(task,display,sku or str(page.get("sbomCode","")))
    selected_code=str(selected["sbomCode"])
    # SSR specifications belong to the loaded SKU. Do not attach them to another SKU.
    same_sku=selected_code==str(page.get("sbomCode"))
    ext=page.get("extData",{}) if same_sku else {}
    detail=ext.get("productRelDetailResp",{})
    specs=detail.get("querySkuSpecificResp",{})
    specifics=specs.get("majorSpecificationList",[])
    all_specs=specs.get("specificationsList",[])
    facts=dict(product_name=display["name"],sku_name=selected["name"],sbomCode=selected_code,
        attributes=selected.get("gbomAttrList",[]),major_specifications=specifics,
        specifications=all_specs,grouped_parameters=(ext.get("parameterData",{}).get("list") or {}).get("data",[]),limitations="仅对应本条商城商品及所列 SKU；不可外推其他配置。")
    # Detail HTML includes footnotes; retain those when present, not just marketing headlines.
    detail_html=detail.get("querySkuPicDetailResp",{}).get("detail") or ext.get("detailsData",{}).get("data","")
    if isinstance(detail_html,str):facts["detail_text_with_conditions"]=plain(detail_html)[:40000]
    needs=(task.get("brief_analysis") or {}).get("commercial_requests",[])
    categories={n["category"] for n in needs}
    if not categories:
        categories={r.get("category") for r in ((task.get("brief_analysis") or {}).get("retrieval_plan") or {}).get("facts",[])} & {"price","promotion"}
    if categories:
        fields={"price":("price","priceMode","estPriceFlag"),"promotion":("benefitInfos","benefitPointList","sbomCouponInfos","subsidyActivity","timerPromInfo","governmentSubsidyRel")}
        facts["commercial_snapshot"]={kind:{key:selected.get(key) for key in fields[kind]} for kind in categories}
        facts["commercial_conditions"]=dict(channel=display.get("carrierName"),sku_name=selected["name"],collected_at=db.now(),
            region="未选择具体地区",eligibility="未验证用户资格",usage="页面快照；预估价不是统一成交价或门店报价。缺少活动期、资格或使用条件的优惠不能视为已支持。")
    photos=selected.get("groupPhotoList",[])
    return dict(display=display,sku=selected,facts=facts,photos=photos,api_url=api_url,page_url=url,retrieval_method=method,retrieved_url=retrieved_url)


async def supplement(task,need_facts=False,minimum_images=1):
    try:
        async with asyncio.timeout(100):
            return await _supplement(task,need_facts,minimum_images)
    except (httpx.HTTPError,TimeoutError,ValueError,KeyError,TypeError,AttributeError) as exc:
        raise ServiceError("华为商城商品资料暂不可读取或格式已变化；未采用不完整内容") from exc


async def _supplement(task,need_facts,minimum_images):
    urls=await candidate_urls(task)
    if not urls:raise ServiceError("未找到当前型号已核对的商城商品链接，请补充商品资料")
    failures=[]
    async with httpx.AsyncClient(timeout=18,trust_env=False,follow_redirects=False,
            headers={"Origin":"https://www.vmall.com","Referer":"https://www.vmall.com/","User-Agent":"Mozilla/5.0"}) as client:
        data=None
        for url in urls:
            try:data=await read_product(client,url,task);break
            except (ServiceError,httpx.HTTPError,ValueError,KeyError,TypeError) as exc:failures.append(type(exc).__name__)
        if data is None:raise ServiceError("商城页面未能返回匹配型号、版本和配置的完整资料")
        raw_json=json.dumps(data['facts'],ensure_ascii=False,indent=2)
        text=evidence_text(data['facts'])
        sid="V"+short_id(data["api_url"]+text)
        sources=[dict(id=sid,title="华为商城商品及 SKU 资料",path=data["page_url"],url=data["page_url"],
            api_url=data["api_url"],retrieval_method=data["retrieval_method"],retrieved_url=data["retrieved_url"],text=text,raw_json=raw_json,text_view='decoded_json_values',retrieved_at=db.now(),knowledge_source="vmall",
            sku=str(data["sku"]["sbomCode"]),response_sha256=hashlib.sha256(text.encode()).hexdigest())] if need_facts else []
        images=[];known={im.get("sha256") for im in task["package"].get("images",[]) if im.get("sha256")}
        needed=max(0,min(6,minimum_images-len([im for im in task["package"].get("images",[]) if im.get("visual_checked") and im.get("usable",True)])))
        for photo in data["photos"][:10]:
            if len(images)>=needed:break
            url=photo_url(photo)
            if not url:continue
            try:
                body,final=await fetch(client,url,IMAGE_HOSTS,10_000_000)
                digest=hashlib.sha256(body).hexdigest()
                if digest in known:continue
                with Image.open(io.BytesIO(body)) as im:
                    width,height=im.size;fmt=im.format
                    if width*height>40_000_000 or min(width,height)<200:continue
                    im.verify()
                mime={"PNG":"image/png","JPEG":"image/jpeg","WEBP":"image/webp"}.get(fmt)
                if not mime:continue
            except (ServiceError,httpx.HTTPError,OSError,ValueError,Image.DecompressionBombError):continue
            iid=short_id(data["page_url"]+digest)
            (ASSETS/iid).write_bytes(body);known.add(digest)
            images.append(dict(id=iid,name=photo["photoName"],model=data["display"]["name"],
                description=data["sku"]["name"]+"：商城官方商品图，画面待核验",purpose="补充当前平台配图",
                source=data["page_url"],source_url=final,sku=str(data["sku"]["sbomCode"]),knowledge_source="vmall",
                width=width,height=height,mime=mime,sha256=digest,url="/api/assets/"+iid,model_verified=True,visual_checked=False))
        return dict(sources=sources,images=images,audit=dict(source="vmall",at=db.now(),status="read",
            page_url=data["page_url"],api_url=data["api_url"],retrieval_method=data["retrieval_method"],retrieved_url=data["retrieved_url"],sku=str(data["sku"]["sbomCode"]),
            source_ids=[s["id"] for s in sources],image_ids=[im["id"] for im in images],failed_candidates=len(failures)))
