/**
 * ESLint 配置
 * 统一代码规范
 */
module.exports = {
  root: true,
  env: { browser: true, es2021: true, node: true },
  extends: [
    'eslint:recommended',
    'plugin:vue/vue3-recommended'
  ],
  parserOptions: {
    ecmaVersion: 'latest',
    sourceType: 'module'
  },
  globals: {
    __APP_VERSION__: 'readonly',
  },
  rules: {
    'no-console': process.env.NODE_ENV === 'production' ? 'warn' : 'off',
    'no-debugger': process.env.NODE_ENV === 'production' ? 'warn' : 'off',
    'vue/multi-word-component-names': 'off',
    'vue/no-unused-vars': 'warn',
    'no-unused-vars': 'warn'
  },
  overrides: [
    {
      files: ['src/components/admin/ShortLinkFormDialog.vue'],
      rules: { 'vue/no-mutating-props': 'off' }
    },
    {
      // 父组件传入 reactive 表单对象，子组件 v-model 绑定字段（与 ShortLinkFormDialog 相同模式）
      files: [
        'src/components/admin/ProductFormDialog.vue',
        'src/components/admin/UserFormDialog.vue',
        'src/components/admin/UserFilterBar.vue',
        'src/components/admin/UserTable.vue',
      ],
      rules: { 'vue/no-mutating-props': 'off' }
    }
  ]
};
