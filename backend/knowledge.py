"""Task-pinned data source routing. No automatic local/cloud fallback."""
from pathlib import Path
from .clients import ima as cloud_ima, ServiceError, KB_NAME
from .local_knowledge import LocalZip
from .settings import get_settings


class Knowledge:
    def __init__(self):self.local_cache={}

    def backend(self, source=None, archive_path=None):
        source=source or get_settings()["knowledge_source"]
        if source=="ima":return cloud_ima
        if source!="local_zip":raise ServiceError("未知资料源")
        path=Path(archive_path or get_settings()["local_knowledge_path"]).expanduser().resolve()
        try:stat=path.stat()
        except OSError as e:raise ServiceError("本地知识库 ZIP 不存在，请检查资料源设置") from e
        key=(str(path),stat.st_size,stat.st_mtime_ns)
        if key not in self.local_cache:
            self.local_cache={key:LocalZip(path)}
        return self.local_cache[key]

    def source_info(self, source=None, archive_path=None):
        chosen=source or get_settings()["knowledge_source"]
        if chosen=="ima":return dict(kind="ima",knowledge_base=KB_NAME)
        return self.backend(chosen,archive_path).snapshot()

    async def catalog(self, refresh=False, source=None, archive_path=None):
        return await self.backend(source,archive_path).catalog(refresh)

    async def retrieve(self, product, brief, source=None, archive_path=None):
        chosen=source or get_settings()["knowledge_source"]
        p=await self.backend(chosen,archive_path).retrieve(product,brief)
        p.setdefault("knowledge_source",chosen);p.setdefault("knowledge_snapshot",self.source_info(chosen,archive_path))
        return p

    async def catalog_for_task(self, task, verify_snapshot=False, refresh=False):
        # Tasks created before source routing always remain cloud-backed.
        source=task.get("knowledge_source","ima");path=task.get("knowledge_zip_path")
        products=await self.catalog(refresh=refresh,source=source,archive_path=path)
        snapshot=self.source_info(source,path)
        old=task.get("knowledge_snapshot") or {}
        if verify_snapshot and old.get("sha256") and old["sha256"]!=snapshot.get("sha256"):
            raise ServiceError("本地知识库 ZIP 已更新，请重新分析并确认 Brief 后检索")
        task["knowledge_snapshot"]=snapshot
        return products

    async def retrieve_for_task(self, task, product, brief):
        source=task.get("knowledge_source","ima");path=task.get("knowledge_zip_path")
        expected=(task.get("knowledge_snapshot") or {}).get("sha256")
        current=self.source_info(source,path)
        if expected and expected!=current.get("sha256"):raise ServiceError("本地 ZIP 版本已变化，请重新分析需求")
        return await self.retrieve(product,brief,source=source,archive_path=path)


knowledge=Knowledge()
