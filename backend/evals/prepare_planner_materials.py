"""Prepare private, live-ima evidence snapshots. No user tasks are created."""
import asyncio,copy,hashlib,json,shutil,sys
from pydantic import BaseModel,ConfigDict
class ExtractedFact(BaseModel):
    model_config=ConfigDict(extra="forbid",strict=True)
    quote_id:str
    claim:str
    conditions:str
class ExtractedFacts(BaseModel):
    model_config=ConfigDict(extra="forbid",strict=True)
    facts:list[ExtractedFact]
from pathlib import Path
from backend import schemas as S,workflow as w
from backend.clients import llm,usage_capture
from backend.settings import DATA,ASSETS,get_settings

async def main():
    folder=Path(sys.argv[1]);calls=[];token=usage_capture.set(calls)
    try:
        for source in sorted(folder.glob('*_raw.json')):
            raw=json.loads(source.read_text(encoding='utf-8'))
            if 'product' not in raw:continue
            output=folder/(raw['product']['id']+'_verified.json')
            if output.exists():continue
            if raw.get('knowledge_source')!='ima':raise ValueError('Only fresh ima materials are eligible')
            p=copy.deepcopy(raw)
            for image in p['images']:
                data=Path(image['cache_path']).read_bytes()
                assert hashlib.sha256(data).hexdigest()==image['sha256']
                old=image['id'];image['id']=hashlib.sha256((old+image['sha256']).encode()).hexdigest()[:20]
                path=ASSETS/image['id']
                if path.exists():assert path.read_bytes()==data
                else:path.write_bytes(data)
                image['url']='/api/assets/'+image['id'];image['original_index_id']=old
            bank={}
            for src in p['sources']:
                for index,line in enumerate(src['text'].splitlines()):
                    if 12<=len(line)<=1400 and not line.startswith(('#','>')):
                        bank[f"{src['id']}:L{index+1}"]=dict(source_id=src['id'],quote=line)
            result=await llm.complete(get_settings()['writer_model'],w.BASE+'为固定评测提取最多8条不同产品事实。输入quote_bank中每项是不可改写的连续原文，返回quote_id以及该原文直接支持的claim与conditions。优先选择规格正文，不选择待确认事项、未解答问题、动态价格或营销假设。覆盖型号系统、屏幕、便携、接口、交互与能力边界。不得将电池容量等同续航时长；所有配置、典型值、约、最高、系统和适配限制必须保留。',dict(product=p['product'],quote_bank=bank),ExtractedFacts)
            extracted=[]
            for n,f in enumerate(result['facts']):
                evidence=bank[f['quote_id']]
                extracted.append(dict(id=f'F{n+1:02d}',category='product',claim=f['claim'],conditions=f['conditions'],**evidence))
            result=dict(facts=extracted,conflicts=[])
            p.update(result);w.verify_facts(p)
            if p['conflicts']:raise ValueError('Conflicting snapshot cannot serve as eval evidence')
            accepted=[]
            for start in range(0,len(p['images']),3):
                batch=p['images'][start:start+3]
                if not batch:break
                assessment=await llm.complete(get_settings()['reviewer_model'],w.BASE+'你是Asset Selector，仅观察实际图片。型号由ima索引核实，不凭外观猜型号。逐一返回全部输入图片的id、description、reason、usable。拒绝带价格优惠、夸大宣传、版本冲突或无法辨识的素材。描述真正可见的内容，不能将外观图称为参数/性能证明。不选择段落，不生成文案。',dict(product=p['product'],facts=p['facts'],images=[{k:v for k,v in im.items() if k in ('id','name','description','model')} for im in batch]),S.AssetSelection,images=batch,role='reviewer')
                by_id={x['id']:x for x in assessment['images']}
                if set(by_id)!={x['id'] for x in batch}:raise ValueError('Incomplete image assessment')
                for image in batch:
                    a=by_id[image['id']];image.update(visual_checked=True,visual_description=a['description'],selection_reason=a['reason'],usable=a['usable'])
                    if a['usable']:accepted.append(image)
                if len(accepted)>=3:break
            p['asset_candidates']=p['images'];p['images']=accepted
            if len(accepted)<3:raise ValueError('Fewer than three visually verified images for '+p['product']['name'])
            p['input_snapshot_sha256']=hashlib.sha256(json.dumps(p,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
            output.write_text(json.dumps(p,ensure_ascii=False,indent=2),encoding='utf-8')
            print(json.dumps({'product':p['product']['name'],'facts':len(p['facts']),'verified_images':len(accepted),'file':str(output)},ensure_ascii=False),flush=True)
    finally:
        audit=folder/'preparation_model_usage.json'
        prior=json.loads(audit.read_text(encoding='utf-8')) if audit.exists() else []
        audit.write_text(json.dumps(prior+calls,ensure_ascii=False,indent=2),encoding='utf-8');usage_capture.reset(token)

if __name__=='__main__':asyncio.run(main())
