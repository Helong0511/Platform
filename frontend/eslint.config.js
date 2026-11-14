/**
 * ESLint 10 flat config.
 * Vue 3 SFC 使用官方 flat/recommended 规则集；风格规则迁移到 @stylistic。
 */
import js from '@eslint/js';
import stylistic from '@stylistic/eslint-plugin';
import pluginVue from 'eslint-plugin-vue';
import globals from 'globals';

const isProduction = process.env.NODE_ENV === 'production';

export default [
  {
    ignores: ['dist/**', 'node_modules/**', 'coverage/**']
  },
  js.configs.recommended,
  ...pluginVue.configs['flat/recommended'],
  {
    files: ['**/*.{js,mjs,cjs,vue}'],
    languageOptions: {
      ecmaVersion: 'latest',
      sourceType: 'module',
      globals: {
        ...globals.browser,
        ...globals.es2021,
        ...globals.node,
        __APP_VERSION__: 'readonly'
      }
    },
    plugins: {
      '@stylistic': stylistic
    },
    rules: {
      // ======= 基础规则 =======
      'no-console': isProduction ? 'warn' : 'off',
      'no-debugger': isProduction ? 'warn' : 'off',
      'no-unused-vars': ['warn', {
        args: 'after-used',
        argsIgnorePattern: '^_',
        varsIgnorePattern: '^_'
      }],
      'no-undef': 'error',
      'no-empty': 'warn',
      'no-redeclare': 'error',
      'no-unreachable': 'error',
      'valid-typeof': 'error',

      // ======= 代码风格：使用已维护的 stylistic 插件规则 =======
      '@stylistic/no-extra-semi': 'warn',
      '@stylistic/indent': ['warn', 2, { SwitchCase: 1 }],
      '@stylistic/quotes': ['warn', 'single', { avoidEscape: true }],
      '@stylistic/semi': ['warn', 'always'],
      '@stylistic/comma-dangle': ['warn', 'never'],
      '@stylistic/comma-spacing': ['warn', { before: false, after: true }],
      '@stylistic/space-before-function-paren': ['warn', 'never'],
      '@stylistic/keyword-spacing': ['warn', { before: true, after: true }],
      '@stylistic/space-infix-ops': 'warn',
      '@stylistic/object-curly-spacing': ['warn', 'always'],
      '@stylistic/array-bracket-spacing': ['warn', 'always'],
      '@stylistic/block-spacing': ['warn', 'always'],

      // ======= Vue 规则 =======
      'vue/multi-word-component-names': 'off',
      'vue/no-unused-vars': ['warn', { ignorePattern: '^_' }],
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

      // Vue 3 应限制 key 放在 v-for 模板的子节点，而不是合法的 template 本身。
      'vue/no-v-for-template-key-on-child': 'error',
      'vue/no-ref-as-operand': 'warn',

      // ======= 安全规则 =======
      'no-eval': 'error',
      'no-implied-eval': 'error',
      'no-new-func': 'error',
      'no-script-url': 'error'
    }
  },
  {
    files: ['src/components/admin/ShortLinkFormDialog.vue'],
    rules: { 'vue/no-mutating-props': 'off' }
  },
  {
    // 父组件传入 reactive 表单对象，子组件 v-model 绑定字段。
    files: [
      'src/components/admin/ProductFormDialog.vue',
      'src/components/admin/UserFormDialog.vue',
      'src/components/admin/UserFilterBar.vue',
      'src/components/admin/UserTable.vue'
    ],
    rules: { 'vue/no-mutating-props': 'off' }
  }
];
