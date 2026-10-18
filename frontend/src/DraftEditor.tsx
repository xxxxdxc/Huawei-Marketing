import { useState } from 'react';
import { BookOpen, CheckCircle2, Copy, Download, FileText, RefreshCw, Save, Settings2 } from 'lucide-react';
import type { Doc, Paragraph, Task } from './types';
import { api, AssetImage, effectiveStatus, Empty, errorMessage, Field, PLATFORMS, POLICIES, type Act } from './shared';
import { ImagePicker } from './PlanEditor';
import PlatformPreview from './PlatformPreview';
import ReviewPanel from './ReviewPanel';
import Dialog from './Dialog';
import type { EvidenceTarget } from './Evidence';

export default function DraftEditor({ task, locked, act, onDirty, onToast, onError, onInspect, initialPanel = 'preview' }: { task: Task; locked: boolean; act: Act; onDirty: (dirty: boolean) => void; onToast: (message: string) => void; onError: (message: string) => void; onInspect: (target: EvidenceTarget) => void; initialPanel?: string }) {
  const [doc, setDoc] = useState<Doc | null>(() => task.document ? structuredClone(task.document) : null), [dirty, setDirty] = useState(false);
  const [panel, setPanel] = useState(initialPanel), [mobilePane, setMobilePane] = useState('editor'), [platformModal, setPlatformModal] = useState(false), [targetPlatform, setTargetPlatform] = useState(task.brief?.platform || task.platform), [exporting, setExporting] = useState(false);
  const [tags, setTags] = useState(task.document?.tags.join(' ') || '');
  const platform = task.brief?.platform || task.platform, policy = POLICIES[platform];
  const editable = !locked && ['approved', 'needs_review'].includes(effectiveStatus(task));
  const allowed = task.can_export && !dirty && !locked && !exporting;
  function change(patch: Partial<Doc>) { setDoc(d => d ? { ...d, ...patch } : d); setDirty(true); onDirty(true); }
  function paragraph(index: number, patch: Partial<Paragraph>) { if (doc) change({ paragraphs: doc.paragraphs.map((p, i) => i === index ? { ...p, ...patch } : p) }); }
  async function exportCurrent(kind: 'copy' | 'md' | 'zip') {
    if (!allowed) return;
    setExporting(true);
    try {
      const current = await api<Task>('/tasks/' + task.id);
      if (current.version !== task.version || !current.can_export) throw new Error('任务已更新或当前版本未核验，请重新载入后再导出。');
      const response = await fetch(`/api/tasks/${encodeURIComponent(task.id)}/export${kind === 'zip' ? '?bundle=true' : ''}`);
      if (!response.ok) { const data = await response.json().catch(() => null); throw new Error(typeof data?.detail === 'string' ? data.detail : '导出未完成，请重新核验当前版本后重试。'); }
      if (kind === 'copy') { await response.text(); const d = current.document!; await navigator.clipboard.writeText([d.title, d.lead, ...d.paragraphs.flatMap(p => [p.heading, p.text, p.caption]), d.cta, d.tags.join(' ')].filter(Boolean).join('\n\n')); onToast('已复制当前核验版本的文案'); }
      else { const blob = await response.blob(), url = URL.createObjectURL(blob); const link = document.createElement('a'); link.href = url; link.download = kind === 'zip' ? 'marketing-bundle.zip' : 'marketing.md'; link.click(); setTimeout(() => URL.revokeObjectURL(url), 30000); onToast('已下载当前核验版本'); }
    } catch (e) { onError(errorMessage(e)); } finally { setExporting(false); }
  }
  function locate(location: string) {
    setMobilePane('editor');
    const index = doc?.paragraphs.findIndex(p => p.heading === location) ?? -1;
    const id = location === '标题' ? 'edit-title' : location === '导语' ? 'edit-lead' : location === '行动引导' ? 'edit-cta' : `edit-paragraph-${index}`;
    requestAnimationFrame(() => { const area = document.getElementById(id); area?.scrollIntoView({ behavior: 'instant', block: 'center' }); area?.querySelector<HTMLElement>('input,textarea')?.focus(); });
  }
  if (!doc) return <Empty icon={<FileText />} title="确认规划后，生成完整图文" text="先完成营销策略与内容规划两次确认，成稿和核验报告会显示在这里。" />;
  const used = doc.paragraphs.map(p => p.image_id).filter((id): id is string => Boolean(id));
  const firstFact = task.package?.facts[0];
  return <><div className="section-heading draft-heading"><div><h2>把内容打磨到可以交付</h2><p>直接编辑文字与配图，右侧预览随内容更新。</p></div><button className="secondary" disabled={locked || dirty} onClick={() => setPlatformModal(true)}><Settings2 size={16} aria-hidden="true" />更换目标平台</button></div>
    <div className={`save-state ${dirty ? 'is-dirty' : ''}`} role="status"><span>{dirty ? '有未保存修改 · 保存后需要重新核验' : `已保存 V${task.version}${task.can_export ? ' · 已核验' : ' · 待核验或处理问题'}`}</span><span>{PLATFORMS[platform]} · {used.length} 张配图</span></div>
    <div className="segmented mobile-pane-toggle">{[['editor', '编辑内容'], ['preview', '预览与核验']].map(([id, label]) => <button key={id} aria-pressed={mobilePane === id} onClick={() => setMobilePane(id)}>{label}</button>)}</div>
    <div className={`creation-grid show-${mobilePane}`}><section className="document-editor" aria-label="图文编辑区"><div className="editor-section" id="edit-title"><Field label="标题"><input disabled={!editable} className="title-input" value={doc.title} onChange={e => change({ title: e.target.value })} /></Field></div><div className="editor-section" id="edit-lead"><Field label="导语"><textarea disabled={!editable} value={doc.lead} onChange={e => change({ lead: e.target.value })} /></Field></div>
      {doc.paragraphs.map((p, i) => { const image = task.package?.images.find(im => im.id === p.image_id); return <section className="editor-section" key={p.section_id} id={`edit-paragraph-${i}`}><div className="paragraph-label"><span>段落 {i + 1}</span><div className="reference-links">{p.fact_ids.map(id => <button className="reference-chip" key={id} onClick={() => onInspect({ type: 'fact', id })}><BookOpen size={13} aria-hidden="true" />依据 {(task.package?.facts.findIndex(f => f.id === id) ?? -1) + 1}</button>)}</div></div><Field label={`段落 ${i + 1} 标题`}><input disabled={!editable} value={p.heading} onChange={e => paragraph(i, { heading: e.target.value })} /></Field><Field label={`段落 ${i + 1} 正文`}><textarea disabled={!editable} rows={5} value={p.text} onChange={e => paragraph(i, { text: e.target.value })} /></Field>{image && <figure className="editor-figure"><AssetImage key={image.id} asset={image} /><figcaption><button className="text-link" onClick={() => onInspect({ type: 'image', id: image.id })}>查看当前图片来源</button></figcaption></figure>}<details className="replace-image"><summary>{image ? '更换本段配图' : '为本段选择配图'}</summary><ImagePicker images={task.package?.images || []} value={p.image_id} used={used} disabled={!editable} onChange={im => paragraph(i, { image_id: im?.id || null, caption: im?.description || '' })} onInspect={onInspect} /><p className="muted">仅限当前产品资料中的图片；换图后需重新核验。</p></details>{image && <Field label={`段落 ${i + 1} 图片说明`}><input disabled={!editable} value={p.caption} onChange={e => paragraph(i, { caption: e.target.value })} /></Field>}</section>; })}
      <div className="editor-section" id="edit-cta"><Field label="行动引导"><textarea disabled={!editable} value={doc.cta} onChange={e => change({ cta: e.target.value })} /></Field><Field label="平台标签" hint="用空格分隔标签。"><input disabled={!editable} value={tags} onChange={e => { setTags(e.target.value); change({ tags: e.target.value.split(/\s+/).filter(Boolean) }); }} /></Field></div>
    </section><aside className="preview-column"><div className="preview-toolbar"><span>{PLATFORMS[platform]}</span><div className="segmented">{[['preview', '预览'], ['review', '核验'], ['evidence', '依据']].map(([id, label]) => <button key={id} aria-pressed={panel === id} onClick={() => setPanel(id)}>{label}</button>)}</div></div>
      {panel === 'preview' ? <><p className="preview-disclaimer">阅读效果预览，尚未发布</p><PlatformPreview document={doc} task={task} /><div className="platform-policy"><strong>当前平台创作提示</strong><p>{policy.note}</p><span>配图要求：{policy.min}–{policy.max} 张不同图片</span></div></> : panel === 'review' ? <ReviewPanel task={task} dirty={dirty} onLocate={locate} onEvidence={() => setPanel('evidence')} /> : <div className="draft-evidence"><h3>本任务事实依据</h3><p className="muted">点击依据可查看限定条件与完整原文。</p>{task.package?.facts.map((f, i) => <button className="evidence-link" key={f.id} onClick={() => onInspect({ type: 'fact', id: f.id })}><span>{i + 1}</span><strong>{f.claim}</strong><BookOpen size={15} aria-hidden="true" /></button>)}{!firstFact && <p className="notice">当前没有可用事实依据，需补充资料后核验。</p>}</div>}
    </aside></div>
    <div className="draft-action-bar"><div className="edit-actions"><button className="primary" disabled={!editable || !dirty || !doc.title.trim()} onClick={() => act('/document', { version: task.version, document: doc }, 'PUT')}><Save size={16} aria-hidden="true" />保存修改</button><button className="secondary" disabled={!editable || dirty} onClick={() => { setPanel('review'); void act('/review', { version: task.version }); }}><RefreshCw size={16} aria-hidden="true" />重新核验</button>{dirty && <button className="text-link" disabled={locked} onClick={() => { if (window.confirm('放弃本次未保存修改，恢复已保存的图文？')) { setDoc(structuredClone(task.document)); setTags(task.document?.tags.join(' ') || ''); setDirty(false); onDirty(false); } }}>撤销编辑</button>}</div><div className="export-actions"><button className="secondary" disabled={!allowed} onClick={() => exportCurrent('copy')}><Copy size={15} aria-hidden="true" />复制</button><button className="secondary" disabled={!allowed} onClick={() => exportCurrent('md')}><Download size={15} aria-hidden="true" />Markdown</button><button className="secondary" disabled={!allowed} onClick={() => exportCurrent('zip')}><Download size={15} aria-hidden="true" />图文包</button></div></div>
    <p className="export-note">{allowed ? <><CheckCircle2 size={14} aria-hidden="true" />当前版本可交付。图文包包含 Markdown、实际配图与核验记录。</> : '仅当前已核验且没有未保存修改的版本可复制或导出。'}</p>
    {platformModal && <Dialog title="更换目标平台" onClose={() => setPlatformModal(false)}><p className="section-intro">新平台会重新应用内容结构、语气与配图规则，并回到策略确认。原稿保留在版本记录中。</p><Field label="新目标平台"><select value={targetPlatform} onChange={e => setTargetPlatform(e.target.value)}>{Object.entries(PLATFORMS).map(([id, label]) => <option key={id} value={id}>{label}</option>)}</select></Field><div className="action-bar"><button className="secondary" onClick={() => setPlatformModal(false)}>取消</button><button className="primary" disabled={locked || dirty || targetPlatform === platform} onClick={async () => { if (await act('/modify', { version: task.version, instruction: `将目标发布平台改为${PLATFORMS[targetPlatform]}，保留产品型号、人群和营销目标，重新应用该平台的内容与配图规则。` })) setPlatformModal(false); }}>更换平台并重新分析</button></div></Dialog>}
  </>;
}
