import type { Coverage, Fact, RetrievalRequest } from './types';
export type Blocker = {code:string;reason:string;request_id?:string;waivable:boolean};
export type ReviewOverview = {
  version:number;knowledge_source:string;local_archive_path?:string|null;task_upload_supported:boolean;actions:string[];
  unmet_requirements:{request:RetrievalRequest;coverage:Coverage|null;found:Fact[];missing:string;affected_direction_ids:string[];blocking:boolean;omitted:boolean;can_drop:boolean;non_waivable_reason?:string|null}[];
  available_facts:Fact[];blockers:Blocker[];
  material_requirements:{request_id:string;question?:string;target_model:string;conditions:string[];document_types:string[]}[];
};
export type ResolutionPreview = {
  task_id:string;version:number;preview_id:string;selected_request_ids:string[];selected_direction_ids:string[];
  removed:{request:RetrievalRequest;coverage:Coverage|null;dependency?:{kind:string;via:string}}[];
  affected_directions:{direction:{id:string;direction:string};request_ids:string[];reason:string}[];
  retained:{request:RetrievalRequest;coverage:Coverage|null}[];retained_fact_ids:string[];excluded_fact_ids:string[];excluded_image_ids:string[];
  remaining_blockers:Blocker[];required_constraint_acks:{id:string;request_id:string;description:string;requires_ack:boolean;evidence:{turn_id:string;quote:string}[]}[];
  prohibited_topic_labels:string[];can_apply:boolean;requires_asset_review:boolean;
};
