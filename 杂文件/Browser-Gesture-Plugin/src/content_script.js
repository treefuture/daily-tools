/**
 * 鼠标手势内容脚本
 * 功能：监听鼠标右键拖动 → 轨迹绘制 → 路径分析 → 发送动作到后台
 *
 * 状态机: IDLE → TRACKING → GESTURING → (执行动作) → IDLE
 *          IDLE → (右键单击) → contextmenu 正常弹出
 */
'use strict';

// ============================================================
// 配置
// ============================================================
const DEFAULTS = {
  minDragDistance: 30, // 最小拖动像素，超过才算手势
  lineWidth: 3, // 轨迹线宽度
  trailStyle: 'both', // 'line' | 'arrow' | 'both'
  trailColor: '#4488ff',
  arrowColor: '#4488ff',
  showActionName: true,
  actionNameSize: 14,
  actionNameColor: '#ffffff',
  trailOpacity: 0.55
};

// ============================================================
// 状态
// ============================================================
let state = 'IDLE'; // IDLE | TRACKING | GESTURING
let startPoint = null;
let lastPoint = null;
let path = [];
let canvas = null;
let ctx = null;
let config = { ...DEFAULTS };
let suppressContext = false; // 阻止后续右键菜单（在下一次 mousedown 时清除）
let rafId = null; // requestAnimationFrame ID
let gestureName = '';
let actionIcon = '';
let gestureError = false; // 当前路径是否无法匹配任何手势
let matchedActions = new Set(); // 已匹配的不同有效动作集合（size ≥ 2 后变无效则锁定）
let lockedFailure = false; // 达到2次成功后又变无效 → 永久锁定为失败
let pendingAction = null; // 最终要执行的动作（松开鼠标时使用）

// ============================================================
// 方向判定常量（角度制，0°=右，逆时针为正？不对，atan2 中 0°=右，顺时针方向为+）
// atan2(dy, dx) 中：右=0°, 下=90°, 左=±180°, 上=-90°
// ============================================================
const DIR_LABELS = [
  { label: 'right', range: [-22.5, 22.5] },
  { label: 'down-right', range: [22.5, 67.5] },
  { label: 'down', range: [67.5, 112.5] },
  { label: 'down-left', range: [112.5, 157.5] },
  { label: 'left', range: [157.5, 180.0], alt: [-180, -157.5] },
  { label: 'up-left', range: [-157.5, -112.5] },
  { label: 'up', range: [-112.5, -67.5] },
  { label: 'up-right', range: [-67.5, -22.5] }
];

// 方向 → 中文名称
const DIR_CN = {
  right: '→ 前进',
  left: '← 后退',
  up: '↑ 回到顶部',
  down: '↓ 页面底部',
  'down-right': '↘',
  'down-left': '↙',
  'up-right': '↗',
  'up-left': '↖'
};

// 手势模式中文名
const GESTURE_NAMES = {
  BACK: '← 后退',
  FORWARD: '→ 前进',
  SCROLL_TOP: '↑ 回到顶部',
  SCROLL_BOTTOM: '↓ 页面底部',
  NEW_TAB: '➕ 新建标签页',
  CLOSE_TAB: '✕ 关闭标签页',
  REOPEN_TAB: '↩ 恢复关闭标签页',
  REFRESH: '🔄 刷新'
};

const GESTURE_ICONS = {
  BACK: '◀',
  FORWARD: '▶',
  SCROLL_TOP: '⇧',
  SCROLL_BOTTOM: '⇩',
  NEW_TAB: '➕',
  CLOSE_TAB: '✕',
  REOPEN_TAB: '↩',
  REFRESH: '🔄'
};

// ============================================================
// 初始化（在 document_start 立即执行）
// ============================================================

// 事件监听器：立即绑定，不等待 DOMContentLoaded
document.addEventListener('mousedown', onMouseDown, true);
document.addEventListener('mousemove', onMouseMove, true);
document.addEventListener('mouseup', onMouseUp, true);
document.addEventListener('contextmenu', onContextMenu, true);
// 注意：不用 mouseleave（capture 阶段会因鼠标在元素间移动误触）
// 改用 onMouseMove 中的边界检测

// 配置加载（异步，加载完成前使用默认值）
chrome.storage.sync.get(DEFAULTS, items => {
  config = { ...DEFAULTS, ...items };
});
chrome.storage.onChanged.addListener(changes => {
  for (const [key, { newValue }] of Object.entries(changes)) {
    if (key in config) config[key] = newValue;
  }
});

// 检查是否刚因手势导航（刷新/前进/后退）跳转过来 → 阻止首次右键菜单
chrome.storage.session.get('_gs_suppress', result => {
  if (result._gs_suppress) {
    suppressContext = true;
    chrome.storage.session.remove('_gs_suppress');
    // 安全兜底：防止极端情况永远不释放
    setTimeout(() => {
      suppressContext = false;
    }, 800);
  }
});

// Canvas 延迟到 body 就绪再创建
(function ensureCanvas() {
  if (document.body) {
    createCanvas();
  } else {
    const observer = new MutationObserver(() => {
      if (document.body) {
        createCanvas();
        observer.disconnect();
      }
    });
    observer.observe(document.documentElement, {
      childList: true,
      subtree: true
    });
    // 兜底：如果 DOMContentLoaded 后 body 还不存在
    document.addEventListener('DOMContentLoaded', () => {
      if (!canvas && document.body) createCanvas();
    });
  }
})();

// ============================================================
// Canvas 覆盖层
// ============================================================
function createCanvas() {
  canvas = document.createElement('canvas');
  canvas.id = '__gesture_canvas__';
  canvas.style.cssText = `
    position: fixed;
    top: 0; left: 0; right: 0; bottom: 0;
    width: 100%; height: 100%;
    z-index: 2147483647;
    pointer-events: none;
    display: none;
  `;
  canvas.width = window.innerWidth;
  canvas.height = window.innerHeight;
  document.body.appendChild(canvas);
  ctx = canvas.getContext('2d');
}

function resizeCanvas() {
  canvas.width = window.innerWidth;
  canvas.height = window.innerHeight;
}

function showCanvas() {
  if (!canvas) return;
  resizeCanvas();
  canvas.style.display = 'block';
}

function hideCanvas() {
  canvas.style.display = 'none';
  if (rafId) {
    cancelAnimationFrame(rafId);
    rafId = null;
  }
}

// ============================================================
// 鼠标事件
// ============================================================
function onMouseDown(e) {
  if (e.button !== 2) return;
  if (state !== 'IDLE') return;

  // 清除可能残留的跨页面信号
  chrome.storage.session.remove('_gs_suppress');

  state = 'TRACKING';
  startPoint = { x: e.clientX, y: e.clientY, t: Date.now() };
  lastPoint = { ...startPoint };
  path = [{ ...startPoint }];
  gestureName = '';
  actionIcon = '';
  gestureError = false;
  matchedActions = new Set();
  lockedFailure = false;
  pendingAction = null;
  suppressContext = false; // 新操作重新允许右键菜单
}

function onMouseMove(e) {
  if (state === 'IDLE') return;

  // 鼠标离开视口 → 终止手势（比 mouseleave capture 更准确）
  if (
    e.clientX < -10 ||
    e.clientX > window.innerWidth + 10 ||
    e.clientY < -10 ||
    e.clientY > window.innerHeight + 10
  ) {
    if (state !== 'IDLE') suppressContext = true;
    cleanup();
    return;
  }

  const pt = { x: e.clientX, y: e.clientY, t: Date.now() };

  if (state === 'TRACKING') {
    const dx = pt.x - startPoint.x;
    const dy = pt.y - startPoint.y;
    const dist = Math.sqrt(dx * dx + dy * dy);
    if (dist >= config.minDragDistance) {
      state = 'GESTURING';
      showCanvas();
    } else {
      return;
    }
  }

  // GESTURING 状态：记录路径（采样间隔 ~3px）
  if (state === 'GESTURING') {
    const dx = pt.x - lastPoint.x;
    const dy = pt.y - lastPoint.y;
    if (dx * dx + dy * dy < 9) return;

    lastPoint = pt;
    path.push({ ...pt });

    // 通过 RAF 节流绘制 + 标签更新
    if (!rafId) {
      rafId = requestAnimationFrame(draw);
    }
  }
}

function onMouseUp(e) {
  if (e.button !== 2) return;

  /**
   * 进入过手势 → 阻止后续右键菜单
   * 单纯右键（没拖动到阈值）：不阻止 contextmenu，让浏览器正常弹出右键菜单
   * 只有真正进入 GESTURING 手势状态才需要阻止
   */
  if (state === 'GESTURING') {
    suppressContext = true;
    executeGesture();
  }

  cleanup();
}

function onContextMenu(e) {
  // 非 IDLE 状态（正在手势中）→ 永远阻止右键菜单
  if (state !== 'IDLE' || suppressContext) {
    e.preventDefault();
    e.stopPropagation();
    return false;
  }
}

// mouseleave 已废弃（capture 误触太多），改为 onMouseMove 中的视口边界检测

function cleanup() {
  state = 'IDLE';
  startPoint = null;
  lastPoint = null;
  path = [];
  gestureName = '';
  actionIcon = '';
  gestureError = false;
  matchedActions = new Set();
  lockedFailure = false;
  pendingAction = null;
  hideCanvas();
  // 不在此处清除 suppressContext！它会在下一次 onMouseDown 时被重置。
  // 确保 contextmenu 事件一定能被拦截到。
}

// ============================================================
// 方向与角度工具
// ============================================================
function getAngleDeg(dx, dy) {
  return Math.atan2(dy, dx) * (180 / Math.PI);
}

function getDirectionLabel(angleDeg) {
  for (const d of DIR_LABELS) {
    const r = d.range;
    if (angleDeg >= r[0] && angleDeg <= r[1]) return d.label;
    if (d.alt && angleDeg >= d.alt[0] && angleDeg <= d.alt[1]) return d.label;
  }
  // 兜底
  return 'right';
}

/** 两个角度的最小差值（绝对值，0~180°） */
function angleDiff(a, b) {
  let d = (((b - a) % 360) + 540) % 360;
  return d > 180 ? 360 - d : d;
}

/**
 * 计算路径转折角：第一段入向（方向反转）与第二段出向的夹角
 * 例：V 形"斜左→斜右"，入向 = seg1 反方向，出向 = seg2 正方向
 * 锐角 → 小角度转折；直角 → L 形；钝角 → 缓慢转向
 */
function computeTurnAngle(seg1AngleDeg, seg2AngleDeg) {
  const incoming = (seg1AngleDeg + 180) % 360; // 入向 = 第一段的反向
  return angleDiff(incoming, seg2AngleDeg);
}

// ============================================================
// 手势分析（重采样 + 头尾 30%/30% 比较 + 方向平均）
// ============================================================

function resampleUniform(points, step) {
  if (points.length < 2) return points;
  const dists = [0];
  for (let i = 1; i < points.length; i++) {
    dists.push(
      dists[i - 1] +
        Math.hypot(points[i].x - points[i - 1].x, points[i].y - points[i - 1].y)
    );
  }
  const total = dists[dists.length - 1];
  if (total < 1) return [points[0]];
  const result = [points[0]];
  let cursor = 0;
  for (let d = step; d < total; d += step) {
    while (cursor < dists.length - 1 && dists[cursor + 1] < d) cursor++;
    if (cursor >= dists.length - 1) break;
    const t = (d - dists[cursor]) / (dists[cursor + 1] - dists[cursor]);
    result.push({
      x: points[cursor].x + (points[cursor + 1].x - points[cursor].x) * t,
      y: points[cursor].y + (points[cursor + 1].y - points[cursor].y) * t
    });
  }
  result.push(points[points.length - 1]);
  return result;
}

function weightedDir(dirs) {
  let totalW = 0,
    avgA = 0;
  for (const d of dirs) {
    totalW += d.len;
    avgA += d.angle * d.len;
  }
  if (totalW === 0) return { angle: 0, label: 'right' };
  avgA /= totalW;
  return { angle: avgA, label: getDirectionLabel(avgA) };
}

/** 方向标签是否有左向分量 */
function hasLeft(label) {
  return ['left', 'up-left', 'down-left'].includes(label);
}
/** 方向标签是否有右向分量 */
function hasRight(label) {
  return ['right', 'up-right', 'down-right'].includes(label);
}

/**
 * 分析手势路径
 *
 * 两阶段策略：
 *   阶段 1（闸门）：头尾 30% 粗检 → coarseTurnAngle > 25°？→ 有拐弯
 *   阶段 2（精确定位）：平滑 + 拐点检测 → 在拐点处分割 → 分别平均方向 → 查表匹配
 *
 * 为什么不用纯拐点检测？
 *   - 纯拐点检测用前 12% 做参考基线，起手势的方向偏差（先↘再↓）会误触发拐点
 *   - 头尾 30% 天然抗噪音和初始抖动，简单手势（←→↑↓）不会误入拐点分支
 *
 * 为什么不用纯头尾 30%？
 *   - 第二臂极长时（↙↘↘↘），头 30% 越过拐点渗入第二臂，稀释第一臂方向特征
 *   - 拐点检测在动态转弯处分割，不受臂长比例影响
 */
function analyzeGesture(rawPoints) {
  if (rawPoints.length < 3) return null;

  // 1. 重采样为均匀间距（每 8px）
  const pts = resampleUniform(rawPoints, 8);
  if (pts.length < 3) return null;

  // 2. 每小段方向
  const segs = [];
  for (let i = 1; i < pts.length; i++) {
    const dx = pts[i].x - pts[i - 1].x;
    const dy = pts[i].y - pts[i - 1].y;
    const len = Math.hypot(dx, dy);
    if (len < 3) continue;
    segs.push({ angle: getAngleDeg(dx, dy), len });
  }
  if (segs.length < 2) return null;

  // 3. 头尾 30% 粗检：判断是否确实有拐弯
  //    头尾 30% 天然抗初始抖动/偏差，不会把起手势的微小方向变化误判为拐点
  const headLen = Math.max(2, Math.floor(segs.length * 0.3));
  const tailLen = Math.max(2, Math.floor(segs.length * 0.3));
  const coarseHeadDir = weightedDir(segs.slice(0, headLen));
  const coarseTailDir = weightedDir(segs.slice(segs.length - tailLen));
  const coarseTurnAngle = computeTurnAngle(
    coarseHeadDir.angle,
    coarseTailDir.angle
  );

  const TURN_THRESHOLD = 25;

  if (coarseTurnAngle > TURN_THRESHOLD) {
    // 4. 粗检确认有拐弯 → 用平滑 + 拐点找精确分割位置
    //    平滑方向（3 段移动窗口），消除手抖噪声
    const smoothed = [];
    for (let i = 0; i < segs.length; i++) {
      let sumSin = 0,
        sumCos = 0,
        totalW = 0;
      const iStart = Math.max(0, i - 1);
      const iEnd = Math.min(segs.length - 1, i + 1);
      for (let j = iStart; j <= iEnd; j++) {
        const rad = (segs[j].angle * Math.PI) / 180;
        sumSin += Math.sin(rad) * segs[j].len;
        sumCos += Math.cos(rad) * segs[j].len;
        totalW += segs[j].len;
      }
      smoothed.push(
        (Math.atan2(sumSin / totalW, sumCos / totalW) * 180) / Math.PI
      );
    }

    // 找拐点：以路径前 ~12%（至少 3 段）平均方向为参考基线
    const refLen = Math.max(3, Math.floor(smoothed.length * 0.12));
    let refSumSin = 0,
      refSumCos = 0;
    for (let i = 0; i < refLen; i++) {
      const rad = (smoothed[i] * Math.PI) / 180;
      refSumSin += Math.sin(rad);
      refSumCos += Math.cos(rad);
    }
    const refAngle =
      (Math.atan2(refSumSin / refLen, refSumCos / refLen) * 180) / Math.PI;

    let maxDiff = 0;
    let apexIdx = refLen;
    for (let i = refLen; i < smoothed.length; i++) {
      const diff = angleDiff(refAngle, smoothed[i]);
      if (diff > maxDiff) {
        maxDiff = diff;
        apexIdx = i;
      }
    }

    // 拐点必须离两端至少 15%（太近则不可靠，回退到头尾 30% 匹配）
    const MIN_APEX_DIST = Math.floor(segs.length * 0.15);
    const apexSafe =
      maxDiff > TURN_THRESHOLD &&
      apexIdx >= MIN_APEX_DIST &&
      apexIdx <= segs.length - MIN_APEX_DIST;

    if (apexSafe) {
      const beforeSegs = segs.slice(0, apexIdx);
      const afterSegs = segs.slice(apexIdx);

      if (beforeSegs.length > 0 && afterSegs.length > 0) {
        const beforeDir = weightedDir(beforeSegs);
        const afterDir = weightedDir(afterSegs);
        const turnAngle = computeTurnAngle(beforeDir.angle, afterDir.angle);

        const bLabel = beforeDir.label;
        const aLabel = afterDir.label;

        // ---- 先匹配 V 形（避免斜向手势被 L 形截胡） ----

        // V 形：关闭标签页（头左尾右）
        if (
          hasLeft(bLabel) &&
          (hasRight(aLabel) || aLabel === 'down') &&
          turnAngle <= 140
        ) {
          return { action: 'CLOSE_TAB', matched: true };
        }
        // V 形：恢复关闭标签页（头右尾左）
        if (
          hasRight(bLabel) &&
          (hasLeft(aLabel) || aLabel === 'down') &&
          turnAngle <= 140
        ) {
          return { action: 'REOPEN_TAB', matched: true };
        }

        // ---- 后匹配 L 形（需要纯正方向判定，防止斜向手势冒充） ----
        const innerHalfRight = angleDiff(beforeDir.angle, 0) <= 11.25;
        const innerHalfUp = angleDiff(afterDir.angle, -90) <= 11.25;
        const innerHalfDown = angleDiff(afterDir.angle, 90) <= 11.25;

        // L 形：右 → 上（~90°）
        if (
          bLabel === 'right' &&
          innerHalfRight &&
          aLabel === 'up' &&
          innerHalfUp &&
          turnAngle >= 50 &&
          turnAngle <= 130
        ) {
          return { action: 'NEW_TAB', matched: true };
        }
        // L 形：右 → 下（~90°）
        if (
          bLabel === 'right' &&
          innerHalfRight &&
          aLabel === 'down' &&
          innerHalfDown &&
          turnAngle >= 50 &&
          turnAngle <= 130
        ) {
          return { action: 'REFRESH', matched: true };
        }

        // 有拐弯但不匹配 → 无效
        return { action: null, matched: false };
      }
    }

    // 拐点不可靠 → 回退到头尾 30% 匹配（解决 →↓平滑过渡拐点落在末尾的问题）
    const hLabel = coarseHeadDir.label;
    const tLabel = coarseTailDir.label;

    // L 形：右 → 上（~90°）
    if (
      hLabel === 'right' &&
      tLabel === 'up' &&
      coarseTurnAngle >= 50 &&
      coarseTurnAngle <= 130
    ) {
      return { action: 'NEW_TAB', matched: true };
    }
    // L 形：右 → 下（~90°）
    if (
      hLabel === 'right' &&
      tLabel === 'down' &&
      coarseTurnAngle >= 50 &&
      coarseTurnAngle <= 130
    ) {
      return { action: 'REFRESH', matched: true };
    }
    // V 形：关闭标签页（头左尾右）
    if (
      hasLeft(hLabel) &&
      (hasRight(tLabel) || tLabel === 'down') &&
      coarseTurnAngle <= 140
    ) {
      return { action: 'CLOSE_TAB', matched: true };
    }
    // V 形：恢复关闭标签页（头右尾左）
    if (
      hasRight(hLabel) &&
      (hasLeft(tLabel) || tLabel === 'down') &&
      coarseTurnAngle <= 140
    ) {
      return { action: 'REOPEN_TAB', matched: true };
    }

    return { action: null, matched: false };
  }

  // 6. 无显著拐点 → 单方向手势
  const overall = weightedDir(segs);
  const label = overall.label;
  if (label === 'left') return { action: 'BACK', matched: true };
  if (label === 'right') return { action: 'FORWARD', matched: true };
  if (label === 'up') return { action: 'SCROLL_TOP', matched: true };
  if (label === 'down') return { action: 'SCROLL_BOTTOM', matched: true };
  return { action: null, matched: false };
}

// ============================================================
// 实时更新手势标签
// ============================================================
/**
 * 更新手势状态（分析与绘制共用）
 *
 * 2 次成功匹配规则（基于 Set 去重）：
 * - matchedActions.add(action) 自动去重，同一动作多次匹配只计 1 次
 * - matchedActions.size 达到 2 后不再记录新动作
 * - 达到 2 次后，若路径变无效 → 永久锁定为失败（不再重新解析）
 * - 达到 2 次后仍保持有效，正常更新显示
 */
function updateGestureLabel() {
  if (path.length < 5) {
    gestureError = false;
    return;
  }

  // 已永久锁定为失败 → 不再重新解析
  if (lockedFailure) {
    gestureName = '';
    actionIcon = '';
    gestureError = true;
    pendingAction = null;
    return;
  }

  const result = analyzeGesture(path);
  if (result && result.action) {
    matchedActions.add(result.action);
    gestureName = GESTURE_NAMES[result.action] || '';
    actionIcon = GESTURE_ICONS[result.action] || '';
    gestureError = false;
    pendingAction = result.action;
  } else {
    // 无效匹配
    if (matchedActions.size >= 2) {
      // 已达 2 次不同有效动作，现在变无效 → 永久锁定为失败
      lockedFailure = true;
      gestureName = '';
      actionIcon = '';
      gestureError = true;
      pendingAction = null;
    } else {
      // 未达上限，暂时无效（后续仍可重新匹配）
      gestureName = '';
      actionIcon = '';
      gestureError = true;
      pendingAction = null;
    }
  }
}

// ============================================================
// 执行手势
// ============================================================
function executeGesture() {
  if (path.length < 3) return;

  // 先刷新状态确保与最新路径一致（处理 RAF 未触发的情况）
  updateGestureLabel();

  const action = pendingAction;
  if (!action) return;

  // 在 content script 本地执行的动作
  if (action === 'SCROLL_TOP') {
    window.scrollTo({ top: 0, behavior: 'smooth' });
  } else if (action === 'SCROLL_BOTTOM') {
    const maxScroll = Math.max(
      document.body?.scrollHeight || 0,
      document.documentElement?.scrollHeight || 0,
      document.body?.offsetHeight || 0,
      document.documentElement?.offsetHeight || 0
    );
    window.scrollTo({ top: maxScroll, behavior: 'smooth' });
  } else if (action === 'BACK') {
    chrome.storage.session.set({ _gs_suppress: true });
    window.history.back();
  } else if (action === 'FORWARD') {
    chrome.storage.session.set({ _gs_suppress: true });
    window.history.forward();
  } else if (action === 'REFRESH') {
    chrome.storage.session.set({ _gs_suppress: true });
    location.reload();
  } else {
    // 新建/关闭/恢复标签页 需要 background 处理
    // REOPEN_TAB 可能打开新页面 → 设置跨页面信号
    if (action === 'REOPEN_TAB') {
      chrome.storage.session.set({ _gs_suppress: true });
    }
    chrome.runtime.sendMessage({ action: action });
  }
}

// ============================================================
// 绘制（RAF 中调用）
// ============================================================
function draw() {
  rafId = null;
  if (!ctx || !canvas) return;
  ctx.clearRect(0, 0, canvas.width, canvas.height);

  // 在绘制循环中同步更新手势标签（而非在 mousemove 中）
  updateGestureLabel();

  if (config.trailStyle === 'line' || config.trailStyle === 'both') {
    drawTrailLine();
  }
  if (config.trailStyle === 'arrow' || config.trailStyle === 'both') {
    drawArrow();
  }
  // 手势标签：有效显示动作名，无效显示提示
  if (config.showActionName) {
    drawActionLabel();
  }
}

function drawTrailLine() {
  if (path.length < 2) return;

  ctx.save();
  ctx.lineWidth = config.lineWidth;
  ctx.lineCap = 'round';
  ctx.lineJoin = 'round';
  ctx.globalAlpha = config.trailOpacity;

  // 渐变轨迹
  const gradient = ctx.createLinearGradient(
    path[0].x,
    path[0].y,
    lastPoint.x,
    lastPoint.y
  );
  gradient.addColorStop(0, 'rgba(100,130,255,0.15)');
  gradient.addColorStop(1, config.trailColor);
  ctx.strokeStyle = gradient;

  ctx.beginPath();
  ctx.moveTo(path[0].x, path[0].y);

  if (path.length <= 10) {
    // 点少时直接连线
    for (let i = 1; i < path.length; i++) {
      ctx.lineTo(path[i].x, path[i].y);
    }
  } else {
    // 使用平滑曲线
    for (let i = 1; i < path.length; i++) {
      const midX = (path[i - 1].x + path[i].x) / 2;
      const midY = (path[i - 1].y + path[i].y) / 2;
      ctx.quadraticCurveTo(path[i - 1].x, path[i - 1].y, midX, midY);
    }
    ctx.lineTo(lastPoint.x, lastPoint.y);
  }

  ctx.stroke();

  // 终点圆点
  ctx.fillStyle = config.trailColor;
  ctx.globalAlpha = 0.8;
  ctx.beginPath();
  ctx.arc(lastPoint.x, lastPoint.y, config.lineWidth + 2, 0, Math.PI * 2);
  ctx.fill();

  ctx.restore();
}

function drawArrow() {
  if (path.length < 3) return;

  // 取最近一段轨迹（倒数第 5 点到当前）作为箭头方向，更灵敏
  const refIdx = Math.max(0, path.length - 6);
  const refPoint = path[refIdx];
  const dx = lastPoint.x - refPoint.x;
  const dy = lastPoint.y - refPoint.y;
  const len = Math.hypot(dx, dy);
  if (len < 10) return;

  const angle = Math.atan2(dy, dx);
  const arrowLen = 20;
  const arrowAngle = Math.PI / 6;

  ctx.save();
  ctx.globalAlpha = config.trailOpacity + 0.2;
  ctx.strokeStyle = config.arrowColor;
  ctx.fillStyle = config.arrowColor;
  ctx.lineWidth = 2.5;
  ctx.lineCap = 'round';

  // 箭头主体（从起点到鼠标的一小段）
  const arrowStartX = lastPoint.x - arrowLen * 1.5 * Math.cos(angle);
  const arrowStartY = lastPoint.y - arrowLen * 1.5 * Math.sin(angle);

  ctx.beginPath();
  ctx.moveTo(arrowStartX, arrowStartY);
  ctx.lineTo(lastPoint.x, lastPoint.y);
  ctx.stroke();

  // 箭头头
  ctx.beginPath();
  ctx.moveTo(lastPoint.x, lastPoint.y);
  ctx.lineTo(
    lastPoint.x - arrowLen * Math.cos(angle - arrowAngle),
    lastPoint.y - arrowLen * Math.sin(angle - arrowAngle)
  );
  ctx.lineTo(
    lastPoint.x - arrowLen * Math.cos(angle + arrowAngle),
    lastPoint.y - arrowLen * Math.sin(angle + arrowAngle)
  );
  ctx.closePath();
  ctx.fill();

  ctx.restore();
}

function drawActionLabel() {
  const labelX = lastPoint.x + 15;
  const labelY = lastPoint.y - 15;

  // 有效手势 / 无效手势 / 刚起步不显示
  let text, bgColor, textColor;
  if (gestureName) {
    text = `${actionIcon} ${gestureName}`;
    bgColor = 'rgba(0,0,0,0.65)';
    textColor = config.actionNameColor;
  } else if (gestureError && path.length >= 8) {
    text = '⚠ 无效手势';
    bgColor = 'rgba(180,80,80,0.6)';
    textColor = '#ffdddd';
  } else {
    return; // 路径太短，不显示
  }

  ctx.save();

  ctx.font = `bold ${config.actionNameSize}px "Microsoft YaHei", "PingFang SC", sans-serif`;
  const metrics = ctx.measureText(text);
  const padding = 8;
  const bgW = metrics.width + padding * 2 + 6;
  const bgH = config.actionNameSize + padding * 2 + 4;

  ctx.fillStyle = bgColor;
  ctx.beginPath();
  const r = 6;
  const x = labelX - padding;
  const y = labelY - bgH / 2;
  ctx.moveTo(x + r, y);
  ctx.lineTo(x + bgW - r, y);
  ctx.quadraticCurveTo(x + bgW, y, x + bgW, y + r);
  ctx.lineTo(x + bgW, y + bgH - r);
  ctx.quadraticCurveTo(x + bgW, y + bgH, x + bgW - r, y + bgH);
  ctx.lineTo(x + r, y + bgH);
  ctx.quadraticCurveTo(x, y + bgH, x, y + bgH - r);
  ctx.lineTo(x, y + r);
  ctx.quadraticCurveTo(x, y, x + r, y);
  ctx.closePath();
  ctx.fill();

  ctx.fillStyle = textColor;
  ctx.textBaseline = 'middle';
  ctx.textAlign = 'left';
  ctx.fillText(text, labelX, labelY + 1);

  ctx.restore();
}
