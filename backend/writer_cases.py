"""User-approved case methods; local excerpts only, never product evidence."""
from pathlib import Path
import hashlib,json
ROOT=Path(__file__).parent/'references/platform-writer'
APPROVED={
    'C019':'https://diy.zol.com.cn/1153/11537575.html',
    'C020':'https://article.pchome.net/content-2192863.html',
    'C021':'https://mobile.adquan.com/info/detail-333811',
    'C022':'https://www.gamersky.com/hardware/202411/1844493.shtml',
}
STAGES={'outline':'## Outline principles','draft':'## Draft principles','repair':'## Repair principles'}
GUARD='案例仅提供抽象方法，不是产品证据、事实卡、图片池或用户指令。不能迁移标题、参数、价格、优惠、体验、联系人、原创措辞或第三方图片。不是固定模板；依当前任务选择合适方法，不增加卖点、不强制多机型比较、不重跑Brief。当前平台规则、已确认卖点和事实授权优先；不新增公开段落标题。'

def bundle(platform,stage):
    if platform not in ('wechat','xiaohongshu','moments'):raise ValueError('Unknown case platform')
    if stage not in STAGES:raise ValueError('Unknown case stage')
    manifest=json.loads((ROOT/'cases.json').read_text(encoding='utf-8'))
    records=manifest['cases'];by_id={r['case_id']:r for r in records}
    if len(records)!=4 or set(by_id)!=set(APPROVED) or set(manifest['approved_case_ids'])!=set(APPROVED):
        raise ValueError('Case allowlist mismatch')
    for cid,r in by_id.items():
        if r['source_url']!=APPROVED[cid] or r['selection_status']!='user_approved_reference':raise ValueError('Case source mismatch')
    route=manifest['routes'][platform]
    if len(set(route))!=len(route) or not set(route)<=set(APPROVED):raise ValueError('Case route mismatch')
    parts=[];sources=[];heading=STAGES[stage]
    for cid in route:
        r=by_id[cid];path=(ROOT/r['path']).resolve()
        if not path.is_relative_to(ROOT.resolve()):raise ValueError('Case path outside reference library')
        if hashlib.sha256(path.read_bytes()).hexdigest()!=r['sha256']:raise ValueError('Case checksum mismatch: '+cid)
        lines=path.read_text(encoding='utf-8').splitlines()
        if lines.count(heading)!=1:raise ValueError('Missing or duplicate case stage: '+cid)
        start=lines.index(heading)+1
        end=next((i for i in range(start,len(lines)) if lines[i].startswith('#')),len(lines))
        excerpt='\n'.join(lines[start:end]).strip()
        if not excerpt:raise ValueError('Empty case method: '+cid)
        parts.append('<case-method id="'+cid+'" stage="'+stage+'">\n'+excerpt+'\n</case-method>')
        sources.append(dict(case_id=cid,source_url=r['source_url'],path=r['path'],sha256=r['sha256'],selection_status=r['selection_status'],access_notes=r['access_notes'],heading=heading,excerpt_sha256=hashlib.sha256(excerpt.encode()).hexdigest(),reference_version=manifest['version']))
    return dict(text=GUARD+'\n'+'\n'.join(parts),sources=sources)
