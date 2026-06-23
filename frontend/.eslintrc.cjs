/**
 * ESLint 配置
 * 统一代码规范
 */
module.exports = {
  root: true,
  env: { browser: true, es2021: true, node: true },
  extends: [
    'eslint:recommended',
    'plugin:vue/vue3-recommended',
    'plugin:vue/vue3-essential'
  ],
  parserOptions: {
    ecmaVersion: 'latest',
    sourceType: 'module'
  },
  globals: {
    __APP_VERSION__: 'readonly',
  },
  rules: {
    // ======= 基础规则 =======
    'no-console': process.env.NODE_ENV === 'production' ? 'warn' : 'off',
    'no-debugger': process.env.NODE_ENV === 'production' ? 'warn' : 'off',
    'no-unused-vars': ['warn', {
      args: 'after-used',
      argsIgnorePattern: '^_',
      varsIgnorePattern: '^_'
    }],
    'no-undef': 'error',
    'no-empty': 'warn',
    'no-extra-semi': 'warn',
    'no-redeclare': 'error',
    'no-unreachable': 'error',
    'valid-typeof': 'error',

    // ======= 代码风格 =======
    'indent': ['warn', 2, { SwitchCase: 1 }],
    'quotes': ['warn', 'single', { avoidEscape: true }],
    'semi': ['warn', 'always'],
    'comma-dangle': ['warn', 'never'],
    'comma-spacing': ['warn', { before: false, after: true }],
    'space-before-function-paren': ['warn', 'never'],
    'keyword-spacing': ['warn', { before: true, after: true }],
    'space-infix-ops': 'warn',
    'object-curly-spacing': ['warn', 'always'],
    'array-bracket-spacing': ['warn', 'always'],
    'block-spacing': ['warn', 'always'],

    // ======= Vue 规则 =======
    'vue/multi-word-component-names': 'off',
    'vue/no-unused-vars': ['warn', { vars: 'all', args: 'after-used' }],
    'vue/no-unused-components': 'warn',
    'vue/no-mutating-props': ['warn', { shallowOnly: true }],
    'vue/require-prop-types': 'warn',
    'vue/require-default-prop': 'warn',
    'vue/no-v-html': 'warn',
    'vue/html-self-closing': ['warn', {
      html: {
        void: 'always',
        normal: 'always',
        component: 'always'
      },
      svg: 'always',
      math: 'always'
    }],
    'vue/html-indent': ['warn', 2],
    'vue/max-attributes-per-line': ['warn', {
      singleline: { max: 3 },
      multiline: { max: 1 }
    }],
    'vue/component-name-in-template-casing': ['warn', 'PascalCase'],
    'vue/script-indent': ['warn', 2, { baseIndent: 1 }],

    // ======= 安全规则 =======
    'no-eval': 'error',
    'no-implied-eval': 'error',
    'no-new-func': 'error',
    'no-script-url': 'error',
    'vue/no-template-v-for-with-key': 'error',
    'vue/no-ref-as-operand': 'warn'
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
