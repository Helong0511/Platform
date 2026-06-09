/**
 * 去除 frontend/src 中重复的文件头注释（保留更详细的一块）
 */
import fs from 'fs';
import path from 'path';

const SRC = path.resolve('frontend/src');
let fixed = 0;

function walk(dir, acc = []) {
  for (const f of fs.readdirSync(dir)) {
    const p = path.join(dir, f);
    if (fs.statSync(p).isDirectory()) walk(p, acc);
    else if (/\.(js|vue)$/.test(f)) acc.push(p);
  }
  return acc;
}

function stripBlock(text, kind) {
  if (kind === 'js') {
    const m = text.match(/^\/\*\*([\s\S]*?)\*\//);
    if (!m) return null;
    return { full: m[0], body: m[1], rest: text.slice(m[0].length).replace(/^\s*\n/, '\n') };
  }
  const m = text.match(/^<!--([\s\S]*?)-->/);
  if (!m) return null;
  return { full: m[0], body: m[1], rest: text.slice(m[0].length).replace(/^\s*\n/, '\n') };
}

function score(body) {
  const cn = (body.match(/[\u4e00-\u9fff]/g) || []).length;
  const lines = body.split('\n').filter((l) => l.trim()).length;
  return cn * 2 + lines;
}

function dedupe(content, kind) {
  let changed = false;
  let trimmed = content.trimStart();
  const prefix = content.slice(0, content.length - trimmed.length);

  const blocks = [];
  while (true) {
    const b = stripBlock(trimmed, kind);
    if (!b) break;
    blocks.push(b);
    trimmed = b.rest.trimStart();
  }

  if (blocks.length <= 1) return { content, changed };

  // 保留得分最高的注释块
  blocks.sort((a, b) => score(b.body) - score(a.body));
  const best = blocks[0].full;
  content = prefix + best + '\n' + trimmed;
  changed = true;
  return { content, changed };
}

for (const f of walk(SRC)) {
  let content = fs.readFileSync(f, 'utf8');
  const orig = content;
  const kind = f.endsWith('.vue') ? 'vue' : 'js';
  const r = dedupe(content, kind);
  content = r.content;
  if (content !== orig) {
    fs.writeFileSync(f, content, 'utf8');
    fixed++;
    console.log('fixed:', path.relative(SRC, f));
  }
}
console.log('total fixed:', fixed);
