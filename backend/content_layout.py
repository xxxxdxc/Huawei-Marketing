"""One section-based layout contract for preview, review and export."""
import copy


def default_position(platform, image_id, index):
    if not image_id:return dict(kind='none',order=None)
    if platform=='wechat':return dict(kind='after_section',order=None)
    return dict(kind='carousel' if platform=='xiaohongshu' else 'grid',order=index)


def effective_layout(plan, platform, document=None):
    paragraphs={p['section_id']:p for p in (document or {}).get('paragraphs',[])}
    slots=[];index=0
    for section in plan['sections']:
        paragraph=paragraphs.get(section['id'])
        image_id=paragraph['image_id'] if paragraph is not None else section['image_id']
        if not image_id:continue
        index+=1
        position=section.get('image_position') or default_position(platform,image_id,index)
        if position['kind']=='none':position=default_position(platform,image_id,index)
        slots.append(dict(section_id=section['id'],image_id=image_id,kind=position['kind'],order=position.get('order') or index))
    if platform!='wechat':slots.sort(key=lambda x:x['order'])
    return dict(platform=platform,slots=slots,cover_section_id=slots[0]['section_id'] if slots and platform=='xiaohongshu' else None)


def validate_layout(plan, platform):
    orders=[]
    for section in plan['sections']:
        position=section.get('image_position')
        if not position:continue
        kind=position['kind'];order=position.get('order')
        if not section['image_id']:
            if kind!='none' or order is not None:raise ValueError('无配图段落不能占用图片位置')
        elif platform=='wechat':
            if kind not in ('before_section','after_section') or order is not None:raise ValueError('公众号图片位置必须为段前或段后')
        else:
            expected='carousel' if platform=='xiaohongshu' else 'grid'
            if kind!=expected or type(order) is not int or order<1:raise ValueError('图片序号或平台布局不合法')
            orders.append(order)
    if orders and sorted(orders)!=list(range(1,len(orders)+1)):raise ValueError('图片展示序号必须从1连续排列且不可重复')
