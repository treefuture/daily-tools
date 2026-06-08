#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
============================================
  窗口识别自动化工具 - 核心引擎
  Window Recognition Automation Core
============================================
  底层基于 pywin32 + uiautomation：
    • 窗口枚举与管理
    • 控件树遍历与识别
    • 控件操作（点击、输入、选择等）
    • 脚本序列化保存 / 加载
============================================
"""

import json
import os
import time
from dataclasses import dataclass, field, asdict
from typing import Optional

import uiautomation as uia
import win32gui
import win32process
import win32con
import win32api


# ────────────────────────────────────────────────────────
#  数据类型定义
# ────────────────────────────────────────────────────────

@dataclass
class ControlMatcher:
    """唯一标识一个控件的特征集"""
    name: str = ""
    automation_id: str = ""
    class_name: str = ""
    control_type: str = ""
    # 当同层级有多个同类控件时，用 index 区分 (0-based)
    index: int = 0

    def to_dict(self) -> dict:
        return {k: v for k, v in asdict(self).items() if v != "" and v != 0}

    @classmethod
    def from_control(cls, ctl: uia.Control) -> "ControlMatcher":
        return cls(
            name=ctl.Name or "",
            automation_id=ctl.AutomationId or "",
            class_name=ctl.ClassName or "",
            control_type=ctl.ControlTypeName or "",
            index=0,
        )

    @classmethod
    def from_dict(cls, d: dict) -> "ControlMatcher":
        return cls(
            name=d.get("name", ""),
            automation_id=d.get("automation_id", ""),
            class_name=d.get("class_name", ""),
            control_type=d.get("control_type", ""),
            index=d.get("index", 0),
        )


@dataclass
class Operation:
    """一条自动化操作"""
    action: str = "click"          # click | dbl_click | set_text | toggle | select | scroll
    window_index: int = 0          # 目标窗口在脚本 windows 列表中的索引
    matcher: ControlMatcher = field(default_factory=ControlMatcher)
    value: str = ""                # set_text 时使用
    wait_after: float = 0.5        # 操作后等待时间（秒）
    description: str = ""          # 用户可见的描述

    def to_dict(self) -> dict:
        return {
            "action": self.action,
            "window_index": self.window_index,
            "matcher": self.matcher.to_dict(),
            "value": self.value,
            "wait_after": self.wait_after,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Operation":
        return cls(
            action=d.get("action", "click"),
            window_index=d.get("window_index", 0),
            matcher=ControlMatcher.from_dict(d.get("matcher", {})),
            value=d.get("value", ""),
            wait_after=d.get("wait_after", 0.5),
            description=d.get("description", ""),
        )


@dataclass
class TargetWindow:
    """一个受管理的目标窗口"""
    name: str = ""                  # 用户自定义别名
    hwnd: int = 0
    title: str = ""
    class_name: str = ""
    process_id: int = 0
    process_name: str = ""
    # 窗口定位用的筛选条件
    find_by_title: str = ""
    find_by_class: str = ""

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "hwnd": self.hwnd,
            "title": self.title,
            "class_name": self.class_name,
            "process_id": self.process_id,
            "process_name": self.process_name,
            "find_by_title": self.find_by_title,
            "find_by_class": self.find_by_class,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "TargetWindow":
        return cls(
            name=d.get("name", ""),
            hwnd=d.get("hwnd", 0),
            title=d.get("title", ""),
            class_name=d.get("class_name", ""),
            process_id=d.get("process_id", 0),
            process_name=d.get("process_name", ""),
            find_by_title=d.get("find_by_title", ""),
            find_by_class=d.get("find_by_class", ""),
        )


@dataclass
class AutomationScript:
    """一个完整的自动化脚本"""
    version: str = "1.0"
    name: str = ""
    description: str = ""
    windows: list[TargetWindow] = field(default_factory=list)
    operations: list[Operation] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "name": self.name,
            "description": self.description,
            "windows": [w.to_dict() for w in self.windows],
            "operations": [o.to_dict() for o in self.operations],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "AutomationScript":
        return cls(
            version=d.get("version", "1.0"),
            name=d.get("name", ""),
            description=d.get("description", ""),
            windows=[TargetWindow.from_dict(w) for w in d.get("windows", [])],
            operations=[Operation.from_dict(o) for o in d.get("operations", [])],
        )

    def save(self, path: str):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)

    @classmethod
    def load(cls, path: str) -> "AutomationScript":
        with open(path, "r", encoding="utf-8") as f:
            return cls.from_dict(json.load(f))


# ────────────────────────────────────────────────────────
#  窗口管理
# ────────────────────────────────────────────────────────

def _get_process_name(pid: int) -> str:
    """通过 PID 获取进程名称"""
    try:
        handle = win32api.OpenProcess(win32con.PROCESS_QUERY_INFORMATION | win32con.PROCESS_VM_READ, False, pid)
        name = win32process.GetModuleFileNameEx(handle, None)
        win32api.CloseHandle(handle)
        return os.path.basename(name) if name else ""
    except Exception:
        return ""


def list_all_windows() -> list[dict]:
    """
    枚举所有可见顶层窗口，返回信息列表：
      [{hwnd, title, class_name, process_id, process_name, rect}, ...]
    """
    windows = []

    def callback(hwnd: int, _):
        if not win32gui.IsWindowVisible(hwnd):
            return True
        title = win32gui.GetWindowText(hwnd) or ""
        if not title:
            return True  # 跳过无标题窗口
        class_name = win32gui.GetClassName(hwnd) or ""
        try:
            pid = win32process.GetWindowThreadProcessId(hwnd)[1]
        except Exception:
            pid = 0
        proc_name = _get_process_name(pid)
        rect = win32gui.GetWindowRect(hwnd)

        windows.append({
            "hwnd": hwnd,
            "title": title,
            "class_name": class_name,
            "process_id": pid,
            "process_name": proc_name,
            "rect": rect,
        })
        return True

    win32gui.EnumWindows(callback, None)
    return windows


def find_window_by_title(title_pattern: str) -> Optional[int]:
    """按标题模糊匹配查找窗口，返回第一个匹配的 hwnd"""
    for w in list_all_windows():
        if title_pattern.lower() in w["title"].lower():
            return w["hwnd"]
    return None


def find_window_by_class(class_name: str) -> Optional[int]:
    """按 class name 查找窗口"""
    for w in list_all_windows():
        if w["class_name"] == class_name:
            return w["hwnd"]
    return None


def bring_window_to_foreground(hwnd: int):
    """将窗口带到前台"""
    try:
        if win32gui.IsIconic(hwnd):
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        win32gui.SetForegroundWindow(hwnd)
    except Exception:
        pass


def is_window_still_valid(hwnd: int) -> bool:
    """检查窗口句柄是否仍然有效"""
    return win32gui.IsWindow(hwnd)


# ────────────────────────────────────────────────────────
#  UIA 控件树操作
# ────────────────────────────────────────────────────────

def get_control_from_hwnd(hwnd: int) -> Optional[uia.Control]:
    """通过窗口句柄获取 UIA Control 根对象"""
    try:
        return uia.ControlFromHandle(hwnd)
    except Exception:
        return None


def get_control_info(ctl: uia.Control, depth: int = 0) -> dict:
    """
    提取单个 UIA Control 的信息：
      { name, automation_id, class_name, control_type,
        bounding_rect, is_enabled, is_visible, is_offscreen,
        children_count, depth, index_in_parent }
    """
    try:
        info = {
            "name": ctl.Name or "",
            "automation_id": ctl.AutomationId or "",
            "class_name": ctl.ClassName or "",
            "control_type": ctl.ControlTypeName or "",
            "bounding_rect": ctl.BoundingRectangle,
            "is_enabled": ctl.IsEnabled,
            "is_visible": ctl.IsVisible,
            "is_offscreen": ctl.IsOffscreen,
            "children_count": len(ctl.GetChildren()),
            "depth": depth,
        }
        return info
    except Exception:
        return {}


def walk_control_tree(ctl: uia.Control, depth: int = 0,
                      max_depth: int = 20, parent_index: int = -1) -> list[dict]:
    """
    递归遍历 UIA 控件树，返回扁平的节点列表（便于 TreeView 展示）。
    每个节点：{info, children_count, nodes: []}
    """
    results = []
    _walk(ctl, depth, max_depth, parent_index, results)
    return results


def _walk(ctl: uia.Control, depth: int, max_depth: int,
          parent_index: int, results: list):
    if depth > max_depth:
        return
    info = get_control_info(ctl, depth)
    node_index = len(results)
    info["parent_index"] = parent_index
    info["_node_index"] = node_index
    results.append(info)

    try:
        children = ctl.GetChildren()
        for child in children:
            _walk(child, depth + 1, max_depth, node_index, results)
    except Exception:
        pass


def find_control_in_tree(ctl: uia.Control, matcher: ControlMatcher) -> Optional[uia.Control]:
    """
    根据 ControlMatcher 特征在控件树中查找目标控件。
    匹配优先级：AutomationId > Name + ControlType > ClassName。
    """
    if matcher.automation_id:
        try:
            return ctl.FindControl(
                lambda c: c.AutomationId == matcher.automation_id,
                cache=False
            )
        except Exception:
            pass

    if matcher.name and matcher.control_type:
        try:
            def pred(c):
                try:
                    return (c.Name == matcher.name and
                            c.ControlTypeName == matcher.control_type)
                except Exception:
                    return False
            return ctl.FindControl(pred, cache=False)
        except Exception:
            pass

    if matcher.class_name:
        try:
            return ctl.FindControl(
                lambda c: c.ClassName == matcher.class_name,
                cache=False
            )
        except Exception:
            pass

    return None


def find_control_by_path(ctl: uia.Control, path: list[int]) -> Optional[uia.Control]:
    """按子控件索引路径查找控件（例如 [0, 2, 1]）"""
    current = ctl
    for idx in path:
        try:
            children = current.GetChildren()
            if idx >= len(children):
                return None
            current = children[idx]
        except Exception:
            return None
    return current


# ────────────────────────────────────────────────────────
#  控件操作
# ────────────────────────────────────────────────────────

def click_control(ctl: uia.Control, wait_time: float = 0.3):
    """点击控件"""
    try:
        ctl.Click(waitTime=wait_time)
        return True
    except Exception:
        return False


def dbl_click_control(ctl: uia.Control, wait_time: float = 0.3):
    """双击控件"""
    try:
        ctl.DoubleClick(waitTime=wait_time)
        return True
    except Exception:
        return False


def set_control_text(ctl: uia.Control, text: str, clear_first: bool = True):
    """设置编辑框文本"""
    try:
        if clear_first:
            ctl.GetValuePattern().SetValue("")
        ctl.SendKeys(text, waitTime=0.1)
        return True
    except Exception:
        return False


def toggle_control(ctl: uia.Control):
    """切换复选框/开关状态"""
    try:
        pattern = ctl.GetTogglePattern()
        pattern.Toggle()
        return True
    except Exception:
        return False


def scroll_control(ctl: uia.Control, direction: str = "down", amount: int = 1):
    """滚动控件内容：direction = 'down'|'up'|'left'|'right'"""
    try:
        scroll = ctl.GetScrollPattern()
        if direction == "down":
            for _ in range(amount):
                scroll.ScrollDown()
        elif direction == "up":
            for _ in range(amount):
                scroll.ScrollUp()
        elif direction == "left":
            for _ in range(amount):
                scroll.ScrollLeft()
        elif direction == "right":
            for _ in range(amount):
                scroll.ScrollRight()
        return True
    except Exception:
        return False


def execute_operation(ctl: uia.Control, op: Operation) -> bool:
    """执行单条操作"""
    try:
        if op.action == "click":
            return click_control(ctl, op.wait_after)
        elif op.action == "dbl_click":
            return dbl_click_control(ctl, op.wait_after)
        elif op.action == "set_text":
            return set_control_text(ctl, op.value)
        elif op.action == "toggle":
            return toggle_control(ctl)
        elif op.action == "scroll":
            parts = op.value.split(":")
            direction = parts[0] if parts else "down"
            amount = int(parts[1]) if len(parts) > 1 else 1
            return scroll_control(ctl, direction, amount)
        return False
    except Exception:
        return False


def execute_script(script: AutomationScript,
                   on_step: callable = None,
                   on_error: callable = None) -> bool:
    """
    执行完整的自动化脚本。
    on_step(index, op)  — 每步执行前回调
    on_error(index, op, error) — 出错时回调，返回 True 跳过继续
    """
    for idx, op in enumerate(script.operations):
        try:
            if on_step:
                should_skip = on_step(idx, op)
                if should_skip:
                    continue

            win_config = script.windows[op.window_index]
            hwnd = find_window_by_title(win_config.find_by_title or win_config.title)
            if hwnd is None:
                raise RuntimeError(f"找不到窗口: {win_config.name or win_config.title}")

            root = get_control_from_hwnd(hwnd)
            if root is None:
                raise RuntimeError(f"无法获取窗口控件树: {win_config.name}")

            target = find_control_in_tree(root, op.matcher)
            if target is None:
                raise RuntimeError(f"找不到控件: {op.matcher.to_dict()}")

            bring_window_to_foreground(hwnd)
            time.sleep(0.3)

            success = execute_operation(target, op)
            if not success and op.action != "scroll":
                raise RuntimeError(f"操作失败: {op.action} -> {op.matcher.name}")

            time.sleep(op.wait_after)

        except Exception as e:
            if on_error:
                should_continue = on_error(idx, op, str(e))
                if should_continue:
                    continue
            return False

    return True


# ────────────────────────────────────────────────────────
#  刷新窗口匹配（重新查找 hwnd）
# ────────────────────────────────────────────────────────

def refresh_window_hwnd(window: TargetWindow) -> bool:
    """根据 find_by_title / find_by_class 刷新窗口 handle"""
    hwnd = None
    if window.find_by_title:
        hwnd = find_window_by_title(window.find_by_title)
    if hwnd is None and window.find_by_class:
        hwnd = find_window_by_class(window.find_by_class)
    if hwnd is None:
        hwnd = find_window_by_title(window.title)

    if hwnd:
        window.hwnd = hwnd
        # 更新属性
        try:
            window.title = win32gui.GetWindowText(hwnd) or window.title
            window.class_name = win32gui.GetClassName(hwnd) or window.class_name
            pid = win32process.GetWindowThreadProcessId(hwnd)[1]
            window.process_id = pid
            window.process_name = _get_process_name(pid)
        except Exception:
            pass
        return True
    return False


# ────────────────────────────────────────────────────────
#  uiautomation 快速调优工具
# ────────────────────────────────────────────────────────

def highlight_control(ctl: uia.Control, duration: float = 1.0, color: str = "red"):
    """高亮显示控件（通过绘制边框）"""
    try:
        rect = ctl.BoundingRectangle
        if rect:
            import tkinter as tk
            top = tk.Tk()
            top.overrideredirect(True)
            top.attributes("-topmost", True)
            top.attributes("-transparentcolor", "white")
            top.geometry(f"{rect.right - rect.left}x{rect.bottom - rect.top}+{rect.left}+{rect.top}")
            canvas = tk.Canvas(top, width=rect.right - rect.left, height=rect.bottom - rect.top,
                               highlightthickness=0, bg="white")
            canvas.pack()
            canvas.create_rectangle(0, 0, rect.right - rect.left, rect.bottom - rect.top,
                                    outline=color, width=3)
            top.after(int(duration * 1000), top.destroy)
            top.mainloop()
    except Exception:
        pass
