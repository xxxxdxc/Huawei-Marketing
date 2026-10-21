import { Check, Circle, CircleAlert, Clock3, LoaderCircle, UserRound } from 'lucide-react';
import type { Task } from './types';
import { isPlatformAdaptation, usesSellingPointFlow } from './platformPresentation';
import { BUSY, effectiveStatus, evidencePaused, plannerGenerationFailed, localTime } from './shared';

export default function WorkflowProgress({ task, onOpen, dirty = false }: { task: Task; dirty?: boolean; onOpen: (tab: string) => void }) {
  const state = effectiveStatus(task);
  const failed = task.status === 'error';
  const briefWaiting = ['brief_ready', 'needs_information'].includes(state);
  const states = [
    task.brief && !briefWaiting ? 'done' : briefWaiting ? 'confirm' : task.status === 'analyzing' ? 'running' : failed && state === 'draft' ? 'failed' : 'waiting',
    task.package ? 'done' : task.status === 'retrieving' ? 'running' : failed && state === 'brief_ready' ? 'failed' : 'waiting',
    task.package ? 'done' : 'waiting',
    state === 'plan_ready' ? (failed ? 'failed' : 'confirm') : task.status === 'planning' ? 'running' : task.plan ? 'done' : 'waiting',
    task.document ? 'done' : task.status === 'writing' ? 'running' : 'waiting',
    task.can_export && !dirty ? 'done' : task.status === 'reviewing' ? 'running' : failed && state === 'needs_review' ? 'failed' : task.document ? 'confirm' : 'waiting',
  ];
  if (evidencePaused(task)) { states[2] = plannerGenerationFailed(task) ? 'done' : 'failed'; states[3] = plannerGenerationFailed(task) ? 'failed' : 'waiting'; states[5] = 'waiting'; }
  if (failed && state === 'plan_ready') { states[3] = 'done'; states[4] = 'failed'; }
  const adaptingPlatform = isPlatformAdaptation(task);
  if (adaptingPlatform) { states[3] = 'done'; states[4] = BUSY.includes(task.status) ? 'running' : 'failed'; states[5] = 'waiting'; }
  const labels: Record<string, string> = { done: '已完成', confirm: '需要你处理', running: '运行中', failed: '已暂停', waiting: '等待中' };
  const selectionFlow = usesSellingPointFlow(task) || plannerGenerationFailed(task);
  const steps = [['理解营销需求', 'strategy'], ['检索产品资料', 'evidence'], ['整理事实与图片', 'evidence'], [plannerGenerationFailed(task) ? '生成卖点建议' : selectionFlow ? '确认核心卖点' : '规划图文内容', plannerGenerationFailed(task) ? 'evidence' : 'plan'], [adaptingPlatform ? '适配新平台资料' : selectionFlow ? '编排并生成图文' : '生成平台文案', 'draft'], ['核验并优化', 'draft']];
  return <section className="workflow-progress" aria-label="任务执行进度"><div className="workflow-steps">{steps.map(([name, tab], i) => { const status = states[i]; const Icon = status === 'done' ? Check : status === 'running' ? LoaderCircle : status === 'failed' ? CircleAlert : status === 'confirm' ? UserRound : Circle; return <button key={name} className={`workflow-step ${status}`} onClick={() => onOpen(tab)}><span className="step-icon"><Icon size={16} className={status === 'running' ? 'spin' : ''} aria-hidden="true" /></span><span><strong>{name}</strong><small>{labels[status]}</small></span></button>; })}</div>
    <details className="workflow-details"><summary><Clock3 size={15} aria-hidden="true" /><span>{BUSY.includes(task.status) ? '查看当前执行情况' : '查看任务过程'}</span></summary><p className="muted">{adaptingPlatform ? '已确认卖点保持完成；当前检查新平台所需的资料与图片，完成后进入写作。接口未单独报告每张图片的进度。' : '资料检索包含原文读取与素材整理；当前接口未单独报告细分进度。'}</p><ol>{task.events.slice(-8).reverse().map((e, i) => <li key={i}><time>{localTime(e.at)}</time><span>{e.text}</span></li>)}</ol>{!task.events.length && <p className="muted">任务已建立，等待分析。</p>}</details>
  </section>;
}
