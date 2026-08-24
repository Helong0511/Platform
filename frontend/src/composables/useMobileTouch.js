/**
 * 移动端触摸手势支持 Composable
 * 提供触摸优化、手势识别等功能
 */

import { ref, onMounted, onUnmounted } from 'vue';

/**
 * 触摸手势支持
 * @param {Object} options 配置选项
 * @returns {Object} 触摸相关的方法和状态
 */
export function useMobileTouch(options = {}) {
  const {
    onSwipeLeft = null,
    onSwipeRight = null,
    onSwipeUp = null,
    onSwipeDown = null,
    onTap = null,
    onLongPress = null,
    swipeThreshold = 50, // 滑动阈值（像素）
    longPressDelay = 500, // 长按延迟（毫秒）
    preventDefault = true // 是否阻止默认行为
  } = options;

  // touchStartX 响应式状态
  const touchStartX = ref(0);
  const touchStartY = ref(0);
  // touchEndX 响应式状态
  const touchEndX = ref(0);
  const touchEndY = ref(0);
  // isTouching 响应式状态
  const isTouching = ref(false);
  const longPressTimer = ref(null);

  // 处理触摸开始
  const handleTouchStart = (e) => {
    const touch = e.touches[0];
    touchStartX.value = touch.clientX;
    touchStartY.value = touch.clientY;
    isTouching.value = true;

    // 长按检测
    if (onLongPress) {
      longPressTimer.value = setTimeout(() => {
        if (isTouching.value) {
          onLongPress(e);
          isTouching.value = false;
        }
      }, longPressDelay);
    }

    if (preventDefault) {
      e.preventDefault();
    }
  };

  // 处理触摸移动
  const handleTouchMove = (e) => {
    // 如果移动距离较大，取消长按
    if (longPressTimer.value) {
      const touch = e.touches[0];
      const deltaX = Math.abs(touch.clientX - touchStartX.value);
      const deltaY = Math.abs(touch.clientY - touchStartY.value);
      
      if (deltaX > 10 || deltaY > 10) {
        clearTimeout(longPressTimer.value);
        longPressTimer.value = null;
      }
    }

    if (preventDefault) {
      e.preventDefault();
    }
  };

  // 处理触摸结束
  const handleTouchEnd = (e) => {
    if (longPressTimer.value) {
      clearTimeout(longPressTimer.value);
      longPressTimer.value = null;
    }

    if (!isTouching.value) {
      return;
    }

    const touch = e.changedTouches[0];
    touchEndX.value = touch.clientX;
    touchEndY.value = touch.clientY;

    const deltaX = touchEndX.value - touchStartX.value;
    const deltaY = touchEndY.value - touchStartY.value;
    const absDeltaX = Math.abs(deltaX);
    const absDeltaY = Math.abs(deltaY);

    // 判断是否为点击
    if (absDeltaX < 10 && absDeltaY < 10) {
      if (onTap) {
        onTap(e);
      }
      isTouching.value = false;
      return;
    }

    // 判断滑动方向
    if (absDeltaX > absDeltaY) {
      // 水平滑动
      if (absDeltaX > swipeThreshold) {
        if (deltaX > 0 && onSwipeRight) {
          onSwipeRight(e, deltaX);
        } else if (deltaX < 0 && onSwipeLeft) {
          onSwipeLeft(e, absDeltaX);
        }
      }
    } else {
      // 垂直滑动
      if (absDeltaY > swipeThreshold) {
        if (deltaY > 0 && onSwipeDown) {
          onSwipeDown(e, deltaY);
        } else if (deltaY < 0 && onSwipeUp) {
          onSwipeUp(e, absDeltaY);
        }
      }
    }

    isTouching.value = false;

    if (preventDefault) {
      e.preventDefault();
    }
  };

  // 处理触摸取消
  const handleTouchCancel = (e) => {
    if (longPressTimer.value) {
      clearTimeout(longPressTimer.value);
      longPressTimer.value = null;
    }
    isTouching.value = false;

    if (preventDefault) {
      e.preventDefault();
    }
  };

  // 绑定触摸事件
  const bindTouchEvents = (element) => {
    if (!element) return;

    element.addEventListener('touchstart', handleTouchStart, { passive: !preventDefault });
    element.addEventListener('touchmove', handleTouchMove, { passive: !preventDefault });
    element.addEventListener('touchend', handleTouchEnd, { passive: !preventDefault });
    element.addEventListener('touchcancel', handleTouchCancel, { passive: !preventDefault });
  };

  // 解绑触摸事件
  const unbindTouchEvents = (element) => {
    if (!element) return;

    element.removeEventListener('touchstart', handleTouchStart);
    element.removeEventListener('touchmove', handleTouchMove);
    element.removeEventListener('touchend', handleTouchEnd);
    element.removeEventListener('touchcancel', handleTouchCancel);
  };

  // 清理
  const cleanup = () => {
    if (longPressTimer.value) {
      clearTimeout(longPressTimer.value);
      longPressTimer.value = null;
    }
  };

  onUnmounted(() => {
    cleanup();
  });

  return {
    bindTouchEvents,
    unbindTouchEvents,
    isTouching,
    cleanup
  };
}

/**
 * 移动端下拉刷新支持
 * @param {Function} onRefresh 刷新回调
 * @param {Object} options 配置选项
 * @returns {Object} 下拉刷新相关的方法和状态
 */
export function usePullToRefresh(onRefresh, options = {}) {
  const {
    threshold = 80, // 下拉阈值（像素）
    resistance = 2.5, // 阻力系数
    maxPullDistance = 150 // 最大下拉距离
  } = options;

  // isRefreshing 响应式状态
  const isRefreshing = ref(false);
  const pullDistance = ref(0);
  // startY 响应式状态
  const startY = ref(0);
  const currentY = ref(0);
  // isPulling 响应式状态
  const isPulling = ref(false);

  const handleTouchStart = (e) => {
    // 只在页面顶部时才能下拉刷新
    if (window.scrollY > 0) {
      return;
    }

    startY.value = e.touches[0].clientY;
    isPulling.value = true;
  };

  const handleTouchMove = (e) => {
    if (!isPulling.value || isRefreshing.value) {
      return;
    }

    currentY.value = e.touches[0].clientY;
    const deltaY = currentY.value - startY.value;

    if (deltaY > 0) {
      // 计算下拉距离（带阻力）
      pullDistance.value = Math.min(
        deltaY / resistance,
        maxPullDistance
      );

      // 阻止默认滚动行为
      if (pullDistance.value > 0) {
        e.preventDefault();
      }
    } else {
      pullDistance.value = 0;
    }
  };

  const handleTouchEnd = async () => {
    if (!isPulling.value) {
      return;
    }

    if (pullDistance.value >= threshold && !isRefreshing.value) {
      isRefreshing.value = true;
      
      try {
        await onRefresh();
      } finally {
        isRefreshing.value = false;
        pullDistance.value = 0;
      }
    } else {
      // 回弹
      pullDistance.value = 0;
    }

    isPulling.value = false;
    startY.value = 0;
    currentY.value = 0;
  };

  const bindPullToRefresh = (element) => {
    if (!element) return;

    element.addEventListener('touchstart', handleTouchStart, { passive: false });
    element.addEventListener('touchmove', handleTouchMove, { passive: false });
    element.addEventListener('touchend', handleTouchEnd, { passive: true });
  };

  const unbindPullToRefresh = (element) => {
    if (!element) return;

    element.removeEventListener('touchstart', handleTouchStart);
    element.removeEventListener('touchmove', handleTouchMove);
    element.removeEventListener('touchend', handleTouchEnd);
  };

  onUnmounted(() => {
    pullDistance.value = 0;
    isPulling.value = false;
    isRefreshing.value = false;
  });

  return {
    isRefreshing,
    pullDistance,
    bindPullToRefresh,
    unbindPullToRefresh
  };
}

/**
 * 移动端双击缩放禁用
 */
export function disableDoubleTapZoom() {
  let lastTouchEnd = 0;

  const handleTouchEnd = (e) => {
    const now = Date.now();
    if (now - lastTouchEnd <= 300) {
      e.preventDefault();
    }
    lastTouchEnd = now;
  };

  onMounted(() => {
    document.addEventListener('touchend', handleTouchEnd, { passive: false });
  });

  onUnmounted(() => {
    document.removeEventListener('touchend', handleTouchEnd);
  });
}

/**
 * 移动端视口高度修复（解决移动端浏览器地址栏导致的高度问题）
 */
export function useViewportHeight() {
  const setViewportHeight = () => {
    // iOS Safari 地址栏伸缩时 visualViewport 比 innerHeight 更准确
    const height = window.visualViewport?.height ?? window.innerHeight;
    const vh = height * 0.01;
    document.documentElement.style.setProperty('--vh', `${vh}px`);
  };

  onMounted(() => {
    setViewportHeight();
    window.addEventListener('resize', setViewportHeight);
    window.addEventListener('orientationchange', setViewportHeight);
    window.visualViewport?.addEventListener('resize', setViewportHeight);
    window.visualViewport?.addEventListener('scroll', setViewportHeight);
  });

  onUnmounted(() => {
    window.removeEventListener('resize', setViewportHeight);
    window.removeEventListener('orientationchange', setViewportHeight);
    window.visualViewport?.removeEventListener('resize', setViewportHeight);
    window.visualViewport?.removeEventListener('scroll', setViewportHeight);
  });

  return {
    setViewportHeight
  };
}

