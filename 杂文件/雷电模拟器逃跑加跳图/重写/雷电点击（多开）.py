"""
雷电模拟器多窗口找图点击程序 v3
功能：同时控制多个雷电模拟器窗口，使用 pyautogui 移动鼠标点击
使用线程锁确保同一时间只有一个窗口操作鼠标
"""

import pyautogui
import cv2
import numpy as np
import time
import logging
import threading
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional
import win32gui
import win32con
import win32api

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('find_click_multi_v3.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# 全局鼠标锁，确保同一时间只有一个窗口操作鼠标
mouse_lock = threading.Lock()


def find_leidian_windows() -> List[Dict]:
    """查找所有雷电模拟器窗口"""
    windows = []
    
    def enum_callback(hwnd, results):
        if win32gui.IsWindowVisible(hwnd):
            title = win32gui.GetWindowText(hwnd)
            if title and any(keyword in title for keyword in ['雷电', 'LDPlayer', 'Player']):
                rect = win32gui.GetWindowRect(hwnd)
                results.append({
                    'hwnd': hwnd,
                    'title': title,
                    'left': rect[0],
                    'top': rect[1],
                    'right': rect[2],
                    'bottom': rect[3],
                    'width': rect[2] - rect[0],
                    'height': rect[3] - rect[1]
                })
        return True
    
    win32gui.EnumWindows(enum_callback, windows)
    return windows


class WindowImageFinder:
    """窗口专用的找图点击类"""
    
    def __init__(self, hwnd: int, window_info: Dict, template_path: str, 
                 confidence: float = 0.8):
        self.hwnd = hwnd
        self.window_info = window_info
        self.template_path = template_path
        self.confidence = confidence
        self.template = None
        self.load_template()
    
    def load_template(self):
        """加载模板图片"""
        abs_path = str(Path(self.template_path).resolve())
        self.template = cv2.imdecode(np.fromfile(abs_path, dtype=np.uint8), cv2.IMREAD_COLOR)
        if self.template is None:
            raise FileNotFoundError(f"无法加载模板图片：{self.template_path}")
        logger.debug(f"[{self.window_info['title']}] 加载模板：{self.template.shape}")
    
    def capture_window(self) -> Optional[np.ndarray]:
        """截取窗口内容"""
        try:
            left, top = self.window_info['left'], self.window_info['top']
            width, height = self.window_info['width'], self.window_info['height']
            screenshot = pyautogui.screenshot(region=(left, top, width, height))
            screenshot_np = np.array(screenshot)
            return cv2.cvtColor(screenshot_np, cv2.COLOR_RGB2BGR)
        except Exception as e:
            logger.error(f"[{self.window_info['title']}] 截图失败：{e}")
            return None
    
    def find_image(self) -> Optional[tuple]:
        """在窗口中查找模板图片，返回窗口相对坐标"""
        screenshot = self.capture_window()
        if screenshot is None or self.template is None:
            return None
        
        result = cv2.matchTemplate(screenshot, self.template, cv2.TM_CCOEFF_NORMED)
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)
        
        if max_val >= self.confidence:
            template_height, template_width = self.template.shape[:2]
            # 返回窗口相对坐标
            rel_x = max_loc[0] + template_width // 2
            rel_y = max_loc[1] + template_height // 2
            # 计算屏幕绝对坐标
            abs_x = self.window_info['left'] + rel_x
            abs_y = self.window_info['top'] + rel_y
            logger.debug(f"[{self.window_info['title']}] 找到：相对坐标=({rel_x}, {rel_y}), 屏幕坐标=({abs_x}, {abs_y})")
            return (rel_x, rel_y, abs_x, abs_y)
        else:
            logger.debug(f"[{self.window_info['title']}] 未找到，置信度={max_val:.4f}")
            return None
    
    def click_at(self, abs_x: int, abs_y: int, window_title: str) -> bool:
        """
        移动鼠标到指定位置并点击
        需要持有 mouse_lock 才能调用此方法
        """
        try:
            # 先激活窗口
            win32gui.ShowWindow(self.hwnd, win32con.SW_RESTORE)
            win32gui.SetForegroundWindow(self.hwnd)
            time.sleep(0.1)
            
            # 移动鼠标并点击
            pyautogui.moveTo(abs_x, abs_y, duration=0.1)
            pyautogui.click()
            
            logger.info(f"[{window_title}] 点击位置：屏幕坐标 ({abs_x}, {abs_y})")
            return True
        except Exception as e:
            logger.error(f"[{window_title}] 点击失败：{e}")
            return False
    
    def find_and_click(self) -> bool:
        """找图并点击（需要持有 mouse_lock）"""
        position = self.find_image()
        if position:
            rel_x, rel_y, abs_x, abs_y = position
            return self.click_at(abs_x, abs_y, self.window_info['title'])
        return False


def auto_skip_round(window_id: int, round_finder: WindowImageFinder, 
                    skip_finder: WindowImageFinder, stop_event: threading.Event,
                    max_clicks_per_round: int = 50, click_interval: float = 0.3) -> bool:
    """
    自动跳过回合逻辑
    """
    title = round_finder.window_info['title']
    logger.info(f"[窗口{window_id}] [{title}] 检测'回合'...")
    
    if not round_finder.find_image():
        return False
    
    logger.info(f"[窗口{window_id}] [{title}] 发现'回合'，开始点击'跳过'...")
    click_count = 0
    
    while click_count < max_clicks_per_round and not stop_event.is_set():
        # 检查"回合"是否还存在
        if not round_finder.find_image():
            logger.info(f"[窗口{window_id}] [{title}] '回合'消失，点击'跳过' {click_count} 次")
            return True
        
        # 获取鼠标锁并点击"跳过"
        with mouse_lock:
            if skip_finder.find_and_click():
                click_count += 1
            else:
                logger.warning(f"[窗口{window_id}] [{title}] 未找到'跳过'")
        
        time.sleep(click_interval)
    
    logger.warning(f"[窗口{window_id}] [{title}] 达到最大点击次数 {max_clicks_per_round}")
    return True


def window_worker(window_id: int, window_info: Dict, stop_event: threading.Event,
                  round_path: str, skip_path: str, confidence: float = 0.8,
                  loop_interval: float = 2, max_loops: int = -1):
    """窗口工作线程"""
    logger.info(f"[窗口{window_id}] {window_info['title']} 线程启动")
    
    try:
        round_finder = WindowImageFinder(window_info['hwnd'], window_info, round_path, confidence)
        skip_finder = WindowImageFinder(window_info['hwnd'], window_info, skip_path, confidence)
        logger.info(f"[窗口{window_id}] {window_info['title']} 初始化成功")
    except Exception as e:
        logger.error(f"[窗口{window_id}] 初始化失败：{e}")
        return
    
    loop_count = 0
    round_count = 0
    
    while not stop_event.is_set() and (max_loops == -1 or loop_count < max_loops):
        loop_count += 1
        logger.info(f"[窗口{window_id}] [{window_info['title']}] >>> 第 {loop_count} 次循环 <<<")
        
        # 检测并自动跳过回合
        if auto_skip_round(window_id, round_finder, skip_finder, stop_event, 
                          max_clicks_per_round=50, click_interval=0.3):
            round_count += 1
        
        if max_loops == -1 or loop_count < max_loops:
            time.sleep(loop_interval)
    
    logger.info(f"[窗口{window_id}] [{window_info['title']}] 结束，循环：{loop_count}, 轮数：{round_count}")


def main():
    """主函数"""
    logger.info("=" * 60)
    logger.info("雷电模拟器多窗口找图点击程序 v3（鼠标移动版）")
    logger.info(f"启动时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # 配置
    ROUND_IMAGE_PATH = "png1/回合.png"
    SKIP_IMAGE_PATH = "png1/跳过.png"
    CONFIDENCE = 0.8
    LOOP_INTERVAL = 2
    MAX_LOOPS = -1
    
    # 设置 pyautogui 安全设置
    pyautogui.FAILSAFE = False  # 禁用故障保护（移动到角落不会停止）
    pyautogui.PAUSE = 0.1  # 设置操作间默认延迟
    
    # 查找窗口
    print("\n正在查找雷电模拟器窗口...")
    windows = find_leidian_windows()
    
    if not windows:
        logger.error("未找到雷电模拟器窗口")
        print("未找到雷电模拟器窗口，请确保已打开")
        return
    
    logger.info(f"找到 {len(windows)} 个窗口:")
    for i, win in enumerate(windows):
        logger.info(f"  窗口{i+1}: {win['title']} (句柄：{win['hwnd']}, 大小：{win['width']}x{win['height']})")
    
    print(f"\n找到 {len(windows)} 个窗口:")
    for i, win in enumerate(windows):
        print(f"  窗口{i+1}: {win['title']}")
    
    # 创建并启动线程
    stop_event = threading.Event()
    threads = []
    
    for i, window_info in enumerate(windows):
        t = threading.Thread(
            target=window_worker,
            args=(i + 1, window_info, stop_event, 
                  ROUND_IMAGE_PATH, SKIP_IMAGE_PATH,
                  CONFIDENCE, LOOP_INTERVAL, MAX_LOOPS),
            daemon=True
        )
        threads.append(t)
    
    print("\n启动工作线程...")
    for t in threads:
        t.start()
    
    print("=" * 60)
    print("所有窗口已开始工作（使用鼠标移动点击，线程锁确保互斥）")
    print("按 Ctrl+C 停止所有窗口")
    print("=" * 60)
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("\n用户请求停止")
        print("\n正在停止...")
        stop_event.set()
        for t in threads:
            t.join(timeout=2)
        logger.info("所有窗口已停止")
        print("已停止")


if __name__ == "__main__":
    main()
