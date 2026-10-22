"""One-use, deployment-only backup restore. Disabled unless a dedicated key exists."""
import base64,copy,hashlib,hmac,io,json,os,re
from fastapi import HTTPException,Request
from PIL import Image
from . import storage as db,schemas as S
from .settings import DATA,ASSETS

async def restore(request:Request):
    key=os.getenv('HUAWEI_MAINTENANCE_KEY','')
    if len(key)<32:raise HTTPException(404,'维护通道未启用')
    if not hmac.compare_digest(request.headers.get('X-Maintenance-Key',''),key):raise HTTPException(401,'维护凭据不匹配')
    marker=DATA/'backup-restore-completed'
    if marker.exists():raise HTTPException(409,'本次备份恢复已完成，通道已关闭')
    if int(request.headers.get('content-length','0'))>40_000_000:raise HTTPException(413,'备份超过大小限制')
    body=await request.body()
    if len(body)>40_000_000:raise HTTPException(413,'备份超过大小限制')
    try:
        bundle=json.loads(body);tasks=bundle['tasks'];assets=bundle.get('assets',[])
        if not isinstance(tasks,list) or not 1<=len(tasks)<=20 or not isinstance(assets,list) or len(assets)>80:raise ValueError('备份条目数量不符合要求')
        checked=[]
        for source in tasks:
            S.TaskView.model_validate(source)
            if not re.fullmatch('[a-f0-9]{32}',source['id']):raise ValueError('任务编号无效')
        for item in assets:
            if not re.fullmatch('[a-f0-9]{16,64}',item['id']):raise ValueError('素材编号无效')
            data=base64.b64decode(item['body'],validate=True)
            if not 1<=len(data)<=10_000_000 or hashlib.sha256(data).hexdigest()!=item['sha256']:raise ValueError('素材完整性检查失败')
            with Image.open(io.BytesIO(data)) as image:
                if image.format not in ('PNG','JPEG','WEBP') or image.width*image.height>40_000_000:raise ValueError('素材格式不支持')
                image.verify()
            path=ASSETS/item['id']
            if path.exists() and hashlib.sha256(path.read_bytes()).hexdigest()!=item['sha256']:raise ValueError('已存在不同内容的素材，拒绝覆盖')
            checked.append((path,data))
    except (ValueError,KeyError,TypeError,OSError) as exc:raise HTTPException(400,'备份结构或完整性检查失败') from exc
    restored=[];skipped=[]
    with db.LOCK:
        if marker.exists():raise HTTPException(409,'本次备份恢复已完成')
        for path,data in checked:
            if not path.exists():path.write_bytes(data)
        for source in tasks:
            try:db.get(source['id']);skipped.append(source['id']);continue
            except KeyError:pass
            task=copy.deepcopy(source);old_version=task['version']
            for field in ('can_export','brief_analysis_hash','render_layout','prewrite_recovery'):task.pop(field,None)
            task['review']=None
            if task['status']=='approved':task['status']='needs_review';task['resume_status']='needs_review'
            if task['status'] in ('analyzing','retrieving','planning','writing','reviewing'):
                task['status']='error';task['error']='部署时中断的任务已恢复，请从已保存步骤继续。'
            task.setdefault('events',[]);db.save(task,f'从部署前备份恢复任务，原版本V{old_version}；旧核验已失效')
            restored.append(task['id'])
        marker.write_text(db.now(),encoding='utf-8')
    return dict(restored=restored,skipped=skipped,assets=len(checked),closed=True)
