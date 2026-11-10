import assert from 'node:assert/strict';
import { chromium } from 'playwright';

const baseURL = process.env.E2E_BASE_URL || 'http://127.0.0.1:4173';
const browser = await chromium.launch({ headless: true });
const failures = [];

const mockApi = async (page) => {
  let currentUser = null;

  await page.route('**/api/v1/**', async (route) => {
    const request = route.request();
    const pathname = new URL(request.url()).pathname;
    const headers = {
      'content-type': 'application/json; charset=utf-8',
      'x-csrf-token': 'isolated-e2e-csrf-token'
    };

    if (pathname === '/api/v1/auth/login' && request.method() === 'POST') {
      const form = new URLSearchParams(request.postData() || '');
      const username = form.get('username') || '';
      const password = form.get('password') || '';

      if (password === 'wrong-password') {
        await route.fulfill({
          status: 401,
          headers,
          body: JSON.stringify({ detail: '用户名或密码不正确' })
        });
        return;
      }

      const isClient = username === 'e2e_client';
      currentUser = isClient
        ? {
            id: 202,
            username,
            full_name: 'E2E 客户',
            role: 'client',
            has_publisher: true,
            client: { has_publisher: true }
          }
        : {
            id: 101,
            username,
            full_name: 'E2E 管理员',
            role: 'admin',
            has_publisher: false
          };

      await route.fulfill({
        status: 200,
        headers: {
          ...headers,
          'set-cookie': 'access_token=e2e-isolated-session; HttpOnly; Path=/; SameSite=Lax'
        },
        body: JSON.stringify({ token_type: 'bearer', user: currentUser })
      });
      return;
    }

    if (pathname.endsWith('/dashboard/stats')) {
      await route.fulfill({
        status: 200,
        headers,
        body: JSON.stringify({ code: 200, message: 'success', data: { stats: [] } })
      });
      return;
    }

    if (pathname.endsWith('/dashboard/trends')) {
      await route.fulfill({
        status: 200,
        headers,
        body: JSON.stringify({ code: 200, message: 'success', data: { dates: [], series: [] } })
      });
      return;
    }

    if (pathname.endsWith('/users/me')) {
      await route.fulfill({
        status: 200,
        headers,
        body: JSON.stringify({ code: 200, message: 'success', data: currentUser || {} })
      });
      return;
    }

    await route.fulfill({
      status: 200,
      headers,
      body: JSON.stringify({
        code: 200,
        message: 'success',
        data: [],
        total: 0,
        page: 1,
        page_size: 20,
        total_pages: 0
      })
    });
  });
};

const newPage = async (viewport) => {
  const context = await browser.newContext({ viewport });
  const page = await context.newPage();
  page.on('pageerror', (error) => failures.push(error.message));
  await mockApi(page);
  return { context, page };
};

const loginAs = async (page, username, password = 'correct-password') => {
  await page.goto(baseURL + '/login');
  await page.locator('#username').fill(username);
  await page.locator('#password').fill(password);
  await page.getByRole('button', { name: '登录' }).click();
};

try {
  // 桌面端：表单校验、错误密码、成功登录、管理员菜单导航、退出登录。
  {
    const { context, page } = await newPage({ width: 1365, height: 900 });
    await page.goto(baseURL + '/login');
    await page.getByRole('button', { name: '登录' }).click();
    await page.locator('.el-form-item__error').first().waitFor({ timeout: 5000 });

    await page.locator('#username').fill('e2e_admin');
    await page.locator('#password').fill('wrong-password');
    await page.getByRole('button', { name: '登录' }).click();
    await page.getByText('用户名或密码不正确', { exact: false }).first().waitFor({ timeout: 5000 });
    assert.match(new URL(page.url()).pathname, /\/login$/);

    await page.locator('#password').fill('correct-password');
    await page.getByRole('button', { name: '登录' }).click();
    await page.waitForURL('**/app/dashboard', { timeout: 15000 });
    await page.getByText('广告数据平台', { exact: true }).waitFor({ timeout: 10000 });

    await page.locator('.desktop-sidebar .el-menu-item').filter({ hasText: 'Postback管理' }).click();
    await page.waitForURL('**/app/admin/postback', { timeout: 10000 });
    await page.getByRole('heading', { name: 'Postback 转化管理' }).waitFor({ timeout: 10000 });

    await page.getByRole('button', { name: /退出登录/ }).click();
    await page.getByText('确定要退出登录吗？', { exact: false }).waitFor({ timeout: 5000 });
    await page.locator('.el-message-box').getByRole('button', { name: '确定' }).click();
    await page.waitForURL('**/login', { timeout: 10000 });
    await context.close();
  }

  // 移动端：真实抽屉菜单交互、点击导航后自动关闭并进入目标页面。
  {
    const { context, page } = await newPage({ width: 390, height: 844 });
    await loginAs(page, 'e2e_admin');
    await page.waitForURL('**/app/dashboard', { timeout: 15000 });
    await page.getByRole('button', { name: '打开导航菜单' }).click();
    await page.locator('.el-drawer').waitFor({ state: 'visible', timeout: 5000 });
    await page.locator('.drawer-menu-scroll .el-menu-item')
      .filter({ hasText: 'Postback管理' })
      .click();
    await page.waitForURL('**/app/admin/postback', { timeout: 10000 });
    await page.getByRole('heading', { name: 'Postback 转化管理' }).waitFor({ timeout: 10000 });
    await page.locator('.el-drawer').waitFor({ state: 'hidden', timeout: 5000 });
    await context.close();
  }

  // 客户角色：不显示管理员菜单，手动访问管理员路由也必须被路由守卫拦截。
  {
    const { context, page } = await newPage({ width: 1365, height: 900 });
    await loginAs(page, 'e2e_client');
    await page.waitForURL('**/app/admin/conversion-summary', { timeout: 15000 });
    assert.equal(
      await page.locator('.desktop-sidebar .el-menu-item').filter({ hasText: 'Postback管理' }).count(),
      0
    );

    await page.goto(baseURL + '/app/admin/postback');
    await page.waitForURL('**/app/admin/conversion-summary', { timeout: 10000 });
    assert.equal(
      await page.locator('.desktop-sidebar .el-menu-item').filter({ hasText: 'Postback管理' }).count(),
      0
    );
    await context.close();
  }

  assert.deepEqual(failures, [], '浏览器页面发生未捕获异常');
  process.stdout.write('Browser E2E passed: login validation, auth failure/success, admin navigation, logout, mobile drawer, client RBAC.\n');
} finally {
  await browser.close();
}
