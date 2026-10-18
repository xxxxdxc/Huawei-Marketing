"""Read-only ZIP adapter reusing the same scoped retrieval/image checks as ima."""
import hashlib
import re
import stat
import zipfile
from pathlib import Path, PurePosixPath
from .clients import Ima, ServiceError, short_id


class LocalZip(Ima):
    def __init__(self, archive):
        super().__init__()
        self.archive=Path(archive).expanduser().resolve()
        if not self.archive.is_file() or self.archive.suffix.lower()!=".zip":raise ServiceError("本地知识库 ZIP 不存在，请检查资料源设置")
        before=self.archive.stat();self.signature=(before.st_size,before.st_mtime_ns)
        with self.archive.open("rb") as f:self.sha256=hashlib.file_digest(f,"sha256").hexdigest()
        self.prefix="local:"+self.sha256+":"
        self.files={};self.children={};names=[]
        try:
            with zipfile.ZipFile(self.archive) as z:
                entries=z.infolist()
                if len(entries)>20000:raise ServiceError("本地 ZIP 条目过多，请使用项目知识库压缩包")
                for i in entries:
                    name=i.filename
                    if "\\" in name or name.startswith("/") or ".." in PurePosixPath(name).parts or stat.S_ISLNK(i.external_attr>>16):raise ServiceError("本地 ZIP 含不安全路径或链接，未读取")
                    if not i.is_dir():names.append(name)
                p1=[n.split("/P1-",1)[0]+"/" for n in names if "/P1-" in n]
                if p1:
                    roots=set(p1)
                    if len(roots)!=1:raise ServiceError("本地 ZIP 有多个产品库根目录，无法确定来源")
                    self.root=next(iter(roots))
                elif any(n.startswith("P1-") for n in names):self.root=""
                else:raise ServiceError("本地 ZIP 中没有 P1 产品参数库")
                for i in entries:
                    if i.is_dir() or not i.filename.startswith(self.root):continue
                    relative=i.filename[len(self.root):]
                    if relative in self.files:raise ServiceError("本地 ZIP 有重复文件路径，无法确定原文")
                    self.files[relative]=i.filename
                    parts=relative.split("/")
                    for depth in range(len(parts)):
                        parent="/".join(parts[:depth]);child="/".join(parts[:depth+1]);folder=depth<len(parts)-1
                        self.children.setdefault(parent,{})[parts[depth]]=dict(title=parts[depth],media_type=99 if folder else 9 if Path(parts[-1]).suffix.lower() in (".png",".jpg",".jpeg",".webp") else 20,media_id=self.prefix+child)
        except (zipfile.BadZipFile,OSError) as e:raise ServiceError("无法读取本地知识库 ZIP") from e
        self._unchanged()

    def _unchanged(self):
        try:s=self.archive.stat()
        except OSError as e:raise ServiceError("本地知识库 ZIP 已不可用") from e
        if (s.st_size,s.st_mtime_ns)!=self.signature:raise ServiceError("本地知识库 ZIP 已变化，请重新分析需求后确认")

    def snapshot(self):
        return dict(kind="local_zip",archive_name=self.archive.name,archive_root=self.root.rstrip("/"),sha256=self.sha256,file_count=len(self.files),size_bytes=self.signature[0],search_mode="local_keyword")

    def _relative(self, token):
        if not token.startswith(self.prefix):raise ServiceError("资料标识不属于当前本地 ZIP 版本")
        return token[len(self.prefix):]

    async def knowledge_base(self):return self.prefix

    async def listing(self, folder=None):
        self._unchanged();relative=self._relative(folder) if folder else ""
        return list(self.children.get(relative,{}).values())

    async def fetch_media(self, media_id):
        self._unchanged();relative=self._relative(media_id)
        if relative not in self.files:raise ServiceError("本地知识库缺少指定原文或图片")
        try:
            with zipfile.ZipFile(self.archive) as z:
                i=z.getinfo(self.files[relative])
                if i.file_size>20*1024*1024:raise ServiceError("本地单项资料超过 20 MB，未读取")
                data=z.read(i)
        except (OSError,zipfile.BadZipFile,RuntimeError) as e:raise ServiceError("本地知识库资料读取或完整性检查失败") from e
        self._unchanged();return data

    async def catalog(self, refresh=False):
        self._unchanged();products=[]
        p1=next((x for x in await self.listing() if x["title"].startswith("P1-") and x["media_type"]==99),None)
        if not p1:raise ServiceError("本地 ZIP 没有产品参数目录")
        for cat in await self.listing(p1["media_id"]):
            if cat["media_type"]!=99 or not cat["title"].startswith(("01-","02-","03-")):continue
            for x in await self.listing(cat["media_id"]):
                if x["media_type"]!=99:continue
                path=f"P1-产品参数库/{cat['title']}/{x['title']}"
                if path+"/产品事实.md" not in self.files and path+"/article.md" not in self.files:continue
                products.append(dict(id=short_id(path),name=x["title"],category=cat["title"].split("-",1)[-1],path=path,folder=x["media_id"]))
        if not products:raise ServiceError("本地 ZIP 产品目录为空")
        return products

    async def call(self, route, body):
        if route!="search_knowledge":raise ServiceError("本地模式不支持此 ima 远程操作")
        self._unchanged();query=body.get("query","")
        norm=lambda s:re.sub(r"\s+","",s).lower()
        products=await self.catalog()
        selected=[p for p in products if norm(p["name"]) in norm(query)]
        if selected:
            longest=max(len(p["name"]) for p in selected);selected=[p for p in selected if len(p["name"])==longest]
        roots=[p["path"]+"/" for p in selected]
        hits=[]
        for relative in self.files:
            if roots and not any(relative.startswith(root) for root in roots):continue
            if Path(relative).suffix.lower() not in (".md",".csv"):continue
            if not roots and norm(query) not in norm(relative):continue
            hits.append(dict(title=Path(relative).name,path=relative,media_id=self.prefix+relative))
        return dict(info_list=hits,search_mode="local_keyword",is_end=True)

    async def retrieve(self, product, brief):
        self._unchanged()
        package=await super().retrieve(product,brief)
        self._unchanged();package["knowledge_source"]="local_zip";package["knowledge_snapshot"]=self.snapshot()
        for source in package["sources"]:
            source.update(knowledge_source="local_zip",archive_sha256=self.sha256)
        for image in package["images"]:image["knowledge_source"]="local_zip"
        return package
