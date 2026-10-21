import type { Task } from '../src/types';
import { selectionPreviewTask, selectionPreviewComposition } from '../src/selectionPreviewData';

export function adaptationTask(): Task {
  const original = selectionPreviewTask('moments');
  const plan = selectionPreviewComposition(original, original.plan!.selected_point_ids!).plan!;
  return { ...original, id: 'fixture-task', version: 31, platform: 'wechat', brief: { ...original.brief!, platform: 'wechat' }, status: 'planning', resume_status: 'plan_ready', plan: null, document: null, review: null, error: null, can_export: false, writer_stage: null, writer_outline: null, selection_confirmation: null,
    brief_analysis_hash: 'fixture-platform-hash',
    brief_confirmation: { authorization: 'platform_only', analysis_hash: 'fixture-platform-hash', authorized_version: 31 },
    platform_changes: [{ from_platform: 'moments', to_platform: 'wechat', analysis_hash: 'fixture-platform-hash', authorized_version: 31, at: '2026-10-21T12:00:00Z' }],
    platform_selection: { plan, confirmed: true, facts: structuredClone(original.package!.facts) },
  };
}
