"""Typed Planner V2 intermediate results. Scores are judgments, never facts."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field
from .store_marketing import StoreContext

class Strict(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)

class Score(Strict):
    value:int=Field(ge=0,le=4)
    reason:str=Field(min_length=1,max_length=300)

class Scores(Strict):
    audience:Score
    evidence:Score
    differentiation:Score
    image:Score

class SellingPoint(Strict):
    id:str=Field(min_length=1)
    direction:str=Field(min_length=1,max_length=250)
    audience_need:str=Field(min_length=1,max_length=250)
    fact_ids:list[str]=Field(min_length=1,max_length=10)
    image_ids:list[str]=Field(max_length=6)
    conditions:list[str]=Field(max_length=10)
    scores:Scores
    recommendation:Literal["recommended","alternative"]
    recommendation_reason:str=Field(min_length=1,max_length=600)
    request_ids:list[str]=Field(default_factory=list,max_length=20)
    mandatory_need_ids:list[str]=Field(default_factory=list,max_length=20)

class CandidateBatch(Strict):
    product_id:str
    candidates:list[SellingPoint]=Field(min_length=1,max_length=8)

class EnrichedSellingPoint(SellingPoint):
    # Up to 10 model conditions plus one source condition for each of 10 facts.
    conditions:list[str]=Field(max_length=20)

class EnrichedCandidateBatch(Strict):
    product_id:str
    candidates:list[EnrichedSellingPoint]=Field(min_length=1,max_length=8)

class Narrative(Strict):
    framework:Literal['scene_story','problem_solution','buying_guide','selling_point_focus']
    reason:str=Field(min_length=1,max_length=600)
    ordering_rationale:str=Field(min_length=1,max_length=600)

class ImagePosition(Strict):
    kind:Literal['none','before_section','after_section','carousel','grid']
    order:int|None=None

class DraftSection(Strict):
    id:str
    heading:str=Field(min_length=1,max_length=200)
    purpose:str=Field(min_length=1,max_length=600)
    reader_question:str=Field(min_length=1,max_length=400)
    role:Literal['opening','argument','objection','summary','cta']
    point_ids:list[str]
    fact_ids:list[str]
    image_id:str|None
    image_reason:str
    image_position:ImagePosition
    target_chars:int=Field(ge=1,le=900)

class ContentPlanDraft(Strict):
    schema_version:Literal['2']
    product_id:str
    angle:str=Field(min_length=1,max_length=500)
    title_direction:str=Field(min_length=1,max_length=300)
    composition_rationale:str=Field(min_length=1,max_length=1000)
    selected_point_ids:list[str]=Field(min_length=1,max_length=8)
    sections:list[DraftSection]=Field(min_length=1,max_length=8)
    cta:str=Field(min_length=1,max_length=300)


class WriterSection(DraftSection):
    connection_to_previous: str = Field(min_length=1, max_length=500)
    reader_progress: str = Field(min_length=1, max_length=500)

class WriterOutline(Strict):
    product_id: str
    selected_point_ids: list[str] = Field(min_length=1, max_length=8)
    main_takeaway: str = Field(min_length=1, max_length=600)
    angle: str = Field(min_length=1, max_length=500)
    title_direction: str = Field(min_length=1, max_length=300)
    composition_rationale: str = Field(min_length=1, max_length=1000)
    sections: list[WriterSection] = Field(min_length=1, max_length=8)
    cta: str = Field(max_length=300)
    store_context: StoreContext | None = None
