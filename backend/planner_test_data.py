"""Synthetic two-stage responses for old end-to-end fixtures; never used in production."""
import copy
from unittest.mock import AsyncMock as BaseAsyncMock

class AsyncMock(BaseAsyncMock):
    async def _execute_mock_call(self,*args,**kwargs):
        from backend import planner_schemas as P
        from backend.content_layout import default_position
        schema=args[3] if len(args)>3 else None
        payload=args[2] if len(args)>2 else {}
        if schema is P.CandidateBatch:
            self.await_count+=1;self.await_args=self.call_args;self.await_args_list.append(self.call_args)
            return dict(product_id=payload['product_id'],candidates=[dict(id='C1',direction='围绕已核实事实介绍产品',audience_need='理解当前产品',fact_ids=[f['id'] for f in payload['facts']],image_ids=[i['id'] for i in payload['images']],conditions=[],recommendation='recommended',recommendation_reason='隔离测试：覆盖明确需求',request_ids=[],scores={key:dict(value=3 if key!='image' or payload['images'] else 0,reason='隔离测试判断') for key in ('audience','evidence','differentiation','image')})])
        result=await super()._execute_mock_call(*args,**kwargs)
        if schema in (P.ContentPlanDraft,P.WriterOutline) and isinstance(result,dict) and 'sections' in result and 'schema_version' not in result:
            result=copy.deepcopy(result)
            platform=payload['brief']['platform'];count=len(result['sections']);budget={'moments':100,'wechat':700,'xiaohongshu':400}[platform];slot=0
            for index,s in enumerate(result['sections']):
                if s['image_id']:slot+=1
                s.update(reader_question=f'问题{index+1}：'+s['purpose'],role='argument' if s['fact_ids'] else 'opening',point_ids=['C1'],image_position=default_position(platform,s['image_id'],slot),target_chars=budget//count+(budget%count if index==0 else 0))
            result.update(schema_version='2',product_id=payload['product_id'],selected_point_ids=['C1'],composition_rationale='隔离测试：先回答场景问题，再按证据展开')
        if schema is P.WriterOutline and isinstance(result,dict) and 'sections' in result:
            result.pop('schema_version',None)
            result['selected_point_ids']=payload['selected_point_ids']
            result['main_takeaway']='隔离测试的核心判断'
            for index,sec in enumerate(result['sections']):
                sec.update(connection_to_previous='承接前段'+str(index),reader_progress='新增理解'+str(index))
        return result
