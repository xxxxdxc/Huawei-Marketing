import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import { mockApi } from './fixtures';
import { adaptationTask } from './platformAdaptationFixture';
import { selectionPreviewComposition, selectionPreviewDocument, selectionPreviewTask } from '../src/selectionPreviewData';

test('confirmed platform adaptation survives reload without reverting to planner', async ({ page }) => {
  const state = await mockApi(page, adaptationTask()); await page.goto('/');
  await expect(page.getByRole('heading', { name: '正在适配新平台资料', exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: '确认核心卖点 已完成', exact: true })).toBeVisible();
  await expect(page.locator('.workflow-step')).toHaveCount(6);
  await expect(page.getByRole('button', { name: '图文与核验', exact: true })).toHaveAttribute('aria-current', 'page');
  await expect(page.getByText('内容规划中', { exact: false })).toHaveCount(0);
  await page.reload();
  await expect(page.getByRole('heading', { name: '正在适配新平台资料', exact: true })).toBeVisible();
  expect(state.writes).toHaveLength(0);
});

test('original confirmed points remain readonly and have original evidence during adaptation', async ({ page }) => {
  const state = await mockApi(page, adaptationTask()); await page.goto('/');
  await page.getByRole('button', { name: '核心卖点', exact: true }).click();
  await expect(page.getByRole('heading', { name: '已确认的核心卖点', exact: true })).toBeVisible();
  await expect(page.getByRole('checkbox', { name: /^选用卖点/ })).toHaveCount(0);
  await expect(page.getByRole('button', { name: /确认.*开始写稿/ })).toHaveCount(0);
  await page.getByText('查看原确认依据', { exact: true }).first().click();
  await expect(page.locator('.confirmed-point-record blockquote').first()).toBeVisible();
  await page.screenshot({ path: 'qa/screenshots/platform-confirmed-points-desktop.png', fullPage: false });
  await page.setViewportSize({ width: 390, height: 1050 });
  await page.locator('.confirmed-point-record').scrollIntoViewIfNeeded();
  await page.screenshot({ path: 'qa/screenshots/platform-confirmed-points-mobile.png', fullPage: false });
  expect(state.writes).toHaveLength(0);
});

test('adaptation transitions to actual Writer stages and then review without another confirmation', async ({ page }) => {
  const state = await mockApi(page, adaptationTask()); await page.goto('/');
  await expect(page.getByRole('heading', { name: '正在适配新平台资料', exact: true })).toBeVisible();
  const ids = state.task!.platform_selection!.plan.selected_point_ids!;
  state.task = { ...state.task!, status: 'writing', version: 32, writer_stage: 'outlining', plan: { ...state.task!.platform_selection!.plan, schema_version: '3', phase: 'selection', sections: [] }, selection_confirmation: { selection_hash: 'fixture-selection', authorization: 'platform_only', authorized_version: 31, at: '2026-10-21T12:00:00Z' } };
  await expect(page.getByRole('heading', { name: '正在安排结构与配图', exact: true })).toBeVisible({ timeout: 10000 });
  state.task = { ...selectionPreviewComposition(state.task!, ids), version: 33 };
  await expect(page.getByRole('heading', { name: '正在生成正文', exact: true })).toBeVisible({ timeout: 10000 });
  state.task = { ...selectionPreviewDocument(state.task!), version: 34 };
  await expect(page.getByLabel('标题', { exact: true })).toBeVisible({ timeout: 10000 });
  await expect(page.getByRole('button', { name: '确认卖点，开始写稿', exact: true })).toHaveCount(0);
  expect(state.writes).toHaveLength(0);
});

test('failed platform adaptation keeps the confirmed snapshot and supports explicit platform retry', async ({ page }) => {
  const task = adaptationTask(); task.status = 'error'; task.error = '模拟：新平台素材检查暂时失败';
  const state = await mockApi(page, task);
  await page.route('**/api/tasks/fixture-task/replan', async route => {
    state.writes.push({ path: '/replan', body: route.request().postDataJSON() });
    state.task = { ...state.task!, status: 'planning', error: null, version: 32 };
    await route.fulfill({ status: 202, json: { accepted: true } });
  });
  await page.goto('/');
  await expect(page.getByRole('button', { name: '确认核心卖点 已完成', exact: true })).toBeVisible();
  await page.getByRole('button', { name: '重试平台资料适配', exact: true }).click();
  await expect(page.getByRole('heading', { name: '正在适配新平台资料', exact: true })).toBeVisible();
  expect(state.writes).toEqual([{ path: '/replan', body: { version: 31 } }]);
  expect(state.task!.platform_selection!.plan.selected_point_ids).toEqual(task.platform_selection!.plan.selected_point_ids);
});

test('stale adaptation retry preserves the snapshot but locks further writes', async ({ page }) => {
  const task = adaptationTask(); task.status = 'error'; task.error = '模拟：适配失败';
  await mockApi(page, task);
  await page.route('**/api/tasks/fixture-task/replan', route => route.fulfill({ status: 409, json: { detail: '任务已更新' } }));
  await page.goto('/'); await page.getByRole('button', { name: '重试平台资料适配', exact: true }).click();
  await expect(page.getByRole('button', { name: '重试平台资料适配', exact: true })).toBeDisabled();
  await expect(page.getByRole('button', { name: '重新载入最新版本', exact: true })).toBeVisible();
});

for (const history of ['evidence_refreshes', 'point_replans', 'resolution_history'] as const) test(`later ${history} is not misrepresented as platform adaptation`, async ({ page }) => {
  const task = adaptationTask(); task.version = 35; task[history] = [{ authorized_version: 35 }];
  await mockApi(page, task); await page.goto('/');
  await expect(page.getByRole('heading', { name: '正在适配新平台资料', exact: true })).toHaveCount(0);
  await expect(page.getByRole('button', { name: '确认核心卖点 已完成', exact: true })).toHaveCount(0);
  await expect(page.getByRole('button', { name: '知识库依据', exact: true })).toHaveAttribute('aria-current', 'page');
});

for (const mismatch of ['hash', 'platform'] as const) test(`a ${mismatch} mismatch cannot authorize a platform adaptation display`, async ({ page }) => {
  const task = adaptationTask();
  if (mismatch === 'hash') task.brief_analysis_hash = 'other-hash';
  else task.platform_changes![0].to_platform = 'xiaohongshu';
  await mockApi(page, task); await page.goto('/');
  await expect(page.getByRole('heading', { name: '正在适配新平台资料', exact: true })).toHaveCount(0);
});

test('unconfirmed points are never displayed as a completed confirmation', async ({ page }) => {
  const task = adaptationTask(); task.platform_selection!.confirmed = false;
  await mockApi(page, task); await page.goto('/');
  await expect(page.getByRole('button', { name: '确认核心卖点 已完成', exact: true })).toHaveCount(0);
  await expect(page.getByRole('heading', { name: '正在适配新平台资料', exact: true })).toHaveCount(0);
});

test('initial selling point planning retains its original workflow', async ({ page }) => {
  const task = selectionPreviewTask(); task.id = 'fixture-task'; task.status = 'planning'; task.plan = null;
  await mockApi(page, task); await page.goto('/');
  await expect(page.getByRole('heading', { name: '正在适配新平台资料', exact: true })).toHaveCount(0);
  await expect(page.getByRole('button', { name: '知识库依据', exact: true })).toHaveAttribute('aria-current', 'page');
});

for (const width of [1440, 390]) test(`platform adaptation is accessible at ${width}px`, async ({ page }) => {
  await page.setViewportSize({ width, height: 1050 }); await mockApi(page, adaptationTask()); await page.goto('/');
  await expect(page.getByRole('heading', { name: '正在适配新平台资料', exact: true })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  expect((await new AxeBuilder({ page }).withTags(['wcag2a','wcag2aa','wcag21aa']).analyze()).violations).toEqual([]);
  await page.screenshot({ path: `qa/screenshots/platform-adaptation-${width}.png`, fullPage: false });
});


test('a fast platform adaptation pause keeps the draft workspace even if status remains needs_review', async ({ page }) => {
  const initial = adaptationTask();
  const plan = initial.platform_selection!.plan;
  const original = selectionPreviewDocument(selectionPreviewComposition({ ...initial, plan, status: 'needs_review' }, plan.selected_point_ids!));
  const state = await mockApi(page, original);
  await page.route('**/api/tasks/fixture-task/modify', async route => {
    state.writes.push({ path: '/modify', body: route.request().postDataJSON() });
    state.task = { ...adaptationTask(), version: 32, status: 'needs_review', error: '模拟：平台适配需要处理图片问题' };
    await route.fulfill({ status: 202, json: { accepted: true } });
  });
  await page.goto('/'); await page.getByRole('button', { name: '知识库依据', exact: true }).click();
  await page.getByText('调整任务目标或平台', { exact: false }).first().click();
  await page.getByLabel('新的修改要求', { exact: true }).fill('改成微信公众号');
  page.once('dialog', dialog => dialog.accept());
  await page.getByRole('button', { name: '提交修改要求', exact: true }).click();
  await expect(page.getByRole('heading', { name: '新平台资料适配已暂停', exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: '图文与核验', exact: true })).toHaveAttribute('aria-current', 'page');
});
