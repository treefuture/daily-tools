/**
 * 任务看板离线去重脚本
 *
 * 用途：直接从服务器上的 task.json 中删除「完全相同」的重复任务。
 * 判定规则与网页端一致：除 id / sortOrder / createdAt / updatedAt / deleted 外，
 * 标题、类型、优先级、状态、分组、标签（顺序无关）、起止时间、描述、备注、
 * 验收要点、附件（名称/类型/大小）全部一致，才算重复。
 *
 * 用法（建议先停止 task-server 再执行，避免并发写盘）：
 *   cd /www/server/nginx/html/dist/ol/task
 *   cp task.json task.json.before-dedupe
 *   node dedupe.mjs
 *
 * 脚本会自动额外备份 task.json 到 task.json.dedupe-<时间戳>，
 * 并把被删除的任务写入 task-archive.json（reason: "dedupe"），可追溯。
 * 每组重复任务保留编号最小（最早创建）的一条。
 */

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = path.dirname(fileURLToPath(import.meta.url));
const DATA_DIR = process.env.DATA_DIR ? path.resolve(process.env.DATA_DIR) : ROOT;
const STATE_FILE = path.join(DATA_DIR, 'task.json');
const ARCHIVE_FILE = path.join(DATA_DIR, 'task-archive.json');

function readJSON(file, fallback) {
  try {
    return JSON.parse(fs.readFileSync(file, 'utf8'));
  } catch (err) {
    if (err.code === 'ENOENT') return fallback;
    throw err;
  }
}

const state = readJSON(STATE_FILE, null);
if (!state || !Array.isArray(state.tasks)) {
  console.error('读取失败：' + STATE_FILE + ' 不是合法的任务数据');
  process.exit(1);
}

const s = v => String(v == null ? '' : v).trim();
const attSig = list => (Array.isArray(list) ? list : [])
  .map(a => `${s(a.name)}|${s(a.type || '')}|${Number(a.size) || 0}`).join(';');
const signature = t => JSON.stringify([
  s(t.title), s(t.type), s(t.prio), s(t.status), s(t.groupId || ''),
  (Array.isArray(t.tags) ? t.tags : []).map(s).sort(),
  Number(t.startTime) || 0, Number(t.endTime) || 0,
  s(t.desc), s(t.note),
  (Array.isArray(t.points) ? t.points : []).map(s),
  attSig(t.images), attSig(t.files)
]);
const idNum = id => {
  const m = /^T(\d+)$/i.exec(id || '');
  return m ? +m[1] : 1e9;
};

const seen = new Set();
const dropped = [];
state.tasks
  .filter(t => !t.deleted)
  .sort((a, b) => idNum(a.id) - idNum(b.id))
  .forEach(t => {
    const sig = signature(t);
    if (seen.has(sig)) dropped.push(t);
    else seen.add(sig);
  });

if (!dropped.length) {
  console.log('没有发现完全相同的重复任务，无需处理。');
  process.exit(0);
}

const stamp = new Date().toISOString().replace(/[:.]/g, '-');
fs.copyFileSync(STATE_FILE, `${STATE_FILE}.dedupe-${stamp}`);

const dropIds = new Set(dropped.map(t => t.id));
state.tasks = state.tasks.filter(t => !dropIds.has(t.id));

const tmp = STATE_FILE + '.tmp';
fs.writeFileSync(tmp, JSON.stringify(state, null, 2), 'utf8');
fs.renameSync(tmp, STATE_FILE);

try {
  const archiveDoc = readJSON(ARCHIVE_FILE, { tasks: [] }) || { tasks: [] };
  const archive = Array.isArray(archiveDoc.tasks) ? archiveDoc.tasks : [];
  const archivedAt = Date.now();
  for (const t of dropped) {
    archive.push({
      archivedAt,
      reason: 'dedupe',
      task: { ...t, deleted: true, deletedAt: t.deletedAt || archivedAt, updatedAt: archivedAt }
    });
  }
  const atmp = ARCHIVE_FILE + '.tmp';
  fs.writeFileSync(atmp, JSON.stringify({ tasks: archive }, null, 2), 'utf8');
  fs.renameSync(atmp, ARCHIVE_FILE);
} catch (err) {
  console.warn('已删除重复任务，但写入归档文件失败：' + err.message);
}

console.log(`已删除 ${dropped.length} 条完全相同的重复任务，保留每组编号最小的一条：`);
for (const t of dropped) console.log(`  - ${t.id}  ${t.title}`);
console.log(`原数据备份：${STATE_FILE}.dedupe-${stamp}`);
