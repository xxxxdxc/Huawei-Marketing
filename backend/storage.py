import hashlib, json, sqlite3, threading, uuid
from datetime import datetime, timezone
from contextlib import contextmanager
from .settings import DATA

LOCK = threading.RLock()
DB = DATA / "tasks.sqlite3"

def now(): return datetime.now(timezone.utc).isoformat()
@contextmanager
def connect():
    c = sqlite3.connect(DB, timeout=10)
    try:
        c.execute("PRAGMA journal_mode=WAL")
        with c:
            yield c
    finally:
        c.close()

def init():
    with connect() as c:
        c.execute("CREATE TABLE IF NOT EXISTS tasks (id TEXT PRIMARY KEY, payload TEXT NOT NULL)")
        c.execute("CREATE TABLE IF NOT EXISTS versions (task_id TEXT, version INTEGER, note TEXT, at TEXT, payload TEXT, PRIMARY KEY(task_id,version))")
        c.execute("CREATE TABLE IF NOT EXISTS cache (key TEXT PRIMARY KEY, payload TEXT)")

def get(tid):
    with connect() as c: row = c.execute("SELECT payload FROM tasks WHERE id=?", (tid,)).fetchone()
    if not row: raise KeyError("任务不存在")
    return json.loads(row[0])

def save(task, note, expected=None):
    with LOCK, connect() as c:
        c.execute("BEGIN IMMEDIATE")
        row = c.execute("SELECT payload FROM tasks WHERE id=?", (task["id"],)).fetchone()
        old = json.loads(row[0]) if row else None
        version = old["version"] if old else 0
        if expected is not None and version != expected: raise ValueError("任务已更新，请刷新后重试")
        task["version"] = version + 1
        task["updated_at"] = now()
        raw = json.dumps(task, ensure_ascii=False)
        c.execute("INSERT OR REPLACE INTO tasks VALUES (?,?)", (task["id"], raw))
        c.execute("INSERT INTO versions VALUES (?,?,?,?,?)", (task["id"],task["version"],note,now(),raw))
    return task

def create(raw, product_id=None, platform=None, knowledge_source=None, knowledge_zip_path=None):
    t = {"id": uuid.uuid4().hex, "title": raw[:36], "raw": raw, "product_id": product_id, "platform": platform, "status": "draft", "version":0, "created_at":now(), "updated_at":now(), "brief":None, "package":None, "plan":None, "document":None, "user_image_overrides":{}, "review":None, "events":[], "error":None, "resume_status":"draft"}
    t.update(brief_analysis=None, brief_confirmation=None, brief_runs=[], dialogue=[dict(id="U1",kind="user",text=raw,at=now())], selected_product_id=product_id, selected_platform=platform)
    if knowledge_source:t["knowledge_source"]=knowledge_source
    if knowledge_zip_path:t["knowledge_zip_path"]=knowledge_zip_path
    return save(t, "创建任务")

def listing():
    with connect() as c: rows = c.execute("SELECT payload FROM tasks").fetchall()
    ts = [json.loads(r[0]) for r in rows]
    return sorted([ {k:t.get(k) for k in ("id","title","status","version","updated_at","platform")} for t in ts], key=lambda t:t["updated_at"], reverse=True)

def history(tid):
    with connect() as c: rows=c.execute("SELECT version,note,at FROM versions WHERE task_id=? ORDER BY version DESC",(tid,)).fetchall()
    return [dict(version=r[0],note=r[1],at=r[2]) for r in rows]

def snapshot(tid, version):
    with connect() as c: row=c.execute("SELECT payload FROM versions WHERE task_id=? AND version=?",(tid,version)).fetchone()
    if not row: raise KeyError("版本不存在")
    return json.loads(row[0])

def digest(t):
    data={k:t.get(k) for k in ("product_id","brief","package","plan","document")}
    if t.get("execution_scope"):data["execution_scope"]=t["execution_scope"]
    if t.get("user_image_overrides"):data["user_image_overrides"]=t["user_image_overrides"]
    if t.get("brief_analysis"):
        data["brief_analysis"]=t["brief_analysis"]
        data["brief_confirmation"]=t.get("brief_confirmation")
    if t.get("knowledge_source"):data["knowledge_source"]=t["knowledge_source"]
    if t.get("knowledge_snapshot"):data["knowledge_snapshot"]=t["knowledge_snapshot"]
    if t.get("store_marketing_version"):
        data["store_marketing"]={k:t.get(k) for k in ("store_marketing_version","store_marketing_context")}
    return hashlib.sha256(json.dumps(data,ensure_ascii=False,sort_keys=True).encode()).hexdigest()

def cache_get(key):
    with connect() as c: row=c.execute("SELECT payload FROM cache WHERE key=?",(key,)).fetchone()
    return json.loads(row[0]) if row else None

def cache_set(key, value):
    with connect() as c: c.execute("INSERT OR REPLACE INTO cache VALUES (?,?)",(key,json.dumps(value,ensure_ascii=False)))
