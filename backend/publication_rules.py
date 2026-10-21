"""Evidence stays internal; public copy uses concise, accurate scope."""
import re

VERSION = "natural_copy_v1"
GENERIC_PATTERNS = (
    r"(?:实际)?(?:尺寸|重量|厚度)[^。！？\n]{0,32}(?:因|随)[^。！？\n]{0,60}(?:制造|工艺|测量)",
    r"(?:实际)?(?:尺寸和重量|重量和尺寸)[^。！？\n]{0,20}(?:因|随)配置",
    r"(?:实际)?(?:尺寸|重量|厚度)[^。！？\n]{0,16}(?:因|随)配置(?:而)?(?:异|变化|不同|有所差异|有所不同)",
    r"(?:具体)?以(?:实际(?:购买|销售|所购)?|所购|购买|销售)(?:的)?(?:版本|配置|实物)为准",
)
CORE = """证据与对外表达必须分开。Fact.conditions、原文摘录和候选conditions完整保留在内部，不要求逐字进入推文。
尺寸重量因制造工艺/测量方法而异、泛泛的“以实际配置/购买版本为准”等属于通用说明，留在内部依据区，不在新推文正文、标题、导语、图片说明、标签或CTA追加。
会改变结论的必要条件不能丢失，应融入简短自然表达：原文为近似值则保留“约”；功能仅适用于某个版本则将该具体版本直接写进功能句。不能去掉版本后泛称全型号都支持；不能把约、最高、典型值改成精确或普遍承诺。测试场景、活动地区/时间、适配条件如影响所用结论，须具体简洁说明；无法准确简洁表达则省略该项结论，改用本段已授权的其他事实，不能以一句通用免责声明代替。
不得将普通“因测量方式不同而变化”的说明写成一段营销正文，也不把缺证、取证过程或内部策划备注写给消费者。"""
PLANNER = CORE + """
heading仅为工作人员的内部阅读提示，不是对外段落标题；purpose写内容目标，不要求Writer照抄证据注释。
规划时优先选能自然表达且回应需求的事实。每段推进一个新问题；不要为总结、咨询或到店引导额外堆段落。最终行动引导只放根级cta，不再单列cta段落或在导语/正文反复铺同一句引导。"""
WRITER = CORE + """
Paragraph.heading仅作内部定位提示，保留字段，不将它复制成正文第一句或对外小标题；整篇title仍为对外文章标题。正文以自然段连贯展开。
最终行动引导只写在根级cta；导语、正文、图注不再重复。若旧规划已包含纯CTA段，保留section_id及配图锚点，可将该段text留空，由根级cta统一承载；有其他事实时只写该事实，不更改已确认的段落顺序、图片或事实范围。"""
REVIEWER = """paragraphs[].heading是内部定位提示，不是对外文案；可用它定位问题，但不得把其中的文字当作已发布标题或要求Writer将它写进正文。
""" + CORE + """
当publication_policy_version为natural_copy_v1，检查是否仍出现通用免责声明、内部提示泄露或重复CTA；这是可改写的platform问题，repairable=true。必要版本/配置/测试条件缺失仍应按事实问题处理，不能为观感放过错误泛化。
当publication_policy_version未设置，旧稿只核对事实，不因既有通用说明或重复CTA要求额外改写；用户未要求重写的历史正文保持原样。
省略通用测量免责声明不等于省略必要条件，不因此要求补回整段免责声明；要求最短、具体且有原文支持的限定。"""
REPAIR = WRITER + """
只处理本轮问题，不给其他段落补通用免责声明。恢复的是影响结论的必要条件，而不是原文每一句防御性措辞；必要时删除该项无依据结论。"""

def generic_notes(text):
    return list(dict.fromkeys(m.group() for pattern in GENERIC_PATTERNS for m in re.finditer(pattern,text)))

def condition_guidance(facts):
    """Hints only. Unclassified/mixed conditions remain substantive; source is intact."""
    notes=[]
    substantive=re.compile(r"Windows|Linux|Harmony|仅|需|标准版|柔光版|账号|设备|地区|活动|测试|最高|典型|\d",re.I)
    for fact in facts:
        parts=[p.strip() for p in re.split(r"[；;\n]+",fact.get("conditions","")) if p.strip()]
        internal=[];required=[]
        for part in parts:
            (internal if generic_notes(part) and not substantive.search(part) else required).append(part)
        notes.append(dict(fact_id=fact["id"],internal_notes=internal,meaningful_conditions=required))
    return notes

def reader_text(document):
    return "\n".join([document["title"],document["lead"],
        *[value for p in document["paragraphs"] for value in (p["text"],p["caption"])],
        document["cta"],*document["tags"]])

def style_issues(document, voice=False):
    issues=[]
    for note in generic_notes(reader_text(document)):
        issues.append(dict(category="platform",location="全文",detail="通用证据说明应留在内部依据区，请自然改写并保留必要限定："+note,severity="error",repairable=True))
    for paragraph in document["paragraphs"]:
        heading=paragraph["heading"].strip()
        if heading and re.match(re.escape(heading)+r"\s*(?:[:：]|\r?\n)",paragraph["text"].lstrip()):
            issues.append(dict(category="platform",location=heading,detail="内部阅读提示被复制进正文，请移除对外段落标题，保留正文与定位字段",severity="error",repairable=True))
    cta=re.sub(r"\W","",document["cta"]).lower()
    if cta:
        for p in document["paragraphs"]:
            if any(cta in re.sub(r"\W","",p[k]).lower() for k in ("text","caption")):
                issues.append(dict(category="platform",location=p["heading"] or "正文段落",detail="行动引导与根级cta重复，正文不再重复CTA，保留段落及配图锚点",severity="error",repairable=True))
        if cta in re.sub(r"\W","",document["lead"]).lower():
            issues.append(dict(category="platform",location="导语",detail="导语与根级cta重复，行动引导只出现一次",severity="error",repairable=True))
    if voice:issues.extend(voice_issues(document))
    return issues


# Narrow, auditable leak patterns. Semantic promises still require independent review.
VOICE_PATTERNS=(
    ('编排旁白',r'(?:下面|接下来)[^。！？\n]{0,18}(?:按这个顺序|按以下顺序|依次来看|依次看|逐一介绍)'),
    ('资料播报',r'(?:目前|当前)(?:能|可以)(?:确认|证实)的是|(?:资料|包装清单|原文)(?:里|中)?(?:列有|列出|记载|显示|写着|提到|表明)|这是机身本身的规格'),
    ('到店核对',r'(?:到店|在店里|去店里|在门店|到门店)[^。！？\n]{0,45}(?:问清|确认|核对|判断|试一试|试试|感受|拿上手|体验|试用|试触屏|试触控)'),
    ('到店核对',r'(?:建议|可以|适合|不妨|值得)[^。！？\n]{0,35}(?:到店|在店里|去店里|到门店|在门店)'),
    ('到店核对',r'(?:欢迎|来|前往|走进)[^。！？\n]{0,12}(?:到店|门店)[^。！？\n]{0,25}(?:体验|咨询|试|感受)'),
)


def voice_issues(document):
    issues=[]
    # A root CTA is intentionally excluded; heading is internal, never published.
    fields=[('标题',document['title']),('导语',document['lead'])]
    fields.extend((p['heading'] or '正文段落',p[k]) for p in document['paragraphs'] for k in ('text','caption'))
    fields.extend(('标签',tag) for tag in document['tags'])
    # CTA may invite a visit but must not become a research/status report.
    for label,pattern in VOICE_PATTERNS:
        if label!='到店核对' and re.search(pattern,document['cta']):
            issues.append(dict(category='platform',location='行动引导',detail=label+'泄露到行动引导，请自然改写',severity='error',repairable=True))
    for location,text in fields:
        for label,pattern in VOICE_PATTERNS:
            match=re.search(pattern,text)
            if match:
                issues.append(dict(category='platform',location=location,
                    detail=label+'泄露到宣传内容：'+match.group()+'。自然表达已知事实，删除核对/编排话语；不增加无依据收益，必要限定保留。',
                    severity='error',repairable=True))
    return issues
