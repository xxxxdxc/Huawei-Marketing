import { directionResults } from '../src/StrategyDirections';
import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import { makeTask, makeV2Task, mockApi, product, watermark } from './fixtures';
import fs from 'node:fs';

const screenshotDir = 'qa/screenshots';
test.beforeAll(() => fs.mkdirSync(screenshotDir, { recursive: true }));
async function noOverflow(page: import('@playwright/test').Page) { expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBeTruthy(); }
async function screenshot(page: import('@playwright/test').Page, name: string) { await watermark(page); await page.evaluate(() => window.scrollTo(0, 0)); await page.screenshot({ path: `${screenshotDir}/${name}.png`, fullPage: false }); }

test('creation preserves two explicit confirmations and sends optional context once', async ({ page }) => {
  const state = await mockApi(page); await page.goto('/');
  await expect(page.getByRole('heading', { name: /聊聊你的想法/ })).toBeVisible();
  await page.getByRole('button', { name: '开学购机', exact: true }).click();
  await page.getByLabel('产品型号', { exact: true }).selectOption(product.id);
  await page.getByText('补充信息', { exact: false }).first().click();
  await page.getByLabel('目标人群', { exact: true }).fill('大学新生');
  await page.getByRole('button', { name: '发送', exact: true }).click();
  await expect(page.getByRole('button', { name: '确认策略，查资料' })).toBeVisible();
  expect(state.writes.map(w => w.path)).toEqual(['/tasks', '/tasks/fixture-task/analyze']);
  expect(state.writes[0].body.raw).toContain('补充目标人群：大学新生');
  await page.getByRole('button', { name: '确认策略，查资料' }).click();
  await expect(page.getByRole('button', { name: '确认规划，开始写稿' })).toBeVisible();
  expect(state.writes.some(w => w.path.endsWith('/confirm-plan'))).toBeFalsy();
  await page.getByRole('button', { name: '确认规划，开始写稿' }).click();
  await expect(page.getByRole('button', { name: 'Markdown', exact: true })).toBeEnabled();
});

test('missing information is answered inline and returns to strategy confirmation', async ({ page }) => {
  const state = await mockApi(page, makeTask('needs_information')); await page.goto('/');
  await expect(page.getByRole('button', { name: '确认策略，查资料' })).toBeDisabled();
  await page.getByLabel('希望读者采取什么行动？').fill('到店了解');
  await page.getByRole('button', { name: '补充信息，更新策略' }).click();
  await expect(page.getByRole('button', { name: '确认策略，查资料' })).toBeEnabled();
  expect(state.writes[0].body.instruction).toContain('到店了解');
});

test('planner order, removal undo, image uniqueness, and fact source modal', async ({ page }) => {
  const state = await mockApi(page, makeTask('plan_ready')); await page.goto('/');
  await page.getByRole('button', { name: '下移段落 1', exact: true }).click();
  await expect(page.getByLabel('段落标题', { exact: true }).first()).toHaveValue('图书馆里，专注学习');
  await page.getByRole('button', { name: '删除段落 1', exact: true }).click();
  await expect(page.getByRole('button', { name: '确认规划，开始写稿' })).toBeDisabled();
  await page.getByRole('button', { name: '撤销移除' }).click();
  await page.getByRole('button', { name: '依据 2', exact: true }).first().click();
  await expect(page.getByRole('dialog')).toContainText('模拟原文：不是 ima 资料');
  await expect(page.locator('mark')).toBeVisible();
  await page.keyboard.press('Escape'); await expect(page.getByRole('dialog')).toHaveCount(0);
  await expect(page.getByRole('button', { name: /选择图片.*其他段落已使用/ }).first()).toBeDisabled();
  await page.getByRole('button', { name: '保存规划', exact: true }).click();
  expect(state.task?.plan?.sections[0].heading).toBe('图书馆里，专注学习');
  await screenshot(page, 'planner-desktop');
});

test('editing invalidates UI immediately, failed save preserves edits, successful save needs review', async ({ page }) => {
  const state = await mockApi(page, makeTask()); await page.goto('/');
  await expect(page.getByRole('button', { name: '复制', exact: true })).toBeEnabled();
  await page.getByLabel('标题', { exact: true }).fill('用户修改后的标题');
  await expect(page.getByRole('button', { name: '复制', exact: true })).toBeDisabled();
  await expect(page.getByRole('button', { name: 'Markdown', exact: true })).toBeDisabled();
  await page.getByRole('button', { name: '核验', exact: true }).click();
  await expect(page.getByRole('heading', { name: '修改后，等待重新核验' })).toBeVisible();
  state.failNext = 500; await page.getByRole('button', { name: '保存修改', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('保存失败');
  await expect(page.getByLabel('标题', { exact: true })).toHaveValue('用户修改后的标题');
  await page.getByRole('button', { name: '保存修改', exact: true }).click();
  await expect(page.getByRole('button', { name: '保存修改', exact: true })).toBeDisabled();
  await expect(page.getByRole('button', { name: 'Markdown', exact: true })).toBeDisabled();
  expect(state.task?.review).toBeNull();
  await page.getByRole('button', { name: '重新核验', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Markdown', exact: true })).toBeEnabled();
  const download = page.waitForEvent('download'); await page.getByRole('button', { name: 'Markdown', exact: true }).click();
  expect((await download).suggestedFilename()).toBe('marketing.md');
});

test('version conflict retains input and requires explicit reload with discard guard', async ({ page }) => {
  const state = await mockApi(page, makeTask()); await page.goto('/');
  await page.getByLabel('标题', { exact: true }).fill('不要丢失的编辑'); state.failNext = 409;
  await page.getByRole('button', { name: '保存修改', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('版本发生变化');
  await expect(page.getByLabel('标题', { exact: true })).toHaveValue('不要丢失的编辑');
  page.once('dialog', dialog => dialog.dismiss()); await page.getByRole('button', { name: '重新载入最新版本' }).click();
  await expect(page.getByLabel('标题', { exact: true })).toHaveValue('不要丢失的编辑');
  page.once('dialog', dialog => dialog.accept()); await page.getByRole('button', { name: '重新载入最新版本' }).click();
  await expect(page.getByLabel('标题', { exact: true })).toHaveValue(makeTask().document!.title);
});

test('same-product image replacement is saved and invalidates export', async ({ page }) => {
  const state = await mockApi(page, makeTask()); await page.goto('/');
  await page.getByText('更换本段配图', { exact: true }).first().click();
  await page.getByRole('button', { name: '选择图片：模拟图片 4：仅用于测试布局', exact: true }).first().click();
  await expect(page.getByRole('button', { name: '图文包', exact: true })).toBeDisabled();
  await page.getByRole('button', { name: '保存修改', exact: true }).click();
  await expect(page.getByRole('button', { name: '保存修改', exact: true })).toBeDisabled();
  expect(state.task?.document?.paragraphs[0].image_id).toBe('fixture-image-4');
  expect(state.task?.can_export).toBeFalsy();
});

test('platform changes rerun the task and never just restyle the old document', async ({ page }) => {
  const state = await mockApi(page, makeTask()); await page.goto('/');
  await page.getByRole('button', { name: '更换目标平台', exact: true }).click();
  await page.getByLabel('新目标平台').selectOption('moments');
  await page.getByRole('button', { name: '更换平台并重新分析' }).click();
  await expect(page.getByRole('button', { name: '确认策略，查资料' })).toBeVisible();
  expect(state.writes.at(-1)?.path).toBe('/tasks/fixture-task/modify');
  expect(state.task?.document).toBeNull();
  expect(state.task?.platform).toBe('moments');
});

test('history restoration requires confirmation and resets review', async ({ page }) => {
  const state = await mockApi(page, makeTask()); await page.goto('/');
  await page.getByRole('button', { name: '版本记录', exact: true }).click();
  page.once('dialog', dialog => dialog.accept()); await page.getByRole('button', { name: '恢复', exact: true }).click();
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Markdown', exact: true })).toBeDisabled();
  expect(state.task?.review).toBeNull();
});

test('failed task shows retained stage and real error; busy editor is locked', async ({ page }) => {
  const failed = makeTask('plan_ready'); failed.status = 'error'; failed.resume_status = 'plan_ready'; failed.error = '模拟：图片素材不足，当前只有两张。';
  await mockApi(page, failed); await page.goto('/');
  await expect(page.getByRole('alert')).toContainText('图片素材不足');
  await expect(page.locator('.workflow-step.failed')).toContainText('生成平台文案');
});

test('polling returns current report and disables controls while reviewing', async ({ page }) => {
  const state = await mockApi(page, makeTask()); await page.goto('/'); state.busyReview = true;
  await page.getByRole('button', { name: '重新核验', exact: true }).click();
  await expect(page.getByLabel('标题', { exact: true })).toBeDisabled();
  await expect(page.getByRole('button', { name: '复制', exact: true })).toBeDisabled();
  state.task!.status = 'approved'; state.task!.can_export = true; state.task!.version++;
  await expect(page.getByRole('button', { name: '复制', exact: true })).toBeEnabled({ timeout: 10000 });
});

for (const platform of ['xiaohongshu', 'wechat', 'moments']) {
  test(`distinct ${platform} preview, keyboard/source access and desktop screenshot`, async ({ page }) => {
    const errors: string[] = []; page.on('pageerror', e => errors.push(e.message));
    await mockApi(page, makeTask('approved', platform)); await page.goto('/');
    await expect(page.locator(`.preview-${platform}`)).toBeVisible();
    await page.getByRole('button', { name: '依据 1', exact: true }).first().click();
    await expect(page.getByRole('dialog')).toBeVisible(); await page.keyboard.press('Escape');
    await expect(page.getByRole('button', { name: '依据 1', exact: true }).first()).toBeFocused();
    await noOverflow(page); await screenshot(page, `editor-${platform}-desktop`);
    expect(errors).toEqual([]);
  });
}

for (const width of [390, 768]) {
  for (const stateName of ['start', 'plan_ready', 'approved']) {
    test(`responsive ${width}px ${stateName} without horizontal overflow`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 }); await mockApi(page, stateName === 'start' ? null : makeTask(stateName)); await page.goto('/');
      await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
      if (stateName === 'approved') { await page.getByRole('button', { name: '预览与核验', exact: true }).click(); await expect(page.locator('.platform-preview')).toBeVisible(); }
      await noOverflow(page); await screenshot(page, `${stateName}-${width}`); if (stateName === 'approved') await page.locator('.preview-column').screenshot({ path: `${screenshotDir}/preview-detail-${width}.png` }); if (stateName === 'plan_ready') await page.locator('.plan-card').first().screenshot({ path: `${screenshotDir}/plan-detail-${width}.png` });
    });
  }
}

test('desktop home, settings, and axe accessibility checks', async ({ page }) => {
  await mockApi(page); await page.goto('/');
  await expect(page.getByLabel('产品型号', { exact: true })).toBeEnabled();
  await screenshot(page, 'home-desktop');
  const home = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze();
  expect(home.violations.map(v => ({ id: v.id, nodes: v.nodes.map(n => n.target) }))).toEqual([]);
  await page.getByRole('button', { name: '连接设置', exact: true }).click();
  await expect(page.getByLabel('API Key', { exact: true })).toHaveValue('');
  await screenshot(page, 'settings-desktop');
  const settings = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze();
  expect(settings.violations.map(v => ({ id: v.id, nodes: v.nodes.map(n => n.target) }))).toEqual([]);
});

test('planner and editor accessibility checks', async ({ page }) => {
  await mockApi(page, makeTask('plan_ready')); await page.goto('/');
  await expect(page.getByRole('heading', { name: '先编排，再落笔' })).toBeVisible();
  const plan = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze();
  expect(plan.violations.map(v => ({ id: v.id, nodes: v.nodes.map(n => n.target) }))).toEqual([]);
  await page.getByRole('button', { name: '确认规划，开始写稿' }).click();
  await expect(page.getByLabel('标题', { exact: true })).toBeVisible();
  const editor = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze();
  expect(editor.violations.map(v => ({ id: v.id, nodes: v.nodes.map(n => n.target) }))).toEqual([]);
});


test('catalog failure offers retry and no-key state prevents task creation', async ({ page }) => {
  const state = await mockApi(page); state.catalogFailure = true; state.settings.has_key = false; await page.goto('/');
  await expect(page.getByRole('alert')).toContainText('知识库连接失败');
  state.catalogFailure = false; await page.getByRole('button', { name: '重新读取知识库' }).click();
  await page.getByRole('button', { name: '开学购机', exact: true }).click();
  await page.getByLabel('产品型号', { exact: true }).selectOption(product.id);
  await page.getByRole('button', { name: '发送', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('先到连接设置');
  expect(state.writes).toHaveLength(0);
});

test('insufficient images or evidence conflict prevents planning confirmation', async ({ page }) => {
  const task = makeTask('plan_ready'); task.package!.images = task.package!.images.slice(0, 2); task.plan!.sections[2].image_id = null; task.package!.conflicts = ['模拟：不同文档存在型号冲突'];
  await mockApi(page, task); await page.goto('/');
  await expect(page.getByText(/当前型号素材不足/)).toBeVisible();
  await expect(page.getByRole('button', { name: '确认规划，开始写稿' })).toBeDisabled();
  await page.getByRole('button', { name: '知识库依据', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('型号冲突');
});

test('review issues locate only known paragraph and keep export disabled', async ({ page }) => {
  await mockApi(page, makeTask('needs_review')); await page.goto('/');
  await expect(page.getByRole('heading', { name: '仍有问题需要处理' })).toBeVisible();
  await page.getByRole('button', { name: '定位到编辑位置' }).click();
  await expect(page.getByLabel('段落 1 标题', { exact: true })).toBeFocused();
  await expect(page.getByRole('button', { name: 'Markdown', exact: true })).toBeDisabled();
  await screenshot(page, 'review-desktop');
});

test('mobile navigation traps focus and closes with Escape', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 900 }); await mockApi(page); await page.goto('/');
  await page.getByRole('button', { name: '展开导航', exact: true }).click();
  await expect(page.getByRole('button', { name: '关闭导航', exact: true })).toBeFocused();
  await page.keyboard.press('Shift+Tab'); await expect(page.getByRole('button', { name: '连接设置', exact: true })).toBeFocused();
  await page.keyboard.press('Escape'); await expect(page.getByRole('button', { name: '展开导航', exact: true })).toBeFocused();
  await expect(page.locator('.sidebar')).not.toBeVisible();
});

test('settings save clears entered key and no keys are in browser storage', async ({ page }) => {
  const state = await mockApi(page); await page.goto('/'); await page.getByRole('button', { name: '连接设置', exact: true }).click();
  await page.getByLabel('API Key', { exact: true }).fill('isolated-test-not-a-secret');
  await page.getByRole('button', { name: '保存设置', exact: true }).click();
  await expect(page.getByLabel('API Key', { exact: true })).toHaveValue('');
  expect(state.writes.at(-1)?.body.api_key).toBe('isolated-test-not-a-secret');
  expect(await page.evaluate(() => JSON.stringify(localStorage))).not.toContain('isolated-test-not-a-secret');
});

test('reduced motion disables progress animation', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' }); await mockApi(page, makeTask('analyzing')); await page.goto('/');
  await expect(page.locator('.chat-thinking')).toBeVisible();
  expect(await page.locator('.spin').first().evaluate(e => getComputedStyle(e).animationName)).toBe('none');
});

test('accepted mutation with failed state refresh locks stale actions and preserves local edits', async ({ page }) => {
  const state = await mockApi(page, makeTask()); await page.goto('/');
  await page.getByLabel('标题', { exact: true }).fill('已提交但状态读取失败');
  state.failNextTaskRead = true;
  await page.getByRole('button', { name: '保存修改', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('请求已提交，但未能读取最新任务状态');
  await expect(page.getByLabel('标题', { exact: true })).toHaveValue('已提交但状态读取失败');
  await expect(page.getByRole('button', { name: '重新核验', exact: true })).toBeDisabled();
  await expect(page.getByRole('button', { name: 'Markdown', exact: true })).toBeDisabled();
  page.once('dialog', dialog => dialog.accept()); await page.getByRole('button', { name: '重新载入最新版本' }).click();
  await expect(page.getByRole('button', { name: '重新核验', exact: true })).toBeEnabled();
});


test('legacy evidence pause resumes only on click and retains planning confirmation', async ({ page }) => {
  const task = makeTask('needs_review'); task.plan = null; task.document = null; task.review = null;
  task.error = '关键检索任务缺少证据或存在冲突';
  task.package!.coverage = [{ request_id: 'offer', status: 'not_found', fact_ids: [], reason: '模拟：未提供优惠资料' }];
  const state = await mockApi(page, task); await page.goto('/');
  await expect(page.getByText('资料检查已暂停', { exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: '核验并优化 等待中' })).toBeVisible();
  expect(state.writes).toHaveLength(0);
  state.failNext = 500;
  await page.getByRole('button', { name: '按当前规则继续规划' }).click();
  await expect(page.getByRole('button', { name: '按当前规则继续规划' })).toBeEnabled();
  await page.getByRole('button', { name: '按当前规则继续规划' }).click();
  await expect(page.getByRole('button', { name: '确认规划，开始写稿' })).toBeVisible();
  expect(state.writes.filter(w => w.path.endsWith('/resume-plan'))).toHaveLength(2);
  expect(state.writes[1].body).toEqual({ version: 10 });
  expect(state.writes.some(w => w.path.endsWith('/confirm-plan'))).toBeFalsy();
});

test('omission notices preserve supported facts and expose archived evidence', async ({ page }) => {
  const task = makeTask('plan_ready'); const pkg = task.package!;
  pkg.all_facts = [...pkg.facts, { ...pkg.facts[0], id: 'archived', claim: '模拟：已省略的优惠资料' }];
  pkg.coverage = [{ request_id: 'offer', status: 'conflict', fact_ids: ['archived'], reason: '模拟：优惠资料冲突' }];
  pkg.content_policy = { notices: ['模拟：仅省略优惠，保留有依据的价格。'], omitted_requests: [{ request_id: 'offer', category: 'promotion', status: 'conflict', reason: '模拟：优惠资料冲突' }], blocked_requests: [] };
  await mockApi(page, task); await page.goto('/');
  await expect(page.getByText(pkg.content_policy.notices[0], { exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: '按当前规则继续规划' })).toHaveCount(0);
  await page.getByRole('button', { name: '知识库依据', exact: true }).click();
  await page.getByText('检索结果与内容取舍（1 项）').click();
  await expect(page.getByText(/本次省略此项/)).toBeVisible();
  await page.getByRole('button', { name: '查看依据 archived（仅供追溯）' }).click();
  await expect(page.getByRole('dialog')).toContainText('此事实仅供追溯，未纳入当前可用内容');
  await page.keyboard.press('Escape');
  await page.setViewportSize({ width: 390, height: 844 }); await noOverflow(page);
  await screenshot(page, 'evidence-omission-mobile');
  const results = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze(); expect(results.violations).toEqual([]);
});

for (const reason of ['product_evidence', 'user_refuses_generation']) test(`real evidence block remains explicit: ${reason}`, async ({ page }) => {
  const task = makeTask('needs_review'); task.plan = null; task.document = null; task.review = null;
  const coverage = { request_id: 'required', status: 'not_found', fact_ids: [], reason: '模拟：所需依据缺失' };
  task.package!.coverage = [coverage];
  task.package!.evidence_gaps = [{ request: { id: 'required', question: '模拟必需项', priority: 'required' }, coverage, blocking_reason: reason, blocking_evidence: reason === 'user_refuses_generation' ? [{ turn_id: 'u1', quote: '没有优惠就不生成' }] : [] }];
  task.error = '模拟：需要处理证据缺项';
  await mockApi(page, task); await page.goto('/');
  await expect(page.getByText('资料检查已暂停', { exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: '按当前规则继续规划' })).toHaveCount(0);
  await page.getByText('检索结果与内容取舍（1 项）').click();
  await expect(page.getByText(/暂停原因：/)).toBeVisible();
  if (reason === 'user_refuses_generation') await expect(page.getByText('用户要求：没有优惠就不生成')).toBeVisible();
});


test('natural language entry omits optional selectors and does not run from scenario click', async ({ page }) => {
  const state = await mockApi(page); state.catalogFailure = true; await page.goto('/');
  await page.getByRole('button', { name:'开学购机', exact:true }).click();
  expect(state.writes).toHaveLength(0);
  await expect(page.getByRole('region', {name:'任务执行进度'})).toHaveCount(0);
  await page.getByRole('button', { name:'发送', exact:true }).click();
  expect(state.writes[0].body).not.toHaveProperty('product_id');
  expect(state.writes[0].body).not.toHaveProperty('platform');
  await expect(page.getByRole('heading', {name:'一起找到这篇图文的方向'})).toBeVisible();
});

test('V2 conversation handles null legacy brief, partial answers, hash confirmation and stage transition', async ({ page }) => {
  const state = await mockApi(page, makeV2Task()); await page.goto('/');
  await expect(page.getByRole('region', {name:'任务执行进度'})).toHaveCount(0);
  await expect(page.getByRole('button', {name:'发送回答'})).toBeDisabled();
  await page.getByRole('button', {name:'小红书', exact:true}).click();
  await screenshot(page, 'conversation-questions-desktop');
  state.failNext = 409;
  await page.getByRole('button', {name:'发送回答'}).click();
  await expect(page.getByLabel('这篇图文发布到哪里？')).toHaveValue('小红书');
  page.once('dialog', dialog => dialog.accept());
  await page.getByRole('button', {name:'重新载入最新版本'}).click();
  await page.getByLabel('这篇图文发布到哪里？').fill('小红书');
  await page.getByRole('button', {name:'发送回答'}).click();
  expect(state.writes.at(-1)?.body.answers).toEqual([{question_id:'Q1',answer:'小红书'}]);
  await expect(page.getByText('这是我理解的营销方向', {exact:true})).toBeVisible();
  await expect(page.getByText('根据需求推断', {exact:true}).first()).toBeVisible();
  await screenshot(page, 'conversation-strategy-desktop');
  const results = await new AxeBuilder({ page }).withTags(['wcag2a','wcag2aa','wcag21aa']).analyze(); expect(results.violations).toEqual([]);
  await page.getByRole('button', {name:'确认策略，查资料'}).click();
  expect(state.writes.at(-1)?.body).toEqual({version:11,analysis_hash:'fixture-server-hash'});
  await expect(page.getByRole('region', {name:'任务执行进度'})).toBeVisible();
  await expect(page.getByRole('button', {name:'确认规划，开始写稿'})).toBeVisible();
});

test('mobile conversation choices, free input and keyboard remain usable', async ({ page }) => {
  await page.setViewportSize({width:390,height:844}); await mockApi(page,makeV2Task()); await page.goto('/');
  await page.getByLabel('这次介绍哪款电脑？').fill('用户自由输入的型号');
  await noOverflow(page);
  await page.getByRole('button',{name:'发送回答'}).focus(); await expect(page.getByRole('button',{name:'发送回答'})).toBeFocused();
  await screenshot(page,'conversation-questions-mobile');
  const results = await new AxeBuilder({ page }).withTags(['wcag2a','wcag2aa','wcag21aa']).analyze(); expect(results.violations).toEqual([]);
});


for (const variant of ['pending','supported','partial','not_found','conflict','omitted','blocked','unlinked']) test(`direction evidence status: ${variant}`, async () => {
  const task = makeV2Task(true);
  const pkg = makeTask('plan_ready').package!;
  task.package = pkg;
  const req = {id:'r1',direction_id:'d1',question:'是否有相关依据？',priority:'required'};
  pkg.retrieval_plan = {facts:variant === 'unlinked' ? [] : [req]};
  if (variant !== 'pending') pkg.coverage = [{request_id:'r1',status:['not_found','conflict'].includes(variant) ? variant : 'supported',fact_ids:variant === 'not_found' ? [] : ['fact-1'],reason:'模拟结果'}];
  if (variant === 'partial') { pkg.retrieval_plan.facts.push({...req,id:'r2'}); pkg.coverage!.push({request_id:'r2',status:'not_found',fact_ids:[],reason:'模拟缺项'}); }
  if (variant === 'omitted') pkg.content_policy = {notices:[],omitted_requests:[{request_id:'r1',category:'promotion',status:'not_usable',reason:'已省略'}]};
  if (variant === 'blocked') pkg.evidence_gaps = [{request:req,coverage:pkg.coverage![0],blocking_reason:'product_evidence'}];
  const expected:Record<string,string> = {pending:'待验证',supported:'有相关依据',partial:'部分有依据',not_found:'未找到依据',conflict:'存在资料冲突',omitted:'本次省略',blocked:'待处理',unlinked:'待关联检索项'};
  expect(directionResults(task,'d1').label).toBe(expected[variant]);
});

test('directions use questions before verification and update after retrieval with evidence access', async ({ page }) => {
  const task = makeV2Task(true); task.brief_analysis!.message_strategy!.priorities[0].direction = '一天课程不用找插座';
  await mockApi(page,task); await page.goto('/');
  await expect(page.getByText('一天课程不用找插座',{exact:true})).not.toBeVisible();
  await expect(page.locator('.direction-heading')).toContainText('待验证');
  await expect(page.locator('.direction-question h4')).toContainText('有哪些有依据的相关特点');
  task.status = 'plan_ready'; task.plan = makeTask('plan_ready').plan; task.package = makeTask('plan_ready').package;
  task.package!.coverage = [{request_id:'r1',status:'supported',fact_ids:['fact-1'],reason:'模拟：仅支持特定配置和条件'}];
  await page.reload();
  await page.getByRole('button',{name:'场景与策略',exact:true}).click();
  await expect(page.locator('.direction-heading')).toContainText('有相关依据');
  await expect(page.getByText('策略保留为创作依据，下面的标签已按当前检索结果更新。')).toBeVisible();
  await page.getByRole('button',{name:'查看依据 fact-1',exact:true}).click();
  await expect(page.getByRole('dialog')).toContainText('适用条件'); await page.keyboard.press('Escape');
  await page.setViewportSize({width:390,height:844}); await noOverflow(page);
  await page.locator('.strategy-proposal').scrollIntoViewIfNeeded(); await watermark(page);
  await page.screenshot({path:'qa/screenshots/strategy-direction-results-mobile.png'});
});
