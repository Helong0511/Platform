# ESLint 10 / Vue 3 lint configuration migration

## Why this migration is required

The frontend was using ESLint 8.57.0, which is outside the currently supported ESLint release line. ESLint 10 no longer supports the legacy `.eslintrc.*` configuration format, so retaining the old config while only changing the package version would break linting.

Official references:

- ESLint version support: https://eslint.org/version-support/
- ESLint 10 migration guide: https://eslint.org/docs/latest/use/migrate-to-10.0.0
- ESLint flat-config migration guide: https://eslint.org/docs/latest/use/configure/migration-guide
- eslint-plugin-vue flat-config guide: https://eslint.vuejs.org/user-guide/

## Changes in this branch

- Upgrade `eslint` to 10.14.0.
- Upgrade `eslint-plugin-vue` to 10.11.1; its peer dependency range explicitly supports ESLint 10.
- Add `@eslint/js`, `@stylistic/eslint-plugin`, and `globals` as direct configuration dependencies.
- Replace `.eslintrc.cjs` with `eslint.config.js`.
- Move deprecated core formatting rules to the maintained `@stylistic` plugin.
- Replace the Vue 2-only deprecated `vue/no-v-for-template-key` rule with the Vue 3 rule `vue/no-v-for-template-key-on-child`.
- Preserve the existing project-specific Vue rules and the four documented `no-mutating-props` exceptions.

## Verification status

The lockfile is being regenerated in an isolated CI workspace. The workflow commits the generated lockfile only after backend tests, frontend lint/build, and Playwright E2E all pass. A subsequent CI run must use the committed lockfile directly with `npm ci`; only that run establishes the migration as verified.

No production server, database, Redis, cache, queue, or live third-party endpoint is used.


## Peer dependency resolution

The first lockfile-only update correctly stopped with `ERESOLVE`: the previous lock graph still contained `eslint-plugin-vue@9.28.0` and its old Vue parser peer while the manifest now requests plugin v10. The workflow does not use `--force` or `--legacy-peer-deps`. It now resolves a fresh lockfile from the declared manifest in the isolated CI workspace, then runs `npm ci`, lint, build and browser E2E before the lockfile can be committed.
