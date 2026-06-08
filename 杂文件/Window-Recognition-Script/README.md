# 窗口识别自动化工具 (Window Recognition Automation)

基于 **Python + pywin32 + uiautomation** 的 Windows GUI 自动化工具。

## 功能

- ✅ **窗口管理**：添加多个目标窗口到管理列表
- ✅ **控件识别**：通过 UIA (UI Automation) 遍历窗口控件树，查看控件属性
- ✅ **操作录制**：从控件树选择控件 + 配置动作 → 生成操作步骤
- ✅ **自动执行**：按顺序执行所有操作步骤（支持跨窗口）
- ✅ **方案保存/加载**：将窗口配置 + 操作步骤保存为 JSON 方案文件
- ✅ **重连机制**：窗口关闭后重启时可重新匹配

## 安装

```bash
pip install -r requirements.txt
```

依赖：
- `pywin32` — Windows API (枚举窗口、获取进程信息)
- `uiautomation` — 微软 UIA (UI Automation) 控件识别与操作
- `comtypes` — COM 接口绑定（uiautomation 依赖）

## 使用

### 启动

```bash
python window_automation_gui.py
```

或直接双击 `启动工具.bat`。

### 工作流程

1. **添加窗口** → 点击工具栏「添加窗口」，从列表选择要管理的窗口
2. **检查控件** → 双击左侧窗口条目，打开控件检查器浏览控件树
3. **添加操作** → 在控件树上选中控件 → 选择动作 → 点「添加操作步骤」
4. **执行回放** → 点击工具栏「执行全部」，自动按顺序操作

### 支持的动作

| 动作        | 说明                 | 参数         |
|------------|----------------------|-------------|
| `click`    | 单击控件             | —           |
| `dbl_click`| 双击控件             | —           |
| `set_text` | 输入文本（编辑框）   | 要输入的文本 |
| `toggle`   | 切换（复选框/开关）  | —           |
| `scroll`   | 滚动                 | `down`/`up`/`left`/`right` |

### 方案文件

方案文件为 JSON 格式，包含：
- 目标窗口列表（标题、类名、进程名）
- 操作步骤列表（动作类型、控件匹配条件、参数）

可保存/加载方案，实现重复利用。

## 项目结构

```
Window-Recognition-Script/
├── window_automation_core.py   # 核心引擎
├── window_automation_gui.py    # GUI 界面
├── requirements.txt            # 依赖
├── README.md                   # 本文件
└── 启动工具.bat                 # 一键启动
```

## 技术说明

- 控件匹配通过 **Name / AutomationId / ClassName / ControlType** 多维特征识别，不依赖绝对坐标或树索引路径，对窗口变动有一定容忍度
- 使用 UIA (UI Automation) 而非传统的坐标模拟，操作更可靠
- 支持不同窗口间的操作序列编排（操作→延迟→下一操作）
