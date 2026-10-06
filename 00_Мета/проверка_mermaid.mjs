#!/usr/bin/env node
/**
 * Проверка синтаксиса Mermaid-диаграмм по всему хранилищу.
 *
 * Зачем: `проверка_базы.py` валидирует python-блоки, но Mermaid не проверяет.
 * Диаграмма с опечаткой в Obsidian молча превращается в текст ошибки — и это видно
 * только глазами. Скрипт прогоняет каждый ```mermaid-блок через настоящий парсер
 * mermaid и печатает, какие блоки не разбираются.
 *
 * Установка (один раз, ВНЕ хранилища — чтобы node_modules не попал в Git):
 *
 *     mkdir -p ~/tools/mermaid-check && cd ~/tools/mermaid-check
 *     npm init -y && npm install mermaid@11 jsdom
 *
 * Запуск из корня хранилища (путь к node_modules — в MERMAID_MODULES):
 *
 *     MERMAID_MODULES=~/tools/mermaid-check/node_modules node 00_Мета/проверка_mermaid.mjs
 *     MERMAID_MODULES=... node 00_Мета/проверка_mermaid.mjs 02_Курсы    # только раздел
 *     MERMAID_MODULES=... node 00_Мета/проверка_mermaid.mjs --list      # с текстом блоков
 *
 * Без MERMAID_MODULES скрипт ищет node_modules рядом с собой и в корне хранилища.
 *
 * Код возврата: 0 — все диаграммы разбираются, 1 — есть битые, 2 — не найден mermaid.
 *
 * Что ловит (реальные поломки, найденные 05.10.2026 — 10 штук):
 *   A[run(greet)]        скобки внутри подписи   → A["run(greet)"]
 *   A[registry[name]]    квадратные скобки       → A["registry[name]"]
 *   A[(3,)<br>1 2 3]     (...) читается как фигура «цилиндр» → A["(3,)<br>1 2 3"]
 *   A[сырые данные<br>"5"]  кавычки внутри подписи → A["...#quot;5#quot;"]
 *   x-axis ["a" "b"]     в xychart-beta нужны запятые → x-axis ["a", "b"]
 *   A[до: if/elif]       двоеточие ломает разбор → A["до: if/elif"]
 */

import fs from 'fs';
import path from 'path';
import { createRequire } from 'module';
import { pathToFileURL } from 'url';
import { fileURLToPath } from 'url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = process.cwd();

// ESM не смотрит на NODE_PATH, поэтому резолвим пакеты сами.
const require = createRequire(import.meta.url);
const candidates = [
  process.env.MERMAID_MODULES,
  path.join(HERE, 'node_modules'),
  path.join(ROOT, 'node_modules'),
  path.join(HERE, '..', 'tools', 'mermaid-check', 'node_modules'),
].filter(Boolean);

let modulesDir = null;
for (const dir of candidates) {
  if (fs.existsSync(path.join(dir, 'mermaid')) && fs.existsSync(path.join(dir, 'jsdom'))) {
    modulesDir = dir;
    break;
  }
}

if (!modulesDir) {
  console.error(
    'Не найден mermaid. Установите вне хранилища и укажите путь:\n' +
      '  mkdir -p ~/tools/mermaid-check && cd ~/tools/mermaid-check\n' +
      '  npm init -y && npm install mermaid@11 jsdom\n' +
      '  MERMAID_MODULES=~/tools/mermaid-check/node_modules node 00_Мета/проверка_mermaid.mjs',
  );
  process.exit(2);
}

const req = createRequire(path.join(modulesDir, '_'));
const { JSDOM } = await import(pathToFileURL(req.resolve('jsdom')).href);

// --- окружение: mermaid нужен DOM, а запускаемся из Node ---
const dom = new JSDOM('<!DOCTYPE html><body></body>', { pretendToBeVisual: true });
global.window = dom.window;
global.document = dom.window.document;
// Node 22: navigator только для чтения — определяем свойством, не присваиванием
Object.defineProperty(global, 'navigator', { value: dom.window.navigator, configurable: true });
global.DOMPurify = { sanitize: (x) => x, addHook: () => {} };

const mermaidMod = await import(pathToFileURL(req.resolve('mermaid')).href);
const mermaid = mermaidMod.default;
mermaid.initialize({ startOnLoad: false, securityLevel: 'loose' });

const args = process.argv.slice(2);
const listOnly = args.includes('--list');
const targets = args.filter((a) => !a.startsWith('--'));

/** Рекурсивно собрать .md, пропуская служебные каталоги. */
function walk(dir, out = []) {
  for (const name of fs.readdirSync(dir)) {
    if (name.startsWith('.') || name === 'node_modules') continue;
    const full = path.join(dir, name);
    const st = fs.statSync(full);
    if (st.isDirectory()) walk(full, out);
    else if (name.endsWith('.md')) out.push(full);
  }
  return out;
}

// Блок mermaid может стоять внутри callout Obsidian — тогда каждая строка с "> ".
const BLOCK = /^[ \t]*(>[ \t]*)?```mermaid[ \t]*$\n([\s\S]*?)^[ \t]*(>[ \t]*)?```[ \t]*$/gm;

const roots = targets.length ? targets : ['.'];
const files = roots.flatMap((r) => {
  const full = path.resolve(ROOT, r);
  return fs.statSync(full).isDirectory() ? walk(full) : [full];
});

let ok = 0;
const broken = [];

for (const file of files) {
  const text = fs.readFileSync(file, 'utf8');
  let m;
  BLOCK.lastIndex = 0;
  while ((m = BLOCK.exec(text))) {
    const inCallout = Boolean(m[1]);
    // снять префикс callout, иначе парсер увидит "> flowchart LR"
    const src = m[2]
      .split('\n')
      .map((l) => l.replace(/^[ \t]*>[ \t]?/, ''))
      .join('\n');
    const line = text.slice(0, m.index).split('\n').length;
    try {
      await mermaid.parse(src);
      ok++;
    } catch (e) {
      broken.push({
        file: path.relative(ROOT, file),
        line,
        inCallout,
        error: String(e.message).split('\n')[0],
        head: src.split('\n').slice(0, 3).join(' | ').slice(0, 120),
      });
    }
  }
}

if (broken.length) {
  console.log(`\n--- Битые Mermaid-блоки: ${broken.length} ---`);
  for (const b of broken) {
    console.log(`  ${b.file}:${b.line}${b.inCallout ? ' (в callout)' : ''}`);
    console.log(`    ${b.error}`);
    if (listOnly) console.log(`    ${b.head}`);
  }
}

console.log(`\nMermaid: разобралось ${ok}, битых ${broken.length}`);
process.exit(broken.length ? 1 : 0);
