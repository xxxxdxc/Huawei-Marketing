import { AlertCircle, CheckCircle2, FileSearch, ShieldCheck } from 'lucide-react';
import type { Task } from './types';
import { localTime } from './shared';

export default function ReviewPanel({ task, dirty, onLocate, onEvidence }: { task: Task; dirty: boolean; onLocate: (location: string) => void; onEvidence: () => void }) {
  const passed = task.can_export && !dirty;
  const report = task.review;
  const validationErrors = report?.validation_errors || [];
  const categories = [['fact', '参数与事实'], ['image', '图片与型号'], ['compliance', '营销合规'], ['evidence', '来源依据'], ['platform', '平台与结构']];
  return <section className="review-panel"><div className={`review-summary ${passed ? 'passed' : ''}`}><span className="review-symbol">{passed ? <CheckCircle2 size={26} aria-hidden="true" /> : <ShieldCheck size={26} aria-hidden="true" />}</span><div><h3>{dirty ? '修改后，等待重新核验' : passed ? '当前版本已核验' : validationErrors.length ? '核验意见需要复核' : report ? '仍有问题需要处理' : '当前版本待核验'}</h3><p>{dirty ? '下方报告对应上一次保存内容，不能证明本次编辑已通过。' : report?.summary || '保存修改后，检查事实、配图与营销合规。'}</p></div></div>
    {report && <p className="report-time">报告时间 {localTime(report.checked_at)}{dirty ? ' · 已过期' : ''}</p>}
    {report?.source_verification?.length ? <p className="notice warning">本次核验含用户补充原文，仅检查文稿与所提供资料的一致性；来源链接及原文真实性未独立验证。<button className="text-link" onClick={onEvidence}>查看补充依据</button></p> : null}
    {validationErrors.length > 0 && <div className="notice" role="status"><strong>原稿与配图已保留</strong><ul>{validationErrors.map((error, index) => <li key={index}>{error}</li>)}</ul><p>这些意见尚未被采纳为产品违规。请点击“重新核验”，无需重新选卖点或写稿。</p></div>}
    <div className="check-categories">{categories.map(([id, name]) => { const count = report?.issues.filter(i => i.category === id).length || 0; return <div key={id}><span>{name}</span><span className={passed ? 'text-success' : ''}>{dirty ? '待重验' : validationErrors.length ? '报告待复核' : count ? `${count} 项问题` : passed ? '已通过' : report ? '本次未报告问题' : '待检查'}</span></div>; })}</div>
    {report?.issues.map((issue, i) => {
      const exact = task.document?.paragraphs.filter(p => p.heading && p.heading === issue.location) || [];
      const locatable = exact.length === 1 || ['标题', '导语', '行动引导'].includes(issue.location);
      return <article className="review-issue" key={i}><div className="issue-heading"><AlertCircle size={17} aria-hidden="true" /><strong>{issue.location || '全文'}</strong><span>{issue.severity === 'error' ? '需要处理' : '提示'}</span></div><p>{issue.detail}</p><small>{issue.category === 'image' ? '请在配图编辑中核对或更换图片，保存后重新核验；文字修订不会自动换图。' : issue.repairable ? '可参考问题说明编辑，保存后重新核验。' : '需要补充或核对原始证据，不能手动标记通过。'}</small><div className="issue-actions">{locatable && <button type="button" className="text-link" onClick={() => onLocate(issue.location)}>定位到编辑位置</button>}<button type="button" className="text-link" onClick={onEvidence}><FileSearch size={14} aria-hidden="true" />查看本任务依据</button></div></article>;
    })}
{report?.scope_audit?.some(entry => entry.accepted === false) && <details className="revision-records"><summary>查看未采纳的核验意见</summary>{report.scope_audit.filter(entry => entry.accepted === false).map((entry, index) => <article key={index}><p>{entry.original_issue?.detail}</p><p className="muted">复核原因：{entry.reasons?.join("；")}</p></article>)}</details>}
    <details className="revision-records"><summary>运行与修订记录</summary><p className="muted">以下为任务实际记录，保留原始事件描述。</p>{task.events.length ? <ol>{task.events.map((event, i) => <li key={i}><time>{localTime(event.at)}</time><p>{event.text}</p></li>)}</ol> : <p className="muted">暂无运行记录。</p>}</details>
  </section>;
}
