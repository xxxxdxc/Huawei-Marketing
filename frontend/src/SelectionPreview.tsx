import { useState } from 'react';
import { Monitor, RotateCcw } from 'lucide-react';
import type { Plan, Task } from './types';
import { selectionPreviewTask, selectionPreviewComposition, selectionPreviewDocument } from './selectionPreviewData';
import PlanEditor from './PlanEditor';
import DraftEditor from './DraftEditor';
import { EvidenceDialog, type EvidenceTarget } from './Evidence';
import { Field, type Act } from './shared';

export default function SelectionPreview() {
  const initial = new URLSearchParams(location.search).get('platform') || 'xiaohongshu';
  const [task, setTask] = useState(() => selectionPreviewTask(['wechat', 'moments'].includes(initial) ? initial : 'xiaohongshu'));
  const [tab, setTab] = useState('plan'), [dirty, setDirty] = useState(false), [pending, setPending] = useState(false), [epoch, setEpoch] = useState(0), [message, setMessage] = useState(''), [target, setTarget] = useState<EvidenceTarget | null>(null);
  function reset(platform: string) {
    if (dirty && !window.confirm('有未保存的演示选择，确定放弃？')) return;
    setTask(selectionPreviewTask(platform)); setTab('plan'); setDirty(false); setEpoch(n => n + 1); setMessage('');
    history.replaceState(null, '', `?preview=planner-v3&platform=${platform}`);
  }
  async function simulateWriting(base: Task, ids: string[]) {
    const selected: Task = { ...base, status: 'writing', version: base.version + 1, plan: { ...base.plan!, phase: 'selection', sections: [], selected_point_ids: ids }, selection_confirmation: { selection_hash: 'local-demo-only', authorized_version: base.version + 1, at: new Date().toISOString() }, writer_stage: 'outlining', document: null, review: null, can_export: false };
    setTask(selected); setTab('draft');
    await new Promise(resolve => setTimeout(resolve, 500));
    const composed = { ...selectionPreviewComposition(selected, ids), version: selected.version + 1 }; setTask(composed);
    await new Promise(resolve => setTimeout(resolve, 500));
    setTask({ ...selectionPreviewDocument(composed), version: composed.version + 1 });
    setMessage('两个写作阶段已在本地模拟完成，没有额外大纲确认。当前演示稿未执行真实核验，不能导出。');
  }
  const act: Act = async (path, payload) => {
    setPending(true); setMessage('');
    const body = payload as { plan?: Plan; selected_point_ids?: string[]; platform?: string; document?: Task['document'] };
    try {
      if (path === '/replan-points') { setTask(old => ({ ...old, version: old.version + 1, plan: { ...old.plan!, selected_point_ids: body.selected_point_ids! } })); setMessage('演示卖点选择已保存。没有编排结构，也没有调用模型。'); }
      else if (path === '/confirm-plan') await simulateWriting(task, body.plan!.selected_point_ids!);
      else if (path === '/change-platform') await simulateWriting({ ...task, platform: body.platform!, brief: { ...task.brief!, platform: body.platform! } }, task.plan!.selected_point_ids!);
      else if (path === '/document') { setTask(old => ({ ...old, version: old.version + 1, document: body.document!, review: null, can_export: false })); setMessage('演示修改已保存，仍需真实核验。'); }
      else { setMessage('此演示不执行真实模型核验；请在实际工作台中运行。'); return false; }
      setDirty(false); return true;
    } finally { setPending(false); }
  };
  function switchTab(next: string) { if (pending || next === tab) return; if (dirty && !window.confirm('有未保存的演示修改，确定放弃并切换？')) return; setDirty(false); setTab(next); }
  return <main className="planner-preview-page"><header className="planner-preview-toolbar"><div><h1>从核心卖点到图文</h1><p>选材确认 → 自动编排与写作 → 核验编辑</p></div><div className="planner-preview-actions"><a className="secondary" href="/"><Monitor size={16} aria-hidden="true" />实际工作台</a><button className="secondary" disabled={pending} onClick={() => reset(task.platform)}><RotateCcw size={16} aria-hidden="true" />重置演示</button></div></header>
    <div className="planner-demo-banner">本地模拟数据与插图，不是 ima 资料或真实模型结果。演示确认会连续模拟结构规划和正文生成，不发送 API 写请求，不调用模型。</div>
    <Field label="演示发布平台"><select value={task.platform} disabled={pending} onChange={e => reset(e.target.value)}><option value="xiaohongshu">小红书</option><option value="wechat">微信公众号</option><option value="moments">门店朋友圈</option></select></Field>
    {message && <div className="notice" role="status">{message}</div>}
    <section className="workspace surface"><nav className="workspace-tabs" aria-label="职责迁移预览"><button className={tab === 'plan' ? 'active' : ''} disabled={pending} aria-current={tab === 'plan' ? 'page' : undefined} onClick={() => switchTab('plan')}>核心卖点</button><button className={tab === 'draft' ? 'active' : ''} disabled={pending} aria-current={tab === 'draft' ? 'page' : undefined} onClick={() => switchTab('draft')}>图文与核验</button></nav><div className="tab-content" key={`${tab}-${epoch}`}>
      {tab === 'plan' ? <PlanEditor task={task} locked={pending} act={act} onDirty={setDirty} onInspect={setTarget} /> : <DraftEditor key={task.version} task={task} locked={pending} act={act} onDirty={setDirty} onToast={setMessage} onError={setMessage} onInspect={setTarget} />}
    </div></section>{target && <EvidenceDialog task={task} target={target} onClose={() => setTarget(null)} />}
  </main>;
}
