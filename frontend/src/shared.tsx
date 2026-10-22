import type { ReactNode, ReactElement, HTMLAttributes } from 'react';
import { cloneElement, isValidElement, useId } from 'react';
import { FileText, ImageOff } from 'lucide-react';
import { useState } from 'react';
import type { Task, Asset } from './types';
import { isPlatformAdaptation } from './platformPresentation';

export const PLATFORMS: Record<string, string> = { xiaohongshu: '小红书', wechat: '微信公众号', moments: '门店朋友圈' };
export const POLICIES: Record<string, { min: number; max: number; recommended?: string; note: string }> = {
  xiaohongshu: { min: 1, max: Infinity, recommended: '3–6', note: '用具体场景展开，短段落配合话题标签；不编造亲身体验。' },
  wechat: { min: 2, max: 4, note: '用导语、分节说明与行动引导组织完整文章。' },
  moments: { min: 1, max: 3, note: '聚焦一个核心卖点，用简短场景引导咨询或到店。' },
};
export const STATUS: Record<string, string> = { draft: '待分析', analyzing: '理解需求中', needs_information: '待补充信息', brief_ready: '待确认策略', retrieving: '检索与整理资料中', planning: '规划内容中', plan_ready: '待确认规划', writing: '生成图文中', reviewing: '核验中', approved: '已核验', needs_review: '待核验 / 处理问题', error: '已暂停' };
export const BUSY = ['analyzing', 'retrieving', 'planning', 'writing', 'reviewing'];
export const effectiveStatus = (task: Task) => task.status === 'error' ? task.resume_status : task.status;
export const errorMessage = (e: unknown) => e instanceof Error ? e.message : '操作未完成，请重试。';
export class ApiError extends Error { constructor(message: string, public status: number) { super(message); } }
export async function api<T>(path: string, method = 'GET', data?: unknown, signal?: AbortSignal): Promise<T> {
  let res: Response;
  try { res = await fetch('/api' + path, { method, signal, headers: data === undefined ? undefined : { 'Content-Type': 'application/json' }, body: data === undefined ? undefined : JSON.stringify(data) }); }
  catch (e) { if ((e as Error).name === 'AbortError') throw e; throw new ApiError('无法连接本机服务。请确认后端正在运行，然后重试。', 0); }
  if (!res.ok) {
    const d = await res.json().catch(() => null);
    const detail = typeof d?.detail === 'string' ? d.detail : Array.isArray(d?.detail) ? d.detail.map((x: { loc?: string[]; msg?: string }) => `${x.loc?.slice(1).join(' / ') || '输入'}：${x.msg || '格式不正确'}`).join('；') : `请求未完成（${res.status}），请稍后重试。`;
    throw new ApiError(res.status === 409 ? '任务已更新。请重新载入最新版本，再继续编辑。当前未保存内容仍保留在页面中。' : detail, res.status);
  }
  return res.json();
}
export type Act = (path: string, body: unknown, method?: string) => Promise<boolean>;
export function Field({ label, children, hint }: { label: string; children: ReactNode; hint?: string }) {
  const id = useId();
  const control = isValidElement(children) ? cloneElement(children as ReactElement<HTMLAttributes<HTMLElement>>, { id, 'aria-describedby': hint ? `${id}-hint` : undefined, ...(['input', 'select', 'textarea'].includes(String(children.type)) ? { name: id, autoComplete: (children.props as { autoComplete?: string }).autoComplete || 'off' } : {}) }) : children;
  return <div className="field"><label htmlFor={id}>{label}</label>{control}{hint && <small id={`${id}-hint`}>{hint}</small>}</div>;
}
export function Badge({ children, good = false }: { children: ReactNode; good?: boolean }) { return <span className={`badge ${good ? 'good' : ''}`}>{children}</span>; }
export function Empty({ title, text, action, icon }: { title: string; text: string; action?: ReactNode; icon?: ReactNode }) { return <div className="empty"><span className="empty-icon" aria-hidden="true">{icon || <FileText size={26} />}</span><h2>{title}</h2><p>{text}</p>{action}</div>; }
export function AssetImage({ asset, className = '' }: { asset: Asset; className?: string }) {
  const [failed, setFailed] = useState(false);
  if (failed) return <div className={`image-unavailable ${className}`} role="img" aria-label={`${asset.description || asset.name}，图片加载失败`}><ImageOff size={22} aria-hidden="true" /><span>图片暂不可用</span></div>;
  return <img className={className} src={import.meta.env.DEV && asset.id.startsWith('demo-planner-') && asset.url.startsWith('/planner-preview/') ? asset.url : `/api/assets/${encodeURIComponent(asset.id)}`} width={640} height={420} loading="lazy" alt={asset.description || asset.name} onError={() => setFailed(true)} />;
}
export function sourceLabel(value: string) { return value.replace(/https?:\/\/\S+/g, '原始资料链接（由本机服务管理）'); }
export function localTime(value: string) { const date = new Date(value); return Number.isNaN(date.getTime()) ? '时间未知' : new Intl.DateTimeFormat('zh-CN', { timeZone: 'Asia/Shanghai', month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' }).format(date); }
export function readLastTask() { try { return localStorage.getItem('hw-last-task'); } catch { return null; } }
export function rememberTask(id: string | null) { try { if (id) localStorage.setItem('hw-last-task', id); else localStorage.removeItem('hw-last-task'); } catch { /* Navigation still works without browser persistence. */ } }



export const evidencePaused = (task: Task) => !isPlatformAdaptation(task) && effectiveStatus(task) === 'needs_review' && !task.plan && !task.document && Boolean(task.package);
export const canResumePlan = (task: Task) => evidencePaused(task) && Boolean(task.package?.coverage?.length) && !task.package?.content_policy?.blocked_requests?.length && !task.package?.evidence_gaps?.some(g => Boolean(g.blocking_reason));

// Older services expose this failure only as text; do not classify all evidence pauses as planner failures.
export const plannerGenerationFailed = (task: Task) => evidencePaused(task) && Boolean(task.error && /候选卖点|卖点候选|规划结果|内容规划|Content Planner/i.test(task.error));
