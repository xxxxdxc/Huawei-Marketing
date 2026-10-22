import { useEffect, useRef, useState } from 'react';
import { CASE_STORAGE_KEY, findDemoPost } from './historyEffectsData';

type CaseState = { ids: string[]; warning: string };
function readCases(): CaseState {
  try {
    const raw = localStorage.getItem(CASE_STORAGE_KEY);
    if (!raw) return { ids: [], warning: '' };
    const value = JSON.parse(raw);
    if (value.version !== 1 || !Array.isArray(value.ids)) throw new Error('invalid demo record');
    return { ids: [...new Set<string>(value.ids.filter((id: unknown): id is string => typeof id === 'string' && !!findDemoPost(id)))], warning: '' };
  } catch { return { ids: [], warning: '浏览器中的演示收藏无法读取，当前从空收藏开始；可用“重置演示”清理此功能的记录。' }; }
}
export default function useDemoCases() {
  const [state, setState] = useState<CaseState>(readCases);
  const current = useRef(state);
  function apply(next: CaseState) { current.current = next; setState(next); }
  useEffect(() => {
    const sync = (event: StorageEvent) => { if (event.key === CASE_STORAGE_KEY || event.key === null) apply(readCases()); };
    window.addEventListener('storage', sync); return () => window.removeEventListener('storage', sync);
  }, []);
  function update(id: string, included: boolean) {
    if (!findDemoPost(id)) return;
    const ids = included ? [...new Set([...current.current.ids, id])] : current.current.ids.filter(item => item !== id);
    try { localStorage.setItem(CASE_STORAGE_KEY, JSON.stringify({version:1,ids})); apply({ids,warning:''}); }
    catch { apply({ids,warning:'浏览器未能保存演示收藏。本次操作仅在当前页面有效，刷新后可能丢失。'}); }
  }

  function reset() {
    try { localStorage.removeItem(CASE_STORAGE_KEY); apply({ids:[],warning:''}); }
    catch { apply({ids:[],warning:'当前页面已重置，但浏览器存储未能更新；刷新后可能恢复旧记录。'}); }
  }
  return { ...state, update, reset };
}
