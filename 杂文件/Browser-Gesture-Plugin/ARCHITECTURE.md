# 鼠标手势插件 — 架构文档

> 每次改动代码前先阅读本文档，改动后同步更新。

---

## 手势表（不可变更）

| 手势路径     | 动作               | 类型     | 转折角  |
| ------------ | ------------------ | -------- | ------- |
| ← 左滑       | ◀ 后退             | 单方向   | —       |
| → 右滑       | ▶ 前进             | 单方向   | —       |
| ↑ 上滑       | ⇧ 回到顶部（平滑） | 单方向   | —       |
| ↓ 下滑       | ⇩ 到底部（平滑）   | 单方向   | —       |
| →↑ 右→上     | ➕ 新建标签页      | L 形 90° | 50~130° |
| →↓ 右→下     | 🔄 刷新            | L 形 90° | 50~130° |
| ↙↘ 斜左→斜右 | ✕ 关闭标签页       | V 形锐角 | ≤ 140°  |
| ↘↙ 斜右→斜左 | ↩ 恢复关闭         | V 形锐角 | ≤ 140°  |

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

### 策略：头尾 30%/30% 取样 + 平均方向比较

```
原始路径 → 重采样(8px间距) → 取开头 30% 和结尾 30% → 各段加权平均方向 → 比较
```

```
turnAngle = computeTurnAngle(头部平均方向, 尾部平均方向)

if turnAngle > 25° → 头尾方向不同 → 多段手势（查表匹配 L / V 形）
if turnAngle ≤ 25° → 头尾方向接近 → 单方向手势
```

**为什么用头尾 30% 而不是对半（50/50）？**

- V 形手势可能不对称（左臂长、右臂短）
- 对半拆会把长臂的一部分分到另一半，稀释方向特征
- 头尾取样只取两端的稳定段，抗不对称

**为什么不用 DP 简化？**

- DP 简化会把"勾形"连续轨迹压成一条直线，丢失拐点
- 加权平均天然抗手抖，手腕自然起伏（10~20°）不会误判

**为什么不用逐点找最大变化？**

- 对噪声敏感
- 快速移动时方向波动大，容易误检

### 转折角计算

```
computeTurnAngle(seg1Angle, seg2Angle):
  incoming = (seg1Angle + 180) % 360  // 入向 = 第一段的反向
  return angleDiff(incoming, seg2Angle)
```

- L 形（右→上）：right(0°) + up(270°) → incoming=180° → angle=90° → 匹配
- L 形（右→下）：right(0°) + down(90°) → incoming=180° → angle=90° → 匹配
- V 形（斜左→斜右）：down-left(135°) + down-right(45°) → incoming=315° → angle=90° → 匹配

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
  ├── analyzeGesture() — 对半拆 + 模式匹配
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

## 修改流程

1. 先读 `ARCHITECTURE.md`，理解当前设计
2. 如果新增手势，更新 **手势表** 和 `analyzeGesture()` 中的模式匹配
3. 如果修改状态逻辑，确保 `suppressContext` 生命周期正确
4. 如果修改分析算法，在 `analyzeGesture()` 中更新并同步更新本文档
5. 完成后更新本文档的对应章节
