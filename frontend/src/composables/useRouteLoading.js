/**
 * 路由切换加载态：菜单点击后立即反馈，避免「点了没反应」体感。
 */
import { ref } from 'vue';

/** @type {import('vue').Ref<boolean>} */
export const routeNavigating = ref(false);

let navigateCount = 0;

export function beginRouteNavigation() {
  navigateCount += 1;
  routeNavigating.value = true;
}

export function endRouteNavigation() {
  navigateCount = Math.max(0, navigateCount - 1);
  if (navigateCount === 0) {
    routeNavigating.value = false;
  }
}

export function resetRouteNavigation() {
  navigateCount = 0;
  routeNavigating.value = false;
}
