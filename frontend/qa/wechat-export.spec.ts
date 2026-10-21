import { test, expect } from '@playwright/test';
import { makeTask, mockApi } from './fixtures';

test('WeChat layout entry opens a versioned preview without task writes', async ({ page }) => {
  const state = await mockApi(page, makeTask('approved', 'wechat'));
  await page.addInitScript(() => { window.open = ((...args: unknown[]) => { (window as any).__wechatOpen = args; return null; }) as typeof window.open; });
  await page.goto('/');
  await page.getByRole('button', { name: '公众号排版与复制', exact: true }).click();
  const args = await page.evaluate(() => (window as any).__wechatOpen);
  expect(args[0]).toBe('/api/tasks/fixture-task/wechat/preview?version=10');
  expect(args[2]).toBe('noopener,noreferrer');
  expect(state.writes).toHaveLength(0);
});

test('WeChat export entry is disabled after an unsaved edit', async ({ page }) => {
  await mockApi(page, makeTask('approved', 'wechat'));
  await page.goto('/');
  await page.getByLabel('标题', { exact: true }).fill('待重新核验的修改');
  await expect(page.getByRole('button', { name: '公众号排版与复制', exact: true })).toBeDisabled();
});

test('WeChat export entry requires passed review', async ({ page }) => {
  await mockApi(page, makeTask('needs_review', 'wechat'));
  await page.goto('/');
  await expect(page.getByRole('button', { name: '公众号排版与复制', exact: true })).toBeDisabled();
});

for (const platform of ['xiaohongshu', 'moments']) {
  test(platform + ' does not load the WeChat layout entry', async ({ page }) => {
    await mockApi(page, makeTask('approved', platform));
    await page.goto('/');
    await expect(page.getByRole('button', { name: '公众号排版与复制', exact: true })).toHaveCount(0);
  });
}

test('mobile WeChat export action remains visible without horizontal overflow', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await mockApi(page, makeTask('approved', 'wechat'));
  await page.goto('/');
  const entry=page.getByRole('button', { name: '公众号排版与复制', exact: true });
  await entry.scrollIntoViewIfNeeded();
  await expect(entry).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  const bounds=await entry.boundingBox();
  expect(bounds!.x).toBeGreaterThanOrEqual(0);
  expect(bounds!.x+bounds!.width).toBeLessThanOrEqual(390);
});
