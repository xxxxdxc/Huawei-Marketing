import { test, expect, type Page } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import { makeTask, makeV2Task, mockApi } from './fixtures';
import { selectionPreviewTask } from '../src/selectionPreviewData';
import type { ReviewOverview } from '../src/evidenceResolutionTypes';

async function setup(page: Page, options: { blocker?: boolean; unmet?: boolean; overviewFailure?: boolean } = {}) {
  const task = makeV2Task(true);
  task.status = 'error'; task.resume_status = 'needs_review'; task.plan = null; task.document = null; task.review = null;
  task.error = '候选卖点关联了没有对应证据的检索请求';
  task.package = makeTask('plan_ready').package;
  task.package!.coverage = [{ request_id: 'r1', status: 'not_found', fact_ids: [], reason: '模拟：该方向缺少依据' }, { request_id: 'r2', status: 'supported', fact_ids: ['fact-1'], reason: '模拟：保留方向有依据' }];
  task.package!.evidence_gaps = [];
  task.execution_scope = { omitted_request_ids: ['r1'], omitted_direction_ids: [] };
  const state = await mockApi(page, task);
  const local = { overviewFailure: !!options.overviewFailure, retryFailure: 0, calls: [] as { path: string; body: any }[] };
  const summary: ReviewOverview = { version: task.version, knowledge_source: 'ima', task_upload_supported: false, actions: ['adjust_content', 'refresh_evidence', 'modify_requirements'], available_facts: task.package!.facts, material_requirements: [], blockers: options.blocker ? [{ code: 'image_shortage', reason: '模拟：可用图片不足，请补充图片', waivable: false }] : [], unmet_requirements: [{ request: { id: 'r1', question: '模拟：安静学习是否有依据？', priority: 'required' }, coverage: task.package!.coverage[0], found: [], missing: '模拟：未找到噪音资料', affected_direction_ids: [], blocking: !!options.unmet, omitted: !options.unmet, can_drop: true }] };
  await page.route('**/api/tasks/fixture-task/evidence-review', route => route.fulfill({ status: local.overviewFailure ? 503 : 200, json: local.overviewFailure ? { detail: '模拟：无法读取当前门槛' } : summary }));
  await page.route('**/api/tasks/fixture-task/resume-plan', async route => {
    const body = route.request().postDataJSON(); local.calls.push({ path: '/resume-plan', body });
    if (local.retryFailure) return route.fulfill({ status: local.retryFailure, json: { detail: local.retryFailure === 409 ? '任务已更新' : '模拟：规划暂未完成，请重试' } });
    const next = selectionPreviewTask(); next.id = 'fixture-task'; next.version = task.version + 1; next.execution_scope = structuredClone(task.execution_scope);
    state.task = next;
    return route.fulfill({ status: 202, json: { accepted: true } });
  });
  await page.goto('/');
  return { state, local, summary };
}

test('handled evidence gaps expose a real planning recovery instead of an impossible omission form', async ({ page }) => {
  const { state, local } = await setup(page);
  await expect(page.getByText('卖点规划已暂停', { exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: '重新生成卖点建议', exact: true })).toBeEnabled();
  await expect(page.getByRole('button', { name: '查看取舍影响', exact: true })).toHaveCount(0);
  await page.getByRole('button', { name: '生成卖点建议 已暂停', exact: true }).click();
  await expect(page.getByRole('button', { name: '重新生成卖点建议', exact: true })).toBeVisible();
  await expect(page.getByText('已确认的省略内容会保留，不会重新写入。', { exact: true })).toBeVisible();
  await page.getByText('查看已省略但未满足的需求', { exact: true }).click();
  await expect(page.getByText(/模拟：安静学习是否有依据？/)).toBeVisible();
  await page.getByRole('button', { name: '补充依据，再检查', exact: true }).click();
  await expect(page.getByRole('button', { name: '重新生成卖点建议', exact: true })).toHaveCount(0);
  await page.getByRole('button', { name: '返回继续规划', exact: true }).click();
  await expect(page.getByRole('button', { name: '重新生成卖点建议', exact: true })).toBeEnabled();
  expect(local.calls).toHaveLength(0); expect(state.writes).toHaveLength(0);
});

test('planning recovery only runs after explicit click and stops at selling point confirmation', async ({ page }) => {
  const { state, local } = await setup(page);
  await page.getByRole('button', { name: '重新生成卖点建议', exact: true }).click();
  await expect(page.getByRole('button', { name: '确认卖点，开始写稿', exact: true })).toBeEnabled();
  expect(local.calls).toEqual([{ path: '/resume-plan', body: { version: 10 } }]);
  expect(state.task!.execution_scope!.omitted_request_ids).toEqual(['r1']);
  expect(state.writes.some(write => write.path.endsWith('/confirm-plan') || write.path.endsWith('/confirm-brief'))).toBe(false);
});

test('failed planning recovery keeps the existing omission and allows another explicit attempt', async ({ page }) => {
  const { state, local } = await setup(page); local.retryFailure = 500;
  await page.getByRole('button', { name: '重新生成卖点建议', exact: true }).click();
  await expect(page.getByText('模拟：规划暂未完成，请重试', { exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: '重新生成卖点建议', exact: true })).toBeEnabled();
  expect(state.task!.execution_scope!.omitted_request_ids).toEqual(['r1']);
  local.retryFailure = 0; await page.getByRole('button', { name: '重新生成卖点建议', exact: true }).click();
  await expect(page.getByRole('button', { name: '确认卖点，开始写稿', exact: true })).toBeVisible();
  expect(local.calls).toHaveLength(2);
});

test('planning recovery version conflicts lock the stale action', async ({ page }) => {
  const { local } = await setup(page); local.retryFailure = 409;
  await page.getByRole('button', { name: '重新生成卖点建议', exact: true }).click();
  await expect(page.getByRole('button', { name: '重新载入最新版本', exact: true }).first()).toBeVisible();
  await expect(page.getByRole('button', { name: '重新生成卖点建议', exact: true })).toBeDisabled();
  expect(local.calls).toHaveLength(1);
});

for (const reason of ['blocker', 'unmet', 'overviewFailure'] as const) test(`planning recovery cannot bypass ${reason}`, async ({ page }) => {
  const { local } = await setup(page, { [reason]: true });
  await expect(page.getByRole('button', { name: '重新生成卖点建议', exact: true })).toHaveCount(0);
  if (reason === 'blocker') await expect(page.getByText('模拟：可用图片不足，请补充图片')).toBeVisible();
  if (reason === 'unmet') await expect(page.getByRole('button', { name: '查看取舍影响', exact: true })).toBeVisible();
  if (reason === 'overviewFailure') await expect(page.getByRole('button', { name: '重新读取审查结果' })).toBeVisible();
  expect(local.calls).toHaveLength(0);
});

for (const width of [1440, 390]) test(`planning recovery remains accessible and usable at ${width}px`, async ({ page }) => {
  await page.setViewportSize({ width, height: 1050 }); await setup(page);
  const button = page.getByRole('button', { name: '重新生成卖点建议', exact: true });
  await expect(button).toBeEnabled(); await button.focus(); await expect(button).toBeFocused();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  expect((await new AxeBuilder({ page }).withTags(['wcag2a','wcag2aa','wcag21aa']).analyze()).violations).toEqual([]);
  await page.screenshot({ path: `qa/screenshots/planning-recovery-${width}.png`, fullPage: false });
});
