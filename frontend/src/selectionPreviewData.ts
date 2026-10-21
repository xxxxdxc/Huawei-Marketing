import type { Task } from './types';
import { plannerPreviewTask, previewPointPlan } from './plannerPreviewData';

export function selectionPreviewTask(platform = 'xiaohongshu'): Task {
  const task = plannerPreviewTask(platform);
  task.title = '校园营销核心卖点 · V3 演示';
  task.plan = { ...task.plan!, schema_version: '3', phase: 'selection', sections: [], angle: '', title_direction: '', composition_rationale: null };
  return task;
}
export function selectionPreviewComposition(task: Task, selectedIds: string[]): Task {
  const plan = { ...previewPointPlan(task, selectedIds), schema_version: '3' as const, phase: 'composed' as const };
  plan.sections = plan.sections.map(section => ({ ...section, heading: section.heading.replace(/^\d+\.\s*/, '') }));
  const outline = { product_id: task.product_id, selected_point_ids: [...selectedIds], main_takeaway: '围绕所选方向，帮助读者了解需要核实的学习信息。', angle: plan.angle, title_direction: '从学习日常理解购机方向', composition_rationale: '演示：先回应主要问题，再按证据组织信息；只使用本次选用的卖点。', sections: plan.sections.map((section, index) => ({ ...section, connection_to_previous: index ? '承接上一段的问题，补充下一步需要了解的信息。' : '从读者熟悉的情境引入。', reader_progress: '读者进一步明确需要核实的资料。' })), cta: plan.cta };
  return { ...task, plan, writer_outline: outline, writer_stage: 'drafting' };
}
export function selectionPreviewDocument(task: Task): Task {
  const paragraphs = task.plan!.sections.map(section => ({ section_id: section.id, heading: section.heading, text: '这是一段本地交互演示文案，用于查看卖点确认后如何连续完成结构与正文。不包含真实产品参数，也不代表实际模型输出。', fact_ids: section.fact_ids, image_id: section.image_id, caption: section.image_id ? '示意插图，非真实产品实拍。' : '' }));
  return { ...task, writer_stage: 'complete', status: 'needs_review', resume_status: 'needs_review', document: { title: '开学选电脑，从学习日常开始', lead: '以下内容仅用于界面演示。', paragraphs, cta: task.plan!.cta, tags: ['#本地演示'] }, review: null, can_export: false };
}
