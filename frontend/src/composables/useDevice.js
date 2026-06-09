/**
 * 组合式函数 - 设备类型检测（移动/桌面）
 * @file composables/useDevice.js
 */
import { ref, computed, onMounted, onUnmounted } from 'vue';

// 设备类型枚举
export const DeviceType = {
  DESKTOP: 'desktop',
  TABLET: 'tablet',
  MOBILE: 'mobile'
};

// 断点定义
const BREAKPOINTS = {
  MOBILE: 768,   // 手机：< 768px
  TABLET: 1024,  // 平板：768px - 1024px，桌面：> 1024px
};

/**
 * 根据窗口宽度检测设备类型
 * @param {number} width - 窗口宽度
 * @returns {string} 设备类型
 */
function detectDeviceType(width) {
  if (width < BREAKPOINTS.MOBILE) {
    return DeviceType.MOBILE;
  } else if (width < BREAKPOINTS.TABLET) {
    return DeviceType.TABLET;
  } else {
    return DeviceType.DESKTOP;
  }
}

/**
 * 设备检测 Composable
 * @returns {Object} 设备信息和方法
 */
export function useDevice() {
  // deviceType 响应式状态
  const deviceType = ref(DeviceType.DESKTOP);
  const windowWidth = ref(typeof window !== 'undefined' ? window.innerWidth : 1024);
  // windowHeight 响应式状态
  const windowHeight = ref(typeof window !== 'undefined' ? window.innerHeight : 768);

  // 更新设备类型
  const updateDeviceType = () => {
    if (typeof window !== 'undefined') {
      windowWidth.value = window.innerWidth;
      windowHeight.value = window.innerHeight;
      deviceType.value = detectDeviceType(windowWidth.value);
    }
  };

  // 计算属性
  const isDesktop = computed(() => deviceType.value === DeviceType.DESKTOP);
  const isTablet = computed(() => deviceType.value === DeviceType.TABLET);
  const isMobile = computed(() => deviceType.value === DeviceType.MOBILE);
  const isMobileOrTablet = computed(() => isMobile.value || isTablet.value);

  // 防抖处理窗口大小变化
  let resizeTimer = null;
  const handleResize = () => {
    if (resizeTimer) {
      clearTimeout(resizeTimer);
    }
    resizeTimer = setTimeout(() => {
      updateDeviceType();
    }, 150); // 150ms 防抖
  };

  // 组件挂载时初始化
  onMounted(() => {
    updateDeviceType();
    window.addEventListener('resize', handleResize);
    // 监听方向变化（移动设备横竖屏切换）
    window.addEventListener('orientationchange', handleResize);
  });

  // 组件卸载时清理
  onUnmounted(() => {
    window.removeEventListener('resize', handleResize);
    window.removeEventListener('orientationchange', handleResize);
    if (resizeTimer) {
      clearTimeout(resizeTimer);
    }
  });

  return {
    deviceType,
    windowWidth,
    windowHeight,
    isDesktop,
    isTablet,
    isMobile,
    isMobileOrTablet,
    updateDeviceType,
    DeviceType,
    BREAKPOINTS
  };
}

