/**
 * 空闲时预加载路由懒加载 chunk，减少菜单切换等待（尤其 Vite 开发模式）。
 */
import router from '../router';

const prefetched = new WeakSet();

function loadComponent(loader) {
  if (typeof loader !== 'function' || prefetched.has(loader)) {
    return;
  }
  prefetched.add(loader);
  loader().catch(() => {
    prefetched.delete(loader);
  });
}

/** 预加载指定路径匹配到的全部懒加载组件 */
export function prefetchRoute(path) {
  try {
    const resolved = router.resolve(path);
    for (const record of resolved.matched) {
      for (const comp of Object.values(record.components || {})) {
        loadComponent(comp);
      }
    }
  } catch {
    // 忽略无效路径
  }
}

/** 登录后空闲时预加载所有已注册路由组件（全局仅调度一次） */
let allRoutesPrefetchScheduled = false;

export function prefetchAllRoutes() {
  if (allRoutesPrefetchScheduled) {
    return;
  }
  allRoutesPrefetchScheduled = true;

  const schedule =
    typeof requestIdleCallback === 'function'
      ? (fn) => requestIdleCallback(fn, { timeout: 8000 })
      : (fn) => setTimeout(fn, 1500);

  schedule(() => {
    for (const route of router.getRoutes()) {
      for (const comp of Object.values(route.components || {})) {
        loadComponent(comp);
      }
    }
  });
}
