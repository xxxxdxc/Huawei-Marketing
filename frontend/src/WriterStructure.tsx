import type { Task, Section } from './types';
import type { EvidenceTarget } from './Evidence';

type Props = { task: Task; onInspect: (target: EvidenceTarget) => void };
export default function WriterStructure({ task, onInspect }: Props) {
  const outline = task.writer_outline;
  const sections: (Section & { connection_to_previous?: string; reader_progress?: string })[] = outline?.sections || (task.plan?.phase === 'composed' ? task.plan.sections : []);
  if (!sections.length) return null;
  return <details className="writer-structure"><summary>查看自动编排记录</summary>
    <p>由写作环节自动完成，供查看内容主线与证据承接，无需额外确认。这是初稿结构记录，后续正文编辑不会自动改写它。</p>
    {outline?.main_takeaway && <p><strong>内容主线：</strong>{outline.main_takeaway}</p>}
    {(outline?.composition_rationale || task.plan?.composition_rationale) && <p><strong>编排考虑：</strong>{outline?.composition_rationale || task.plan?.composition_rationale}</p>}
    <ol>{sections.map(section => <li key={section.id}><strong>{section.heading}</strong><p>{section.purpose}</p>{'connection_to_previous' in section && section.connection_to_previous && <p>与上一段衔接：{section.connection_to_previous}</p>}{'reader_progress' in section && section.reader_progress && <p>读者进展：{section.reader_progress}</p>}<div className="reference-links">{section.fact_ids.map(id => <button className="reference-chip" type="button" key={id} onClick={() => onInspect({ type: 'fact', id })}>{id} · 查看依据</button>)}{section.image_id && <button className="text-link" type="button" onClick={() => onInspect({ type: 'image', id: section.image_id! })}>查看本段配图来源</button>}</div></li>)}</ol>
  </details>;
}
