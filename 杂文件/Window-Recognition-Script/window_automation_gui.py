#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
============================================
  窗口识别自动化工具 - GUI 界面
  Window Recognition Automation GUI
============================================
  管理目标窗口 → 录制控件操作 → 一键回放
============================================
"""

import json
import os
import sys
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

# ────────────────────────────────────────────────────────
#  引入核心引擎
# ────────────────────────────────────────────────────────
try:
    import window_automation_core as core
except ImportError:
    # 如果直接运行此文件且在同一目录下
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import window_automation_core as core

import uiautomation as uia


# ────────────────────────────────────────────────────────
#  全局样式方案
# ────────────────────────────────────────────────────────
FONT_FAMILY = "微软雅黑"
COLOR_BG = "#f5f5f5"
COLOR_FG = "#333333"
COLOR_ACCENT = "#0078d4"
COLOR_ACCENT_LIGHT = "#deecf9"
COLOR_SUCCESS = "#107c10"
COLOR_WARNING = "#d83b01"
COLOR_MUTED = "#666666"


def _style_ttk():
    style = ttk.Style()
    style.theme_use("vista" if "vista" in style.theme_names() else "clam")
    style.configure("Treeview", rowheight=26, font=(FONT_FAMILY, 10))
    style.configure("Treeview.Heading", font=(FONT_FAMILY, 10, "bold"))
    style.configure("TButton", font=(FONT_FAMILY, 10), padding=(6, 3))
    style.configure("TLabel", font=(FONT_FAMILY, 10))
    style.configure("TFrame", background=COLOR_BG)
    return style


# ────────────────────────────────────────────────────────
#  窗口选择器（Dialog：列出所有可见窗口）
# ────────────────────────────────────────────────────────

class WindowPickerDialog(tk.Toplevel):
    """显示所有可见顶层窗口供用户选择添加"""

    def __init__(self, parent, existing_hwnds: set):
        super().__init__(parent)
        self.title("选择目标窗口")
        self.geometry("700x450")
        self.resizable(True, True)
        self.transient(parent)
        self.grab_set()

        self.selected_windows: list[dict] = []
        self._existing_hwnds = existing_hwnds

        self._build_ui()
        self._load_windows()

    def _build_ui(self):
        # 筛选行
        filter_frame = ttk.Frame(self)
        filter_frame.pack(fill=tk.X, padx=8, pady=(8, 4))
        ttk.Label(filter_frame, text="筛选:").pack(side=tk.LEFT, padx=(0, 4))
        self._filter_var = tk.StringVar()
        self._filter_var.trace_add("write", lambda *_: self._filter())
        ttk.Entry(filter_frame, textvariable=self._filter_var, width=30).pack(side=tk.LEFT)

        self._count_label = ttk.Label(filter_frame, text="")
        self._count_label.pack(side=tk.RIGHT, padx=8)

        # 表格
        cols = ("title", "class_name", "process_name", "process_id")
        self._tree = ttk.Treeview(self, columns=cols, show="headings",
                                  selectmode="extended", height=14)
        self._tree.heading("title", text="窗口标题")
        self._tree.heading("class_name", text="类名")
        self._tree.heading("process_name", text="进程")
        self._tree.heading("process_id", text="PID")
        self._tree.column("title", width=280, minwidth=150)
        self._tree.column("class_name", width=160, minwidth=100)
        self._tree.column("process_name", width=120, minwidth=80)
        self._tree.column("process_id", width=60, minwidth=50)

        scroll_y = ttk.Scrollbar(self, orient=tk.VERTICAL, command=self._tree.yview)
        self._tree.configure(yscrollcommand=scroll_y.set)
        self._tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(8, 0), pady=4)
        scroll_y.pack(side=tk.RIGHT, fill=tk.Y, padx=(0, 8), pady=4)

        self._tree.bind("<Double-1>", lambda e: self._add_selected())

        # 底部按钮
        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill=tk.X, padx=8, pady=8)
        ttk.Button(btn_frame, text="全选", command=self._select_all).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="取消全选", command=self._deselect_all).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="刷新", command=self._load_windows).pack(side=tk.LEFT, padx=2)
        ttk.Label(btn_frame, text="").pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(btn_frame, text="添加选中窗口", command=self._add_selected).pack(side=tk.RIGHT, padx=2)
        ttk.Button(btn_frame, text="取消", command=self.destroy).pack(side=tk.RIGHT, padx=2)

    def _load_windows(self):
        """加载所有窗口到表格"""
        self._tree.delete(*self._tree.get_children())
        self._all_windows = core.list_all_windows()
        for w in self._all_windows:
            if w["hwnd"] in self._existing_hwnds:
                continue  # 跳过已在管理的窗口
            self._tree.insert("", tk.END, iid=str(w["hwnd"]),
                              values=(w["title"], w["class_name"],
                                      w["process_name"], w["process_id"]))
        self._update_count()

    def _filter(self):
        text = self._filter_var.get().lower()
        self._tree.delete(*self._tree.get_children())
        for w in self._all_windows:
            if w["hwnd"] in self._existing_hwnds:
                continue
            if (text in w["title"].lower() or text in w["class_name"].lower()
                    or text in w["process_name"].lower()):
                self._tree.insert("", tk.END, iid=str(w["hwnd"]),
                                  values=(w["title"], w["class_name"],
                                          w["process_name"], w["process_id"]))
        self._update_count()

    def _update_count(self):
        self._count_label.config(text=f"共 {len(self._tree.get_children())} 个窗口")

    def _select_all(self):
        for item in self._tree.get_children():
            self._tree.selection_add(item)

    def _deselect_all(self):
        self._tree.selection_remove(*self._tree.selection())

    def _add_selected(self):
        sel = self._tree.selection()
        if not sel:
            messagebox.showinfo("提示", "请先在列表中选择窗口", parent=self)
            return
        for item in sel:
            hwnd = int(item)
            for w in self._all_windows:
                if w["hwnd"] == hwnd:
                    self.selected_windows.append(w)
                    break
        self.destroy()


# ────────────────────────────────────────────────────────
#  控件检查器（Dialog：查看控件树 + 添加操作）
# ────────────────────────────────────────────────────────

class InspectorDialog(tk.Toplevel):
    """检查目标窗口的控件树，并添加操作步骤"""

    def __init__(self, parent, target: core.TargetWindow):
        super().__init__(parent)
        self.title(f"控件检查器 - {target.name or target.title}")
        self.geometry("800x600")
        self.transient(parent)
        self.grab_set()

        self._target = target
        self._added_operations: list[core.Operation] = []
        self._flat_nodes: list[dict] = []   # 平面节点列表
        self._ctrl_map: dict[int, uia.Control] = {}  # node_index -> UIA Control

        self._build_ui()
        self._refresh_tree()

    def _build_ui(self):
        paned = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)

        # ── 左侧：控件树 ──
        left_frame = ttk.Frame(paned)
        paned.add(left_frame, weight=3)

        ttk.Label(left_frame, text="控件树", font=(FONT_FAMILY, 11, "bold")).pack(anchor=tk.W, padx=4, pady=(0, 2))
        self._tree = ttk.Treeview(left_frame, columns=("type", "name"),
                                  show="tree headings", height=20)
        self._tree.heading("#0", text="控件名称")
        self._tree.heading("type", text="类型")
        self._tree.heading("name", text="AutomationId")
        self._tree.column("#0", width=220, minwidth=120)
        self._tree.column("type", width=120, minwidth=80)
        self._tree.column("name", width=150, minwidth=80)

        scroll_y = ttk.Scrollbar(left_frame, orient=tk.VERTICAL, command=self._tree.yview)
        self._tree.configure(yscrollcommand=scroll_y.set)
        self._tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll_y.pack(side=tk.RIGHT, fill=tk.Y)

        self._tree.bind("<<TreeviewSelect>>", self._on_select)

        # ── 右侧：属性 + 操作 ──
        right_frame = ttk.Frame(paned)
        paned.add(right_frame, weight=2)

        ttk.Label(right_frame, text="控件属性", font=(FONT_FAMILY, 11, "bold")).pack(anchor=tk.W, padx=4, pady=(0, 2))

        prop_frame = ttk.LabelFrame(right_frame, text="属性")
        prop_frame.pack(fill=tk.BOTH, expand=True, padx=4, pady=2)

        self._prop_text = tk.Text(prop_frame, height=12, width=35,
                                  font=(FONT_FAMILY, 9), wrap=tk.WORD,
                                  state=tk.DISABLED, bg="#fffff0")
        self._prop_text.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        # 操作配置区
        action_frame = ttk.LabelFrame(right_frame, text="添加操作")
        action_frame.pack(fill=tk.X, padx=4, pady=(6, 2))

        grid = ttk.Frame(action_frame)
        grid.pack(fill=tk.X, padx=4, pady=4)

        ttk.Label(grid, text="动作:").grid(row=0, column=0, sticky=tk.W, padx=(0, 4), pady=2)
        self._action_var = tk.StringVar(value="click")
        ttk.Combobox(grid, textvariable=self._action_var,
                     values=["click", "dbl_click", "set_text", "toggle", "scroll"],
                     width=14, state="readonly").grid(row=0, column=1, sticky=tk.W, pady=2)

        ttk.Label(grid, text="参数:").grid(row=1, column=0, sticky=tk.W, padx=(0, 4), pady=2)
        self._value_entry = ttk.Entry(grid, width=22)
        self._value_entry.grid(row=1, column=1, sticky=tk.W, pady=2)
        self._value_entry.insert(0, "输入文本或滚动方向(down/up)")

        ttk.Label(grid, text="等待(秒):").grid(row=2, column=0, sticky=tk.W, padx=(0, 4), pady=2)
        self._wait_spin = ttk.Spinbox(grid, from_=0.0, to=5.0, increment=0.1, width=8)
        self._wait_spin.set(0.5)
        self._wait_spin.grid(row=2, column=1, sticky=tk.W, pady=2)

        ttk.Label(grid, text="描述:").grid(row=3, column=0, sticky=tk.W, padx=(0, 4), pady=2)
        self._desc_entry = ttk.Entry(grid, width=22)
        self._desc_entry.grid(row=3, column=1, sticky=tk.W, pady=2)

        btn_frame = ttk.Frame(right_frame)
        btn_frame.pack(fill=tk.X, padx=4, pady=4)
        ttk.Button(btn_frame, text="➕ 添加操作步骤", command=self._add_operation).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="🔍 高亮控件", command=self._highlight_control).pack(side=tk.LEFT, padx=2)

        # 已添加的操作列表
        list_frame = ttk.LabelFrame(right_frame, text="已添加的操作")
        list_frame.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        self._op_listbox = tk.Listbox(list_frame, height=6, font=(FONT_FAMILY, 9))
        scroll_op = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self._op_listbox.yview)
        self._op_listbox.configure(yscrollcommand=scroll_op.set)
        self._op_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=4, pady=4)
        scroll_op.pack(side=tk.RIGHT, fill=tk.Y, pady=4)

        btn_op_frame = ttk.Frame(right_frame)
        btn_op_frame.pack(fill=tk.X, padx=4, pady=(0, 4))
        ttk.Button(btn_op_frame, text="删除选中操作", command=self._remove_operation).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_op_frame, text="清空所有操作", command=self._clear_operations).pack(side=tk.LEFT, padx=2)
        ttk.Label(btn_op_frame, text="").pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(btn_op_frame, text="✅ 确认添加", command=self._confirm).pack(side=tk.RIGHT, padx=2)

    def _refresh_tree(self):
        """刷新控件树"""
        self._tree.delete(*self._tree.get_children())
        self._flat_nodes.clear()
        self._ctrl_map.clear()

        hwnd = self._target.hwnd
        if not core.is_window_still_valid(hwnd):
            # 尝试自动刷新
            if not core.refresh_window_hwnd(self._target):
                messagebox.showerror("错误", "目标窗口已关闭", parent=self)
                return
            hwnd = self._target.hwnd

        root_ctl = core.get_control_from_hwnd(hwnd)
        if root_ctl is None:
            messagebox.showerror("错误", "无法获取窗口控件树", parent=self)
            return

        nodes = core.walk_control_tree(root_ctl, max_depth=12)
        self._flat_nodes = nodes

        # 构建 TreeView
        id_map = {}
        for node in nodes:
            node_id = node["_node_index"]
            parent_idx = node.get("parent_index", -1)

            ctl = core.find_control_by_path(root_ctl, _node_path(nodes, node_id))
            if ctl:
                self._ctrl_map[node_id] = ctl

            display_name = node["name"] or node["control_type"] or "(无名称)"
            if node["automation_id"]:
                display_name += f" [id={node['automation_id']}]"

            if parent_idx >= 0 and parent_idx in id_map:
                parent_iid = id_map[parent_idx]
            else:
                parent_iid = ""

            iid = self._tree.insert(parent_iid, tk.END, text=display_name,
                                    values=(node["control_type"], node["automation_id"]))
            id_map[node_id] = iid

    def _on_select(self, event):
        """选中节点时显示属性"""
        sel = self._tree.selection()
        if not sel:
            return
        # 反向查找 _node_index
        for node in self._flat_nodes:
            # 找对应的 tree item
            pass

        # 更简单的方案：获取选中的节点数据
        item = sel[0]
        # 查找对应的 node_index
        for node in self._flat_nodes:
            ctl = self._ctrl_map.get(node["_node_index"])
            if ctl is None:
                continue
            try:
                display_text = f"名称: {ctl.Name}\n" \
                               f"AutomationId: {ctl.AutomationId}\n" \
                               f"ClassName: {ctl.ClassName}\n" \
                               f"ControlType: {ctl.ControlTypeName}\n" \
                               f"LocalizedType: {ctl.LocalizedControlType}\n" \
                               f"BoundingRect: {ctl.BoundingRectangle}\n" \
                               f"Enabled: {ctl.IsEnabled}\n" \
                               f"Visible: {ctl.IsVisible}\n" \
                               f"Offscreen: {ctl.IsOffscreen}\n" \
                               f"HasKeyboardFocus: {ctl.HasKeyboardFocus}\n"
            except Exception:
                display_text = "(无法读取属性)"

            self._prop_text.config(state=tk.NORMAL)
            self._prop_text.delete("1.0", tk.END)
            self._prop_text.insert("1.0", display_text)
            self._prop_text.config(state=tk.DISABLED)
            break

    def _add_operation(self):
        """从选中控件添加一个操作步骤"""
        sel = self._tree.selection()
        if not sel:
            messagebox.showinfo("提示", "请在控件树中选择一个控件", parent=self)
            return

        # 查找选中节点对应的 _node_index
        # 遍历 flat_nodes 生成匹配
        target_node = None
        for node in self._flat_nodes:
            ctl = self._ctrl_map.get(node["_node_index"])
            if ctl is None:
                continue
            # 简单方式：直接用 AutomationId/Name 匹配
            item_display = self._tree.item(sel[0], "text")
            display_name = node["name"] or node["control_type"] or "(无名称)"
            if node["automation_id"]:
                display_name += f" [id={node['automation_id']}]"
            if display_name == item_display:
                target_node = node
                break

        if target_node is None:
            messagebox.showerror("错误", "无法定位控件数据", parent=self)
            return

        ctl = self._ctrl_map.get(target_node["_node_index"])
        if ctl is None:
            messagebox.showerror("错误", "无法获取 UIA 控件对象", parent=self)
            return

        action = self._action_var.get()
        value = self._value_entry.get()
        if action == "set_text" and (not value or value == "输入文本或滚动方向(down/up)"):
            messagebox.showinfo("提示", "set_text 操作需要输入文本参数", parent=self)
            return
        desc = self._desc_entry.get().strip()
        if not desc:
            desc = f"{action} -> {ctl.Name or target_node['control_type']}"

        matcher = core.ControlMatcher.from_control(ctl)

        op = core.Operation(
            action=action,
            window_index=0,
            matcher=matcher,
            value=value if action in ("set_text", "scroll") else "",
            wait_after=float(self._wait_spin.get()),
            description=desc,
        )
        self._added_operations.append(op)
        self._op_listbox.insert(tk.END, f"[{len(self._added_operations)}] {desc}")

    def _remove_operation(self):
        sel = self._op_listbox.curselection()
        if not sel:
            return
        idx = sel[0]
        self._op_listbox.delete(idx)
        self._added_operations.pop(idx)
        # 重新编号
        for i in range(self._op_listbox.size()):
            text = self._op_listbox.get(i)
            self._op_listbox.delete(i)
            # 去除旧的编号前缀
            parts = text.split("]", 1)
            new_text = f"[{i + 1}]" + (parts[1] if len(parts) > 1 else text)
            self._op_listbox.insert(i, new_text)

    def _clear_operations(self):
        self._op_listbox.delete(0, tk.END)
        self._added_operations.clear()

    def _highlight_control(self):
        sel = self._tree.selection()
        if not sel:
            return
        for node in self._flat_nodes:
            ctl = self._ctrl_map.get(node["_node_index"])
            if ctl is None:
                continue
            item_display = self._tree.item(sel[0], "text")
            display_name = node["name"] or node["control_type"] or "(无名称)"
            if node["automation_id"]:
                display_name += f" [id={node['automation_id']}]"
            if display_name == item_display:
                threading.Thread(target=lambda: core.highlight_control(ctl, 1.5),
                                 daemon=True).start()
                break

    def _confirm(self):
        """确认并返回添加的操作列表"""
        if not self._added_operations:
            if not messagebox.askyesno("确认", "尚未添加任何操作，确定退出吗？", parent=self):
                return
        self.destroy()


def _node_path(nodes: list[dict], target_id: int) -> list[int]:
    """根据 flat node list 重建从根到目标节点的索引路径"""
    # 先映射 parent_index -> children indices
    children_of = {}
    for node in nodes:
        pid = node.get("parent_index", -1)
        if pid >= 0:
            children_of.setdefault(pid, []).append(node["_node_index"])

    # 自顶向下构建路径
    path = []
    current = target_id
    while current >= 0:
        node = nodes[current]
        parent = node.get("parent_index", -1)
        if parent >= 0:
            siblings = children_of.get(parent, [])
            try:
                idx = siblings.index(current)
            except ValueError:
                idx = 0
            path.insert(0, idx)
        current = parent
    return path


# ────────────────────────────────────────────────────────
#  主窗口
# ────────────────────────────────────────────────────────

class MainApplication:
    """窗口识别自动化工具的主界面"""

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("窗口识别自动化工具 - Window Automation")
        self.root.geometry("1050x680")
        self.root.minsize(850, 550)
        self.root.configure(bg=COLOR_BG)

        _style_ttk()

        # ── 数据 ──
        self.target_windows: list[core.TargetWindow] = []
        self.operations: list[core.Operation] = []
        self.current_script_name: str = "未命名方案"
        self.current_script_path: str | None = None
        self._is_playing = False
        self._play_thread: threading.Thread | None = None
        self._stop_playback = False

        # ── 构建 UI ──
        self._build_menu()
        self._build_toolbar()
        self._build_main_area()
        self._build_status_bar()

        # 初始化更新
        self._update_window_list()

    # ── 菜单 ──
    def _build_menu(self):
        menubar = tk.Menu(self.root, font=(FONT_FAMILY, 9))
        self.root.config(menu=menubar)

        file_menu = tk.Menu(menubar, tearoff=0, font=(FONT_FAMILY, 9))
        file_menu.add_command(label="新建方案", command=self._new_script, accelerator="Ctrl+N")
        file_menu.add_command(label="打开方案...", command=self._open_script, accelerator="Ctrl+O")
        file_menu.add_command(label="保存方案", command=self._save_script, accelerator="Ctrl+S")
        file_menu.add_command(label="另存为...", command=self._save_script_as, accelerator="Ctrl+Shift+S")
        file_menu.add_separator()
        file_menu.add_command(label="退出", command=self.root.quit, accelerator="Alt+F4")
        menubar.add_cascade(label="文件", menu=file_menu)

        tool_menu = tk.Menu(menubar, tearoff=0, font=(FONT_FAMILY, 9))
        tool_menu.add_command(label="刷新窗口列表", command=self._update_window_list)
        tool_menu.add_command(label="重连所有窗口", command=self._reconnect_windows)
        tool_menu.add_separator()
        tool_menu.add_command(label="清空所有", command=self._clear_all)
        menubar.add_cascade(label="工具", menu=tool_menu)

        help_menu = tk.Menu(menubar, tearoff=0, font=(FONT_FAMILY, 9))
        help_menu.add_command(label="使用说明", command=self._show_help)
        help_menu.add_command(label="关于", command=self._show_about)
        menubar.add_cascade(label="帮助", menu=help_menu)

        # 快捷键
        self.root.bind("<Control-n>", lambda e: self._new_script())
        self.root.bind("<Control-o>", lambda e: self._open_script())
        self.root.bind("<Control-s>", lambda e: self._save_script())

    # ── 工具栏 ──
    def _build_toolbar(self):
        toolbar = ttk.Frame(self.root)
        toolbar.pack(fill=tk.X, padx=8, pady=(6, 2))

        ttk.Button(toolbar, text="➕ 添加窗口",
                   command=self._add_window).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="🗑️ 删除选中窗口",
                   command=self._remove_window).pack(side=tk.LEFT, padx=2)
        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=8, pady=2)

        ttk.Button(toolbar, text="▶ 执行全部",
                   command=self._play_all).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="⏹ 停止",
                   command=self._stop_playback).pack(side=tk.LEFT, padx=2)
        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=8, pady=2)

        ttk.Label(toolbar, text="方案:").pack(side=tk.LEFT, padx=(0, 4))
        self._script_name_var = tk.StringVar(value=self.current_script_name)
        ttk.Entry(toolbar, textvariable=self._script_name_var, width=25).pack(side=tk.LEFT)
        self._dirty_var = tk.StringVar(value="")
        ttk.Label(toolbar, textvariable=self._dirty_var, foreground=COLOR_WARNING).pack(side=tk.LEFT, padx=4)

    # ── 主区域 ──
    def _build_main_area(self):
        paned = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)

        # ─── 左侧：窗口列表 ───
        left_frame = ttk.Frame(paned)
        paned.add(left_frame, weight=2)

        header_left = ttk.Frame(left_frame)
        header_left.pack(fill=tk.X, padx=2, pady=(0, 2))
        ttk.Label(header_left, text="受管理的窗口",
                  font=(FONT_FAMILY, 11, "bold")).pack(side=tk.LEFT)
        self._win_count_label = ttk.Label(header_left, text="(0)", foreground=COLOR_MUTED)
        self._win_count_label.pack(side=tk.LEFT, padx=6)

        cols = ("name", "title", "status")
        self._win_tree = ttk.Treeview(left_frame, columns=cols, show="tree headings",
                                      selectmode="browse", height=10)
        self._win_tree.heading("#0", text="别名")
        self._win_tree.heading("name", text="进程")
        self._win_tree.heading("title", text="窗口标题")
        self._win_tree.heading("status", text="状态")
        self._win_tree.column("#0", width=100, minwidth=60)
        self._win_tree.column("name", width=100, minwidth=60)
        self._win_tree.column("title", width=200, minwidth=100)
        self._win_tree.column("status", width=60, minwidth=50)

        scroll_win = ttk.Scrollbar(left_frame, orient=tk.VERTICAL, command=self._win_tree.yview)
        self._win_tree.configure(yscrollcommand=scroll_win.set)
        self._win_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll_win.pack(side=tk.RIGHT, fill=tk.Y)

        self._win_tree.bind("<Double-1>", lambda e: self._inspect_window())
        self._win_tree.bind("<Delete>", lambda e: self._remove_window())

        # ─── 右侧：操作步骤 ───
        right_frame = ttk.Frame(paned)
        paned.add(right_frame, weight=3)

        header_right = ttk.Frame(right_frame)
        header_right.pack(fill=tk.X, padx=2, pady=(0, 2))
        ttk.Label(header_right, text="操作步骤",
                  font=(FONT_FAMILY, 11, "bold")).pack(side=tk.LEFT)
        self._op_count_label = ttk.Label(header_right, text="(0)", foreground=COLOR_MUTED)
        self._op_count_label.pack(side=tk.LEFT, padx=6)

        # 操作步骤表格
        op_cols = ("seq", "action", "target", "value", "wait")
        self._op_tree = ttk.Treeview(right_frame, columns=op_cols, show="headings",
                                     selectmode="extended", height=8)
        self._op_tree.heading("seq", text="#")
        self._op_tree.heading("action", text="动作")
        self._op_tree.heading("target", text="目标控件")
        self._op_tree.heading("value", text="参数")
        self._op_tree.heading("wait", text="等待")
        self._op_tree.column("seq", width=36, anchor=tk.CENTER)
        self._op_tree.column("action", width=80)
        self._op_tree.column("target", width=200)
        self._op_tree.column("value", width=120)
        self._op_tree.column("wait", width=50, anchor=tk.CENTER)

        scroll_op = ttk.Scrollbar(right_frame, orient=tk.VERTICAL, command=self._op_tree.yview)
        self._op_tree.configure(yscrollcommand=scroll_op.set)
        self._op_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll_op.pack(side=tk.RIGHT, fill=tk.Y)

        self._op_tree.bind("<Delete>", lambda e: self._remove_operation())
        self._op_tree.bind("<Double-1>", lambda e: self._edit_operation())

        # 操作按钮行
        op_btn_frame = ttk.Frame(right_frame)
        op_btn_frame.pack(fill=tk.X, padx=2, pady=(4, 0))

        ttk.Button(op_btn_frame, text="📋 检查控件",
                   command=self._inspect_window).pack(side=tk.LEFT, padx=2)
        ttk.Button(op_btn_frame, text="✏️ 编辑",
                   command=self._edit_operation).pack(side=tk.LEFT, padx=2)
        ttk.Button(op_btn_frame, text="↑ 上移",
                   command=self._move_up_operation).pack(side=tk.LEFT, padx=2)
        ttk.Button(op_btn_frame, text="↓ 下移",
                   command=self._move_down_operation).pack(side=tk.LEFT, padx=2)
        ttk.Button(op_btn_frame, text="删除",
                   command=self._remove_operation).pack(side=tk.LEFT, padx=2)
        ttk.Button(op_btn_frame, text="清空所有",
                   command=self._clear_operations).pack(side=tk.LEFT, padx=2)

        # ─── 日志输出 ───
        log_frame = ttk.LabelFrame(self.root, text="运行日志")
        log_frame.pack(fill=tk.BOTH, padx=8, pady=(0, 6))
        self._log_text = tk.Text(log_frame, height=6, font=(FONT_FAMILY, 9),
                                 wrap=tk.WORD, state=tk.DISABLED, bg="#1e1e1e", fg="#d4d4d4")
        scroll_log = ttk.Scrollbar(log_frame, orient=tk.VERTICAL, command=self._log_text.yview)
        self._log_text.configure(yscrollcommand=scroll_log.set)
        self._log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=2, pady=2)
        scroll_log.pack(side=tk.RIGHT, fill=tk.Y, pady=2)

    def _build_status_bar(self):
        status = ttk.Frame(self.root)
        status.pack(fill=tk.X, padx=8, pady=(0, 4))
        self._status_label = ttk.Label(status, text="就绪", foreground=COLOR_MUTED)
        self._status_label.pack(side=tk.LEFT)

    # ────────────────────────────────────────────────
    #  日志工具
    # ────────────────────────────────────────────────
    def _log(self, msg: str, level: str = "info"):
        """添加日志，level: info/success/warning/error"""
        colors = {"info": "#d4d4d4", "success": "#4ec9b0",
                  "warning": "#ce9178", "error": "#f44747"}
        tag = level if level in colors else "info"
        self._log_text.config(state=tk.NORMAL)
        self._log_text.insert(tk.END, f"[{time.strftime('%H:%M:%S')}] {msg}\n", tag)
        self._log_text.tag_config("info", foreground=colors["info"])
        self._log_text.tag_config("success", foreground=colors["success"])
        self._log_text.tag_config("warning", foreground=colors["warning"])
        self._log_text.tag_config("error", foreground=colors["error"])
        self._log_text.see(tk.END)
        self._log_text.config(state=tk.DISABLED)

    def _set_status(self, text: str):
        self._status_label.config(text=text)
        self.root.update_idletasks()

    # ────────────────────────────────────────────────
    #  窗口管理
    # ────────────────────────────────────────────────
    def _add_window(self):
        """打开窗口选择器"""
        existing = {w.hwnd for w in self.target_windows if w.hwnd > 0}
        dialog = WindowPickerDialog(self.root, existing)
        self.root.wait_window(dialog)

        for win_info in dialog.selected_windows:
            target = core.TargetWindow(
                name=win_info["process_name"] or win_info["class_name"],
                hwnd=win_info["hwnd"],
                title=win_info["title"],
                class_name=win_info["class_name"],
                process_id=win_info["process_id"],
                process_name=win_info["process_name"],
                find_by_title=win_info["title"],
                find_by_class=win_info["class_name"],
            )
            self.target_windows.append(target)
            self._log(f"添加窗口: {target.title} (pid={target.process_id})", "success")

        self._update_window_list()

    def _remove_window(self):
        sel = self._win_tree.selection()
        if not sel:
            return
        idx = self._win_tree.index(sel[0])
        if idx < len(self.target_windows):
            removed = self.target_windows.pop(idx)
            self._log(f"移除窗口: {removed.title}", "warning")
            self._update_window_list()

    def _update_window_list(self):
        """刷新窗口列表显示"""
        self._win_tree.delete(*self._win_tree.get_children())
        for i, w in enumerate(self.target_windows):
            valid = core.is_window_still_valid(w.hwnd)
            status = "✓" if valid else "✗"
            self._win_tree.insert("", tk.END, iid=str(i),
                                  text=w.name or f"窗口{i}",
                                  values=(w.process_name, w.title, status))
        self._win_count_label.config(text=f"({len(self.target_windows)})")

    def _reconnect_windows(self):
        """尝试重连所有失效窗口"""
        count = 0
        for w in self.target_windows:
            if not core.is_window_still_valid(w.hwnd):
                if core.refresh_window_hwnd(w):
                    count += 1
        self._update_window_list()
        self._log(f"重连完成，成功重连 {count} 个窗口", "success")

    # ────────────────────────────────────────────────
    #  检查器
    # ────────────────────────────────────────────────
    def _inspect_window(self):
        """打开控件检查器"""
        sel = self._win_tree.selection()
        if not sel:
            messagebox.showinfo("提示", "请先在左侧选择一个目标窗口")
            return
        idx = self._win_tree.index(sel[0])
        if idx >= len(self.target_windows):
            return
        target = self.target_windows[idx]

        if not core.is_window_still_valid(target.hwnd):
            if not core.refresh_window_hwnd(target):
                messagebox.showerror("错误", "目标窗口已关闭，无法打开检查器")
                return
            self._update_window_list()

        dialog = InspectorDialog(self.root, target)
        self.root.wait_window(dialog)

        if dialog._added_operations:
            # 将新操作添加到主列表（调整 window_index）
            for op in dialog._added_operations:
                op.window_index = idx
                self.operations.append(op)
            self._update_operation_list()
            self._log(f"从 [{target.name}] 添加了 {len(dialog._added_operations)} 个操作步骤", "success")

    # ────────────────────────────────────────────────
    #  操作步骤管理
    # ────────────────────────────────────────────────
    def _update_operation_list(self):
        self._op_tree.delete(*self._op_tree.get_children())
        for i, op in enumerate(self.operations):
            win_name = ""
            if op.window_index < len(self.target_windows):
                win_name = self.target_windows[op.window_index].name
            target_text = f"[{win_name}] {op.matcher.name or op.matcher.control_type or '(泛匹配)'}"
            value_text = op.value if op.value else "-"
            self._op_tree.insert("", tk.END, iid=str(i),
                                 values=(i + 1, op.action, target_text, value_text, op.wait_after))
        self._op_count_label.config(text=f"({len(self.operations)})")

    def _remove_operation(self):
        sel = self._op_tree.selection()
        if not sel:
            return
        indices = sorted([self._op_tree.index(item) for item in sel], reverse=True)
        for idx in indices:
            if idx < len(self.operations):
                self.operations.pop(idx)
        self._update_operation_list()

    def _edit_operation(self):
        sel = self._op_tree.selection()
        if not sel:
            return
        idx = self._op_tree.index(sel[0])
        if idx >= len(self.operations):
            return
        EditOperationDialog(self.root, self.operations, idx, self.target_windows,
                            lambda: self._update_operation_list())

    def _move_up_operation(self):
        sel = self._op_tree.selection()
        if not sel:
            return
        idx = self._op_tree.index(sel[0])
        if idx <= 0:
            return
        self.operations[idx], self.operations[idx - 1] = self.operations[idx - 1], self.operations[idx]
        self._update_operation_list()
        self._op_tree.selection_set(str(idx - 1))

    def _move_down_operation(self):
        sel = self._op_tree.selection()
        if not sel:
            return
        idx = self._op_tree.index(sel[0])
        if idx >= len(self.operations) - 1:
            return
        self.operations[idx], self.operations[idx + 1] = self.operations[idx + 1], self.operations[idx]
        self._update_operation_list()
        self._op_tree.selection_set(str(idx + 1))

    def _clear_operations(self):
        if not self.operations:
            return
        if messagebox.askyesno("确认", "确定清空所有操作步骤吗？"):
            self.operations.clear()
            self._update_operation_list()
            self._log("已清空所有操作步骤", "warning")

    # ────────────────────────────────────────────────
    #  方案文件管理
    # ────────────────────────────────────────────────
    def _new_script(self):
        self.target_windows.clear()
        self.operations.clear()
        self.current_script_name = "未命名方案"
        self.current_script_path = None
        self._script_name_var.set(self.current_script_name)
        self._update_window_list()
        self._update_operation_list()
        self._log("已创建新方案", "info")

    def _open_script(self):
        path = filedialog.askopenfilename(
            title="打开方案",
            filetypes=[("自动化方案", "*.json"), ("所有文件", "*.*")],
            initialdir=".",
        )
        if not path:
            return
        try:
            script = core.AutomationScript.load(path)
            self.target_windows = script.windows
            self.operations = script.operations
            self.current_script_name = script.name or os.path.splitext(os.path.basename(path))[0]
            self.current_script_path = path
            self._script_name_var.set(self.current_script_name)

            # 尝试重连 hwnd
            for w in self.target_windows:
                core.refresh_window_hwnd(w)

            self._update_window_list()
            self._update_operation_list()
            self._log(f"已加载方案: {path}", "success")
        except Exception as e:
            messagebox.showerror("加载失败", f"无法加载方案文件:\n{e}")

    def _save_script(self):
        if self.current_script_path:
            self._do_save(self.current_script_path)
        else:
            self._save_script_as()

    def _save_script_as(self):
        path = filedialog.asksaveasfilename(
            title="保存方案",
            defaultextension=".json",
            filetypes=[("自动化方案", "*.json"), ("所有文件", "*.*")],
            initialdir=".",
        )
        if not path:
            return
        self.current_script_path = path
        self._do_save(path)

    def _do_save(self, path: str):
        name = self._script_name_var.get().strip() or "未命名方案"
        script = core.AutomationScript(
            name=name,
            description=f"由窗口识别自动化工具创建于 {time.strftime('%Y-%m-%d %H:%M:%S')}",
            windows=self.target_windows,
            operations=self.operations,
        )
        try:
            script.save(path)
            self.current_script_name = name
            self._log(f"方案已保存: {path}", "success")
        except Exception as e:
            messagebox.showerror("保存失败", f"无法保存方案文件:\n{e}")

    def _clear_all(self):
        if messagebox.askyesno("确认", "确定要清空所有窗口和操作步骤吗？"):
            self._new_script()

    # ────────────────────────────────────────────────
    #  执行播放
    # ────────────────────────────────────────────────
    def _play_all(self):
        if self._is_playing:
            return
        if not self.operations:
            messagebox.showinfo("提示", "没有可执行的操作步骤。\n请先添加窗口并使用检查器添加操作。")
            return
        if not self.target_windows:
            messagebox.showinfo("提示", "没有目标窗口。\n请先添加窗口。")
            return

        self._is_playing = True
        self._stop_playback = False
        self._play_thread = threading.Thread(target=self._play_worker, daemon=True)
        self._play_thread.start()

    def _stop_playback(self):
        if self._is_playing:
            self._stop_playback = True
            self._log("用户请求停止播放...", "warning")

    def _play_worker(self):
        self.root.after(0, lambda: self._set_playback_ui(True))
        script = core.AutomationScript(
            name=self.current_script_name,
            windows=self.target_windows,
            operations=self.operations,
        )

        def on_step(idx, op):
            if self._stop_playback:
                return True  # skip
            win_name = ""
            if op.window_index < len(self.target_windows):
                win_name = self.target_windows[op.window_index].name
            self.root.after(0, lambda: self._log(
                f"▶ [{idx + 1}/{len(self.operations)}] {op.description} "
                f"(窗口: {win_name})", "info"))
            self.root.after(0, lambda: self._set_status(
                f"执行中: [{idx + 1}/{len(self.operations)}] {op.description}"))
            time.sleep(0.1)
            return False

        def on_error(idx, op, error):
            if self._stop_playback:
                return True
            self.root.after(0, lambda: self._log(
                f"✗ [{idx + 1}] 失败: {error}", "error"))
            # 继续执行下一个
            return True

        result = core.execute_script(script, on_step=on_step, on_error=on_error)

        self.root.after(0, lambda: self._finalize_playback(result))

    def _finalize_playback(self, success: bool):
        self._is_playing = False
        if success:
            self._log("✅ 全部操作执行完成！", "success")
            self._set_status("执行完成")
        else:
            self._log("⚠️ 执行过程中有错误（已跳过继续）", "warning")
            self._set_status("执行完成（有错误）")
        self._set_playback_ui(False)

    def _set_playback_ui(self, playing: bool):
        """切换播放状态下的 UI"""
        pass  # 暂时不做复杂 UI 锁定

    # ────────────────────────────────────────────────
    #  帮助 / 关于
    # ────────────────────────────────────────────────
    def _show_help(self):
        help_text = """\
窗口识别自动化工具 使用说明

1. 添加目标窗口
   - 点击工具栏「添加窗口」按钮
   - 从列表中选择要管理的窗口（支持多选）
   - 选中的窗口会出现在左侧「受管理的窗口」列表中

2. 检查控件
   - 双击左侧的窗口条目（或选中后点「检查控件」）
   - 在控件树中浏览控件的层级结构
   - 点击任一控件可查看其属性详情

3. 添加操作步骤
   - 在控件树中选择一个控件
   - 选择要执行的动作（点击 / 双击 / 输入文字 / 切换 / 滚动）
   - 填写参数（如需）
   - 点击「添加操作步骤」

4. 管理操作步骤
   - 在右侧列表中可上下移动、编辑、删除步骤
   - 可通过「清空所有」一键重置

5. 执行自动化
   - 点击工具栏「执行全部」按钮
   - 工具会按顺序执行所有操作步骤
   - 可在执行中随时点击「停止」

6. 保存/加载方案
   - 文件菜单中可新建、保存、加载方案文件（.json）
   - 方案包含了窗口信息和所有操作步骤

提示：
   - 窗口标题变化时，可用「工具 → 重连所有窗口」刷新
   - 控件通过 Name/AutomationId/ClassName 等多维特征匹配，具有一定的抗变化能力
"""
        messagebox.showinfo("使用说明", help_text)

    def _show_about(self):
        messagebox.showinfo("关于",
                            "窗口识别自动化工具 v1.0\n\n"
                            "基于 Python + pywin32 + uiautomation\n"
                            "实现对 Windows 窗口控件的识别与自动化操作")


# ────────────────────────────────────────────────────────
#  操作编辑 Dialog
# ────────────────────────────────────────────────────────

class EditOperationDialog(tk.Toplevel):
    """编辑单个操作的详情"""

    def __init__(self, parent, operations: list, index: int,
                 windows: list, on_save: callable):
        super().__init__(parent)
        self.title(f"编辑操作 #{index + 1}")
        self.geometry("450x350")
        self.transient(parent)
        self.grab_set()

        self._operations = operations
        self._index = index
        self._windows = windows
        self._on_save = on_save
        op = operations[index]

        ttk.Label(self, text=f"窗口:", font=(FONT_FAMILY, 10)).pack(anchor=tk.W, padx=12, pady=(12, 2))
        win_names = [w.name or w.title for w in windows]
        self._win_var = tk.StringVar(value=win_names[op.window_index] if op.window_index < len(win_names) else "")
        ttk.Combobox(self, textvariable=self._win_var, values=win_names,
                     width=40, state="readonly").pack(fill=tk.X, padx=12, pady=2)

        ttk.Label(self, text=f"动作:", font=(FONT_FAMILY, 10)).pack(anchor=tk.W, padx=12, pady=(6, 2))
        self._action_var = tk.StringVar(value=op.action)
        ttk.Combobox(self, textvariable=self._action_var,
                     values=["click", "dbl_click", "set_text", "toggle", "scroll"],
                     width=40, state="readonly").pack(fill=tk.X, padx=12, pady=2)

        ttk.Label(self, text="参数:", font=(FONT_FAMILY, 10)).pack(anchor=tk.W, padx=12, pady=(6, 2))
        self._value_entry = ttk.Entry(self, width=50)
        self._value_entry.pack(fill=tk.X, padx=12, pady=2)
        self._value_entry.insert(0, op.value)

        ttk.Label(self, text="等待(秒):", font=(FONT_FAMILY, 10)).pack(anchor=tk.W, padx=12, pady=(6, 2))
        self._wait_spin = ttk.Spinbox(self, from_=0.0, to=5.0, increment=0.1, width=10)
        self._wait_spin.set(op.wait_after)
        self._wait_spin.pack(anchor=tk.W, padx=12, pady=2)

        ttk.Label(self, text="描述:", font=(FONT_FAMILY, 10)).pack(anchor=tk.W, padx=12, pady=(6, 2))
        self._desc_entry = ttk.Entry(self, width=50)
        self._desc_entry.pack(fill=tk.X, padx=12, pady=2)
        self._desc_entry.insert(0, op.description)

        ttk.Label(self, text=f"匹配条件: {op.matcher.name} | {op.matcher.automation_id} | {op.matcher.class_name}",
                  foreground=COLOR_MUTED, font=(FONT_FAMILY, 8)).pack(anchor=tk.W, padx=12, pady=(6, 2))

        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill=tk.X, padx=12, pady=12)
        ttk.Button(btn_frame, text="保存", command=self._save).pack(side=tk.RIGHT, padx=2)
        ttk.Button(btn_frame, text="取消", command=self.destroy).pack(side=tk.RIGHT, padx=2)

    def _save(self):
        op = self._operations[self._index]
        # 窗口索引
        win_name = self._win_var.get()
        for i, w in enumerate(self._windows):
            full = w.name or w.title
            if full == win_name:
                op.window_index = i
                break

        op.action = self._action_var.get()
        op.value = self._value_entry.get()
        try:
            op.wait_after = float(self._wait_spin.get())
        except ValueError:
            op.wait_after = 0.5
        op.description = self._desc_entry.get().strip() or op.description

        self._on_save()
        self.destroy()


# ────────────────────────────────────────────────────────
#  入口
# ────────────────────────────────────────────────────────

def main():
    root = tk.Tk()
    app = MainApplication(root)
    root.mainloop()


if __name__ == "__main__":
    main()
