// Isolated browser fixtures only. None of these records or images come from ima.
import type { Page } from '@playwright/test';
import type { Task } from '../src/types';
export const product = { id: 'fixture-product', name: 'MateBook 示例型号（测试）', category: '模拟目录', path: '交互测试/非真实产品资料' };
export function makeTask(status = 'approved', platform = 'xiaohongshu'): Task {
  const quote = '此段是界面交互测试用的模拟资料，不代表任何真实华为产品参数。';
  const images = [1, 2, 3, 4].map(i => ({ id: `fixture-image-${i}`, name: `模拟素材 ${i}`, model: product.name, source: `交互测试/模拟素材${i}.svg`, description: `模拟图片 ${i}：仅用于测试布局`, url: `/api/assets/fixture-image-${i}`, visual_checked: true, selection_reason: '验证配图与段落的关联操作' }));
  const facts = [1, 2, 3].map(i => ({ id: `fact-${i}`, claim: `测试卖点 ${i}：围绕学习场景展开`, quote, source_id: 'source-fixture', conditions: '模拟内容，不可作为真实宣传依据。' }));
  const task: Task = { id: 'fixture-task', title: '模拟营销任务：开学购机', raw: '【隔离测试数据】面向大学新生，围绕校园学习创作图文。', product_id: product.id, platform, status, version: 10,
    brief: { audience: '大学新生与家长', scenario: '开学购机 / 校园学习', platform, goal: '引导到店了解并体验', purchase_stage: '比较与选购', pain_points: ['学习场景与产品能力是否匹配'], strategy: '从课堂记录、图书馆学习到小组协作，逐步介绍有依据的产品信息。所有内容均为交互测试。', tone: '亲切、清晰', emphasis: ['场景适配', '限定条件'], questions: [] },
    package: { product, sources: [{ id: 'source-fixture', title: '模拟原文：不是 ima 资料', path: '交互测试/模拟原文.md', text: `测试文档。\n${quote}\n请勿将本文件作为产品证据。`, retrieved_at: '2026-10-18T06:00:00Z' }], facts, images, conflicts: [], search_hits: 1 },
    plan: { angle: '从校园的一天出发，帮助新生理解适合自己的购机方向。', title_direction: '开学选电脑，先想清楚这些学习场景', sections: images.slice(0, 3).map((im, i) => ({ id: `section-${i + 1}`, heading: ['课堂记录，有条不紊', '图书馆里，专注学习', '小组协作，表达想法'][i], purpose: ['回应课堂资料整理需求', '回应图书馆学习场景', '回应展示与协作需求'][i], fact_ids: [facts[i].id], image_id: im.id, image_reason: '模拟图片用于验证对应段落展示' })), cta: '欢迎到店了解具体型号与适用条件。' },
    document: { title: '开学选电脑，先从你的学习日常出发', lead: '课堂、图书馆、小组讨论，每个学习场景都有不同需求。以下为界面测试文案，不包含真实产品结论。', paragraphs: images.slice(0, 3).map((im, i) => ({ section_id: `section-${i + 1}`, heading: ['课堂记录，有条不紊', '图书馆里，专注学习', '小组协作，表达想法'][i], text: '先想清楚自己的使用场景，再对照具体型号的官方资料。这段模拟内容用于检查编辑、预览和证据追溯是否顺畅，不构成任何产品能力说明。', fact_ids: [facts[i].id], image_id: im.id, caption: `模拟素材 ${i + 1}，非产品实拍` })), cta: '欢迎到店了解具体型号与适用条件。', tags: ['#开学购机', '#模拟内容'] },
    review: { summary: '模拟核验报告：仅供测试界面门槛，非真实模型核验。', issues: [], passed: status === 'approved', checked_at: '2026-10-18T06:20:00Z', model: 'fixture-reviewer', document_hash: 'fixture-hash' }, error: null, events: [{ at: '2026-10-18T06:00:00Z', text: '【模拟】用户已确认策略' }, { at: '2026-10-18T06:01:00Z', text: '【模拟】用户已确认规划，生成图文' }], can_export: status === 'approved', resume_status: status };
  if (['draft', 'analyzing', 'needs_information', 'brief_ready', 'retrieving', 'planning', 'plan_ready'].includes(status)) { task.document = null; task.review = null; }
  if (['draft', 'analyzing', 'needs_information', 'brief_ready', 'retrieving'].includes(status)) { task.package = null; task.plan = null; }
  if (['draft', 'analyzing'].includes(status)) task.brief = null;
  if (status === 'needs_information') task.brief!.questions = ['希望读者采取什么行动？'];
  if (status === 'needs_review') task.review!.issues = [{ category: 'fact', location: '课堂记录，有条不紊', detail: '测试问题：请保留模拟资料中的限定条件。', severity: 'error', repairable: true }];
  return task;
}
export async function mockApi(page: Page, initial: Task | null = null) {
  const state = { task: initial, writes: [] as { path: string; body: any }[], failNext: 0, busyReview: false, failNextTaskRead: false, settings: { base_url: 'https://example.invalid/v1', writer_model: 'fixture-writer', reviewer_model: 'fixture-reviewer', vision: true, has_key: true, ima_ready: true, credential_storage: 'fixture-only' }, catalogFailure: false };
  await page.addInitScript(id => { localStorage.clear(); if (id) localStorage.setItem('hw-last-task', id); }, initial?.id || null);
  await page.route('**/api/**', async route => {
    const req = route.request(), url = new URL(req.url()), path = url.pathname.replace('/api', ''), method = req.method();
    const send = (data: unknown, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(data) });
    if (path.startsWith('/assets/')) { const label = path.split('-').at(-1); return route.fulfill({ contentType: 'image/svg+xml', body: `<svg xmlns="http://www.w3.org/2000/svg" width="640" height="420"><rect width="640" height="420" fill="#edf1f8"/><rect x="130" y="80" width="380" height="230" rx="14" fill="#c4cede"/><rect x="145" y="95" width="350" height="200" rx="5" fill="#f8fafc"/><path d="M100 310H540L570 335H70Z" fill="#a9b8ce"/><text x="320" y="180" text-anchor="middle" font-family="sans-serif" font-size="24" fill="#536789">TEST FIXTURE ${label}</text><text x="320" y="220" text-anchor="middle" font-family="sans-serif" font-size="17" fill="#536789">Not a product photograph</text></svg>` }); }
    if (path === '/settings' && method === 'GET') return send(state.settings);
    if (path === '/settings' && method === 'PUT') { state.writes.push({ path, body: req.postDataJSON() }); return send(state.settings); }
    if (path === '/settings/probe') return send({ note: '模拟连接测试', writer_available: true, reviewer_available: true });
    if (path === '/catalog') return state.catalogFailure ? send({ detail: '模拟：知识库连接失败，请检查配置。' }, 503) : send({ products: [product], connected: true });
    if (path === '/tasks' && method === 'GET') return send(state.task ? [{ id: state.task.id, title: state.task.title, status: state.task.status, version: state.task.version, platform: state.task.platform, updated_at: '2026-10-18T06:00:00Z' }] : []);
    if (path.endsWith('/history')) return send([{ version: 10, note: '模拟已保存版本', at: '2026-10-18T06:00:00Z' }, { version: 3, note: '模拟早期规划', at: '2026-10-18T05:00:00Z' }]);
    if (path.endsWith('/export')) { if (!state.task?.can_export) return send({ detail: '模拟：当前版本未核验' }, 400); return route.fulfill({ contentType: url.searchParams.has('bundle') ? 'application/zip' : 'text/markdown', body: '# TEST FIXTURE — not a real marketing export' }); }
    if (path === '/tasks' && method === 'POST') { state.writes.push({ path, body: req.postDataJSON() }); state.task = makeTask('draft', req.postDataJSON().platform); return send(state.task, 201); }
    if (path === '/tasks/fixture-task' && method === 'GET') { if (state.failNextTaskRead) { state.failNextTaskRead = false; return send({ detail: '模拟：状态读取失败' }, 503); } return state.task ? send(state.task) : send({ detail: '模拟任务不存在' }, 404); }
    if (method !== 'GET' && state.task) {
      const body = req.postDataJSON(); state.writes.push({ path, body });
      if (state.failNext) { const code = state.failNext; state.failNext = 0; return send({ detail: code === 409 ? '任务已更新' : '模拟：保存失败，请重试。' }, code); }
      if (body.version !== state.task.version) return send({ detail: '任务已更新' }, 409);
      const version = state.task.version + 1;
      if (path.endsWith('/analyze') || path.endsWith('/modify')) { let platform = state.task.platform; if (body.instruction?.includes('朋友圈')) platform = 'moments'; if (body.instruction?.includes('公众号')) platform = 'wechat'; state.task = makeTask('brief_ready', platform); }
      else if (path.endsWith('/brief/answers')) { state.task = makeV2Task(true); }
      else if (path.endsWith('/confirm-brief')) { state.task = makeTask('plan_ready', body.brief?.platform || state.task.platform); if (body.brief) state.task.brief = body.brief; }
      else if (path.endsWith('/resume-plan')) state.task = makeTask('plan_ready', state.task.platform);
      else if (path.endsWith('/confirm-plan')) { state.task = { ...makeTask('approved', state.task.platform), plan: body.plan }; }
      else if (path.endsWith('/plan')) state.task.plan = body.plan;
      else if (path.endsWith('/document')) { state.task.document = body.document; state.task.status = 'needs_review'; state.task.review = null; state.task.can_export = false; }
      else if (path.endsWith('/review')) { state.task.review = makeTask().review; state.task.status = state.busyReview ? 'reviewing' : 'approved'; state.task.can_export = !state.busyReview; }
      else if (path.endsWith('/restore')) { state.task = makeTask('needs_review'); state.task.review = null; }
      else return send({ detail: 'Unexpected fixture route' }, 500);
      state.task.version = version; return send({ accepted: true });
    }
    return send({ detail: `Unexpected fixture route ${method} ${path}` }, 500);
  });
  return state;
}
export async function watermark(page: Page) {
  await page.evaluate(() => { document.getElementById('fixture-watermark')?.remove(); const label = document.createElement('div'); label.textContent = '隔离交互测试 / 模拟数据 · 非真实 ima 或模型结果'; label.style.cssText = 'position:fixed;bottom:0;right:0;background:#2446a8;color:white;font:12px sans-serif;padding:7px 12px;z-index:500;pointer-events:none'; label.id = 'fixture-watermark'; document.body.append(label); });
}



export function makeV2Task(ready = false): Task {
  const task = makeTask(ready ? 'brief_ready' : 'needs_information');
  task.dialogue = [{ id: 'U1', kind: 'user', text: '【模拟对话】给大学新生写一篇校园学习图文。', at: '2026-10-18T06:00:00Z' }];
  task.brief_analysis_hash = 'fixture-server-hash';
  const value = (v:string, source = 'explicit') => ({ value:v, source, reason:'隔离测试的判断依据', evidence: source === 'explicit' ? [{ turn_id:'U1', quote:'大学新生' }] : [] });
  task.brief_analysis = { schema_version:'2', status:ready ? 'ready' : 'need_clarification', requirements: { product_model:value(product.name), target_audience:value('大学新生'), scenario:value('校园学习', 'inferred'), platform:value('xiaohongshu'), marketing_goal:value('到店体验', 'inferred') }, questions:ready ? [] : [{id:'Q1',field:'platform',kind:'missing',question:'这篇图文发布到哪里？',reason:'平台决定图文形式',choices:['小红书','公众号']},{id:'Q2',field:'product_model',kind:'missing',question:'这次介绍哪款电脑？',reason:'需要确认具体型号',choices:[product.name]}], product_resolution:{state:ready ? 'resolved' : 'unresolved',product_model:ready ? product.name : null,candidates:[product]}, audience_insight:ready ? {job_to_be_done:'校园学习',problems:['资料整理'],decision_factors:[{point:'适用性',reason:'按证据介绍'}]} : null, message_strategy:ready ? { theme:'从校园的一天介绍产品', angle:'课堂与图书馆', tone:'自然', cta_direction:'欢迎到店体验', reason:'模拟策略', priorities:[{id:'d1',direction:'学习场景适配',reason:'回应资料整理需求'}]} : null, retrieval_plan:ready ? {facts:[{id:'r1',direction_id:'d1',question:'有哪些有依据的相关特点？',priority:'required'}],images:[{id:'i1',description:'模拟产品图',reason:'介绍场景'}]} : null };
  if (!ready) task.brief = null;
  return task;
}
