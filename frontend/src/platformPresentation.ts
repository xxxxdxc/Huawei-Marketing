import type { Task, Plan } from './types';

// Match the server's current platform-only authorization, not historical events or a null plan alone.
export function platformChangeContext(task: Task) {
  const snapshot = task.platform_selection;
  const change = task.platform_changes?.at(-1);
  const confirmation = task.brief_confirmation;
  if (!snapshot?.plan?.selected_point_ids?.length || !change || !confirmation) return null;
  if (confirmation.authorization !== 'platform_only' || change.to_platform !== task.platform || task.brief?.platform && task.brief.platform !== task.platform) return null;
  if (!change.analysis_hash || change.analysis_hash !== task.brief_analysis_hash || change.analysis_hash !== confirmation.analysis_hash) return null;
  if (!Number.isInteger(change.authorized_version) || change.authorized_version < 1 || change.authorized_version !== confirmation.authorized_version || change.authorized_version > task.version) return null;
  if (snapshot.plan.product_id && snapshot.plan.product_id !== task.product_id) return null;
  const laterOperations = [...(task.evidence_refreshes || []), ...(task.point_replans || []), ...(task.resolution_history || [])];
  if (laterOperations.some(operation => operation.authorized_version > change.authorized_version)) return null;
  return snapshot;
}

export function usesSellingPointFlow(task: Task): boolean {
  return task.plan?.schema_version === '3' || Boolean(task.selection_confirmation) || Boolean(platformChangeContext(task));
}

export function isPlatformAdaptation(task: Task): boolean {
  if (task.plan || task.document || platformChangeContext(task)?.confirmed !== true) return false;
  return ['planning', 'retrieving', 'needs_review'].includes(task.status) || task.status === 'error' && ['plan_ready', 'needs_review'].includes(task.resume_status);
}

export function confirmedPlatformPlan(task: Task): Plan | null {
  const snapshot = platformChangeContext(task);
  return !task.plan && snapshot?.confirmed === true ? snapshot.plan : null;
}

export function writerProgressLabel(task: Task): string | null {
  if (isPlatformAdaptation(task)) return '适配新平台资料';
  if (usesSellingPointFlow(task) && task.status === 'writing') return task.writer_stage === 'outlining' ? '结构编排中' : task.writer_stage === 'drafting' ? '正文写作中' : '自动编排并写作中';
  return null;
}
