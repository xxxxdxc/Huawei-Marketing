import { useCallback, useEffect, useState } from 'react';
import { AlertCircle, History, LoaderCircle, MessageSquarePlus } from 'lucide-react';
import type { Product, Task } from './types';
import { api, Badge, BUSY, evidencePaused, canResumePlan, effectiveStatus, errorMessage, Field, localTime, PLATFORMS, STATUS, type Act } from './shared';
import { Strategy } from './StrategyEvidence';
import Evidence, { EvidenceDialog, type EvidenceTarget } from './Evidence';
import PlanEditor from './PlanEditor';
import DraftEditor from './DraftEditor';
import Dialog from './Dialog';
import WorkflowProgress from './WorkflowProgress';
import EvidenceResolution from './EvidenceResolution';

type HistoryEntry = { version: number; note: string; at: string };
function defaultTab(task: Task) { const state = effectiveStatus(task); return ['draft', 'analyzing', 'needs_information', 'brief_ready'].includes(state) ? 'strategy' : ['retrieving', 'planning'].includes(task.status) ? 'evidence' : state === 'plan_ready' ? 'plan' : task.document ? 'draft' : 'evidence'; }
export default function TaskView({ task, products, pending, act, onDirty, onToast, onError, onReload }: { task: Task; products: Product[]; pending: boolean; act: Act; onDirty: (dirty: boolean) => void; onToast: (message: string) => void; onError: (message: string) => void; onReload: () => void }) {
  const [tab, setTab] = useState(() => defaultTab(task)), [dirty, setDirty] = useState(false), [instruction, setInstruction] = useState('');
  const [history, setHistory] = useState<HistoryEntry[] | null>(null), [historyLoading, setHistoryLoading] = useState(false), [target, setTarget] = useState<EvidenceTarget | null>(null);
  const busy = BUSY.includes(task.status), locked = busy || pending;
  const product = task.package?.product || products.find(p => p.id === task.product_id);
  const changed = useCallback((value: boolean) => setDirty(value), []);
  useEffect(() => onDirty(dirty || Boolean(instruction.trim())), [dirty, instruction, onDirty]);
  useEffect(() => { setTab(defaultTab(task)); }, [task.id, task.status]);
  useEffect(() => { changed(false); setInstruction(''); }, [task.version, changed]);
  function switchTab(next: string) { if (next === tab) return; if ((dirty || instruction.trim()) && !window.confirm('有未保存修改。选择“确定”放弃并切换，选择“取消”继续编辑。')) return; changed(false); setInstruction(''); setTab(next); }
  async function loadHistory() { setHistoryLoading(true); try { setHistory(await api<HistoryEntry[]>('/tasks/' + task.id + '/history')); } catch (e) { onError(errorMessage(e)); } finally { setHistoryLoading(false); } }
  const pausedAtEvidence = evidencePaused(task);
  const errorStage = pausedAtEvidence ? '资料检查' : effectiveStatus(task) === 'draft' ? '需求分析' : effectiveStatus(task) === 'brief_ready' ? '资料读取与规划' : effectiveStatus(task) === 'plan_ready' ? '图文生成' : '内容核验';
  const conversational = ['draft', 'analyzing', 'needs_information', 'brief_ready'].includes(effectiveStatus(task)) && !task.plan && !task.document;
  if (conversational) return <div className="conversation-task"><header className="conversation-title"><span>需求对话</span><h1>一起找到这篇图文的方向</h1><p>聊清产品、人群和场景，再开始查证与创作。</p></header>{task.error && <div className="error-banner" role="alert"><div><strong>{errorStage}已暂停</strong><p>{task.error}</p>{effectiveStatus(task) === 'brief_ready' && <button className="secondary" disabled={locked} onClick={() => act('/analyze', { version: task.version })}>重新分析需求</button>}</div></div>}<Strategy key={task.version} task={task} locked={locked} act={act} onDirty={changed} /></div>;
  return <><header className="task-heading"><div><p className="overline">营销任务</p><h1>{product?.name || task.title || '产品图文'}<Badge good={task.can_export && !dirty}>{dirty ? '未保存修改' : pausedAtEvidence ? '资料检查待处理' : STATUS[task.status] || task.status}</Badge></h1></div><button className="secondary" disabled={historyLoading} onClick={loadHistory}><History size={16} aria-hidden="true" />{historyLoading ? '读取中…' : '版本记录'}</button></header>
    <dl className="task-context"><div><dt>人群</dt><dd>{task.brief?.audience || '待分析'}</dd></div><div><dt>场景</dt><dd>{task.brief?.scenario || '待分析'}</dd></div><div><dt>平台</dt><dd>{PLATFORMS[task.brief?.platform || task.platform]}</dd></div><div><dt>保存</dt><dd>{dirty ? '有未保存修改' : `本机 V${task.version}`}</dd></div></dl>
    <WorkflowProgress task={task} dirty={dirty} onOpen={switchTab} />
    {task.error && <div className="error-banner" role="alert"><AlertCircle size={21} aria-hidden="true" /><div><strong>{errorStage}已暂停</strong><p>{task.error}</p><p>{pausedAtEvidence ? '请在知识库依据中查看未满足项，选择调整内容、补充资料或重新描述需求。' : '已保留可用中间结果。请先处理上述原因，再回到对应阶段重试。'}</p><button className="text-link" disabled={locked} onClick={() => switchTab(defaultTab(task))}>查看当前可继续的步骤</button></div></div>}
    {task.package?.content_policy?.notices.map((notice, i) => <div className="notice" role="status" key={i}>{notice}</div>)}
    {canResumePlan(task) && !task.brief_analysis && <div className="notice"><p>此任务保留了检索资料。按当前规则重新检查后，可继续规划；核心证据缺失仍会暂停，完成后仍需你确认规划。</p><button className="secondary" disabled={locked || dirty || Boolean(instruction.trim())} onClick={() => act('/resume-plan', { version: task.version })}>{pending ? '正在提交…' : '按当前规则继续规划'}</button></div>}
    <section className="workspace surface"><nav className="workspace-tabs" aria-label="任务工作区">{[['strategy', '场景与策略'], ['evidence', '知识库依据'], ['plan', '内容规划'], ['draft', '图文与核验']].map(([id, label]) => <button key={id} aria-current={tab === id ? 'page' : undefined} className={tab === id ? 'active' : ''} onClick={() => switchTab(id)}>{label}{id === 'plan' && task.status === 'plan_ready' && <span className="tab-dot" />}</button>)}</nav>
      {busy && <div className="progress-note" role="status"><LoaderCircle size={17} className="spin" aria-hidden="true" /><span>{STATUS[task.status]}，进度会自动更新。可展开上方过程查看实际记录。</span></div>}
      <div className={`tab-content ${tab === 'draft' ? 'draft-content' : ''}`} key={`${tab}-${task.version}`}>
        {tab === 'strategy' ? <Strategy task={task} locked={locked} act={act} onDirty={changed} /> : tab === 'evidence' ? <>{task.brief_analysis?.retrieval_plan && task.package?.coverage && !task.document && !busy && <EvidenceResolution task={task} locked={locked || Boolean(instruction.trim())} act={act} onDirty={changed} onInspect={setTarget} onReload={onReload} />}<Evidence task={task} onInspect={setTarget} /></> : tab === 'plan' ? <PlanEditor task={task} locked={locked} act={act} onDirty={changed} onInspect={setTarget} /> : <DraftEditor task={task} locked={locked} act={act} onDirty={changed} onToast={onToast} onError={onError} onInspect={setTarget} initialPanel={task.review && !task.can_export ? 'review' : 'preview'} />}
      </div>
      {!busy && <details className="modify-task"><summary><MessageSquarePlus size={17} aria-hidden="true" />调整任务目标或平台<span>重新进入策略确认</span></summary><Field label="新的修改要求" hint="用于更改目标、场景或平台。细小文字修改请直接在图文编辑区完成。"><textarea maxLength={4000} disabled={locked} value={instruction} onChange={e => setInstruction(e.target.value)} placeholder="例如：改成门店朋友圈，聚焦出差办公场景…" /></Field><button className="secondary" disabled={locked || dirty || instruction.trim().length < 2} onClick={async () => { if (window.confirm('这会重新分析需求，原稿仍保留在版本记录中。继续？')) { if (await act('/modify', { version: task.version, instruction })) setInstruction(''); } }}>提交要求，重新分析</button>{dirty && <p className="muted">请先保存或撤销当前编辑，再修改任务目标。</p>}</details>}
    </section>
    {target && <EvidenceDialog task={task} target={target} onClose={() => setTarget(null)} />}
    {history && <Dialog title="版本记录" onClose={() => setHistory(null)} wide><p className="section-intro">恢复会新建一个版本，保留历史，并使旧核验结果失效。</p>{history.length ? history.map(h => <div className="history-row" key={h.version}><span className="version-label">V{h.version}</span><div><strong>{h.note}</strong><small>{localTime(h.at)}</small></div><button className="secondary" disabled={locked || h.version === task.version} onClick={async () => { if (window.confirm(`恢复到 V${h.version}？${dirty ? '当前未保存编辑将被放弃。' : ''}恢复后需要重新核验。`)) { if (await act('/restore', { version: task.version, target_version: h.version })) setHistory(null); } }}>{h.version === task.version ? '当前版本' : '恢复'}</button></div>) : <p className="notice">暂无历史版本。</p>}</Dialog>}
  </>;
}
