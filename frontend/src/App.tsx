import { lazy, Suspense, useCallback, useEffect, useRef, useState } from 'react';
import { AlertCircle, ArrowUpRight, CheckCircle2, ChevronRight, Database, FileText, History, LayoutDashboard, Menu, Monitor, Plus, Settings2, X } from 'lucide-react';
import type { Task, Product, Summary, Settings } from './types';
import { api, ApiError, Badge, BUSY, Empty, errorMessage, localTime, PLATFORMS, readLastTask, rememberTask, STATUS } from './shared';
import StartPage from './StartPage';
import SettingsPage from './SettingsPage';
import TaskView from './TaskView';
const HistoryPage = lazy(() => import('./HistoryPage'));

export default function App() {
  const [view, setView] = useState('work'), [settings, setSettings] = useState<Settings | null>(null), [products, setProducts] = useState<Product[]>([]);
  const [catalogState, setCatalogState] = useState('loading'), [catalogError, setCatalogError] = useState('');
  const [tasks, setTasks] = useState<Summary[]>([]), [task, setTask] = useState<Task | null>(null), [error, setError] = useState(''), [conflict, setConflict] = useState(false);
  const [pending, setPending] = useState(false), [toast, setToast] = useState(''), [dirty, setDirty] = useState(false), [menu, setMenu] = useState(false), [loadEpoch, setLoadEpoch] = useState(0);
  const requestLock = useRef(false), currentId = useRef<string | null>(null), navigation = useRef(0);
  const refreshList = useCallback(async () => { try { setTasks(await api<Summary[]>('/tasks')); } catch (e) { setError(errorMessage(e)); } }, []);
  const loadCatalog = useCallback(async (refresh = false) => { setCatalogState('loading'); setCatalogError(''); try { const d = await api<{ products: Product[] }>('/catalog' + (refresh ? '?refresh=true' : '')); setProducts(d.products); setCatalogState('ready'); } catch (e) { setCatalogState('error'); setCatalogError(errorMessage(e)); } }, []);
  const reportError = useCallback((e: unknown) => { setError(errorMessage(e)); if (e instanceof ApiError && e.status === 409) setConflict(true); }, []);
  function discard() { return !dirty || window.confirm('有未保存的修改。选择“确定”放弃修改并离开，选择“取消”继续编辑。'); }
  function go(next: string) { if (next === view) { setMenu(false); return; } if (requestLock.current || !discard()) return; setDirty(false); setView(next); setMenu(false); }
  async function selectTask(id: string, initial = false) {
    if (requestLock.current || (!initial && !discard())) return;
    const ticket = ++navigation.current; requestLock.current = true; setPending(true); setError('');
    try { const loaded = await api<Task>('/tasks/' + encodeURIComponent(id)); if (ticket !== navigation.current) return; currentId.current = id; setTask(loaded); setLoadEpoch(v => v + 1); setConflict(false); setView('work'); setDirty(false); setMenu(false); rememberTask(id); }
    catch (e) { reportError(e); if (initial) rememberTask(null); }
    finally { requestLock.current = false; setPending(false); }
  }
  useEffect(() => {
    api<Settings>('/settings').then(setSettings).catch(reportError);
    void refreshList(); void loadCatalog();
    const last = readLastTask(); if (last) void selectTask(last, true);
  }, []);
  useEffect(() => {
    if (!task || !BUSY.includes(task.status)) return;
    const id = task.id, controller = new AbortController(); let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      try { const updated = await api<Task>('/tasks/' + encodeURIComponent(id), 'GET', undefined, controller.signal); if (controller.signal.aborted || currentId.current !== id) return; setTask(old => old?.id === id && updated.version >= old.version ? updated : old); if (!BUSY.includes(updated.status)) { void refreshList(); return; } }
      catch (e) { if (!controller.signal.aborted) reportError(e); }
      if (!controller.signal.aborted) timer = setTimeout(poll, 1800);
    }
    timer = setTimeout(poll, 1800); return () => { controller.abort(); clearTimeout(timer); };
  }, [task?.id, task?.status, refreshList, reportError]);
  useEffect(() => { if (!toast) return; const timer = setTimeout(() => setToast(''), 4500); return () => clearTimeout(timer); }, [toast]);
  useEffect(() => { if (!dirty) return; const guard = (e: BeforeUnloadEvent) => { e.preventDefault(); e.returnValue = ''; }; window.addEventListener('beforeunload', guard); return () => window.removeEventListener('beforeunload', guard); }, [dirty]);
  useEffect(() => {
    if (!menu) return;
    const previous = document.activeElement as HTMLElement | null;
    const side = document.querySelector<HTMLElement>('.sidebar');
    const controls = () => Array.from(side?.querySelectorAll<HTMLElement>('button:not(:disabled),a[href]') || []).filter(e => e.getClientRects().length > 0);
    controls()[0]?.focus();
    const oldOverflow = document.body.style.overflow; document.body.style.overflow = 'hidden';
    const key = (e: KeyboardEvent) => {
      if (e.key === 'Escape') { e.preventDefault(); setMenu(false); }
      if (e.key === 'Tab') { const items = controls(); const first = items[0], last = items.at(-1); if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last?.focus(); } else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first?.focus(); } }
    };
    document.addEventListener('keydown', key);
    return () => { document.removeEventListener('keydown', key); document.body.style.overflow = oldOverflow; previous?.focus(); };
  }, [menu]);
  async function act(path: string, body: unknown, method = 'POST') {
    if (!task || requestLock.current || conflict) return false;
    const id = task.id; let accepted = false; requestLock.current = true; setPending(true); setError('');
    try {
      await api('/tasks/' + encodeURIComponent(id) + path, method, body); accepted = true;
      const updated = await api<Task>('/tasks/' + encodeURIComponent(id));
      if (currentId.current === id) { setTask(updated); setDirty(false); }
      void refreshList(); setToast(method === 'PUT' ? '修改已保存' : '操作已提交'); return true;
    } catch (e) { reportError(e); if (accepted) { setConflict(true); setError('请求已提交，但未能读取最新任务状态。当前编辑仍保留，请重新载入后继续。'); } return false; } finally { requestLock.current = false; setPending(false); }
  }
  async function create(raw: string, product: string, platform: string) {
    if (requestLock.current) return false;
    requestLock.current = true; setPending(true); setError('');
    try {
      const created = await api<Task>('/tasks', 'POST', { raw, ...(product ? { product_id: product } : {}), ...(platform ? { platform } : {}) });
      currentId.current = created.id; setTask(created); setDirty(false); rememberTask(created.id);
      await api('/tasks/' + created.id + '/analyze', 'POST', { version: created.version });
      setTask(await api<Task>('/tasks/' + created.id)); void refreshList(); return true;
    } catch (e) { reportError(e); return false; } finally { requestLock.current = false; setPending(false); }
  }
  function newTask() { if (requestLock.current || !discard()) return; navigation.current++; currentId.current = null; setTask(null); setView('work'); setDirty(false); setError(''); setConflict(false); setMenu(false); rememberTask(null); }
  return <div className="app-shell"><a href="#main-content" className="skip-link">跳到主内容</a>{menu && <button className="nav-scrim" aria-label="收起导航" onClick={() => setMenu(false)} />}
    <aside className={`sidebar ${menu ? 'is-open' : ''}`} aria-label="主导航"><button className="icon-button mobile-close" aria-label="关闭导航" onClick={() => setMenu(false)}><X size={20} aria-hidden="true" /></button><button className="brand" aria-label="华为 PC，创建新任务" onClick={newTask} disabled={pending}><span className="brand-mark"><Monitor size={22} aria-hidden="true" /></span><span>华为 PC<small>门店图文助手</small></span></button><button className="new-button" onClick={newTask} disabled={pending}><Plus size={18} aria-hidden="true" />新建营销任务</button>
      <nav aria-label="工作空间"><button className={`nav-item ${view === 'work' ? 'active' : ''}`} aria-current={view === 'work' ? 'page' : undefined} disabled={pending} onClick={() => go('work')}><LayoutDashboard size={18} aria-hidden="true" />内容工作台</button><button className={`nav-item ${view === 'all' ? 'active' : ''}`} aria-current={view === 'all' ? 'page' : undefined} disabled={pending} onClick={() => { go('all'); void refreshList(); }}><History size={18} aria-hidden="true" />历史任务<span>{tasks.length}</span></button></nav>
      <p className="nav-caption">最近任务</p><div className="recent-list">{tasks.length ? tasks.slice(0, 7).map(t => <button disabled={pending} key={t.id} className={`recent ${task?.id === t.id ? 'selected' : ''}`} onClick={() => selectTask(t.id)}><FileText size={16} aria-hidden="true" /><span>{t.title}<small>{PLATFORMS[t.platform]} · {STATUS[t.status] || '状态待同步'}</small></span></button>) : <p className="sidebar-empty">你的策略、图文与版本记录<br />会保存在这里。</p>}</div>
      <div className="sidebar-bottom"><div className="library-label"><Database size={17} aria-hidden="true" /><span>ima 产品知识库<small><i className={`dot ${catalogState === 'ready' ? '' : 'amber'}`} />{catalogState === 'ready' ? '产品目录已读取' : catalogState === 'loading' ? '连接中…' : '连接待检查'}</small></span></div><button className={`nav-item ${view === 'settings' ? 'active' : ''}`} disabled={pending} onClick={() => go('settings')}><Settings2 size={18} aria-hidden="true" />连接设置</button><p className="sidebar-footnote">任务保存在本机</p></div>
    </aside><div className="main-shell" inert={menu}><header className="topbar"><div className="breadcrumb"><button className="icon-button mobile-menu" aria-label={menu ? '收起导航' : '展开导航'} aria-expanded={menu} onClick={() => setMenu(!menu)}><Menu size={20} aria-hidden="true" /></button><span>工作空间</span><ChevronRight size={14} aria-hidden="true" /><strong>{view === 'settings' ? '连接设置' : view === 'all' ? '历史任务' : task ? '营销任务' : '新建任务'}</strong></div><button className="connection-status" disabled={pending} onClick={() => go('settings')}><i className={`dot ${settings?.has_key ? '' : 'amber'}`} />{settings?.has_key ? '模型已配置' : '连接模型'}<ArrowUpRight size={14} aria-hidden="true" /></button></header>
      <main id="main-content" className="main-content" tabIndex={-1}>{error && <div className="error-banner" role="alert"><AlertCircle size={20} aria-hidden="true" /><div><strong>{conflict ? '版本发生变化' : '操作需要处理'}</strong><p>{error}</p>{conflict && task && <button className="text-link" onClick={() => selectTask(task.id)}>重新载入最新版本</button>}</div><button disabled={conflict} className="icon-button" onClick={() => setError('')} aria-label="关闭错误提示"><X size={18} aria-hidden="true" /></button></div>}
        {view === 'settings' ? <SettingsPage settings={settings} onDirty={setDirty} onSaved={s => { setSettings(s); setDirty(false); setToast('连接设置已保存'); }} /> : view === 'all' ? <Suspense fallback={<p className="notice" role="status">正在读取历史任务…</p>}><HistoryPage tasks={tasks} pending={pending} onOpenTask={id => { void selectTask(id); }} onNewTask={newTask} /></Suspense> : task ? <TaskView key={`${task.id}-${loadEpoch}`} task={task} products={products} pending={pending || conflict} act={act} onDirty={setDirty} onToast={setToast} onError={setError} onReload={() => { if (task) void selectTask(task.id); }} /> : <StartPage products={products} catalogState={catalogState} catalogError={catalogError} hasKey={!!settings?.has_key} pending={pending} onCreate={create} onSettings={() => go('settings')} onReconnect={() => loadCatalog(true)} onDirty={setDirty} />}
      </main><footer className="app-footer"><span>华为 PC 门店图文助手</span><span>事实有据可查，内容由你把关。</span></footer>
    </div>{toast && <div className="toast" role="status"><CheckCircle2 size={18} aria-hidden="true" />{toast}</div>}
  </div>;
}
