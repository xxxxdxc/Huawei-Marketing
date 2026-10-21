import type { Plan, Section } from './types';

export const SECTION_ROLES: Record<NonNullable<Section['role']>, string> = {
  opening: '场景引入', argument: '事实论证', objection: '回应疑虑', summary: '归纳选择', cta: '行动引导',
};
export const CHAR_BUDGETS: Record<string, [number, number]> = { xiaohongshu: [300, 500], wechat: [600, 900], moments: [80, 150] };
export function planWarnings(plan: Plan, platform: string): string[] {
  if (plan.schema_version !== '2') return [];
  const warnings: string[] = [];

  const budget = plan.sections.reduce((total, section) => total + (section.target_chars || 0), 0);
  const [min, max] = CHAR_BUDGETS[platform];
  if (budget < min || budget > max) warnings.push(`段落篇幅预算合计 ${budget} 字，建议调整为 ${min}–${max} 字。`);
  const questions = new Set<string>();
  const selected = new Set(plan.selected_point_ids || []);
  const candidates = plan.planning_analysis?.candidates || [];
  const hasAudit = candidates.length > 0;
  const covered = new Set(plan.sections.flatMap(s => s.point_ids || []));
  if (hasAudit && !selected.size) warnings.push('当前大纲没有有效的选用卖点，请先选择并更新大纲。');
  if (hasAudit && [...selected].some(id => !covered.has(id))) warnings.push('有入选卖点尚未安排段落，请补充承接段落，或在上方调整选择并更新大纲。');
  plan.sections.forEach((section, index) => {
    const points = section.point_ids || [];
    if (hasAudit && points.some(id => !selected.has(id))) warnings.push(`第 ${index + 1} 段引用了未选用的卖点，请使用本篇已有方向。`);
    if (hasAudit && ['argument', 'objection'].includes(section.role || '') && !points.length) warnings.push(`第 ${index + 1} 段需要关联本篇卖点。`);
    const allowed = new Set(candidates.filter(c => points.includes(c.id)).flatMap(c => c.fact_ids));
    if (hasAudit && section.fact_ids.some(id => !allowed.has(id))) warnings.push(`第 ${index + 1} 段的事实需要与所关联卖点一致。`);
    const question = (section.reader_question || '').trim();
    if (!question) warnings.push(`第 ${index + 1} 段还没有填写读者问题。`);
    const normalized = question.replace(/[\s\p{P}\p{S}]/gu, '').toLowerCase();
    if (normalized && questions.has(normalized)) warnings.push(`第 ${index + 1} 段的读者问题与其他段落重复。`);
    if (normalized) questions.add(normalized);
    if (['argument', 'objection'].includes(section.role || '') && !section.fact_ids.length) warnings.push(`第 ${index + 1} 段需要引用事实，或改为合适的段落角色。`);
    if (!section.target_chars || !Number.isInteger(section.target_chars) || section.target_chars < 1 || section.target_chars > 900) warnings.push(`第 ${index + 1} 段的篇幅预算需要为 1–900 的整数。`);
  });
  return warnings;
}

export function executedPoints(plan: Plan | null): string[] {
  return plan?.selected_point_ids ? [...plan.selected_point_ids] : [...new Set(plan?.sections.flatMap(s => s.point_ids || []) || [])];
}
export function samePointSelection(a: string[], b: string[]): boolean {
  return a.length === b.length && [...a].sort().every((id, i) => id === [...b].sort()[i]);
}
export const POINT_GUIDANCE: Record<string, string> = { moments: '通常先聚焦 1 个重点', xiaohongshu: '通常选用 2–3 个重点', wechat: '通常选用 3–4 个重点' };
