from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

class Brief(Strict):
    audience: str = Field(min_length=1, max_length=300)
    scenario: str = Field(min_length=1, max_length=300)
    platform: Literal["xiaohongshu","wechat","moments"]
    goal: str = Field(min_length=1, max_length=300)
    purchase_stage: str = Field(min_length=1, max_length=100)
    pain_points: list[str]
    strategy: str = Field(min_length=1, max_length=2000)
    tone: str
    emphasis: list[str]
    questions: list[str]

class Fact(Strict):
    category: Literal["product", "price", "promotion"] = "product"
    id: str
    claim: str
    quote: str = Field(min_length=8)
    source_id: str
    conditions: str

class Facts(Strict):
    facts: list[Fact] = Field(min_length=1, max_length=10)
    conflicts: list[str]

class PlanSection(Strict):
    id: str
    heading: str = Field(min_length=1)
    purpose: str = Field(min_length=1)
    fact_ids: list[str]
    image_id: str | None
    image_reason: str

class Plan(Strict):
    angle: str = Field(min_length=1)
    title_direction: str
    sections: list[PlanSection] = Field(min_length=1, max_length=8)
    cta: str

class Paragraph(Strict):
    section_id: str
    heading: str
    text: str
    fact_ids: list[str]
    image_id: str | None
    caption: str

class Document(Strict):
    title: str = Field(min_length=1)
    lead: str
    paragraphs: list[Paragraph] = Field(min_length=1)
    cta: str
    tags: list[str]

class Issue(Strict):
    category: Literal["fact","image","compliance","platform","evidence"]
    location: str
    detail: str
    severity: Literal["warning","error"]
    repairable: bool

class Review(Strict):
    summary: str
    issues: list[Issue]

class NewTask(Strict):
    knowledge_source: Literal["ima", "local_zip"] | None = None
    raw: str = Field(min_length=4, max_length=6000)
    product_id: str | None = Field(default=None, min_length=1)
    platform: Literal["xiaohongshu","wechat","moments"] | None = None

class Versioned(Strict):
    version: int = Field(ge=1)

class BriefUpdate(Versioned):
    brief: Brief | None = None
    analysis_hash: str | None = None

class PlanUpdate(Versioned):
    plan: Plan

class DocumentUpdate(Versioned):
    document: Document

class Modify(Versioned):
    instruction: str = Field(min_length=2, max_length=4000)

class Restore(Versioned):
    target_version: int = Field(ge=1)

class SettingsUpdate(Strict):
    knowledge_source: Literal["ima", "local_zip"] | None = None
    local_knowledge_path: str | None = None
    base_url: str
    writer_model: str
    reviewer_model: str
    vision: bool
    api_key: str | None = None
    reviewer_api_key: str | None = None

class AssetChoice(Strict):
    id: str
    description: str
    reason: str
    usable: bool

class AssetSelection(Strict):
    images: list[AssetChoice]


# Brief V2: canonical analysis is separate from the legacy frontend projection.
BriefFieldName = Literal["product_query", "product_model", "target_audience", "scenario", "buying_stage", "customer_needs", "marketing_goal", "platform", "user_constraints"]

class EvidenceRef(Strict):
    turn_id: str = Field(min_length=1)
    quote: str = Field(min_length=1, max_length=2000)

class Provenance(Strict):
    source: Literal["explicit", "inferred", "unknown"]
    evidence: list[EvidenceRef]
    reason: str = Field(max_length=1000)

class TextField(Provenance):
    value: str | None = Field(max_length=500)

    @model_validator(mode="after")
    def consistent(self):
        if self.source == "unknown" and self.value is not None:
            raise ValueError("unknown field must have null value")
        if self.source != "unknown" and (not self.value or not self.value.strip()):
            raise ValueError("known field needs a value")
        if self.source == "explicit" and not self.evidence:
            raise ValueError("explicit field needs user evidence")
        if self.source == "inferred" and not self.reason.strip():
            raise ValueError("inferred field needs a reason")
        return self

class ListField(Provenance):
    value: list[str] = Field(max_length=20)

    @model_validator(mode="after")
    def consistent(self):
        if self.source == "unknown" and self.value:
            raise ValueError("unknown field must have empty list")
        if any(not x.strip() for x in self.value):
            raise ValueError("empty list item")
        if self.source == "explicit" and not self.evidence:
            raise ValueError("explicit field needs user evidence")
        if self.source == "inferred" and not self.reason.strip():
            raise ValueError("inferred field needs a reason")
        return self

class Requirements(Strict):
    product_query: TextField
    product_model: TextField
    target_audience: TextField
    scenario: TextField
    buying_stage: TextField
    customer_needs: ListField
    marketing_goal: TextField
    platform: TextField
    user_constraints: ListField

class BriefQuestion(Strict):
    id: str = Field(min_length=1, max_length=100)
    field: BriefFieldName
    kind: Literal["missing", "conflict"]
    question: str = Field(min_length=1, max_length=600)
    reason: str = Field(min_length=1, max_length=1000)
    choices: list[str] = Field(max_length=12)

class CommercialNeed(Strict):
    category: Literal["price", "promotion"]
    request: str = Field(min_length=1, max_length=500)
    evidence: list[EvidenceRef] = Field(min_length=1)
    on_missing: Literal["omit", "block"] = "omit"
    blocking_evidence: list[EvidenceRef] = Field(default_factory=list)

    @model_validator(mode="after")
    def explicit_block(self):
        if self.on_missing=="block" and not self.blocking_evidence:
            raise ValueError("block requires the user's explicit refusal-to-generate evidence")
        return self

class DetailNeed(Strict):
    category: Literal["address", "schedule", "appointment"]
    request: str = Field(min_length=1, max_length=500)
    evidence: list[EvidenceRef] = Field(min_length=1)

class ParsingResult(Strict):
    requirements: Requirements
    commercial_requests: list[CommercialNeed] = Field(default_factory=list, max_length=4)
    detail_requests: list[DetailNeed] = Field(default_factory=list, max_length=4)
    questions: list[BriefQuestion] = Field(max_length=8)

class ReasonedPoint(Strict):
    point: str = Field(min_length=1, max_length=500)
    reason: str = Field(min_length=1, max_length=1000)

class AudienceInsight(Strict):
    job_to_be_done: str = Field(min_length=1, max_length=1000)
    problems: list[str] = Field(min_length=1, max_length=8)
    decision_factors: list[ReasonedPoint] = Field(min_length=1, max_length=8)

class SellingDirection(Strict):
    id: str = Field(min_length=1)
    direction: str = Field(min_length=1, max_length=500)
    reason: str = Field(min_length=1, max_length=1000)
    customer_needs: list[str] = Field(min_length=1, max_length=8)
    verification: Literal["pending"]

class MessageStrategy(Strict):
    theme: str = Field(min_length=1, max_length=500)
    reason: str = Field(min_length=1, max_length=1000)
    priorities: list[SellingDirection] = Field(min_length=1, max_length=5)
    angle: str = Field(min_length=1, max_length=500)
    cta_direction: str = Field(min_length=1, max_length=500)
    tone: str = Field(min_length=1, max_length=300)

class FactRequest(Strict):
    depends_on: list[str] = Field(default_factory=list, max_length=8)
    waivable: bool = True
    guardrail: Literal["none","identity","safety","compatibility"] = "none"
    category: Literal["product", "price", "promotion"] = "product"
    id: str = Field(min_length=1)
    direction_id: str
    question: str = Field(min_length=1, max_length=500)
    conditions: list[str] = Field(max_length=8)
    priority: Literal["required", "supporting"]

class ImageRequest(Strict):
    id: str = Field(min_length=1)
    direction_id: str
    description: str = Field(min_length=1, max_length=500)
    reason: str = Field(min_length=1, max_length=500)

class RetrievalPlan(Strict):
    facts: list[FactRequest] = Field(min_length=1, max_length=8)
    images: list[ImageRequest] = Field(min_length=1, max_length=6)

class StrategyResult(Strict):
    message_strategy: MessageStrategy
    retrieval_plan: RetrievalPlan

    @model_validator(mode="after")
    def linked(self):
        directions=[p.id for p in self.message_strategy.priorities]
        facts=[r.id for r in self.retrieval_plan.facts]
        images=[r.id for r in self.retrieval_plan.images]
        if any(len(v)!=len(set(v)) for v in (directions,facts,images)):
            raise ValueError("duplicate strategy/request id")
        if any(r.direction_id not in directions for r in [*self.retrieval_plan.facts,*self.retrieval_plan.images]):
            raise ValueError("unknown strategy direction")
        if any(set(r.depends_on)-set(facts) or r.id in r.depends_on for r in self.retrieval_plan.facts):
            raise ValueError("unknown or self request dependency")
        if not any(r.priority=="required" for r in self.retrieval_plan.facts):
            raise ValueError("core evidence request must be required")
        if set(directions)-{r.direction_id for r in self.retrieval_plan.facts}:
            raise ValueError("each selling direction needs evidence requests")
        return self

class ProductCandidate(Strict):
    id: str
    name: str
    category: str

class ProductResolution(Strict):
    state: Literal["unresolved", "ambiguous", "resolved"]
    product_id: str | None
    product_model: str | None
    candidates: list[ProductCandidate]

class MarketingBrief(Strict):
    schema_version: Literal["2"]
    status: Literal["need_clarification", "needs_resolution", "ready"]
    requirements: Requirements
    commercial_requests: list[CommercialNeed] = Field(default_factory=list)
    product_resolution: ProductResolution
    questions: list[BriefQuestion]
    audience_insight: AudienceInsight | None
    message_strategy: MessageStrategy | None
    retrieval_plan: RetrievalPlan | None

class BriefAnswer(Strict):
    question_id: str = Field(min_length=1, max_length=100)
    answer: str = Field(min_length=1, max_length=2000)

class BriefAnswers(Versioned):
    answers: list[BriefAnswer] = Field(min_length=1, max_length=8)

class FactCoverage(Strict):
    request_id: str
    status: Literal["supported", "not_found", "conflict"]
    fact_ids: list[str]
    reason: str = Field(min_length=1)

class EvidenceConflict(Strict):
    category: Literal["product", "price", "promotion"]
    request_ids: list[str]
    source_ids: list[str] = Field(min_length=1)
    detail: str = Field(min_length=1)

class RetrievalFacts(Facts):
    conflicts: list[EvidenceConflict]
    facts: list[Fact] = Field(max_length=10)
    coverage: list[FactCoverage]


class TaskView(Strict):
    """Preserve existing task properties while publishing the V2 response schema."""
    model_config = ConfigDict(extra="allow", strict=True)
    id: str
    version: int
    status: str
    product_id: str | None = None
    platform: Literal["xiaohongshu", "wechat", "moments"] | None = None
    brief: Brief | None = None
    brief_analysis: MarketingBrief | None = None
    brief_analysis_hash: str | None = None
    brief_confirmation: dict | None = None
    dialogue: list[dict] = Field(default_factory=list)
    brief_runs: list[dict] = Field(default_factory=list)
    can_export: bool = False
    knowledge_source: Literal["ima", "local_zip"] | None = None
    knowledge_snapshot: dict | None = None


class KnowledgeSourceUpdate(Strict):
    source: Literal["ima", "local_zip"]
    local_knowledge_path: str | None = None


class PlatformChange(Versioned):
    platform: Literal["xiaohongshu", "wechat", "moments"]


class EvidenceResolutionPreview(Versioned):
    drop_request_ids: list[str] = Field(default_factory=list,max_length=8)
    drop_direction_ids: list[str] = Field(default_factory=list,max_length=5)


class EvidenceResolutionConfirm(EvidenceResolutionPreview):
    preview_id: str = Field(min_length=1,max_length=100)
    confirmed: bool
    acknowledged_constraint_ids: list[str] = Field(default_factory=list,max_length=16)
