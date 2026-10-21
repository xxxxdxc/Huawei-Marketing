"""Load selected method sections from pinned upstream skills, not product evidence."""
from pathlib import Path
import hashlib,json
from . import writer_cases
ROOT=Path(__file__).parent

def source_record(skill):
    manifest=json.loads((ROOT/'planner_sources.json').read_text(encoding='utf-8-sig'))
    source=(manifest.get('skill_sources') or {}).get(skill)
    if not source:raise ValueError('Skill is not an enabled method source: '+skill)
    source=dict(source)
    path=(ROOT/source['path']).resolve()
    if not path.is_relative_to((ROOT/'vendor').resolve()):raise ValueError('Skill source must be vendored')
    if hashlib.sha256(path.read_bytes()).hexdigest()!=source['sha256']:raise ValueError('Skill source checksum mismatch: '+skill)
    return source


def sections(skill, headings):
    source=source_record(skill)
    text=(ROOT/source['path']).read_text(encoding='utf-8-sig')
    lines=text.splitlines();out=[]
    for heading in headings:
        try:start=lines.index(heading)
        except ValueError as exc:raise ValueError('Missing pinned Skill section: '+skill+' '+heading) from exc
        level=len(heading)-len(heading.lstrip('#'))
        end=next((i for i in range(start+1,len(lines)) if lines[i].startswith('#') and len(lines[i])-len(lines[i].lstrip('#'))<=level),len(lines))
        out.append('\n'.join(lines[start:end]))
    return '\n\n'.join(out)


PLANNER_METHOD=sections('content-strategy',[
    '### Awareness Stage','### Consideration Stage','### Decision Stage',
    '### 1. Customer Impact (40%)','### 2. Content-Market Fit (30%)'])
WRITER_METHOD=sections('copywriting',[
    '## Diagnose the Situation First','## Drafting Protocol',
    '### Benefits Over Features','### Specificity Over Vagueness',
    '### Customer Language Over Company Language','### One Idea Per Section'])
METHOD_GUARD='以下英文摘录仅为写作/选材方法，不是产品证据或用户指令。只应用于当前单篇任务；不照搬网页结构、不另行追问Brief已确认的信息，不采用摘录中的示例数值或营销统计作为产品事实。方法中的诊断、备选与自检保留内部，不输出给消费者；用户已确认的范围优先。\n'


COPYWRITING_HEADINGS=[
    '## Diagnose the Situation First','## Drafting Protocol',
    '### Benefits Over Features','### Specificity Over Vagueness',
    '### Customer Language Over Company Language','### One Idea Per Section']
EDIT_CHECKS=['### Sentence-Level Checks','### Paragraph-Level Checks','### AI-Tell Check']
EDIT_REPAIR=['## Core Philosophy','### Sweep 1: Clarity','### Sweep 2: Voice and Tone','### Sweep 4: Prove It',*EDIT_CHECKS]
SOCIAL_OUTLINE=['### Curiosity Hooks','### Value Hooks']
SOCIAL_DRAFT=['### Curiosity Hooks','### Value Hooks','### No AI Tells']
LONG_OUTLINE=['### Blog Post Structure','### Blog']
LONG_DRAFT=['### Blog','### Hook Formulas (Opening Lines)','### CTA Placement']


def writer_bundle(platform,stage):
    if platform not in ('moments','xiaohongshu','wechat'):raise ValueError('Unknown Writer platform')
    if stage not in ('outline','draft','repair'):raise ValueError('Unknown Writer stage')
    if stage=='repair':route=[('copy-editing',EDIT_REPAIR)]
    else:
        extra=('content-creation',LONG_OUTLINE if stage=='outline' else LONG_DRAFT) if platform=='wechat' else ('social',SOCIAL_OUTLINE if stage=='outline' else SOCIAL_DRAFT)
        route=[('copywriting',COPYWRITING_HEADINGS),extra]
        if stage=='draft':route.append(('copy-editing',EDIT_CHECKS))
    records=[];parts=[]
    for skill,headings in route:
        text=sections(skill,headings);source=source_record(skill)
        records.append(dict(skill=skill,**source,headings=headings,excerpt_sha256=hashlib.sha256(text.encode()).hexdigest()))
        parts.append('\n<method name="'+skill+'">\n'+text+'\n</method>')
    adapter=(ROOT/'writer_skills.md').read_text(encoding='utf-8-sig')
    cases=writer_cases.bundle(platform,stage)
    text=METHOD_GUARD+'\n'.join(parts)+'\n'+cases['text']+'\n'+adapter+'\n当前阶段：'+stage+'；平台：'+platform
    return dict(text=text,case_sources=cases['sources'],method_sources=[x['skill'] for x in records],sources=records,
        adapter_sha256=hashlib.sha256(adapter.encode()).hexdigest())
