# 鼠标手势插件 — 架构文档

> 每次改动代码前先阅读本文档，改动后同步更新。

---

## 手势表（不可变更）

| 手势路径     | 动作               | 类型   | 转折角   | 可调 |
| ------------ | ------------------ | ------ | -------- | ---- |
| ← 左滑       | ◀ 后退             | 单方向 | —        | —    |
| → 右滑       | ▶ 前进             | 单方向 | —        | —    |
| ↑ 上滑       | ⇧ 回到顶部（平滑） | 单方向 | —        | —    |
| ↓ 下滑       | ⇩ 到底部（平滑）   | 单方向 | —        | —    |
| →↑ 右→上     | ➕ 新建标签页      | L 形   | 50°~120° | ✅   |
| →↓ 右→下     | 🔄 刷新            | L 形   | 50°~120° | ✅   |
| ↙↘ 斜左→斜右 | ✕ 关闭标签页       | V 形   | 30°~180° | ✅   |
| ↘↙ 斜右→斜左 | ↩ 恢复关闭         | V 形   | 30°~180° | ✅   |

**规则：**

- 只有表内的手势可执行动作，其余一律判"无效手势"
- 斜角单方向（↖↗↙↘）不匹配任何动作
- 手势必须为连续一条线，不允许分段操作

---

## 事件与状态机

### 状态

```
IDLE → TRACKING → GESTURING → (执行/无效) → IDLE
                ↘ (短按松开) → IDLE
```

- **IDLE**: 空闲，右键弹窗正常弹出
- **TRACKING**: 右键已按下，但未超过最小拖动阈值（30px）
- **GESTURING**: 已进入手势模式，绘制轨迹 + 实时分析

### 关键规则

1. **进入 GESTURING 后，右键弹窗永远禁止弹出**
   - `suppressContext = true` 在 `onMouseUp` / `onMouseMove`（边界检测）设置
   - 在下一轮 `onMouseDown` 才重置为 false
   - 不在 `cleanup()` 中清除（确保 contextmenu 事件永远被拦截）

2. **鼠标离开页面检测（不用 mouseleave）**
   - `mouseleave` 在 capture 阶段会因鼠标在子元素间移动而误触
   - 改用 `onMouseMove` 中的视口边界检测：`clientX/clientY` 超出 `[-10, innerWidth/Height + 10]` 才判定为离开
   - 离开时标记 `suppressContext = true` 并调用 `cleanup()`

3. **手势退出时机 = 用户松开鼠标右键**
   - 任何无效手势都不应强制退出
   - `cleanup()` 只在 `onMouseUp` 或离开视口时调用

---

## 手势分析算法

### 策略：三阶段分析（头尾 30% 闸门 → 拐点定位 → 回退匹配）

```
原始路径 → 重采样(8px间距) → 各段方向
  │
  ├─ 阶段 1（闸门）：头尾 30% 粗检
  │   └─ coarseTurnAngle > 25°？
  │       ├─ 否 → 单方向手势 → 整体加权平均 → 匹配 ←→↑↓
  │       └─ 是 → 进入阶段 2
  │
  ├─ 阶段 2（拐点定位）：3 段平滑 + 拐点检测
  │   └─ 拐点离两端 ≥ 15%？（apexSafe）
  │       ├─ 是 → 在拐点分割 → 两段平均 → 先查 V 形再查 L 形
  │       └─ 否 → 进入阶段 3（回退）
  │
  └─ 阶段 3（回退）：头尾 30% 原始匹配
      └─ 用 coarseHeadDir / coarseTailDir 直接查表
```

```
阶段 1：
  coarseTurnAngle = computeTurnAngle(头 30%, 尾 30%)

  if coarseTurnAngle ≤ 25° → 单方向手势
  if coarseTurnAngle > 25° → 进入拐点定位

阶段 2（拐点定位）：
  平滑各段方向 → 以前 ~12% 平均为基线找拐点
  → 拐点离两端 ≥ 15%？ → 是 → 在拐点分割 → 两段平均 → 查表（V 形优先于 L 形）
  → 否 → 进入阶段 3

阶段 3（回退，处理 →↓ 平滑过渡拐点落在末尾的问题）：
  → 用头尾 30% 的原始方向标签 (coarseHeadDir / coarseTailDir) 查表
  → 与原始算法相同，天然抗平滑过渡
```

**为什么需要三阶段？**

单一算法无法同时解决三个问题：

| 问题                                                | 纯头尾 30%          | 纯拐点检测           |
| :-------------------------------------------------- | :------------------ | :------------------- |
| 非对称 V 形（↙↘↘↘）头 30% 渗入第二臂 → 稀释方向特征 | ❌ 方向被拉到中间   | ✅ 拐点分割精确      |
| 简单手势起手势偏差（先↘再↓）12% 基线偏移 → 误判拐点 | ✅ 偏差被稀释       | ❌ 窗口太小触发误判  |
| L 形平滑过渡（→↓ 转弯圆滑）拐点落在路径末尾         | ✅ 头尾固定取样可靠 | ❌ 拐点后只剩 1~2 段 |

**匹配顺序：V 形先于 L 形（防截胡）**

```
阶段 2 中查表顺序：
  1. V 形：CLOSE_TAB（hasLeft 头 + hasRight 尾）
  2. V 形：REOPEN_TAB（hasRight 头 + hasLeft 尾）
  3. L 形：NEW_TAB（右/右偏上 → 上，带纯正方向检查）
  4. L 形：REFRESH（右/右偏上 → 下，带纯正方向检查）
```

V 形在前、L 形在后。如果 L 形在前，斜向手势（↘↙）的拐点分割可能因方向标签落入 'right'/'down' 而被 L 形误匹配。

V 形匹配不再包含 `aLabel === 'down'` 条件（此前导致右→下误判为 REOPEN_TAB），
L 形头方向放宽至接收 `'right'` 或 `'down-right'`（解决自然右拉略偏下时匹配不上 REFRESH 的问题）。

**角度阈值可配置（2026-06 新增）**

所有 V 形和 L 形的转折角阈值已改为可配置项，在设置页可调：

| 配置项      | 默认值 | 对应手势                            |
| ----------- | ------ | ----------------------------------- |
| `vShapeMin` | 30°    | V 形 CLOSE/REOPEN 最小角 - 排除抖动 |
| `vShapeMax` | 180°   | V 形 CLOSE/REOPEN 最大角 - 横/斜    |
| `lShapeMin` | 50°    | L 形 NEW/REFRESH 最小角 - 含平滑弯  |
| `lShapeMax` | 120°   | L 形 NEW/REFRESH 最大角             |

阈值存储于 `chrome.storage.sync`，通过 `config` 对象在 `analyzeGesture()` 中读取。
修改阈值后无需刷新页面，`onChanged` 监听器自动同步到 content script。

**L 形方向检查（防斜向冒充）**

L 形的方向必须在标签区间的**内半区**（远离斜向边界）：

```javascript
// 'right' 标签区间 [-22.5°, 22.5°]，内半区 [-11.25°, 11.25°]
const innerHalfRight = angleDiff(beforeDir.angle, 0) <= 11.25;
```

| 方向  | 完整标签区间  | 纯正内半区      | 意义                |
| :---- | :------------ | :-------------- | :------------------ |
| right | ±22.5°        | ±11.25°         | 排除 20° 的↘冒充→   |
| down  | 67.5~112.5°   | 78.75~101.25°   | 排除 105° 的↙冒充↓  |
| up    | -112.5~-67.5° | -101.25~-78.75° | 排除 -105° 的↖冒充↑ |

**拐点可靠性检查（防平滑过渡）**

```javascript
const MIN_APEX_DIST = Math.floor(segs.length * 0.15);
const apexSafe =
  maxDiff > 25 &&
  apexIdx >= MIN_APEX_DIST &&
  apexIdx <= segs.length - MIN_APEX_DIST;
```

拐点必须在路径中间 70% 范围内（离两端各至少 15%）。若拐点落在末尾（平滑过渡时最大累积偏差在终点），回退到头尾 30% 原始匹配，确保动作准确。

### 转折角计算

```
computeTurnAngle(seg1Angle, seg2Angle):
  incoming = (seg1Angle + 180) % 360  // 反转第一段
  return angleDiff(incoming, seg2Angle)
```

- 直线（→→）：0° vs 0° → incoming=180° → angleDiff(180,0)=0° → 不进入拐点分支 ✓
- L 形（右→上）：0° vs 270° → incoming=180° → angle=90° → 进入拐点分支 ✓
- L 形（右→下）：0° vs 90° → incoming=180° → angle=90° → 进入拐点分支 ✓
- V 形（斜左→斜右）：135° vs 45° → incoming=315° → angle=90° → 进入拐点分支 ✓

> `angleDiff` + `computeTurnAngle` 反转是一对搭配逻辑，单独动任何一个会崩。详见"已知陷阱"章节。

---

## 跨页面信号（navigation signal）

当手势触发页面导航时，content script 会被销毁，新页面重新注入。
此时需要在旧页面销毁前将状态传递给新页面。

### 机制

```
旧页面                         新页面
  │                              │
  ├─ set _gs_suppress=true        │
  ├─ location.reload() ───────►  ├─ 读取 _gs_suppress
  │                              ├─ suppressContext=true
  │                              ├─ 清除 _gs_suppress
  │                              ├─ 800ms 安全超时
  │                              └─ contextmenu 被阻止 ✓
```

- 使用 `chrome.storage.session`（内存级，跨页面共享）
- 触发导航的动作：BACK（`history.back()`）、FORWARD（`history.forward()`）、REFRESH（`location.reload()`）、REOPEN_TAB
- 安全兜底：800ms 后自动清除，防止信号残留
- `onMouseDown` 时额外清除一次，兜底

---

## 视觉反馈

### 绘制模式（可切换）

- **轨迹线**：从起点到当前鼠标位置的渐变线 + 终点圆点
- **方向箭头**：最近一段轨迹（倒数第 6 点到当前点）的方向
- **两者**（默认）：同时显示

### 手势标签

| 状态     | 显示         | 背景色     |
| -------- | ------------ | ---------- |
| 有效手势 | 🅇 关闭标签页 | 黑色半透明 |
| 无效手势 | ⚠ 无效手势   | 红色半透明 |
| 路径太短 | 不显示       | —          |

### 箭头方向

| 状态     | 显示         | 背景色     |
| -------- | ------------ | ---------- |
| 有效手势 | 🅇 关闭标签页 | 黑色半透明 |
| 无效手势 | ⚠ 无效手势   | 红色半透明 |
| 路径太短 | 不显示       | —          |

### 箭头方向

- 用**最近一段轨迹**（倒数第 6 点到当前点）计算方向
- 不用起点到终点的整体方向（响应滞后）

---

## 文件结构

```
Browser-Gesture-Plugin/
├── ARCHITECTURE.md            ← 本文档，改动前必读
├── manifest.json              # Manifest V3
├── src/
│   ├── content_script.js      # 核心：手势检测 + 分析 + 视觉
│   ├── background.js          # Service Worker：标签操作 + 命令
│   ├── options.html           # 设置页面
│   ├── options.js             # 设置逻辑
│   └── popup.html / popup.js  # 工具栏弹出面板
├── icons/
│   ├── icon.svg
│   └── generate-icons.bat
└── README.md
```

### content_script.js 模块划分

```
初始化（top-level, document_start）
  ├── 事件绑定（mousedown/move/up/contextmenu/mouseleave）
  ├── 配置加载（chrome.storage.sync）
  ├── 跨页面信号检查（chrome.storage.session）
  └── Canvas 延迟创建（MutationObserver）

状态管理
  ├── IDLE → TRACKING → GESTURING → IDLE
  └── suppressContext 生命周期

手势分析
  ├── resampleUniform() — 均匀重采样
  ├── weightedDir() — 加权平均方向
  ├── analyzeGesture() — 动态拐点检测 + 两段分割匹配
  └── computeTurnAngle() — 转折角计算

执行
  ├── executeGesture() — 分发到本地或 background
  └── chrome.runtime.sendMessage() — 跨进程通信

视觉
  ├── draw() — RAF 主循环
  ├── drawTrailLine() — 轨迹线
  ├── drawArrow() — 方向箭头（最近一段）
  └── drawActionLabel() — 手势标签
```

---

## 2 次成功匹配规则（v2）

当手势路径在绘制过程中被持续分析时，引入以下规则来稳定最终判定。

### 机制

```
updateGestureLabel() / executeGesture()
       │
       ├─ lockedFailure = true? → 直接返回失败（永久锁定）
       │
       ├─ analyzeGesture(path) 返回有效动作?
       │     └─ matchedActions.add(action) → 自动去重
       │
       └─ 返回无效?
             ├─ matchedActions.size ≥ 2? → lockedFailure = true（永久锁定）
             └─ matchedActions.size < 2? → 暂时无效，可重新匹配
```

### 核心规则

1. **Set 自动去重**
   - `matchedActions.add(action)` 自动处理重复，同一动作多次匹配只计 1 次
   - Set 内部通过 hash 去重，无需手动比对 `lastMatchedAction`

2. **上限 2 个不同动作**
   - `matchedActions.size` 达到 2 后不再记录新动作
   - 但 `pendingAction` 仍可更新显示（松开时执行最后一次匹配到的有效动作）

3. **锁定为永久失败**
   - 当 `matchedActions.size ≥ 2` 且当前分析返回无效 → `lockedFailure = true`
   - 后续 `updateGestureLabel()` 直接返回失败，不再调用 `analyzeGesture()`
   - 直至下一次 `onMouseDown` / `cleanup()` 重置

4. **executeGesture() 使用 pendingAction**
   - 松开鼠标时调用 `updateGestureLabel()` 确保状态最新
   - 使用跟踪的 `pendingAction` 执行（而非重新分析路径）
   - 若 `pendingAction` 为 null 则不执行

### 示例

| 时序 | 分析结果 | matchedActions            | pendingAction | 说明                      |
| :--- | :------- | :------------------------ | :------------ | :------------------------ |
| 1    | 无效     | {}                        | null          | 路径太短或未匹配          |
| 2    | FORWARD  | {FORWARD}                 | FORWARD       | 第 1 个不同动作           |
| 3    | REFRESH  | {FORWARD, REFRESH}        | REFRESH       | 第 2 个不同动作，达到上限 |
| 4    | REFRESH  | {FORWARD, REFRESH}        | REFRESH       | 同一动作，Set 不变        |
| 5    | 无效     | {FORWARD, REFRESH} (锁定) | null          | 永久失败，不再解析        |
| 松开 | —        | —                         | null          | 不执行任何动作            |

| 时序 | 分析结果 | matchedActions     | pendingAction | 说明            |
| :--- | :------- | :----------------- | :------------ | :-------------- |
| 1    | FORWARD  | {FORWARD}          | FORWARD       | 第 1 个不同动作 |
| 2    | FORWARD  | {FORWARD}          | FORWARD       | 同一动作不变    |
| 3    | REFRESH  | {FORWARD, REFRESH} | REFRESH       | 第 2 个不同动作 |
| 松开 | —        | —                  | REFRESH       | ✓ 执行刷新      |

### 相关状态变量

- `matchedActions` (`Set`) — 已匹配的不同有效动作集合（`set.size ≥ 2` 后变无效则锁定）
- `lockedFailure` — 永久锁定为失败标志
- `pendingAction` — 最终要执行的动作

所有变量在 `onMouseDown()` 和 `cleanup()` 中重置。`Set` 天然去重，无需额外的比对逻辑。

---

## 已知陷阱与已修复 Bug（改代码前必读）

> 以下都是线上踩过的坑。改动 `storage`、`sendMessage`、角度计算相关代码时，
> 先检查是否落入这些模式。

### 1. angleDiff + computeTurnAngle 是配对逻辑（不可单独改动）

`angleDiff` 的 `+540` 公式在数学上"有误"（相差 180° 时返回 0，完全相同时返回 180），但这是**有意为之**：

- `computeTurnAngle` 先反转 seg1 再加 180°，和 `angleDiff` 的异常刚好抵消
- 配对后所有关键场景（直线/ L 形/ V 形）都给出正确的转折角
- `angleDiff` 直接用于 `innerHalf*` 检查时（`angleDiff(angle, 0) ≤ 11.25`），旧公式对所有角度返回 > 168，相当于 L 形永远不走拐点分支——但 stage 3 回退中的 L 形匹配（只用 label，不用 `angleDiff`）能兜底

**教训**：`angleDiff` 和 `computeTurnAngle` 必须一起改。单独动任何一个，三阶段分析都会崩。
不要试图把 `angleDiff` 改成 `Math.abs` 然后去掉 `computeTurnAngle` 的反转——虽然数学上结果相同，
但拐点检测（`maxDiff` 比较）和 `innerHalf*` 检查的行为会完全改变，导致拐点分支从"从不进入"变成"广泛进入"，
暴露 V 形/L 形匹配顺序差异，产生误判。

### 2. chrome.storage.session 在 content script 中可能返回 undefined（2026-06 修复）

```javascript
// ❌ 旧代码：回调中直接访问 result，storage 不可用时 result = undefined
chrome.storage.session.get('_gs_suppress', result => {
  if (result._gs_suppress) {   // TypeError: Cannot read properties of undefined
    ...
  }
});

// ✅ 修复后：防御性空值检查（严格相等）
chrome.storage.session.get('_gs_suppress', result => {
  if (result !== null && result !== undefined && result._gs_suppress) { ... }
});
```

**根因**：MV3 content script 在 `document_start` 运行时，extension 系统可能未完全就绪。
`chrome.storage.sync.get` 同样有这个问题（options.js 中也已加 `if (items)` 保护）。

**所有 storage 回调都需要加空值检查**：

| 调用位置                 | 状态      | 修复方式                           |
| ------------------------ | --------- | ---------------------------------- |
| `content_script.js`      | ✅ 已修复 | `result !== null && !== undefined` |
| `content_script.js:108`  | ✅ 已修复 | `items !== null && !== undefined`  |
| `options.js:44`          | ✅ 已修复 | `items !== null && !== undefined`  |
| `storage.session.set`    | ✅ 已修复 | 加 `() => {}` 回调                 |
| `storage.session.remove` | ✅ 已修复 | 加 `() => {}` 回调                 |

### 3. chrome.runtime.sendMessage 在 MV3 中可能无声失败（2026-06 修复）

```javascript
// ❌ 旧代码：无回调 → SW 休眠时丢消息 + 控制台 Unchecked runtime.lastError
chrome.runtime.sendMessage({ action: action });

// ✅ 修复后：加 callback 处理错误
chrome.runtime.sendMessage({ action }, () => {
  if (chrome.runtime.lastError) {
    // SW 可能已休眠，忽略（不影响当次操作）
  }
});
```

**根因**：MV3 Service Worker 空闲约 30 秒后被 Chrome 终止。重新激活是异步的，
`sendMessage` 在 SW 未就绪时抛出 `"Could not establish connection. Receiving end does not exist."`

**影响范围**：`content_script.js` — NEW_TAB / CLOSE_TAB / REOPEN_TAB

### 4. 设置页面 options.js 无 storage 错误保护（2026-06 修复）

`options.js:44`：

```javascript
// ❌ 旧代码：items 可能为 undefined 导致 TypeError
chrome.storage.sync.get(DEFAULTS, applySettings);

// ✅ 修复后：加空值保护
chrome.storage.sync.get(DEFAULTS, items => {
  if (items) applySettings(items);
});
```

如果 storage 访问受限，设置页打开后白屏崩溃。现已加 `if (items)` 保护。

### 5. Canvas 未响应窗口 resize（2026-06 修复）

`resizeCanvas()` 只在 `showCanvas()` 时调用。如果用户在手势过程中调整窗口大小，
轨迹坐标会偏移。在 `createCanvas()` 中加了 `window.addEventListener('resize', resizeCanvas)`。

> 注意：Canvas 销毁时没有 `removeEventListener`。Content script 随页面销毁，
> listener 随 window 生命周期自动回收，无需手动清理。

### 6. chrome.storage.session.remove/set 无回调（2026-06 修复）

多处调用：

- `content_script.js:120` — suppress 清理
- `content_script.js:197` — mousedown 时清除
- `content_script.js` — executeGesture() 中设置 \_gs_suppress

storage 不可用时产生 `Unchecked runtime.lastError`。所有此类调用已加空回调：

```javascript
chrome.storage.session.remove('_gs_suppress', () => {});
chrome.storage.session.set({ _gs_suppress: true }, () => {});
```

---

## 修改流程

1. 先读 `ARCHITECTURE.md`，理解当前设计
2. 检查**已知陷阱**章节，确保改动不踩坑
3. 如果新增手势，更新 **手势表** 和 `analyzeGesture()` 中的模式匹配
4. 如果修改状态逻辑，确保 `suppressContext` 生命周期正确
5. 如果修改分析算法（`analyzeGesture()`），同步更新本文档的"手势分析算法"章节
6. 完成后更新本文档的对应章节
