import { useState } from 'react';
import { Monitor, RotateCcw } from 'lucide-react';
import type { Plan } from './types';
import { plannerPreviewTask, previewPointPlan } from './plannerPreviewData';
import PlanEditor from './PlanEditor';
import { EvidenceDialog, type EvidenceTarget } from './Evidence';
import { Field } from './shared';

export default function PlannerPreview() {
  const initial = new URLSearchParams(location.search).get('platform') || 'xiaohongshu';
  const [task, setTask] = useState(() => plannerPreviewTask(['wechat', 'moments'].includes(initial) ? initial : 'xiaohongshu'));
  const [pending, setPending] = useState(false), [epoch, setEpoch] = useState(0), [versions, setVersions] = useState<{ version: number; plan: Plan }[]>([]);
  const [dirty, setDirty] = useState(false), [message, setMessage] = useState(''), [target, setTarget] = useState<EvidenceTarget | null>(null);
  function reset(platform: string) {
    if (dirty && !window.confirm('有未保存的演示修改，确定放弃并重新载入？')) return;
    setTask(plannerPreviewTask(platform)); setDirty(false); setMessage(''); setVersions([]); setEpoch(n => n + 1);
    history.replaceState(null, '', `?preview=planner-v2&platform=${platform}`);
  }
  return <main className="planner-preview-page"><header className="planner-preview-toolbar"><div><h1>图文规划工作台</h1><p>Planner V2 · 本地交互预览</p></div><div className="planner-preview-actions"><a className="secondary" href="/"><Monitor size={16} aria-hidden="true" />进入实际工作台</a><button className="secondary" disabled={pending} onClick={() => reset(task.platform)}><RotateCcw size={16} aria-hidden="true" />重置演示</button></div></header>
    <div className="planner-demo-banner">模拟数据 · 非真实 ima 资料、产品参数或模型评分。保存仅更新此演示页，确认不会调用模型或修改真实任务。</div>
    <Field label="演示发布平台"><select disabled={pending} value={task.platform} onChange={e => reset(e.target.value)}><option value="xiaohongshu">小红书</option><option value="wechat">微信公众号</option><option value="moments">门店朋友圈</option></select></Field>
    {message && <div className="notice planner-preview-status" role="status">{message}</div>}
    <div className="surface planner-preview-body"><PlanEditor key={`${task.platform}-${epoch}`} task={task} locked={pending} onDirty={setDirty} onInspect={setTarget} act={async (path, payload) => {
      setPending(true);
      setVersions(old => [{ version: task.version, plan: structuredClone(task.plan!) }, ...old].slice(0, 8));
      if (path === '/replan-points') {
        const { selected_point_ids } = payload as { selected_point_ids: string[] };
        setTask(old => ({ ...old, status: 'planning', version: old.version + 1 }));
        await new Promise(resolve => setTimeout(resolve, 450));
        const plan = previewPointPlan(task, selected_point_ids);
        setTask(old => ({ ...old, status: 'plan_ready', version: old.version + 1, plan }));
        setMessage('演示大纲已按所选卖点更新，旧版本已保留。还没有开始写稿。');
      } else {
        const { plan } = payload as { plan: Plan };
        setTask(old => ({ ...old, version: old.version + 1, plan: { ...structuredClone(plan), planning_analysis: { ...old.plan!.planning_analysis!, status: 'user_modified' } } }));
        setMessage(path === '/confirm-plan' ? '演示规划已确认。本页不执行写稿；实际工作台会在此开始生成。' : '演示修改已保存。原评分仅保留为生成时记录。');
      }
      setPending(false); setDirty(false);
      return true;
    }} /></div>{versions.length > 0 && <details className="planner-preview-versions"><summary>演示版本记录 · {versions.length} 个旧版本</summary>{versions.map((version, index) => <div className="history-row" key={`${version.version}-${index}`}><div><strong>V{version.version} · {version.plan.sections.length} 个段落</strong><small>{version.plan.selected_point_ids?.length || 0} 个选用卖点</small></div><button className="secondary" disabled={pending} onClick={() => { if (dirty && !window.confirm('有未保存演示编辑，确定放弃并恢复？')) return; setTask(old => ({ ...old, version: old.version + 1, plan: structuredClone(version.plan) })); setMessage('旧演示版本已恢复，需重新确认规划。'); }}>恢复此演示版本</button></div>)}</details>}{target && <EvidenceDialog task={task} target={target} onClose={() => setTarget(null)} />}
  </main>;
}
