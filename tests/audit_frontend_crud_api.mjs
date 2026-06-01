/**
 * 校验 frontend/src/api 中 createCrudApi 解构名与 methodNames 导出一致。
 * 运行: node tests/audit_frontend_crud_api.mjs
 */
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const apiRoot = path.join(path.dirname(fileURLToPath(import.meta.url)), '..', 'frontend', 'src', 'api');

function capitalize(str) {
  if (!str) return '';
  return str.charAt(0).toUpperCase() + str.slice(1);
}

function extractResourceName(basePath) {
  const lastPart = basePath.split('/').filter(Boolean).pop() || '';
  if (lastPart.endsWith('s')) return lastPart.slice(0, -1);
  return lastPart;
}

function parseObjectLiteral(block, key) {
  const idx = block.indexOf(key);
  if (idx === -1) return {};
  const start = block.indexOf('{', idx + key.length);
  if (start === -1) return {};
  let depth = 0;
  let end = start;
  for (let i = start; i < block.length; i++) {
    if (block[i] === '{') depth++;
    if (block[i] === '}') depth--;
    if (depth === 0) {
      end = i;
      break;
    }
  }
  try {
    return Function(`return (${block.slice(start, end + 1)})`)();
  } catch {
    return {};
  }
}

function parseMethodNames(block) {
  return parseObjectLiteral(block, 'methodNames');
}

function parseCustomMethodKeys(block) {
  if (!block.includes('customMethods')) return [];
  const keys = [];
  const re = /(\w+)\s*:\s*(?:async\s*)?\([^)]*\)\s*=>\s*\{/g;
  let km;
  while ((km = re.exec(block))) keys.push(km[1]);
  return keys;
}

function parseResourceName(block) {
  const m = block.match(/resourceName\s*:\s*['"]([^'"]+)['"]/);
  return m ? m[1] : null;
}

function parseInclude(block) {
  const m = block.match(/include\s*:\s*(\[[^\]]+\])/);
  if (!m) return ['list', 'get', 'create', 'update', 'delete'];
  try {
    return Function(`return (${m[1]})`)();
  } catch {
    return ['list', 'get', 'create', 'update', 'delete'];
  }
}

function expectedExportNames(basePath, block) {
  const resourceName = parseResourceName(block);
  const methodNames = parseMethodNames(block);
  const resource = resourceName || extractResourceName(basePath);
  const R = capitalize(resource);
  const Rs = `${R}s`;
  return {
    list: methodNames.list || `get${Rs}`,
    get: methodNames.get || `get${R}`,
    create: methodNames.create || `create${R}`,
    update: methodNames.update || `update${R}`,
    delete: methodNames.delete || `delete${R}`,
    include: parseInclude(block),
  };
}

function walk(dir, files = []) {
  for (const ent of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, ent.name);
    if (ent.isDirectory()) walk(p, files);
    else if (ent.name.endsWith('.js')) files.push(p);
  }
  return files;
}

function auditFile(filePath) {
  const src = fs.readFileSync(filePath, 'utf8');
  if (!src.includes('createCrudApi')) return [];

  const issues = [];
  const callRe = /createCrudApi\s*\(\s*['"]([^'"]+)['"]\s*,\s*(\{[\s\S]*?\})\s*\)/g;
  const destructureRe = /(?:const|export const)\s*\{([^}]+)\}\s*=\s*createCrudApi/g;

  let callMatch;
  const calls = [];
  while ((callMatch = callRe.exec(src)) !== null) {
    calls.push({ basePath: callMatch[1], block: callMatch[2], index: callMatch.index });
  }

  let destMatch;
  const destructures = [];
  while ((destMatch = destructureRe.exec(src)) !== null) {
    destructures.push({ keys: destMatch[1], index: destMatch.index });
  }

  for (let i = 0; i < calls.length; i++) {
    const call = calls[i];
    const dest = destructures.find((d) => d.index < call.index + 200 && d.index >= call.index - 500)
      || destructures[i];
    if (!dest) continue;

    const expected = expectedExportNames(call.basePath, call.block);
    const importedKeys = dest.keys
      .split(',')
      .map((part) => part.trim())
      .filter(Boolean)
      .map((part) => part.split(':')[0].trim());

    const valid = new Set(
      ['list', 'get', 'create', 'update', 'delete']
        .filter((role) => expected.include.includes(role))
        .map((role) => expected[role])
    );

    for (const key of parseCustomMethodKeys(call.block)) {
      valid.add(key);
    }

    for (const key of importedKeys) {
      if (!valid.has(key)) {
        issues.push({
          file: path.relative(process.cwd(), filePath),
          imported: key,
          expected: [...valid],
          basePath: call.basePath,
        });
      }
    }
  }

  return issues;
}

const allIssues = [];
for (const file of walk(apiRoot)) {
  allIssues.push(...auditFile(file));
}

if (allIssues.length === 0) {
  console.log('OK: 所有 createCrudApi 解构名称与导出一致');
  process.exit(0);
}

console.error('createCrudApi 解构错误:');
for (const issue of allIssues) {
  console.error(`  ${issue.file}: "${issue.imported}" 不存在，应为之一: ${issue.expected.join(', ')} (${issue.basePath})`);
}
process.exit(1);
