import { useEffect, useState } from 'react';
import { CheckCircle2, ExternalLink, LoaderCircle, RefreshCw, Save, ShieldCheck } from 'lucide-react';
import type { Settings } from './types';
import { api, Badge, Empty, errorMessage, Field } from './shared';

export default function SettingsPage({ settings, onSaved, onDirty }: { settings: Settings | null; onSaved: (settings: Settings) => void; onDirty: (dirty: boolean) => void }) {
  const [form, setForm] = useState(settings), [key, setKey] = useState(''), [reviewKey, setReviewKey] = useState('');
  const [busy, setBusy] = useState(false), [result, setResult] = useState(''), [error, setError] = useState('');
  useEffect(() => setForm(settings), [settings]);
  useEffect(() => { onDirty(Boolean(key || reviewKey) || JSON.stringify(form) !== JSON.stringify(settings)); }, [form, settings, key, reviewKey, onDirty]);
  async function save(probe: boolean) {
    if (!form) return;
    setBusy(true); setError(''); setResult('');
    try {
      const { base_url, writer_model, reviewer_model, vision } = form;
      const saved = await api<Settings>('/settings', 'PUT', { base_url, writer_model, reviewer_model, vision, api_key: key || null, ...('has_reviewer_key' in form ? { reviewer_api_key: reviewKey || null } : {}) });
      setKey(''); setReviewKey(''); setForm(saved); onSaved(saved);
      if (probe) { const response = await api<{ writer_available: boolean; reviewer_available: boolean; note: string }>('/settings/probe', 'POST'); setResult(`${response.note}；写作模型${response.writer_available ? '可见' : '未出现在列表'}，核验模型${response.reviewer_available ? '可见' : '未出现在列表'}。`); }
      else setResult('连接设置已保存。');
    } catch (e) { setError(errorMessage(e)); } finally { setBusy(false); }
  }
  if (!form) return <Empty title="正在读取连接设置…" text="若长时间没有响应，请检查本机后端连接，再刷新页面。" />;
  return <><div className="page-heading"><div><p className="overline">本机连接</p><h1>连接模型与产品资料</h1><p>配置保存在本机，已保存密钥不会返回浏览器。</p></div></div><div className="settings-layout"><form className="surface settings-card" onSubmit={e => { e.preventDefault(); void save(false); }}><fieldset disabled={busy}><div className="section-heading"><div><h2>模型服务</h2><p>用于需求理解、创作与独立核验。</p></div></div><Field label="API Base URL"><input required type="url" spellCheck={false} value={form.base_url} onChange={e => setForm({ ...form, base_url: e.target.value })} /></Field><Field label="API Key" hint={form.has_key ? '已保存；留空保留原值。' : '保存后输入框会清空。'}><input type="password" autoComplete="new-password" value={key} placeholder={form.has_key ? '已配置，留空保留…' : '输入模型服务密钥…'} onChange={e => setKey(e.target.value)} /></Field>{'has_reviewer_key' in form && <Field label="独立核验 API Key（可选）" hint={form.has_reviewer_key ? '已配置独立核验密钥；留空保留原值。' : '未配置时沿用写作密钥；不同模型需要不同密钥时填写。'}><input type="password" autoComplete="new-password" value={reviewKey} placeholder="输入独立核验密钥…" onChange={e => setReviewKey(e.target.value)} /></Field>}<div className="two-fields"><Field label="理解、规划与写作模型"><input required spellCheck={false} value={form.writer_model} onChange={e => setForm({ ...form, writer_model: e.target.value })} /></Field><Field label="图片理解与核验模型"><input required spellCheck={false} value={form.reviewer_model} onChange={e => setForm({ ...form, reviewer_model: e.target.value })} /></Field></div><label className="toggle-field"><input type="checkbox" name="vision" checked={form.vision} onChange={e => setForm({ ...form, vision: e.target.checked })} /><span><strong>启用实际图片理解</strong><p>检查候选图片的实际画面。关闭后，图文不会标记为完整核验通过。</p></span></label><div className="settings-help"><ExternalLink size={15} aria-hidden="true" /><a href="https://credits.openai-next.com/guide/quickstart" target="_blank" rel="noreferrer">查看服务接入指南</a><span>凭证保护：{form.credential_storage}</span></div>{error && <div className="notice warning" role="alert">{error}</div>}{result && <div className="success-note" role="status"><CheckCircle2 size={17} aria-hidden="true" /> {result}</div>}<div className="action-bar"><button className="secondary" type="submit"><Save size={16} aria-hidden="true" />保存设置</button><button className="primary" type="button" disabled={busy || (!key && !form.has_key)} onClick={() => save(true)}>{busy ? <LoaderCircle className="spin" size={16} aria-hidden="true" /> : <RefreshCw size={16} aria-hidden="true" />}保存并测试连接</button></div><p className="export-note">连接测试只读取模型列表，不执行生成。文本、图片输入及输出质量需通过真实任务验证。</p></fieldset></form><aside className="start-aside"><div className="flow-card"><p className="overline">产品资料</p><h3>事实与图片<br />来自指定 ima 库</h3><Badge good={form.ima_ready}>{form.ima_ready ? '本机凭证已配置' : '本机凭证待配置'}</Badge><p>任德耀新建华为PC知识库</p><p>实际访问状态以工作台读取产品目录的结果为准。</p></div><div className="quiet-card"><ShieldCheck size={22} aria-hidden="true" /><h4>模型判断，证据支撑</h4><p>不同模型交叉核验，也需要保留原文、型号和适用条件。</p></div></aside></div></>;
}
