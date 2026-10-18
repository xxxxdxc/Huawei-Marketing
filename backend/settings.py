import base64, ctypes, json, os, sys
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
DATA = Path(os.getenv("HUAWEI_DATA_DIR", str(ROOT / ".local"))).resolve()
DATA.mkdir(parents=True, exist_ok=True)
ASSETS = DATA / "assets"
ASSETS.mkdir(exist_ok=True)
DEFAULTS = {"base_url": "https://api.openai-next.com/v1", "writer_model": "claude-sonnet-5-5", "reviewer_model": "gpt-6.1-sol", "vision": True, "knowledge_source": "ima", "local_knowledge_path": str(ROOT.parent / "华为PC知识库.zip")}

def user_env(name):
    if os.getenv(name): return os.environ[name]
    if sys.platform == "win32":
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
                return winreg.QueryValueEx(key, name)[0]
        except OSError: pass
    return ""

class Blob(ctypes.Structure):
    _fields_ = [("cbData", ctypes.c_ulong), ("pbData", ctypes.POINTER(ctypes.c_ubyte))]

def protect(value, decrypt=False):
    if sys.platform != "win32": return value
    buf = ctypes.create_string_buffer(value)
    src = Blob(len(value), ctypes.cast(buf, ctypes.POINTER(ctypes.c_ubyte)))
    dst = Blob()
    crypt = ctypes.windll.crypt32
    if decrypt: ok = crypt.CryptUnprotectData(ctypes.byref(src), None, None, None, None, 1, ctypes.byref(dst))
    else: ok = crypt.CryptProtectData(ctypes.byref(src), "Huawei Marketing", None, None, None, 1, ctypes.byref(dst))
    if not ok: raise RuntimeError("无法保护本机凭证")
    try: return ctypes.string_at(dst.pbData, dst.cbData)
    finally: ctypes.windll.kernel32.LocalFree(dst.pbData)

def api_key(role="writer"):
    if role not in ("writer", "reviewer"):
        raise ValueError("未知模型凭证角色")
    env_name = "HUAWEI_LLM_REVIEWER_API_KEY" if role == "reviewer" else "HUAWEI_LLM_API_KEY"
    env = user_env(env_name)
    if env: return env
    path = DATA / ("reviewer_credential.bin" if role == "reviewer" else "credential.bin")
    if path.exists():
        return protect(path.read_bytes(), decrypt=True).decode()
    # Preserve compatibility for existing single-key deployments.
    return api_key("writer") if role == "reviewer" else ""


def get_settings():
    p = DATA / "settings.json"
    d = DEFAULTS | (json.loads(p.read_text(encoding="utf-8")) if p.exists() else {})
    d["base_url"] = os.getenv("HUAWEI_LLM_BASE_URL", d["base_url"])
    return d

def save_settings(d, key=None, reviewer_key=None):
    p = urlparse(d["base_url"])
    if p.scheme != "https" or not p.hostname or p.username or p.password or p.query or p.fragment:
        raise ValueError("API 地址必须是无内嵌凭证、查询参数的 HTTPS 地址")
    if d.get("knowledge_source","ima") not in ("ima","local_zip"):raise ValueError("资料源必须为 ima 或 local_zip")
    if d.get("knowledge_source")=="local_zip":
        archive=Path(d.get("local_knowledge_path","")).expanduser().resolve()
        if archive.suffix.lower()!=".zip" or not archive.is_file():raise ValueError("请选择存在的本地知识库 ZIP")
        d["local_knowledge_path"]=str(archive)
    if not d["writer_model"].strip() or not d["reviewer_model"].strip(): raise ValueError("请填写模型名称")
    (DATA / "settings.json").write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    for filename, secret in (("credential.bin", key), ("reviewer_credential.bin", reviewer_key)):
        if secret:
            p = DATA / filename
            p.write_bytes(protect(secret.strip().encode()))
            if sys.platform != "win32": p.chmod(0o600)


def public_settings():
    return get_settings() | {"has_key": bool(api_key("writer")), "has_writer_key": bool(api_key("writer")), "has_reviewer_key": bool(api_key("reviewer")), "reviewer_uses_writer_key": not bool(user_env("HUAWEI_LLM_REVIEWER_API_KEY") or (DATA / "reviewer_credential.bin").exists()), "local_archive_ready": Path(get_settings()["local_knowledge_path"]).is_file(), "ima_ready": bool(user_env("IMA_OPENAPI_CLIENTID") and user_env("IMA_OPENAPI_APIKEY")), "credential_storage": "Windows DPAPI" if sys.platform == "win32" else "本机权限为 600 的凭证文件"}
