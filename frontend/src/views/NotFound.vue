<template>
  <div class="not-found-container">
    <h1>404 - 页面未找到</h1>
    <p>您访问的页面不存在或已被移除</p>
    <router-link to="/dashboard" class="back-link">返回首页</router-link>
  </div>
</template>

<script setup>
// 404页面组件逻辑
</script>

<style scoped>
.not-found-container {
  padding: var(--spacing-xxxxl);
  text-align: center;
  background-color: var(--bg-page);
  min-height: calc(100vh - var(--header-height));
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
}

.not-found-container h1 {
  font-size: var(--font-size-large-title);
  font-weight: var(--font-weight-bold);
  color: var(--text-primary);
  margin-bottom: var(--spacing-lg);
}

.not-found-container p {
  font-size: var(--font-size-lg);
  color: var(--text-secondary);
  margin-bottom: var(--spacing-xxl);
}

.back-link {
  display: inline-block;
  margin-top: var(--spacing-xl);
  padding: var(--spacing-md) var(--spacing-xl);
  color: var(--primary-color);
  text-decoration: none;
  font-weight: var(--font-weight-medium);
  border: 1px solid var(--primary-color);
  border-radius: var(--radius-md);
  transition: var(--transition-base);
}

.back-link:hover {
  background-color: var(--primary-color);
  color: var(--text-white);
  transform: translateY(-2px);
  box-shadow: var(--shadow-light);
}

.back-link:active {
  transform: translateY(0);
}

/* 移动端优化 */
@media (max-width: 767px) {
  .not-found-container {
    padding: var(--spacing-xl);
  }
  
  .not-found-container h1 {
    font-size: var(--font-size-xxl);
    margin-bottom: var(--spacing-md);
  }
  
  .not-found-container p {
    font-size: var(--font-size-base);
    margin-bottom: var(--spacing-xl);
  }
  
  .back-link {
    width: 100%;
    max-width: 300px;
    min-height: var(--touch-target-size);
    text-align: center;
    padding: var(--spacing-md) var(--spacing-lg);
  }
}
</style>