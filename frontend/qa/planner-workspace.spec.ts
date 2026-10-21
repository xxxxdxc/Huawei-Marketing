import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import { plannerPreviewTask } from '../src/plannerPreviewData';
import { mockApi, watermark } from './fixtures';
function fixturePlan() { const task = plannerPreviewTask(); task.id = 'fixture-task'; return task; }

test('V2 candidates expose source evidence without changing the task', async ({ page }) => {
  const state = await mockApi(page, fixturePlan());
  await page.goto('/');
  await expect(page.getByRole('region', { name: '卖点取舍与排序' })).toBeVisible();
  const candidates = page.locator('.planner-point');
  await expect(candidates).toHaveCount(3);
  await expect(candidates.first()).toContainText('83.8');
  await candidates.first().getByRole('button', { name: 'F01 · 查看原文' }).click();
  await expect(page.getByRole('dialog')).toContainText('仅用于演示事实引用');
  await page.getByRole('button', { name: '关闭面板' }).click();
  await candidates.first().getByText('查看评分依据', { exact: true }).click();
  await expect(candidates.first().getByText('受众关联', { exact: true })).toBeVisible();
  expect(state.task!.version).toBe(1);
});

test('paragraph decisions keep the selected scope in the unchanged plan API shell', async ({ page }) => {
  const state = await mockApi(page, fixturePlan()); await page.goto('/');
  await expect(page.getByLabel('叙事框架', { exact: true })).toHaveCount(0);
  await page.getByLabel('读者问题', { exact: true }).first().fill('怎样整理课堂中的学习信息？');
  await page.getByLabel('段落篇幅预算（字）', { exact: true }).first().fill('140');
  await page.locator('.planner-section-points').first().getByLabel('围绕专注学习组织信息', { exact: false }).check();
  await expect(page.getByText('规划已修改，以下评分仅为生成时记录，不代表当前规划的最新评价。')).toBeVisible();
  await page.getByRole('button', { name: '保存规划', exact: true }).click();
  expect(state.task!.plan!.sections[0].reader_question).toBe('怎样整理课堂中的学习信息？');
  expect(state.task!.plan!.selected_point_ids).toEqual(['C1', 'C2']);
  expect(state.task!.plan!.sections[0].target_chars).toBe(140);
  expect(state.task!.plan!.sections[0].point_ids).toEqual(['C1', 'C2']);
  expect(state.task!.document).toBeNull();
});

test('invalid budget blocks confirmation while draft saving stays available', async ({ page }) => {
  await mockApi(page, fixturePlan()); await page.goto('/');
  await page.getByLabel('段落篇幅预算（字）', { exact: true }).first().fill('800');
  await expect(page.getByRole('button', { name: '确认规划，开始写稿' })).toBeDisabled();
  await expect(page.getByRole('button', { name: '保存规划', exact: true })).toBeEnabled();
  await page.getByLabel('段落篇幅预算（字）', { exact: true }).first().fill('130');
  await expect(page.getByRole('button', { name: '确认规划，开始写稿' })).toBeEnabled();
});

test('duplicate reader questions require a clear correction', async ({ page }) => {
  await mockApi(page, fixturePlan()); await page.goto('/');
  const questions = page.getByLabel('读者问题', { exact: true });
  await questions.nth(1).fill(await questions.first().inputValue());
  await expect(page.getByText('第 2 段的读者问题与其他段落重复。', { exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: '确认规划，开始写稿' })).toBeDisabled();
});

test('stale server analysis does not claim fresh scores or passed content review', async ({ page }) => {
  const task = fixturePlan(); task.plan!.planning_analysis!.status = 'user_modified';
  task.plan!.selected_point_ids = []; task.plan!.sections.forEach(s => { s.point_ids = []; });
  await mockApi(page, task); await page.goto('/');
  await expect(page.locator('.planner-point-state').first()).toHaveText('备选方向');
  await expect(page.locator('.planner-stale')).toBeVisible();
  await expect(page.getByRole('button', { name: '确认规划，开始写稿' })).toBeVisible();
  await expect(page.getByRole('button', { name: '下载 Markdown' })).toHaveCount(0);
});

for (const width of [1440, 390]) test(`V2 preview remains usable and accessible at ${width}px`, async ({ page }) => {
  await page.setViewportSize({ width, height: 1050 });
  const errors: string[] = []; page.on('pageerror', error => errors.push(error.message));
  await page.goto('/?preview=planner-v2');
  await expect(page.getByRole('heading', { name: '图文规划工作台', exact: true })).toBeVisible();
  await expect(page.locator('.image-choice img').first()).toBeVisible();
  await page.locator('.image-choice img').first().scrollIntoViewIfNeeded();
  await expect(page.locator('.image-choice img').first()).toHaveJSProperty('naturalWidth', 800);
  await page.evaluate(() => window.scrollTo(0, 0));
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  expect((await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze()).violations).toEqual([]);
  await watermark(page);
  await page.screenshot({ path: `qa/screenshots/planner-v2-workspace-${width}.png`, fullPage: false });
  expect(errors).toEqual([]);
});

test('preview uses only local state and retains second explicit confirmation', async ({ page }) => {
  let writes = 0; page.on('request', r => { if (r.url().includes('/api/') && r.method() !== 'GET') writes++; });
  await page.goto('/?preview=planner-v2&platform=wechat');
  await page.getByLabel('图片插入位置', { exact: true }).first().selectOption('before_section');
  await page.getByRole('button', { name: '保存规划', exact: true }).click();
  await expect(page.getByText('演示修改已保存。原评分仅保留为生成时记录。', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: '确认规划，开始写稿' }).click();
  await expect(page.getByText('演示规划已确认。本页不执行写稿；实际工作台会在此开始生成。', { exact: true })).toBeVisible();
  expect(writes).toBe(0);
});
