/**
 * 广告数据相关请求配置
 */

const MOBILE_UA = /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i;

/** 列表/汇总查询超时（移动端更长） */
export function getAdDataListTimeout(desktopMs = 45000, mobileMs = 60000) {
  const isMobile = typeof navigator !== 'undefined' && MOBILE_UA.test(navigator.userAgent);
  return isMobile ? mobileMs : desktopMs;
}
