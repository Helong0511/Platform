#!/usr/bin/env node
/**
 * 前端 CRUD API 路径审计（CI 门禁）。
 *
 * 校验 frontend/src/api 中 createCrudApi('/api/v1/...') 的路径
 * 是否在后端 app/api_v1/__init__.py 的 include_router(prefix=...) 中注册。
 */
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, '..');
const API_DIR = path.join(ROOT, 'frontend', 'src', 'api');
const INIT_PY = path.join(ROOT, 'app', 'api_v1', '__init__.py');

function collectFrontendCrudPaths() {
  const paths = new Set();
  if (!fs.existsSync(API_DIR)) {
    throw new Error(`缺少目录: ${API_DIR}`);
  }
  for (const name of fs.readdirSync(API_DIR)) {
    if (!name.endsWith('.js')) continue;
    const text = fs.readFileSync(path.join(API_DIR, name), 'utf8');
    const re = /createCrudApi\(\s*['"]([^'"]+)['"]/g;
    let m;
    while ((m = re.exec(text)) !== null) {
      paths.add(m[1].replace(/\/$/, ''));
    }
  }
  return paths;
}

function collectBackendPrefixes() {
  const text = fs.readFileSync(INIT_PY, 'utf8');
  const prefixes = new Set();
  const re = /include_router\([^)]*prefix\s*=\s*["']([^"']+)["']/gs;
  let m;
  while ((m = re.exec(text)) !== null) {
    const p = m[1];
    if (p) {
      prefixes.add(`/api/v1${p}`.replace(/\/$/, '') || '/api/v1');
    }
  }
  return prefixes;
}

function main() {
  const frontendPaths = collectFrontendCrudPaths();
  const backendPrefixes = collectBackendPrefixes();
  const missing = [];
  const initText = fs.readFileSync(INIT_PY, 'utf8');

  for (const p of frontendPaths) {
    let ok = backendPrefixes.has(p);
    if (!ok) {
      for (const bp of backendPrefixes) {
        if (p === bp || p.startsWith(`${bp}/`)) {
          ok = true;
          break;
        }
      }
    }
    if (!ok) {
      const tail = p.replace(/^\/api\/v1/, '');
      if (tail && (initText.includes(`"${tail}"`) || initText.includes(`'${tail}'`))) {
        ok = true;
      }
    }
    if (!ok && p.includes('/postback/')) {
      const pb = path.join(ROOT, 'app', 'api_v1', 'postback');
      if (fs.existsSync(pb)) {
        for (const f of fs.readdirSync(pb)) {
          if (!f.endsWith('.py')) continue;
          const t = fs.readFileSync(path.join(pb, f), 'utf8');
          if (t.includes('ip-whitelist') && p.endsWith('/ip-whitelist')) {
            ok = true;
            break;
          }
        }
      }
    }
    if (!ok) missing.push(p);
  }

  if (frontendPaths.size === 0) {
    console.error('FRONTEND CRUD AUDIT FAILED: 未发现 createCrudApi 调用');
    process.exit(1);
  }

  if (missing.length) {
    console.error('FRONTEND CRUD AUDIT FAILED');
    for (const p of missing) {
      console.error(`  - 前端路径未在后端注册: ${p}`);
    }
    console.error('后端已知 prefix:');
    for (const bp of [...backendPrefixes].sort()) {
      console.error(`  * ${bp}`);
    }
    process.exit(1);
  }

  console.log(`FRONTEND CRUD AUDIT PASSED (${frontendPaths.size} paths)`);
}

main();
