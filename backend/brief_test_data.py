"""Synthetic model responses for isolated tests only."""
import copy

def explicit(value, quote, turn="selection"):
    return dict(value=value,source="explicit",evidence=[dict(turn_id=turn,quote=quote)],reason="用户提供")

def inferred(value):
    return dict(value=value,source="inferred",evidence=[],reason="根据任务场景提出的待确认假设")

def unknown(is_list=False):
    return dict(value=[] if is_list else None,source="unknown",evidence=[],reason="尚未提供")

def parsing(platform="moments",platform_turn="selection",query="测试型号",product_turn="selection"):
    names={"moments":"门店朋友圈","wechat":"公众号","xiaohongshu":"小红书"}
    return dict(requirements=dict(product_query=explicit(query,query,product_turn),product_model=unknown(),target_audience=inferred("大学生"),scenario=inferred("上课携带电脑"),buying_stage=inferred("了解比较"),customer_needs=inferred(["携带方便"]),marketing_goal=inferred("引导到店咨询"),platform=explicit(platform,names[platform],platform_turn),user_constraints=unknown(True)),questions=[])

AUDIENCE=dict(job_to_be_done="携带电脑完成学习任务",problems=["上课往返携带负担"],decision_factors=[dict(point="便携性",reason="需要经常携带")])
STRATEGY=dict(message_strategy=dict(theme="学习场景中的携带需求",reason="围绕学生的真实任务",priorities=[dict(id="D1",direction="便携性",reason="回应携带负担",customer_needs=["携带方便"],verification="pending")],angle="从上课携带的场景切入",cta_direction="到店了解具体配置",tone="自然"),retrieval_plan=dict(facts=[dict(id="R1",direction_id="D1",question="具体配置的重量及测量条件是什么",conditions=["配置","版本"],priority="required")],images=[dict(id="I1",direction_id="D1",description="能呈现机身与携带场景的图片",reason="帮助理解携带场景")]))

def responses(parsed=None):
    return [copy.deepcopy(parsed or parsing()),copy.deepcopy(AUDIENCE),copy.deepcopy(STRATEGY)]
