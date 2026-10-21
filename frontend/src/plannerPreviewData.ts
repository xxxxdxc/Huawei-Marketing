import type { Task } from './types';
import { sequenceImages } from './contentLayout';

export function plannerPreviewTask(platform = 'xiaohongshu'): Task {
  const descriptions = ['课堂资料如何整理', '图书馆学习如何展开', '小组讨论如何准备'];
  const directions = ['从课堂资料整理切入', '围绕专注学习组织信息', '回应小组展示准备需求'];
  const images = descriptions.map((description, i) => ({ id: `demo-planner-${i + 1}`, name: `演示插图 ${i + 1}`, model: 'MateBook 演示型号', source: '本地界面演示 / 非 ima 素材', description: `${description}（示意插图，非产品实拍）`, url: `/planner-preview/scene-${i + 1}.svg`, visual_checked: false }));
  const facts = directions.map((claim, i) => ({ id: `F0${i + 1}`, claim: `${claim}的事实示例`, quote: '此内容仅用于演示事实引用和段落编排，不代表任何真实产品能力或参数。', source_id: 'demo-source', conditions: '仅用于界面演示，不可作为产品宣传依据。' }));
  const candidates = directions.map((direction, i) => ({ id: `C${i + 1}`, direction, audience_need: descriptions[i], fact_ids: [facts[i].id], image_ids: [images[i].id], conditions: [facts[i].conditions], scores: { audience: { value: 4 - i, reason: '按演示人群需求判断关联程度。' }, evidence: { value: 3, reason: '模拟资料可用于说明来源入口，不代表真实证据。' }, differentiation: { value: 3, reason: '该方向在本篇内容中承担不同作用。' }, image: { value: 3, reason: '演示插图提供布局参照，非真实素材匹配结果。' } }, rank: i + 1, total_score: 83.75 - i * 8.75 }));
  const selected = platform === 'moments' ? ['C1'] : platform === 'xiaohongshu' ? ['C1', 'C2'] : ['C1', 'C2', 'C3'];
  candidates.forEach(candidate => Object.assign(candidate, { recommendation: selected.includes(candidate.id) ? 'recommended' : 'alternative', recommendation_reason: selected.includes(candidate.id) ? '回应这次模拟任务的主要问题，在篇幅内优先展开。' : '与本篇重点有部分重合，先保留为备选；需要时可以选入。' }));
  const sections = sequenceImages(descriptions.map((question, i) => ({ id: `P${i + 1}`, heading: ['从一天的课堂开始', '把信息带入学习情境', '留出体验和咨询入口'][i], purpose: '借助可核查的资料解释这一场景，保留事实的适用条件。', reader_question: `${question}？`, role: 'argument' as const, point_ids: [selected[i % selected.length]], fact_ids: [facts[Number(selected[i % selected.length].slice(1)) - 1].id], image_id: images[i].id, image_reason: '以示意插图检查图文位置和阅读顺序。', target_chars: platform === 'wechat' ? 250 : platform === 'moments' ? 35 : 130 })), platform);
  return { id: 'demo-planner-task', title: '开学季校园图文 · 演示任务', raw: '【本地演示】面向大学新生规划校园学习图文', product_id: 'demo-product', platform, status: 'plan_ready', version: 1,
    brief: { audience: '准备开学购机的大学新生', scenario: '课堂学习 / 图书馆 / 小组讨论', platform, goal: '帮助读者了解产品，再到店体验', purchase_stage: '了解与比较', pain_points: ['想知道产品是否适合自己的学习日常'], strategy: '以学习情境组织信息；所有事实均需真实资料验证。', tone: '自然、清晰', emphasis: directions, questions: [] },
    package: { product: { id: 'demo-product', name: 'MateBook 演示型号（模拟数据）', category: '演示', path: '本地界面演示' }, sources: [{ id: 'demo-source', title: '本地模拟资料，不来自 ima', path: '演示 / 模拟原文', text: facts[0].quote, retrieved_at: '2026-10-21T00:00:00Z' }], facts, images, conflicts: [], search_hits: 0 },
    plan: { schema_version: '2', product_id: 'demo-product', angle: '从校园学习的一天出发，帮助新生理解需要核实哪些购机信息。', title_direction: '开学选电脑，先想清楚你的学习日常', composition_rationale: '先回应课堂里的实际问题，再用证据展开已选重点；不将备选方向全部塞进本篇。', selected_point_ids: selected, sections, cta: '欢迎到店了解具体型号与适用条件。', planning_analysis: { status: 'generated', candidates, warnings: ['此页为隔离演示。评分、事实和插图均为模拟内容。'] } },
    document: null, review: null, error: null, events: [], can_export: false, resume_status: 'plan_ready' };
}

// Local demonstration only: this deterministic outline is not a model-generated result.
export function previewPointPlan(task: Task, selectedIds: string[]) {
  const old = task.plan!;
  const selected = old.planning_analysis!.candidates!.filter(candidate => selectedIds.includes(candidate.id));
  const minImages = task.platform === 'xiaohongshu' ? 3 : task.platform === 'wechat' ? 2 : 1;
  const count = Math.max(selected.length, minImages);
  const total = task.platform === 'wechat' ? 750 : task.platform === 'moments' ? 120 : 400;
  const sections = sequenceImages(Array.from({ length: count }, (_, index) => {
    const candidate = selected[index % selected.length];
    const image = task.package!.images[index] || null;
    return { id: `DEMO-${index + 1}`, heading: `${index + 1}. ${candidate.direction}`, purpose: '按本次选用范围组织证据，本段仅为本地界面演示。', reader_question: `第 ${index + 1} 步如何了解${candidate.audience_need}？`, role: 'argument' as const, point_ids: [candidate.id], fact_ids: [...candidate.fact_ids], image_id: image?.id || null, image_reason: image ? '以示意插图验证位置与阅读顺序。' : '', target_chars: Math.floor(total / count) + (index < total % count ? 1 : 0) };
  }), task.platform);
  return { ...structuredClone(old), selected_point_ids: [...selectedIds], sections, composition_rationale: '本地演示：只围绕本次所选卖点重新安排段落。原评分保持，不执行新评分或真实模型调用。' };
}
