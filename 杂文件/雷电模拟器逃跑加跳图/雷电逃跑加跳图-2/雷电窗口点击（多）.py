import cv2
import numpy as np
import time
import os
import win32gui
import win32ui
import win32con
import win32api
import sys
import ctypes
import keyboard  # 监听按键

# 全局变量：用于控制程序运行状态
running = True

def on_quit():
    """Q键回调函数"""
    global running
    print("\n🛑 检测到 Q 键，程序已结束")
    running = False

# ==================== 配置区域 ====================
# 窗口配置（已弃用，改为动态查找）
# 不再需要手动填写窗口标题，程序自动枚举所有雷电模拟器窗口

# 子窗口配置（从外到内的层级）
CHILD_WINDOWS = [
    {"class_name": "RenderWindow", "title": "TheRender"},  # 中间层
    {"class_name": "subWin", "title": "sub"},              # 最内层
]

# 找图配置
IMAGE_FOLDER = "jpg1"           # 模板图片文件夹
MATCH_THRESHOLD = 0.75          # 匹配置信度阈值
CLICK_INTERVAL = 0.5            # 点击间隔（秒）
RETRY_INTERVAL = 0.05           # 未找到图片时的重试间隔（秒）
MAX_RETRY = 100                 # 单张图片最大重试次数（找不到则跳过）

# 点击方式配置（如果 PostMessage 不生效，改为 "sendmessage" 或 "physical"）
CLICK_METHOD = "physical"    # 可选: "postmessage", "sendmessage", "physical"

# 参考分辨率（模板图片截取时的窗口分辨率）
# 截图会自动缩放到此分辨率后再匹配，使脚本兼容不同窗口尺寸
REF_WIDTH = 356
REF_HEIGHT = 632
# ==================================================

PW_RENDERFULLCONTENT = 2
user32 = ctypes.windll.user32


def print_window(hwnd, hdc):
    """使用 PrintWindow 进行窗口截图"""
    return user32.PrintWindow(hwnd, hdc, PW_RENDERFULLCONTENT)


def get_child_window(hwnd_parent, target_class, target_title=None):
    """查找指定类名和标题的子窗口"""
    result = []

    def callback(child_hwnd, lparam):
        if win32gui.GetClassName(child_hwnd) == target_class:
            if target_title is None or win32gui.GetWindowText(child_hwnd) == target_title:
                result.append(child_hwnd)

    win32gui.EnumChildWindows(hwnd_parent, callback, None)
    return result[0] if result else None


def get_full_window_chain(outer_hwnd):
    """获取完整的窗口层级链（外层 -> 中间层 -> 内层）"""
    chain = [outer_hwnd]
    current = outer_hwnd

    for child_config in CHILD_WINDOWS:
        child_hwnd = get_child_window(current, child_config["class_name"], child_config["title"])
        if child_hwnd is None:
            print(f"⚠️ 未找到子窗口: {child_config['class_name']} / {child_config.get('title', 'N/A')}")
            return None
        chain.append(child_hwnd)
        current = child_hwnd

    return chain


def find_leidian_windows():
    """动态查找所有雷电模拟器窗口（枚举顶层窗口，按类名 LDPlayerMainFrame 过滤）"""
    windows = []

    def enum_callback(hwnd, results):
        if win32gui.IsWindowVisible(hwnd):
            class_name = win32gui.GetClassName(hwnd)
            title = win32gui.GetWindowText(hwnd)
            if class_name == "LDPlayerMainFrame" and ("雷电" in title or "LDPlayer" in title):
                results.append({"class_name": class_name, "title": title, "hwnd": hwnd})
        return True

    win32gui.EnumWindows(enum_callback, windows)
    return windows


def window_screenshot(hwnd):
    """对指定窗口进行截图，返回 (opencv图像, 屏幕左上角坐标)"""
    left, top, right, bottom = win32gui.GetWindowRect(hwnd)
    width = right - left
    height = bottom - top

    hdc_window = win32gui.GetWindowDC(hwnd)
    hdc_mem = win32ui.CreateDCFromHandle(hdc_window)
    compatibleDC = hdc_mem.CreateCompatibleDC()
    bmp = win32ui.CreateBitmap()
    bmp.CreateCompatibleBitmap(hdc_mem, width, height)
    compatibleDC.SelectObject(bmp)

    result = print_window(hwnd, compatibleDC.GetSafeHdc())
    if result == 0:
        print(f"⚠️ PrintWindow 截图失败 hwnd={hwnd}")

    bmpinfo = bmp.GetInfo()
    bmpstr = bmp.GetBitmapBits(True)
    img = np.frombuffer(bmpstr, dtype=np.uint8).reshape((bmpinfo['bmHeight'], bmpinfo['bmWidth'], 4))

    win32gui.DeleteObject(bmp.GetHandle())
    compatibleDC.DeleteDC()
    hdc_mem.DeleteDC()
    win32gui.ReleaseDC(hwnd, hdc_window)

    return cv2.cvtColor(img, cv2.COLOR_BGRA2BGR), (left, top)


def load_templates(script_dir):
    """按文件名数字顺序加载模板图片（如1.jpg、2.jpg...）"""
    jpg_dir = os.path.join(script_dir, IMAGE_FOLDER)
    if not os.path.exists(jpg_dir):
        print(f"❌ 未找到图片目录: {jpg_dir}")
        return []

    # 按文件名中的数字排序
    jpg_files = sorted(
        [f for f in os.listdir(jpg_dir) if f.lower().endswith((".jpg", ".png", ".bmp"))],
        key=lambda x: int(os.path.splitext(x)[0]) if os.path.splitext(x)[0].isdigit() else 99999
    )

    templates = []
    for f in jpg_files:
        path = os.path.join(jpg_dir, f)
        # 使用 np.fromfile + cv2.imdecode 处理中文路径问题
        try:
            img_data = np.fromfile(path, dtype=np.uint8)
            img = cv2.imdecode(img_data, cv2.IMREAD_COLOR)
            if img is not None:
                templates.append((f, img))
                print(f"✅ 加载模板: {f} ({img.shape[1]}x{img.shape[0]})")
            else:
                print(f"⚠️ 加载失败: {f} (无法解码图片)")
        except Exception as e:
            print(f"⚠️ 加载失败: {f} ({e})")

    if not templates:
        print("❌ 没有可用的模板图片")
    return templates


def find_image(target, template, threshold=MATCH_THRESHOLD):
    """在目标图像中查找模板，返回 (中心点, 左上角, 宽高, 匹配度)"""
    res = cv2.matchTemplate(target, template, cv2.TM_CCOEFF_NORMED)
    min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)

    if max_val >= threshold:
        h, w = template.shape[:2]
        center = (max_loc[0] + w // 2, max_loc[1] + h // 2)
        return center, max_loc, (w, h), max_val
    return None, None, None, max_val


def send_click_to_window(hwnd, x, y):
    """向单个窗口发送鼠标点击事件（使用客户区坐标）"""
    try:
        lParam = win32api.MAKELONG(int(x), int(y))
        # 尝试 PostMessage（异步，不等待响应）
        win32gui.PostMessage(hwnd, win32con.WM_LBUTTONDOWN, win32con.MK_LBUTTON, lParam)
        time.sleep(0.01)  # 短暂延迟
        win32gui.PostMessage(hwnd, win32con.WM_LBUTTONUP, 0, lParam)
        return True
    except Exception as e:
        print(f"⚠️ 窗口 {hwnd} 点击失败: {e}")
        return False


def send_click_to_window_sendmessage(hwnd, x, y):
    """使用 SendMessage 方式点击（备用方案）"""
    try:
        lParam = win32api.MAKELONG(int(x), int(y))
        win32api.SendMessage(hwnd, win32con.WM_LBUTTONDOWN, win32con.MK_LBUTTON, lParam)
        win32api.SendMessage(hwnd, win32con.WM_LBUTTONUP, 0, lParam)
        return True
    except Exception as e:
        print(f"⚠️ 窗口 {hwnd} SendMessage 点击失败: {e}")
        return False


def send_click_to_all(window_list, coords_list, screen_coords_list=None):
    """向多个窗口发送点击，每个窗口对应自己的坐标
    Args:
        window_list: 窗口句柄列表
        coords_list: 客户区坐标列表
        screen_coords_list: 屏幕绝对坐标列表 (用于 physical 模式，每个窗口对应一个坐标)
    """
    if CLICK_METHOD == "physical" and screen_coords_list:
        # 物理鼠标点击：依次激活每个窗口并点击
        import pyautogui
        for i, (hwnd, screen_coords) in enumerate(zip(window_list, screen_coords_list)):
            x, y = screen_coords
            print(f"  🖱️ 窗口{i+1} - 激活窗口并移动鼠标到: ({x}, {y})")
            # 激活窗口（使用更可靠的方法）
            try:
                # 方法1：尝试使用 AttachThreadInput 技巧
                foreground_hwnd = win32gui.GetForegroundWindow()
                if foreground_hwnd != hwnd:
                    # 获取线程ID
                    current_thread = win32api.GetCurrentThreadId()
                    foreground_thread = win32gui.GetWindowThreadProcessId(foreground_hwnd, None)
                    target_thread = win32gui.GetWindowThreadProcessId(hwnd, None)
                    
                    # 附加线程输入
                    if foreground_thread != current_thread:
                        ctypes.windll.user32.AttachThreadInput(foreground_thread, current_thread, True)
                    
                    if target_thread != current_thread:
                        ctypes.windll.user32.AttachThreadInput(target_thread, current_thread, True)
                    
                    # 设置前台窗口
                    win32gui.SetForegroundWindow(hwnd)
                    
                    # 分离线程输入
                    if foreground_thread != current_thread:
                        ctypes.windll.user32.AttachThreadInput(foreground_thread, current_thread, False)
                    
                    if target_thread != current_thread:
                        ctypes.windll.user32.AttachThreadInput(target_thread, current_thread, False)
                
                time.sleep(0.15)
            except Exception as e:
                print(f"  ⚠️ 窗口{i+1} 激活失败: {e}")
                # 备用方法：最小化其他窗口
                try:
                    win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                    win32gui.BringWindowToTop(hwnd)
                    time.sleep(0.15)
                except Exception as e2:
                    print(f"  ⚠️ 窗口{i+1} 备用激活也失败: {e2}")
                    # 即使激活失败，也尝试点击（可能窗口已经在前面）
            
            # 移动并点击
            pyautogui.moveTo(x, y, duration=0.1)
            pyautogui.click()
            print(f"  🖱️ 窗口{i+1} - 点击完成")
            time.sleep(0.2)  # 窗口切换延迟
    else:
        for hwnd, (x, y) in zip(window_list, coords_list):
            if CLICK_METHOD == "sendmessage":
                send_click_to_window_sendmessage(hwnd, x, y)
            else:
                send_click_to_window(hwnd, x, y)


def calculate_coords(screen_x, screen_y, window_handles):
    """将屏幕坐标转换为各窗口的客户区坐标"""
    coords = []
    for hwnd in window_handles:
        try:
            client_x, client_y = win32gui.ScreenToClient(hwnd, (screen_x, screen_y))
            coords.append((client_x, client_y))
        except Exception as e:
            print(f"⚠️ 坐标转换失败 hwnd={hwnd}: {e}")
            coords.append((screen_x, screen_y))
    return coords


def calculate_screen_coords_for_all_windows(relative_x, relative_y, window_chains):
    """为所有窗口计算屏幕绝对坐标
    Args:
        relative_x, relative_y: 相对于主窗口的相对坐标
        window_chains: 所有窗口链列表
    Returns:
        每个窗口对应的屏幕绝对坐标列表
    """
    screen_coords_list = []
    # 获取主窗口的偏移
    primary_chain = window_chains[0]
    primary_left, primary_top, _, _ = win32gui.GetWindowRect(primary_chain[0])
    
    for chain in window_chains:
        # 获取每个窗口的左上角坐标
        left, top, _, _ = win32gui.GetWindowRect(chain[0])
        # 计算该窗口的屏幕绝对坐标
        abs_x = left + relative_x
        abs_y = top + relative_y
        screen_coords_list.append((abs_x, abs_y))
    
    return screen_coords_list


def main():
    print("=" * 50)
    print("雷电模拟器多窗口循环找图点击脚本")
    print("按 Q 键结束程序")
    print("=" * 50)

    # 1. 动态查找所有雷电模拟器窗口
    all_windows = []
    found_windows = find_leidian_windows()
    if not found_windows:
        print("❌ 未找到任何雷电模拟器窗口")
        return

    print(f"🔍 找到 {len(found_windows)} 个雷电模拟器窗口:")
    for win in found_windows:
        print(f"   - {win['title']} (句柄: {hex(win['hwnd'])})")

    for win in found_windows:
        # 获取完整窗口链
        window_chain = get_full_window_chain(win['hwnd'])
        if window_chain:
            all_windows.append(window_chain)
            print(f"✅ 窗口链完整: {win['title']} -> {[hex(h) for h in window_chain]}")
        else:
            print(f"⚠️ 窗口链不完整（已跳过）: {win['title']}")

    if not all_windows:
        print("❌ 没有找到任何可用窗口，程序退出")
        return

    # 使用第一个窗口链进行截图识别（其他窗口同步点击）
    primary_chain = all_windows[0]
    # 所有窗口的最内层句柄（用于接收点击）
    inner_windows = [chain[-1] for chain in all_windows]

    print(f"\n📺 主识别窗口: {hex(primary_chain[-1])}")
    print(f"🖱️  点击目标窗口: {[hex(h) for h in inner_windows]}")

    # 检查所有窗口的宽高比是否与参考分辨率一致
    ref_ratio = REF_WIDTH / REF_HEIGHT
    for i, chain in enumerate(all_windows):
        left, top, right, bottom = win32gui.GetWindowRect(chain[0])
        w, h = right - left, bottom - top
        ratio = w / h
        if abs(ratio - ref_ratio) > 0.02:
            print(f"⚠️ 窗口{i+1} ({w}x{h}) 宽高比 ({ratio:.3f}) 与参考 {REF_WIDTH}x{REF_HEIGHT} ({ref_ratio:.3f}) 不一致")
            print(f"   请将模拟器窗口设为 {REF_WIDTH}x{REF_HEIGHT} 以保证找图准确")

    # 2. 加载模板图片
    script_dir = os.path.abspath(os.path.dirname(sys.argv[0]))
    templates = load_templates(script_dir)
    if not templates:
        print("❌ 没有模板图片，程序退出")
        return

    total_templates = len(templates)
    print(f"\n📋 共加载 {total_templates} 张模板图片")
    print(f"⚙️  配置: 阈值={MATCH_THRESHOLD}, 点击间隔={CLICK_INTERVAL}s, 重试间隔={RETRY_INTERVAL}s")
    print("\n开始循环找图点击... 按 Q 键结束\n")

    # 注册全局热键 Q
    keyboard.add_hotkey('q', on_quit)
    print("📌 已注册全局热键 Q，随时按 Q 结束程序")

    # 获取模板字典（按文件名访问）
    template_dict = {name: img for name, img in templates}
    
    # 检查必要的模板是否存在
    has_img1 = "1.jpg" in template_dict
    has_img2 = "2.jpg" in template_dict
    has_img3 = "3.jpg" in template_dict
    
    if not has_img3:
        print("❌ 未找到 3.jpg，无法执行新逻辑")
        return
    
    print("\n📋 执行逻辑: 找3.jpg → 点击1.jpg一次 → 循环点击2.jpg直到3.jpg消失")
    
    # 注册全局热键 Q
    keyboard.add_hotkey('q', on_quit)
    print("📌 已注册全局热键 Q，随时按 Q 结束程序")
    
    # 3. 主循环 - 新逻辑
    round_count = 0
    img1_clicked = False  # 标记是否已点击过1.jpg
    img2_click_count = 0  # 记录2.jpg点击次数
    _scaling_notified = False

    while running:
        # 截图
        img, (screen_left, screen_top) = window_screenshot(primary_chain[0])

        # 获取窗口实际尺寸，计算缩放比例，将截图缩放到参考分辨率后匹配
        ref_w, ref_h = REF_WIDTH, REF_HEIGHT
        left, top, right, bottom = win32gui.GetWindowRect(primary_chain[0])
        actual_w, actual_h = right - left, bottom - top
        if actual_w != ref_w or actual_h != ref_h:
            scale_x = actual_w / ref_w
            scale_y = actual_h / ref_h
            img = cv2.resize(img, (ref_w, ref_h))
            if not _scaling_notified:
                print(f"📐 窗口 {actual_w}x{actual_h}，自动缩放至 {ref_w}x{ref_h} 匹配")
                _scaling_notified = True
        else:
            scale_x = scale_y = 1.0

        # 先检查 3.jpg 是否存在
        pt3, _, _, score3 = find_image(img, template_dict["3.jpg"]) if has_img3 else (None, None, None, 0)

        if pt3 is not None:
            # 3.jpg 存在
            abs_x3 = screen_left + int(pt3[0] * scale_x)
            abs_y3 = screen_top + int(pt3[1] * scale_y)
            coords3 = calculate_coords(abs_x3, abs_y3, inner_windows)
            print(f"🎯 找到 3.jpg | 匹配度: {score3:.2f} | 坐标: {coords3}")

            if not img1_clicked and has_img1:
                # 第一次找到3.jpg，点击1.jpg
                print("   首次找到3.jpg，点击1.jpg...")
                pt1, _, _, score1 = find_image(img, template_dict["1.jpg"])
                if pt1 is not None:
                    abs_x1 = screen_left + int(pt1[0] * scale_x)
                    abs_y1 = screen_top + int(pt1[1] * scale_y)
                    coords1 = calculate_coords(abs_x1, abs_y1, inner_windows)
                    print(f"  ✅ 找到 1.jpg | 匹配度: {score1:.2f} | 坐标: {coords1}")
                    # 为所有窗口计算屏幕坐标（将参考坐标映射回实际尺寸）
                    rel_x = int(pt1[0] * scale_x)
                    rel_y = int(pt1[1] * scale_y)
                    screen_coords_list = calculate_screen_coords_for_all_windows(rel_x, rel_y, all_windows)
                    send_click_to_all(inner_windows, coords1, screen_coords_list=screen_coords_list)
                    img1_clicked = True
                    print("  ✅ 已点击1.jpg，开始循环点击2.jpg")
                else:
                    print("  ⚠️ 未找到1.jpg，等待下次重试...")
            elif img1_clicked and has_img2:
                # 已点击过1.jpg，循环点击2.jpg
                pt2, _, _, score2 = find_image(img, template_dict["2.jpg"])
                if pt2 is not None:
                    abs_x2 = screen_left + int(pt2[0] * scale_x)
                    abs_y2 = screen_top + int(pt2[1] * scale_y)
                    coords2 = calculate_coords(abs_x2, abs_y2, inner_windows)
                    img2_click_count += 1
                    print(f"  ✅ 找到 2.jpg | 匹配度: {score2:.2f} | 坐标: {coords2} | 点击次数: {img2_click_count}")
                    # 为所有窗口计算屏幕坐标（将参考坐标映射回实际尺寸）
                    rel_x = int(pt2[0] * scale_x)
                    rel_y = int(pt2[1] * scale_y)
                    screen_coords_list = calculate_screen_coords_for_all_windows(rel_x, rel_y, all_windows)
                    send_click_to_all(inner_windows, coords2, screen_coords_list=screen_coords_list)
                else:
                    # 未找到2.jpg，尝试找1.jpg
                    print("  ⚠️ 未找到2.jpg，尝试找1.jpg...")
                    if has_img1:
                        pt1, _, _, score1 = find_image(img, template_dict["1.jpg"])
                        if pt1 is not None:
                            abs_x1 = screen_left + int(pt1[0] * scale_x)
                            abs_y1 = screen_top + int(pt1[1] * scale_y)
                            coords1 = calculate_coords(abs_x1, abs_y1, inner_windows)
                            print(f"  ✅ 找到 1.jpg | 匹配度: {score1:.2f} | 坐标: {coords1}")
                            # 为所有窗口计算屏幕坐标（将参考坐标映射回实际尺寸）
                            rel_x = int(pt1[0] * scale_x)
                            rel_y = int(pt1[1] * scale_y)
                            screen_coords_list = calculate_screen_coords_for_all_windows(rel_x, rel_y, all_windows)
                            send_click_to_all(inner_windows, coords1, screen_coords_list=screen_coords_list)
                            print("  ✅ 已点击1.jpg")
                        else:
                            print("  ⚠️ 也未找到1.jpg，等待下次重试...")
                    else:
                        print("  ⚠️ 未加载1.jpg，无法点击")

            time.sleep(CLICK_INTERVAL)
        else:
            # 3.jpg 不存在
            if img1_clicked:
                # 之前点击过1.jpg，现在3.jpg消失了，一轮完成
                round_count += 1
                print(f"\n🔄 3.jpg已消失，完成第 {round_count} 轮循环")
                print(f"  📊 2.jpg共点击 {img2_click_count} 次")
                # 重置状态，等待下一轮
                img1_clicked = False
                img2_click_count = 0
            else:
                print(" 等待3.jpg出现...")

            time.sleep(RETRY_INTERVAL)

    # 清理热键
    keyboard.remove_hotkey('q')
    print(f"\n📊 最终统计: 完成 {round_count} 轮循环")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n🛑 用户中断，程序结束")
    except Exception as e:
        print(f"\n❌ 发生错误: {e}")
        import traceback
        traceback.print_exc()
