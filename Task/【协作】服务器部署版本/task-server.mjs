#!/usr/bin/env node
/**
 * 开发任务看板 · 多人共享服务
 *
 * 启动：
 *   node task-server.mjs
 * 然后浏览器访问：
 *   http://<服务器IP>:8765
 *
 * 环境变量（均可选）：
 *   HOST=0.0.0.0        监听地址（默认 0.0.0.0，供局域网/公网访问）
 *   PORT=8765           端口
 *   AUTH_USER=admin     访问用户名（设置 AUTH_PASS 后生效）
 *   AUTH_PASS=          访问密码；不设置则不校验（公网部署强烈建议设置）
 *   DATA_DIR=./data     数据目录（默认脚本所在目录）
 *
 * 数据：
 *   task.json           任务与分组（附件只存元数据）
 *   task.json.bak       上一次写入的自动备份
 *   task-files/         附件实体文件
 *
 * 不依赖任何第三方包，Node 18+ 即可运行。
 */

import http from 'node:http';
import os from 'node:os';
import path from 'node:path';
import crypto from 'node:crypto';
import { gzipSync, brotliCompressSync, constants as zlibConstants } from 'node:zlib';
import { fileURLToPath } from 'node:url';
import {
  readFile, writeFile, rename, mkdir, unlink, stat, copyFile, readdir
} from 'node:fs/promises';

const ROOT = path.dirname(fileURLToPath(import.meta.url));
const INDEX_FILE = path.join(ROOT, 'index.html');
const DATA_DIR = process.env.DATA_DIR ? path.resolve(process.env.DATA_DIR) : ROOT;
const STATE_FILE = path.join(DATA_DIR, 'task.json');
const BACKUP_FILE = STATE_FILE + '.bak';
const ARCHIVE_FILE = path.join(DATA_DIR, 'task-archive.json');
const ARCHIVE_BACKUP = ARCHIVE_FILE + '.bak';
const FILES_DIR = path.join(DATA_DIR, 'task-files');

const HOST = process.env.HOST || '0.0.0.0';
const PORT = Number(process.env.PORT) || 8765;
const AUTH_USER = process.env.AUTH_USER || 'admin';
const AUTH_PASS = process.env.AUTH_PASS || '';

const MAX_BODY = 200 * 1024 * 1024;   // 请求体上限 200MB
const MAX_FILE = 100 * 1024 * 1024;   // 单个附件上限 100MB

const MIME = {
  '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.gif': 'image/gif',
  '.webp': 'image/webp', '.bmp': 'image/bmp', '.svg': 'image/svg+xml', '.ico': 'image/x-icon',
  '.pdf': 'application/pdf',
  '.doc': 'application/msword',
  '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  '.xls': 'application/vnd.ms-excel',
  '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  '.ppt': 'application/vnd.ms-powerpoint',
  '.pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
  '.zip': 'application/zip', '.rar': 'application/vnd.rar', '.7z': 'application/x-7z-compressed',
  '.tar': 'application/x-tar', '.gz': 'application/gzip',
  '.txt': 'text/plain; charset=utf-8', '.md': 'text/markdown; charset=utf-8',
  '.json': 'application/json; charset=utf-8', '.html': 'text/html; charset=utf-8',
  '.css': 'text/css; charset=utf-8', '.js': 'text/javascript; charset=utf-8',
  '.mp3': 'audio/mpeg', '.wav': 'audio/wav', '.ogg': 'audio/ogg',
  '.mp4': 'video/mp4', '.webm': 'video/webm', '.mov': 'video/quicktime'
};

const PRIOS = new Set(['P0', 'P1', 'P2']);
const STATUSES = new Set(['todo', 'doing', 'done']);

class HttpError extends Error {
  constructor(status, message, extra) {
    super(message);
    this.status = status;
    this.extra = extra || null;
  }
}

/* ---------- 内存状态 ---------- */

let state = { tasks: [], groups: [] };
// 彻底删除的任务不销毁，归档到这里（附件也保留）
let archive = [];
// 每次数据变化都会递增，客户端据此发现他人改动；启动时用时间戳避免重启后与旧值相同
let rev = Date.now();
const BOOT_ID = crypto.randomUUID();

function bumpRev() {
  rev = Math.max(Date.now(), rev + 1);
}

/* ---------- 持久化 ---------- */

let persistChain = Promise.resolve();

function persist(skipBackup = false) {
  const snapshot = JSON.stringify(state, null, 2);
  const next = persistChain
    .catch(() => {})
    .then(async () => {
      await mkdir(DATA_DIR, { recursive: true });
      const tmp = STATE_FILE + '.tmp';
      await writeFile(tmp, snapshot, 'utf8');
      // 备份上一次的数据；写入前先把旧文件留一份
      if (!skipBackup) await copyFile(STATE_FILE, BACKUP_FILE).catch(() => {});
      await rename(tmp, STATE_FILE);
    });
  persistChain = next;
  return next;
}

let archivePersistChain = Promise.resolve();

function persistArchive(skipBackup = false) {
  const snapshot = JSON.stringify({ tasks: archive }, null, 2);
  const next = archivePersistChain
    .catch(() => {})
    .then(async () => {
      await mkdir(DATA_DIR, { recursive: true });
      const tmp = ARCHIVE_FILE + '.tmp';
      await writeFile(tmp, snapshot, 'utf8');
      if (!skipBackup) await copyFile(ARCHIVE_FILE, ARCHIVE_BACKUP).catch(() => {});
      await rename(tmp, ARCHIVE_FILE);
    });
  archivePersistChain = next;
  return next;
}

/* ---------- 数据规范化 ---------- */

function has(obj, key) {
  return Object.prototype.hasOwnProperty.call(obj, key);
}

function toStr(v, max = 10000) {
  return String(v == null ? '' : v).slice(0, max);
}

function toNum(v) {
  const n = Number(v);
  return Number.isFinite(n) ? n : 0;
}

function strArray(v, maxItems = 200, maxLen = 200) {
  if (!Array.isArray(v)) return [];
  const out = [];
  for (const item of v) {
    const s = toStr(item, maxLen).trim();
    if (s && !out.includes(s)) out.push(s);
    if (out.length >= maxItems) break;
  }
  return out;
}

function normalizeAttachmentList(list) {
  if (!Array.isArray(list)) return [];
  const out = [];
  for (const a of list) {
    if (!a || typeof a !== 'object') continue;
    const serverName = String(a.serverName || '');
    if (!/^[A-Za-z0-9._-]+$/.test(serverName)) {
      throw new HttpError(400, '附件缺少有效的 serverName（页面需要先上传附件）');
    }
    out.push({
      id: String(a.id || crypto.randomUUID()),
      name: toStr(a.name || 'file', 300),
      serverName,
      type: toStr(a.type, 200),
      size: toNum(a.size)
    });
  }
  return out;
}

function stripTaskBlobs(t) {
  const task = { ...t };
  for (const key of ['images', 'files']) {
    if (!Array.isArray(task[key])) {
      task[key] = [];
      continue;
    }
    // 读取旧数据时宽松处理：丢弃没有有效 serverName 的附件
    task[key] = task[key]
      .filter(a => a && typeof a === 'object' && /^[A-Za-z0-9._-]+$/.test(String(a.serverName || '')))
      .map(a => ({
        id: String(a.id || crypto.randomUUID()),
        name: toStr(a.name || 'file', 300),
        serverName: String(a.serverName),
        type: toStr(a.type, 200),
        size: toNum(a.size)
      }));
  }
  return task;
}

function normalizeLoadedTask(t) {
  const out = stripTaskBlobs(t);
  out.id = toStr(out.id, 40).trim();
  out.title = toStr(out.title, 500);
  out.type = toStr(out.type || '其他', 100) || '其他';
  out.prio = PRIOS.has(out.prio) ? out.prio : 'P1';
  out.status = STATUSES.has(out.status) ? out.status : 'todo';
  out.groupId = toStr(out.groupId, 100);
  out.tags = strArray(out.tags, 50, 40);
  out.startTime = toNum(out.startTime);
  out.endTime = toNum(out.endTime);
  out.desc = toStr(out.desc, 20000);
  out.note = toStr(out.note, 20000);
  out.points = strArray(out.points, 200, 1000);
  out.sortOrder = toNum(out.sortOrder);
  out.deleted = !!out.deleted;
  out.deletedAt = toNum(out.deletedAt);
  out.createdAt = toNum(out.createdAt) || Date.now();
  out.updatedAt = toNum(out.updatedAt) || out.createdAt;
  return out;
}

function normalizeLoadedGroup(g) {
  return {
    id: toStr(g.id, 60).trim(),
    name: toStr(g.name || '未命名组', 80).trim() || '未命名组',
    sortOrder: toNum(g.sortOrder),
    collapsed: !!g.collapsed,
    createdAt: toNum(g.createdAt) || Date.now(),
    updatedAt: toNum(g.updatedAt) || Date.now()
  };
}

function buildTask(input, base) {
  const t = base ? { ...base } : {
    id: '', title: '', type: '其他', prio: 'P1', status: 'todo',
    groupId: '', tags: [], startTime: 0, endTime: 0,
    desc: '', note: '', points: [], images: [], files: [],
    sortOrder: 0, deleted: false, deletedAt: 0,
    createdAt: Date.now(), updatedAt: 0
  };

  if (has(input, 'title')) t.title = toStr(input.title, 500).trim();
  if (has(input, 'type')) t.type = toStr(input.type, 100).trim() || '其他';
  if (has(input, 'prio')) {
    const p = toStr(input.prio, 10).trim().toUpperCase();
    if (PRIOS.has(p)) t.prio = p;
  }
  if (has(input, 'status')) {
    const s = toStr(input.status, 10).trim().toLowerCase();
    if (STATUSES.has(s)) t.status = s;
  }
  if (has(input, 'groupId')) t.groupId = toStr(input.groupId, 100).trim();
  if (has(input, 'tags')) t.tags = strArray(input.tags, 50, 40);
  if (has(input, 'startTime')) t.startTime = toNum(input.startTime);
  if (has(input, 'endTime')) t.endTime = toNum(input.endTime);
  if (has(input, 'desc')) t.desc = toStr(input.desc, 20000);
  if (has(input, 'note')) t.note = toStr(input.note, 20000);
  if (has(input, 'points')) t.points = strArray(input.points, 200, 1000);
  if (has(input, 'images')) t.images = normalizeAttachmentList(input.images);
  if (has(input, 'files')) t.files = normalizeAttachmentList(input.files);
  if (has(input, 'sortOrder')) {
    const n = Number(input.sortOrder);
    if (Number.isFinite(n)) t.sortOrder = n;
  }
  if (has(input, 'deleted')) t.deleted = !!input.deleted;
  if (has(input, 'deletedAt')) t.deletedAt = toNum(input.deletedAt);

  if (!base && has(input, 'id')) {
    const id = toStr(input.id, 40).trim();
    if (/^[A-Za-z0-9_-]{1,40}$/.test(id)) t.id = id;
  }

  // 引用了不存在的组时归入未分组，避免出现孤儿任务
  if (t.groupId && !state.groups.some(g => String(g.id) === t.groupId)) t.groupId = '';

  t.updatedAt = Date.now();
  return t;
}

function buildGroup(input, base) {
  const g = base ? { ...base } : {
    id: '', name: '', sortOrder: 0, collapsed: false,
    createdAt: Date.now(), updatedAt: 0
  };
  if (has(input, 'name')) g.name = toStr(input.name, 80).trim();
  if (has(input, 'sortOrder')) {
    const n = Number(input.sortOrder);
    if (Number.isFinite(n)) g.sortOrder = n;
  }
  if (has(input, 'collapsed')) g.collapsed = !!input.collapsed;
  if (!base && has(input, 'id')) {
    const id = toStr(input.id, 60).trim();
    if (/^[A-Za-z0-9_-]{1,60}$/.test(id)) g.id = id;
  }
  g.updatedAt = Date.now();
  return g;
}

function publicTask(t) {
  const out = { ...t };
  const withUrl = list => (Array.isArray(list) ? list.map(a => ({
    id: a.id, name: a.name, serverName: a.serverName,
    type: a.type || '', size: a.size || 0,
    url: '/files/' + encodeURIComponent(a.serverName)
  })) : []);
  out.images = withUrl(t.images);
  out.files = withUrl(t.files);
  return out;
}

function collectServerNames(t) {
  const names = [];
  for (const list of [t.images, t.files]) {
    if (!Array.isArray(list)) continue;
    for (const a of list) if (a && a.serverName) names.push(a.serverName);
  }
  return names;
}

function nextTaskId() {
  let max = 0;
  for (const t of state.tasks) {
    const m = /^T(\d+)$/i.exec(String(t.id || ''));
    if (m) max = Math.max(max, Number(m[1]));
  }
  return 'T' + String(max + 1).padStart(2, '0');
}

function collectAllUsedFiles() {
  const used = new Set();
  const add = t => collectServerNames(t).forEach(n => used.add(n));
  state.tasks.forEach(add);
  // 归档任务引用的附件同样保留，保证归档记录完整可恢复
  archive.forEach(e => { if (e && e.task) add(e.task); });
  return used;
}

async function cleanupUnusedFiles(names) {
  if (!names.length) return;
  const used = collectAllUsedFiles();
  for (const name of names) {
    if (used.has(name)) continue;
    await unlink(path.join(FILES_DIR, name)).catch(() => {});
  }
}

async function cleanupOrphanFiles() {
  let names;
  try {
    names = await readdir(FILES_DIR);
  } catch {
    return;
  }
  const used = collectAllUsedFiles();
  let removed = 0;
  for (const name of names) {
    if (used.has(name) || !/^[A-Za-z0-9._-]+$/.test(name)) continue;
    await unlink(path.join(FILES_DIR, name)).catch(() => {});
    removed++;
  }
  if (removed) console.log(`已清理 ${removed} 个未被引用的附件文件`);
}

function makeServerName(originalName) {
  const rawExt = path.extname(String(originalName || '')).toLowerCase();
  const ext = rawExt.replace(/[^.a-zA-Z0-9]/g, '').slice(0, 12);
  return crypto.randomBytes(8).toString('hex') + ext;
}

/* ---------- 启动时载入数据 ---------- */

async function loadState() {
  await mkdir(FILES_DIR, { recursive: true });

  let raw = '';
  try {
    raw = await readFile(STATE_FILE, 'utf8');
  } catch (err) {
    if (err.code !== 'ENOENT') throw err;
  }

  let parsed = null;
  let recovered = false;

  if (raw.trim()) {
    try {
      parsed = JSON.parse(raw);
    } catch (err) {
      console.warn(`task.json 解析失败（${err.message}），尝试从备份恢复…`);
      const bak = await readFile(BACKUP_FILE, 'utf8').catch(() => '');
      if (!bak.trim()) {
        throw new Error('task.json 不是合法 JSON，且没有可用备份：' + STATE_FILE);
      }
      try {
        parsed = JSON.parse(bak);
        recovered = true;
      } catch {
        throw new Error('task.json 和备份都不是合法 JSON，请手动检查：' + STATE_FILE);
      }
    }
  }

  if (!parsed) {
    state = { tasks: [], groups: [] };
    await persist();
    return;
  }

  const tasks = [];
  for (const t of Array.isArray(parsed.tasks) ? parsed.tasks : []) {
    if (!t || typeof t !== 'object') continue;
    const task = normalizeLoadedTask(t);
    if (!task.id) {
      console.warn('忽略了一条缺少 id 的任务');
      continue;
    }
    tasks.push(task);
  }
  const groups = [];
  for (const g of Array.isArray(parsed.groups) ? parsed.groups : []) {
    if (!g || typeof g !== 'object') continue;
    const group = normalizeLoadedGroup(g);
    if (!group.id) continue;
    groups.push(group);
  }

  state = { tasks, groups };

  if (recovered) {
    const corrupt = STATE_FILE + '.corrupt-' + Date.now();
    await copyFile(STATE_FILE, corrupt).catch(() => {});
    console.warn(`已从备份恢复数据，原损坏文件另存为 ${path.basename(corrupt)}`);
    await persist(true);
  }
}

async function loadArchive() {
  await mkdir(DATA_DIR, { recursive: true });
  let raw = '';
  try {
    raw = await readFile(ARCHIVE_FILE, 'utf8');
  } catch (err) {
    if (err.code !== 'ENOENT') throw err;
    archive = [];
    await persistArchive();
    return;
  }

  let parsed = null;
  let recovered = false;

  if (raw.trim()) {
    try {
      parsed = JSON.parse(raw);
    } catch (err) {
      console.warn(`task-archive.json 解析失败（${err.message}），尝试从备份恢复…`);
      const bak = await readFile(ARCHIVE_BACKUP, 'utf8').catch(() => '');
      try {
        parsed = JSON.parse(bak);
        recovered = true;
      } catch {
        // 归档损坏且备份不可用：保留原文件供人工恢复，本次以空归档启动
        const corrupt = ARCHIVE_FILE + '.corrupt-' + Date.now();
        await copyFile(ARCHIVE_FILE, corrupt).catch(() => {});
        console.warn(`归档文件与备份均不可用，原文件另存为 ${path.basename(corrupt)}，本次以空归档启动`);
        archive = [];
        await persistArchive(true);
        return;
      }
    }
  }

  const entries = Array.isArray(parsed)
    ? parsed
    : (parsed && Array.isArray(parsed.tasks)) ? parsed.tasks : [];

  archive = [];
  for (const e of entries) {
    if (!e || typeof e !== 'object') continue;
    const taskRaw = (e.task && typeof e.task === 'object') ? e.task : e;
    if (!taskRaw || typeof taskRaw !== 'object') continue;
    const task = normalizeLoadedTask(taskRaw);
    archive.push({
      archivedAt: toNum(e.archivedAt) || toNum(task.deletedAt) || Date.now(),
      task
    });
  }

  if (recovered) {
    const corrupt = ARCHIVE_FILE + '.corrupt-' + Date.now();
    await copyFile(ARCHIVE_FILE, corrupt).catch(() => {});
    console.warn(`归档已从备份恢复，原损坏文件另存为 ${path.basename(corrupt)}`);
    await persistArchive(true);
  } else if (!raw.trim()) {
    await persistArchive();
  }
}

/* ---------- HTTP 工具 ---------- */

function corsFor(req) {
  const origin = req.headers.origin;
  if (!origin) return {};
  // 正常部署是前后端同源；这里只额外放行本机开发地址
  const allowed = /^https?:\/\/(localhost|127\.0\.0\.1)(:\d+)?$/.test(origin);
  if (!allowed) return {};
  return {
    'Access-Control-Allow-Origin': origin,
    'Access-Control-Allow-Methods': 'GET,POST,PATCH,DELETE,OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type, Authorization',
    'Access-Control-Max-Age': '600',
    'Vary': 'Origin'
  };
}

// ===== 文本资源压缩：html / json 用 br 优先、gzip 兜底 =====
const COMPRESS_MIN = 1024;

function acceptsEncoding(header, enc) {
  return String(header || '').toLowerCase().split(',').some(part => {
    const [name, ...params] = part.trim().split(';');
    if (name !== enc && name !== '*') return false;
    const q = params.find(p => p.trim().startsWith('q='));
    return !q || Number(q.split('=')[1]) > 0;
  });
}

function compressIfAccepted(req, raw) {
  if (raw.length < COMPRESS_MIN) return { body: raw, encoding: '' };
  const ae = req.headers['accept-encoding'];
  if (acceptsEncoding(ae, 'br')) {
    return {
      body: brotliCompressSync(raw, {
        params: {
          [zlibConstants.BROTLI_PARAM_QUALITY]: 5,
          [zlibConstants.BROTLI_PARAM_SIZE_HINT]: raw.length
        }
      }),
      encoding: 'br'
    };
  }
  if (acceptsEncoding(ae, 'gzip')) {
    return { body: gzipSync(raw, { level: 6 }), encoding: 'gzip' };
  }
  return { body: raw, encoding: '' };
}

function addVary(headers, value) {
  const cur = headers.Vary;
  headers.Vary = cur ? cur + ', ' + value : value;
}

function sendJSON(req, res, status, data, extraHeaders = {}) {
  const raw = Buffer.from(JSON.stringify(data), 'utf8');
  const { body, encoding } = compressIfAccepted(req, raw);
  const headers = {
    ...corsFor(req),
    'Content-Type': 'application/json; charset=utf-8',
    'Content-Length': body.length,
    'Cache-Control': 'no-store',
    'X-Content-Type-Options': 'nosniff',
    ...extraHeaders
  };
  if (encoding) headers['Content-Encoding'] = encoding;
  addVary(headers, 'Accept-Encoding');
  res.writeHead(status, headers);
  res.end(body);
}

function readBody(req) {
  return new Promise((resolve, reject) => {
    const chunks = [];
    let size = 0;
    req.on('data', chunk => {
      size += chunk.length;
      if (size > MAX_BODY) {
        reject(new HttpError(413, '请求体过大'));
        req.destroy();
        return;
      }
      chunks.push(chunk);
    });
    req.on('end', () => resolve(Buffer.concat(chunks)));
    req.on('error', reject);
  });
}

async function readJSON(req) {
  // 只接受 JSON，顺便挡住跨站表单提交（表单无法伪造这个请求头）
  const ct = String(req.headers['content-type'] || '');
  if (!/^application\/json\b/i.test(ct)) {
    throw new HttpError(415, 'Content-Type 必须是 application/json');
  }
  const buf = await readBody(req);
  if (!buf.length) return {};
  try {
    return JSON.parse(buf.toString('utf8'));
  } catch {
    throw new HttpError(400, '请求体不是合法 JSON');
  }
}

function safeEqual(a, b) {
  const ab = Buffer.from(String(a));
  const bb = Buffer.from(String(b));
  if (ab.length !== bb.length) return false;
  return crypto.timingSafeEqual(ab, bb);
}

function isAuthorized(req) {
  if (!AUTH_PASS) return true;
  const header = String(req.headers.authorization || '');
  const m = /^Basic\s+(.+)$/i.exec(header);
  if (!m) return false;
  let decoded = '';
  try {
    decoded = Buffer.from(m[1], 'base64').toString('utf8');
  } catch {
    return false;
  }
  const i = decoded.indexOf(':');
  const user = i >= 0 ? decoded.slice(0, i) : '';
  const pass = i >= 0 ? decoded.slice(i + 1) : decoded;
  return safeEqual(user, AUTH_USER) && safeEqual(pass, AUTH_PASS);
}

/* ---------- 路由 ---------- */

async function handle(req, res) {
  let url;
  try {
    url = new URL(req.url, `http://${req.headers.host || '127.0.0.1'}`);
  } catch {
    throw new HttpError(400, '非法请求');
  }
  let pathname;
  try {
    pathname = decodeURIComponent(url.pathname);
  } catch {
    throw new HttpError(400, '非法路径');
  }

  if (req.method === 'OPTIONS') {
    res.writeHead(204, corsFor(req));
    res.end();
    return;
  }

  if (!isAuthorized(req)) {
    const body = '需要登录';
    res.writeHead(401, {
      ...corsFor(req),
      'WWW-Authenticate': 'Basic realm="Task Board", charset="UTF-8"',
      'Content-Type': 'text/plain; charset=utf-8',
      'Content-Length': Buffer.byteLength(body),
      'Cache-Control': 'no-store'
    });
    res.end(body);
    return;
  }

  /* 版本号：客户端轮询它来发现他人改动 */
  if (pathname === '/api/rev' && req.method === 'GET') {
    sendJSON(req, res, 200, { rev, bootId: BOOT_ID, time: Date.now() });
    return;
  }

  /* 完整状态 */
  if (pathname === '/api/state' && req.method === 'GET') {
    sendJSON(req, res, 200, {
      tasks: state.tasks.map(publicTask),
      groups: state.groups,
      rev,
      bootId: BOOT_ID
    });
    return;
  }

  /* 上传附件 */
  if (pathname === '/api/files' && req.method === 'POST') {
    const body = await readJSON(req);
    const name = toStr(body.name || 'file', 300);
    const type = toStr(body.type, 200);
    const data = String(body.data || '');
    if (!data) throw new HttpError(400, '附件内容为空');

    let buf;
    const m = /^data:([^;,]*)(;base64)?,([\s\S]*)$/.exec(data);
    if (m) buf = Buffer.from(m[3], m[2] ? 'base64' : 'utf8');
    else buf = Buffer.from(data, 'base64');

    if (!buf.length) throw new HttpError(400, '附件内容为空');
    if (buf.length > MAX_FILE) throw new HttpError(413, '单个附件不能超过 100MB');

    const serverName = makeServerName(name);
    await mkdir(FILES_DIR, { recursive: true });
    await writeFile(path.join(FILES_DIR, serverName), buf);
    sendJSON(req, res, 200, { serverName, name, type, size: buf.length });
    return;
  }

  /* 新增任务：编号由服务器统一分配，避免多人同时新增时撞号 */
  if (pathname === '/api/tasks' && req.method === 'POST') {
    const body = await readJSON(req);
    const input = body && typeof body.task === 'object' && body.task ? body.task : body;
    if (!input || typeof input !== 'object') throw new HttpError(400, '请求体不正确');

    const task = buildTask(input, null);
    if (!task.title) throw new HttpError(400, '任务标题不能为空');
    if (task.id) {
      if (state.tasks.some(t => String(t.id) === String(task.id))) {
        throw new HttpError(409, '任务编号已存在：' + task.id);
      }
    } else {
      task.id = nextTaskId();
    }

    state.tasks.push(task);
    bumpRev();
    await persist();
    console.log(`[创建] ${task.id} ${task.title}`);
    sendJSON(req, res, 200, { ok: true, rev, task: publicTask(task) });
    return;
  }

  const taskMatch = /^\/api\/tasks\/([^/]+)$/.exec(pathname);
  if (taskMatch && req.method === 'PATCH') {
    const id = taskMatch[1];
    const body = await readJSON(req);
    const idx = state.tasks.findIndex(t => String(t.id) === id);
    if (idx < 0) throw new HttpError(404, '任务不存在');

    const old = state.tasks[idx];
    // 乐观锁：编辑页可带上打开时看到的 updatedAt，冲突时由用户确认是否覆盖
    if (has(body, 'baseUpdatedAt') && toNum(body.baseUpdatedAt) !== toNum(old.updatedAt)) {
      throw new HttpError(409, '这条任务已被其他人修改', {
        task: publicTask(old),
        rev,
        bootId: BOOT_ID
      });
    }

    const updated = buildTask(body, old);
    if (!updated.title) throw new HttpError(400, '任务标题不能为空');
    state.tasks[idx] = updated;
    bumpRev();
    await persist();
    await cleanupUnusedFiles(collectServerNames(old));
    console.log(`[更新] ${updated.id} ${updated.title}`);
    sendJSON(req, res, 200, { ok: true, rev, task: publicTask(updated) });
    return;
  }

  /* 彻底删除任务：先写入归档文件，再从 task.json 移除；附件保留 */
  if (taskMatch && req.method === 'DELETE') {
    const id = taskMatch[1];
    const idx = state.tasks.findIndex(t => String(t.id) === id);
    if (idx < 0) throw new HttpError(404, '任务不存在');

    const removed = state.tasks[idx];
    const archivedAt = Date.now();
    archive.push({
      archivedAt,
      reason: 'purge',
      task: {
        ...removed,
        deleted: true,
        deletedAt: removed.deletedAt || archivedAt,
        updatedAt: archivedAt
      }
    });

    try {
      // 归档写盘成功后才动主数据，确保不会丢记录
      await persistArchive();
    } catch (err) {
      archive.pop();
      throw err;
    }

    state.tasks.splice(idx, 1);
    bumpRev();
    await persist();
    console.log(`[彻底删除] ${removed.id} ${removed.title}`);
    sendJSON(req, res, 200, { ok: true, rev });
    return;
  }

  /* 新增分组 */
  if (pathname === '/api/groups' && req.method === 'POST') {
    const body = await readJSON(req);
    const input = body && typeof body.group === 'object' && body.group ? body.group : body;
    if (!input || typeof input !== 'object') throw new HttpError(400, '请求体不正确');

    const group = buildGroup(input, null);
    if (!group.name) throw new HttpError(400, '组名不能为空');
    if (group.id && state.groups.some(g => String(g.id) === String(group.id))) {
      throw new HttpError(409, '分组已存在');
    }
    if (!group.id) group.id = 'G_' + crypto.randomBytes(8).toString('hex');

    state.groups.push(group);
    bumpRev();
    await persist();
    sendJSON(req, res, 200, { ok: true, rev, group });
    return;
  }

  const groupMatch = /^\/api\/groups\/([^/]+)$/.exec(pathname);
  if (groupMatch && req.method === 'PATCH') {
    const id = groupMatch[1];
    const body = await readJSON(req);
    const idx = state.groups.findIndex(g => String(g.id) === id);
    if (idx < 0) throw new HttpError(404, '分组不存在');

    const updated = buildGroup(body, state.groups[idx]);
    if (!updated.name) throw new HttpError(400, '组名不能为空');
    state.groups[idx] = updated;
    bumpRev();
    await persist();
    sendJSON(req, res, 200, { ok: true, rev, group: updated });
    return;
  }

  /* 删除分组：组内任务自动回到“未分组” */
  if (groupMatch && req.method === 'DELETE') {
    const id = groupMatch[1];
    const idx = state.groups.findIndex(g => String(g.id) === id);
    if (idx < 0) throw new HttpError(404, '分组不存在');
    state.groups.splice(idx, 1);
    for (const t of state.tasks) {
      if (String(t.groupId) === id) {
        t.groupId = '';
        t.updatedAt = Date.now();
      }
    }
    bumpRev();
    await persist();
    sendJSON(req, res, 200, { ok: true, rev });
    return;
  }

  /* 附件下载 / 预览 */
  if (pathname.startsWith('/files/') && req.method === 'GET') {
    const name = pathname.slice('/files/'.length);
    if (!/^[A-Za-z0-9._-]+$/.test(name)) throw new HttpError(400, '非法文件名');
    const filePath = path.join(FILES_DIR, name);
    try {
      const info = await stat(filePath);
      if (!info.isFile()) throw new Error('not a file');
    } catch {
      throw new HttpError(404, '附件不存在');
    }
    const data = await readFile(filePath);
    res.writeHead(200, {
      ...corsFor(req),
      'Content-Type': MIME[path.extname(name).toLowerCase()] || 'application/octet-stream',
      'Content-Length': data.length,
      'Cache-Control': 'private, max-age=31536000, immutable',
      'X-Content-Type-Options': 'nosniff',
      // 强制下载而不是在站点内直接渲染，避免上传的 SVG/HTML 被当作页面执行
      'Content-Disposition': `attachment; filename="${name}"`,
      'Content-Security-Policy': "default-src 'none'; sandbox"
    });
    res.end(data);
    return;
  }

  /* 页面 */
  if ((pathname === '/' || pathname === '/index.html') && req.method === 'GET') {
    let html;
    try {
      html = await readFile(INDEX_FILE);
    } catch {
      throw new HttpError(500, '找不到 index.html，请确认它和 task-server.mjs 在同一目录');
    }
    const { body, encoding } = compressIfAccepted(req, html);
    const headers = {
      ...corsFor(req),
      'Content-Type': 'text/html; charset=utf-8',
      'Content-Length': body.length,
      'Cache-Control': 'no-store',
      'X-Content-Type-Options': 'nosniff',
      'X-Frame-Options': 'SAMEORIGIN',
      'Referrer-Policy': 'no-referrer',
      'Content-Security-Policy': [
        "default-src 'self'",
        "img-src 'self' data: blob:",
        "media-src 'self' blob:",
        "style-src 'self' 'unsafe-inline'",
        // Cloudflare 会在页面里注入 Web Analytics 统计脚本，放行其脚本与上报地址
        "script-src 'self' 'unsafe-inline' https://static.cloudflareinsights.com",
        "connect-src 'self' http://127.0.0.1:8765 http://localhost:8765 https://cloudflareinsights.com",
        "object-src 'none'",
        "base-uri 'none'",
        "form-action 'none'",
        "frame-ancestors 'self'"
      ].join('; ')
    };
    if (encoding) headers['Content-Encoding'] = encoding;
    addVary(headers, 'Accept-Encoding');
    res.writeHead(200, headers);
    res.end(body);
    return;
  }

  if (pathname === '/favicon.ico') {
    res.writeHead(204, corsFor(req));
    res.end();
    return;
  }

  throw new HttpError(404, '接口不存在');
}

/* ---------- 启动 ---------- */

const server = http.createServer((req, res) => {
  handle(req, res).catch(err => {
    const status = err instanceof HttpError ? err.status : 500;
    if (status >= 500) console.error(err);
    if (!res.headersSent) {
      sendJSON(req, res, status, {
        error: err.message || '服务器内部错误',
        ...(err instanceof HttpError && err.extra ? err.extra : {})
      });
    } else {
      res.end();
    }
  });
});

await loadState();
await loadArchive();
await cleanupOrphanFiles();

server.listen(PORT, HOST, () => {
  console.log('开发任务看板已启动');
  console.log(`  本机    http://127.0.0.1:${PORT}`);
  if (HOST === '0.0.0.0' || HOST === '::') {
    for (const list of Object.values(os.networkInterfaces())) {
      for (const n of list || []) {
        if (n.family === 'IPv4' && !n.internal) {
          console.log(`  局域网  http://${n.address}:${PORT}`);
        }
      }
    }
  }
  console.log(`  数据    ${STATE_FILE}`);
  console.log(`  归档    ${ARCHIVE_FILE}${archive.length ? `（${archive.length} 条）` : ''}`);
  console.log(`  附件    ${FILES_DIR}`);
  if (AUTH_PASS) console.log(`  访问认证 已开启（用户名：${AUTH_USER}）`);
  else if (HOST !== '127.0.0.1' && HOST !== 'localhost') {
    console.log('  ⚠ 未设置 AUTH_PASS：能访问该端口的人都可以查看和修改任务。公网部署请设置密码。');
  }
  console.log('按 Ctrl+C 退出。');
});

server.on('error', err => {
  if (err.code === 'EADDRINUSE') {
    console.error(`端口 ${PORT} 已被占用，可用环境变量指定其他端口，例如：PORT=9000 node task-server.mjs`);
  } else {
    console.error(err);
  }
  process.exit(1);
});

let shuttingDown = false;
async function shutdown(signal) {
  if (shuttingDown) return;
  shuttingDown = true;
  console.log(`\n收到 ${signal}，正在保存数据…`);
  server.close();
  try {
    await Promise.allSettled([persistChain, archivePersistChain]);
  } catch (err) {
    console.error('保存数据失败：', err);
  }
  process.exit(0);
}
process.on('SIGINT', () => shutdown('SIGINT'));
process.on('SIGTERM', () => shutdown('SIGTERM'));
