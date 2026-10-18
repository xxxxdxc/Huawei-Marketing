import { Check, Circle, CircleAlert, Clock3, LoaderCircle, UserRound } from 'lucide-react';
import type { Task } from './types';
import { BUSY, effectiveStatus, evidencePaused, localTime } from './shared';

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
  if (evidencePaused(task)) { states[2] = 'failed'; states[3] = 'waiting'; states[5] = 'waiting'; }
  if (failed && state === 'plan_ready') { states[3] = 'done'; states[4] = 'failed'; }
  const labels: Record<string, string> = { done: '已完成', confirm: '需要你处理', running: '运行中', failed: '已暂停', waiting: '等待中' };
  const steps = [['理解营销需求', 'strategy'], ['检索产品资料', 'evidence'], ['整理事实与图片', 'evidence'], ['规划图文内容', 'plan'], ['生成平台文案', 'draft'], ['核验并优化', 'draft']];
  return <section className="workflow-progress" aria-label="任务执行进度"><div className="workflow-steps">{steps.map(([name, tab], i) => { const status = states[i]; const Icon = status === 'done' ? Check : status === 'running' ? LoaderCircle : status === 'failed' ? CircleAlert : status === 'confirm' ? UserRound : Circle; return <button key={name} className={`workflow-step ${status}`} onClick={() => onOpen(tab)}><span className="step-icon"><Icon size={16} className={status === 'running' ? 'spin' : ''} aria-hidden="true" /></span><span><strong>{name}</strong><small>{labels[status]}</small></span></button>; })}</div>
    <details className="workflow-details"><summary><Clock3 size={15} aria-hidden="true" /><span>{BUSY.includes(task.status) ? '查看当前执行情况' : '查看任务过程'}</span></summary><p className="muted">资料检索包含原文读取与素材整理；当前接口未单独报告细分进度。</p><ol>{task.events.slice(-8).reverse().map((e, i) => <li key={i}><time>{localTime(e.at)}</time><span>{e.text}</span></li>)}</ol>{!task.events.length && <p className="muted">任务已建立，等待分析。</p>}</details>
  </section>;
}
