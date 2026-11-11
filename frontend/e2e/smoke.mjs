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

    const normalizedPath = pathname.replace(/\\/+$/, '');
    if (normalizedPath === '/api/v1/third-party-reports' && request.method() === 'GET') {
      await route.fulfill({
        status: 200,
        headers,
        body: JSON.stringify({
          code: 200,
          message: 'success',
          data: [
            {
              id: 1, source: 'postback', adsid: 'e2e-ad-retry', event: 'Purchase',
              conversion_id: 'e2e-conversion-retry', currency: 'USD', amount: '9.50',
              status: 'failed', attempt_count: 2, max_attempts: 12,
              response_status: 503, log_id: null, created_at: '2026-11-11T10:00:00',
              report_start_time: '2026-11-11T09:00:00',
              next_retry_time: new Date(Date.now() + 300000).toISOString(),
              outbox_enqueued: true, outbox_error_category: '第三方请求超时',
              can_requeue: true, use_hash: true
            },
            {
              id: 2, source: 'postback', adsid: 'e2e-ad-config-missing', event: 'Purchase',
              conversion_id: 'e2e-conversion-config-missing', currency: 'USD', amount: '1.00',
              status: 'failed', attempt_count: 12, max_attempts: 12,
              response_status: null, log_id: null, created_at: '2026-11-11T10:01:00',
              report_start_time: null, next_retry_time: null,
              outbox_enqueued: true,
              outbox_error_category: '像素配置缺失或不可用；检查配置后可重新排队',
              can_requeue: false, use_hash: true
            }
          ],
          total: 2,
          page: 1,
          page_size: 10,
          total_pages: 1
        })
      });
      return;
    }

    if (normalizedPath === '/api/v1/third-party-reports/stats/summary' && request.method() === 'GET') {
      await route.fulfill({
        status: 200,
        headers,
        body: JSON.stringify({
          code: 200, message: 'success',
          data: { total: 2, success: 0, failed: 2, pending: 0, source_stats: { postback: 2 }, event_stats: { Purchase: 2 } }
        })
      });
      return;
    }

    if (normalizedPath === '/api/v1/third-party-reports/2' && request.method() === 'GET') {
      await route.fulfill({
        status: 200,
        headers,
        body: JSON.stringify({
          code: 200, message: 'success',
          data: {
            id: 2, source: 'postback', adsid: 'e2e-ad-config-missing', event: 'Purchase',
            conversion_id: 'e2e-conversion-config-missing', currency: 'USD', amount: '1.00',
            status: 'failed', attempt_count: 12, max_attempts: 12,
            response_status: null, log_id: null, created_at: '2026-11-11T10:01:00',
            report_start_time: null, report_success_time: null, completed_at: null,
            outbox_enqueued: true, next_retry_time: null,
            error_message: '像素配置缺失或不可用；检查配置后可重新排队',
            email: 'a***@example.invalid', ip: '203.0.*.*',
            phone: '415****0123', ua: '[已隐藏]', use_hash: true,
            report_params: '{"data":[{"user_data":{"client_ip_address":"203.0.*.*","client_user_agent":"[已隐藏]"}}]}'
          }
        })
      });
      return;
    }

    if (/\\/third-party-reports\\/\\d+\\/retry$/.test(normalizedPath) && request.method() === 'POST') {
      await route.fulfill({
        status: 200, headers,
        body: JSON.stringify({ code: 200, message: '已重新排队，后台 worker 将处理；请稍后刷新查看结果', data: { success: true } })
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

    // 第三方 Outbox：只有后端判定可重新排队的失败事件显示操作按钮。
    await page.goto(baseURL + '/app/admin/third-party-reports');
    await page.getByRole('heading', { name: '第三方上报日志' }).waitFor({ timeout: 10000 });
    const reportRows = page.locator('.el-table__body-wrapper tbody tr');
    await reportRows.nth(1).waitFor({ timeout: 10000 });
    assert.equal(await reportRows.nth(0).getByRole('button', { name: '重新排队' }).count(), 1);
    assert.equal(await reportRows.nth(1).getByRole('button', { name: '重新排队' }).count(), 0);

    await reportRows.nth(1).getByRole('button', { name: '详情' }).click();
    await page.getByText('像素配置缺失或不可用；检查配置后可重新排队', { exact: false }).waitFor({ timeout: 5000 });
    assert.equal(await page.getByText('203.0.113.77', { exact: false }).count(), 0);
    await page.locator('.report-detail-dialog .el-dialog__headerbtn').click();

    await reportRows.nth(0).getByRole('button', { name: '重新排队' }).click();
    await page.getByText('确定将这条失败的 Outbox 事件重新排队吗？', { exact: false }).waitFor({ timeout: 5000 });
    await page.locator('.el-message-box').getByRole('button', { name: '确定' }).click();
    await page.getByText('已重新排队，后台 worker 将处理', { exact: false }).waitFor({ timeout: 5000 });

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
  process.stdout.write('Browser E2E passed: login validation, auth failure/success, admin navigation, Outbox retry eligibility/details, logout, mobile drawer, client RBAC.\n');
} finally {
  await browser.close();
}
