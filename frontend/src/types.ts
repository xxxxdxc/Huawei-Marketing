export type Product={id:string;name:string;category:string;path:string};
export type Brief={audience:string;scenario:string;platform:string;goal:string;purchase_stage:string;pain_points:string[];strategy:string;tone:string;emphasis:string[];questions:string[]};
export type Fact={id:string;claim:string;quote:string;source_id:string;conditions:string};
export type Asset={id:string;name:string;model:string;source:string;description:string;url:string;selection_reason?:string;visual_checked?:boolean};
export type Section={id:string;heading:string;purpose:string;fact_ids:string[];image_id:string|null;image_reason:string};
export type Plan={angle:string;title_direction:string;sections:Section[];cta:string};
export type Paragraph={section_id:string;heading:string;text:string;fact_ids:string[];image_id:string|null;caption:string};
export type Doc={title:string;lead:string;paragraphs:Paragraph[];cta:string;tags:string[]};
export type Issue={category:string;location:string;detail:string;severity:string;repairable:boolean};
export type Task={execution_scope?:{omitted_request_ids:string[];omitted_direction_ids:string[];excluded_fact_ids?:string[]};brief_analysis?:BriefAnalysis|null;brief_analysis_hash?:string;dialogue?:{id:string;kind:string;text:string;at:string;question?:string}[];id:string;title:string;raw:string;product_id:string;platform:string;status:string;version:number;brief:Brief|null;package:{product:Product;sources:{id:string;title:string;path:string;text:string;retrieved_at:string}[];facts:Fact[];images:Asset[];conflicts:(string | {detail:string;source_ids:string[]})[];search_hits:number;coverage?:Coverage[];execution_coverage?:Coverage[];all_facts?:Fact[];retrieval_plan?:{facts:RetrievalRequest[]};evidence_gaps?:EvidenceGap[];content_policy?:ContentPolicy}|null;plan:Plan|null;document:Doc|null;review:{summary:string;issues:Issue[];passed:boolean;checked_at:string;model:string;document_hash:string}|null;error:string|null;events:{at:string;text:string}[];can_export:boolean;resume_status:string};
export type Summary={id:string;title:string;status:string;version:number;platform:string;updated_at:string};
export type Settings={base_url:string;writer_model:string;reviewer_model:string;vision:boolean;has_key:boolean;ima_ready:boolean;credential_storage:string;has_writer_key?:boolean;has_reviewer_key?:boolean;reviewer_uses_writer_key?:boolean};

export type RetrievalRequest = {id:string;direction_id?:string;question:string;category?:string;priority:string};
export type Coverage = {request_id:string;status:string;fact_ids:string[];reason:string};
export type EvidenceGap = {request:RetrievalRequest;coverage:Coverage;blocking_reason?:string;reason?:string;blocking_evidence?:{quote:string;turn_id:string}[]};
export type OmittedRequest = {request_id:string;category:string;status:string;reason:string;on_missing?:string;blocking_evidence?:{quote:string;turn_id:string}[]};
export type ContentPolicy = {notices:string[];omitted_requests:OmittedRequest[];blocked_requests?:OmittedRequest[];allowed_categories?:string[];omitted_fact_ids?:string[]};

export type BriefValue = {value:string|string[]|null;source:string;reason:string;evidence:{turn_id:string;quote:string}[]};
export type BriefAnalysis = {schema_version:string;status:string;requirements:Record<string,BriefValue>;questions:{id:string;field:string;kind:string;question:string;reason:string;choices:string[]}[];product_resolution:{state:string;product_model:string|null;candidates:{id:string;name:string;category:string}[]};audience_insight:{job_to_be_done:string;problems:string[];decision_factors:{point:string;reason:string}[]}|null;message_strategy:{theme:string;angle:string;tone:string;cta_direction:string;reason:string;priorities:{id:string;direction:string;reason:string}[]}|null;retrieval_plan:{facts:RetrievalRequest[];images:{id:string;description:string;reason:string}[]}|null};
