"""Strict model output decoding and private failure diagnostics; no input coercion."""
import json
import re
import uuid
from pathlib import Path
from pydantic import ValidationError
from .settings import DATA

LABELS={"Review":"内容核验","AssetSelection":"图片筛选","Plan":"内容规划","Document":"文案生成",
    "RetrievalFacts":"事实提取","ParsingResult":"需求解析","AudienceInsight":"受众分析","StrategyResult":"策略制定"}


class InvalidOutput(ValueError):
    def __init__(self,kind,detail,content="",finish_reason=None,usage=None):
        super().__init__(kind);self.kind=kind;self.detail=detail;self.content=content
        self.finish_reason=finish_reason;self.usage=usage or {}


def decode(data,schema):
    if not isinstance(data,dict):raise InvalidOutput("envelope","响应不是对象")
    choices=data.get("choices")
    if not isinstance(choices,list) or not choices or not isinstance(choices[0],dict):
        raise InvalidOutput("envelope","响应缺少 choices[0]")
    choice=choices[0];finish=choice.get("finish_reason");usage=data.get("usage",{})
    message=choice.get("message")
    if not isinstance(message,dict):raise InvalidOutput("envelope","响应缺少 message",finish_reason=finish,usage=usage)
    content=message.get("content")
    if isinstance(content,list):
        content="".join(part.get("text","") for part in content if isinstance(part,dict)
            and part.get("type") in ("text","output_text") and isinstance(part.get("text"),str))
    if not isinstance(content,str):content=""
    if finish in ("length","max_tokens","max_output_tokens"):
        raise InvalidOutput("truncated","模型达到输出上限，不能采用被截断结果",content,finish,usage)
    if finish in ("content_filter","refusal") or message.get("refusal"):
        raise InvalidOutput("refusal","模型未完成本次输出",content,finish,usage)
    if not content.strip():raise InvalidOutput("empty_content","模型未返回可读取的文本",content,finish,usage)
    text=content.strip().lstrip("\ufeff")
    fence=chr(96)*3
    match=re.fullmatch(fence+r"(?:json)?\s*(.*?)\s*"+fence,text,re.S|re.I)
    if match:text=match[1]
    try:value=json.loads(text)
    except (ValueError,TypeError) as exc:
        detail=dict(message="响应不是完整 JSON",line=getattr(exc,"lineno",None),column=getattr(exc,"colno",None))
        raise InvalidOutput("invalid_json",detail,content,finish,usage) from exc
    try:return schema.model_validate(value).model_dump()
    except ValidationError as exc:
        errors=[]
        for error in exc.errors(include_input=False,include_url=False):
            item={key:error[key] for key in ("type","loc","msg") if key in error}
            if error.get("ctx"):item["context"]={key:str(v)[:500] for key,v in error["ctx"].items()}
            errors.append(item)
        raise InvalidOutput("schema",errors,content,finish,usage) from exc


def feedback(error,schema):
    if error.kind in ("truncated","empty_content"):
        return "上一响应被截断或没有最终文本。本次输出预算已增加。请直接输出完整、简洁的最终 JSON，不输出推理过程；不要省略必填字段，也不要截断。"
    return ("上一响应未通过本地严格校验。请根据下面的具体错误修正，并重新输出一个完整 JSON 对象；"
        "保持原证据与内容边界，不添加新事实，不改用户约束，不调用工具。"
        "\n校验错误："+json.dumps(error.detail,ensure_ascii=False,default=str)[:5000]
        +"\n尤其检查枚举值、必填字段、布尔值和列表类型；合法取值以原 JSON Schema 为准。")


def save_failure(model,schema,attempts):
    identifier=uuid.uuid4().hex[:20]
    folder=DATA/"llm_diagnostics"
    try:
        folder.mkdir(parents=True,exist_ok=True)
        # No API key, HTTP headers, input payload or image base64 is saved.
        content=dict(id=identifier,model=model,schema=schema.__name__,attempts=attempts)
        (folder/(identifier+".json")).write_text(json.dumps(content,ensure_ascii=False,indent=2,default=str),encoding="utf-8")
    except OSError:return None
    return identifier


def describe(error,schema,identifier):
    label=LABELS.get(schema.__name__,schema.__name__)
    if error.kind=="truncated":reason="两次响应均未形成完整结果，最后一次达到输出上限"
    elif error.kind=="empty_content":reason="两次尝试后仍未返回最终文本"
    elif error.kind=="invalid_json":reason="两次尝试后仍不是完整 JSON"
    elif error.kind=="refusal":reason="模型未完成本次核验或生成"
    elif error.kind=="schema":
        entries=error.detail[:2]
        reason="响应字段未通过校验："+"；".join(".".join(map(str,e["loc"]))+" "+e["msg"] for e in entries)
    else:reason="响应缺少完整的模型结果"
    return label+"失败："+reason+"。已保留中间结果。"+("诊断编号："+identifier if identifier else "")
