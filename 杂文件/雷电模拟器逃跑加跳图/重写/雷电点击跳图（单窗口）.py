"""
雷电模拟器找图点击程序
功能：在屏幕上查找指定图片并自动点击，同时输出日志
"""

import pyautogui
import cv2
import numpy as np
import time
import logging
from datetime import datetime
from pathlib import Path

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('find_click.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class ImageFinder:
    """找图点击类"""
    
    def __init__(self, template_path: str, confidence: float = 0.8, click_delay: float = 0.5):
        """
        初始化找图点击器
        
        Args:
            template_path: 模板图片路径
            confidence: 匹配置信度阈值 (0-1)，默认 0.8
            click_delay: 点击间隔延迟 (秒)，默认 0.5
        """
        self.template_path = template_path
        self.confidence = confidence
        self.click_delay = click_delay
        self.template = None
        self.load_template()
    
    def load_template(self):
        """加载模板图片"""
        try:
            # 使用绝对路径处理中文文件名
            abs_path = str(Path(self.template_path).resolve())
            self.template = cv2.imdecode(np.fromfile(abs_path, dtype=np.uint8), cv2.IMREAD_COLOR)
            if self.template is None:
                logger.error(f"无法加载模板图片：{self.template_path}")
                raise FileNotFoundError(f"无法加载模板图片：{self.template_path}")
            logger.info(f"成功加载模板图片：{self.template_path}, 尺寸：{self.template.shape}")
        except Exception as e:
            logger.error(f"加载模板图片失败：{e}")
            raise
    
    def find_image(self, screenshot=None):
        """
        在屏幕上查找模板图片
        
        Args:
            screenshot: 可选的截图，如果不提供则自动截取
            
        Returns:
            tuple: (找到位置的中心点 x, y) 或 None
        """
        try:
            # 截取屏幕
            if screenshot is None:
                screenshot = pyautogui.screenshot()
            
            # 转换为 numpy 数组
            screenshot_np = np.array(screenshot)
            screenshot_cv = cv2.cvtColor(screenshot_np, cv2.COLOR_RGB2BGR)
            
            # 模板匹配
            result = cv2.matchTemplate(screenshot_cv, self.template, cv2.TM_CCOEFF_NORMED)
            min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)
            
            logger.debug(f"匹配结果 - 最大值：{max_val:.4f}, 位置：{max_loc}")
            
            # 检查是否找到匹配
            if max_val >= self.confidence:
                # 计算中心点
                template_height, template_width = self.template.shape[:2]
                center_x = max_loc[0] + template_width // 2
                center_y = max_loc[1] + template_height // 2
                
                logger.info(f"找到匹配图片！置信度：{max_val:.4f}, 位置：({center_x}, {center_y})")
                return (center_x, center_y)
            else:
                logger.info(f"未找到匹配图片，最高置信度：{max_val:.4f} (阈值：{self.confidence})")
                return None
                
        except Exception as e:
            logger.error(f"找图过程出错：{e}")
            return None
    
    def click_at(self, x: int, y: int):
        """
        点击指定位置
        
        Args:
            x: X 坐标
            y: Y 坐标
        """
        try:
            pyautogui.click(x, y)
            logger.info(f"已点击位置：({x}, {y})")
            time.sleep(self.click_delay)  # 点击后延迟
        except Exception as e:
            logger.error(f"点击失败：{e}")
    
    def find_and_click(self) -> bool:
        """
        找图并点击
        
        Returns:
            bool: 是否成功找到并点击
        """
        logger.info("=" * 50)
        logger.info("开始找图...")
        
        position = self.find_image()
        
        if position:
            self.click_at(position[0], position[1])
            logger.info("找图点击完成！")
            return True
        else:
            logger.info("未找到目标图片，未执行点击")
            return False
    
    def find_all_images(self, screenshot=None):
        """
        查找屏幕上所有匹配的图片位置
        
        Args:
            screenshot: 可选的截图
            
        Returns:
            list: 所有匹配位置的中心点列表 [(x1,y1), (x2,y2), ...]
        """
        try:
            if screenshot is None:
                screenshot = pyautogui.screenshot()
            
            screenshot_np = np.array(screenshot)
            screenshot_cv = cv2.cvtColor(screenshot_np, cv2.COLOR_RGB2BGR)
            
            result = cv2.matchTemplate(screenshot_cv, self.template, cv2.TM_CCOEFF_NORMED)
            locations = np.where(result >= self.confidence)
            
            positions = []
            template_height, template_width = self.template.shape[:2]
            
            # 去重处理
            used_positions = set()
            for pt in zip(*locations[::-1]):
                center_x = pt[0] + template_width // 2
                center_y = pt[1] + template_height // 2
                
                # 简单的去重：检查是否已有接近的位置
                is_duplicate = False
                for existing in used_positions:
                    if abs(existing[0] - center_x) < template_width // 2 and \
                       abs(existing[1] - center_y) < template_height // 2:
                        is_duplicate = True
                        break
                
                if not is_duplicate:
                    positions.append((center_x, center_y))
                    used_positions.add((center_x, center_y))
            
            logger.info(f"找到 {len(positions)} 个匹配位置")
            for i, pos in enumerate(positions):
                logger.info(f"  位置 {i+1}: {pos}")
            
            return positions
            
        except Exception as e:
            logger.error(f"查找所有图片失败：{e}")
            return []
    
    def find_all_and_click(self, click_all: bool = True, max_clicks: int = 10) -> int:
        """
        查找所有匹配图片并点击
        
        Args:
            click_all: 是否点击所有找到的位置
            max_clicks: 最大点击次数
            
        Returns:
            int: 实际点击次数
        """
        logger.info("=" * 50)
        logger.info("开始查找所有匹配图片...")
        
        positions = self.find_all_images()
        
        if not positions:
            logger.info("未找到任何匹配图片")
            return 0
        
        click_count = 0
        for i, pos in enumerate(positions):
            if click_count >= max_clicks:
                logger.info(f"已达到最大点击次数：{max_clicks}")
                break
            
            if click_all:
                self.click_at(pos[0], pos[1])
                click_count += 1
            else:
                logger.info(f"找到位置 {i+1}: {pos} (未点击)")
        
        logger.info(f"总共点击 {click_count} 次")
        return click_count


def auto_skip_round(round_finder: ImageFinder, skip_finder: ImageFinder, 
                    max_clicks_per_round: int = 50, click_interval: float = 0.3) -> bool:
    """
    自动跳过回合逻辑：当找到"回合"图片时，一直点击"跳过"直到"回合"消失
    
    Args:
        round_finder: "回合"图片找图器
        skip_finder: "跳过"图片找图器
        max_clicks_per_round: 每轮最大点击次数
        click_interval: 点击间隔 (秒)
        
    Returns:
        bool: 是否完成了一轮
    """
    logger.info("检测'回合'图片...")
    
    # 检查是否有"回合"图片
    if not round_finder.find_image():
        logger.debug("未找到'回合'图片")
        return False
    
    logger.info("发现'回合'图片，开始自动点击'跳过'...")
    click_count = 0
    
    while click_count < max_clicks_per_round:
        # 检查"回合"是否还存在
        if not round_finder.find_image():
            logger.info(f"'回合'已消失，本轮完成！共点击'跳过' {click_count} 次")
            return True
        
        # 点击"跳过"
        if skip_finder.find_and_click():
            click_count += 1
        else:
            logger.warning("未找到'跳过'图片，尝试继续查找...")
            time.sleep(click_interval)
            continue
        
        time.sleep(click_interval)
    
    logger.warning(f"达到最大点击次数 {max_clicks_per_round}，'回合'仍未消失")
    return True


def main():
    """主函数"""
    logger.info("=" * 50)
    logger.info("雷电模拟器找图点击程序启动")
    logger.info(f"当前时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # 配置
    TEMPLATE_PATH = "png1/1.png"  # 模板图片路径（可选）
    ROUND_IMAGE_PATH = "png1/回合.png"  # "回合"图片路径
    SKIP_IMAGE_PATH = "png1/跳过.png"  # "跳过"图片路径
    CONFIDENCE = 0.8  # 匹配置信度
    CLICK_DELAY = 0.5  # 点击延迟 (秒)
    LOOP_INTERVAL = 2  # 循环间隔 (秒)
    MAX_LOOPS = 10  # 最大循环次数，设为 -1 表示无限循环
    MAX_CLICKS_PER_ROUND = 50  # 每轮最大点击次数
    SKIP_CLICK_INTERVAL = 0.3  # 点击"跳过"的间隔 (秒)
    
    # 创建找图器
    try:
        # 创建主找图器（可选）
        finder = None
        if Path(TEMPLATE_PATH).exists():
            finder = ImageFinder(
                template_path=TEMPLATE_PATH,
                confidence=CONFIDENCE,
                click_delay=CLICK_DELAY
            )
            logger.info(f"已加载主模板图片：{TEMPLATE_PATH}")
        else:
            logger.warning(f"主模板图片不存在：{TEMPLATE_PATH}，将跳过主找图逻辑")
        
        # 创建"回合"找图器
        round_finder = None
        if Path(ROUND_IMAGE_PATH).exists():
            round_finder = ImageFinder(
                template_path=ROUND_IMAGE_PATH,
                confidence=CONFIDENCE,
                click_delay=SKIP_CLICK_INTERVAL
            )
            logger.info(f"已加载'回合'模板图片：{ROUND_IMAGE_PATH}")
        else:
            logger.warning(f"'回合'图片不存在：{ROUND_IMAGE_PATH}")
        
        # 创建"跳过"找图器
        skip_finder = None
        if Path(SKIP_IMAGE_PATH).exists():
            skip_finder = ImageFinder(
                template_path=SKIP_IMAGE_PATH,
                confidence=CONFIDENCE,
                click_delay=SKIP_CLICK_INTERVAL
            )
            logger.info(f"已加载'跳过'模板图片：{SKIP_IMAGE_PATH}")
        else:
            logger.warning(f"'跳过'图片不存在：{SKIP_IMAGE_PATH}")
            
    except Exception as e:
        logger.error(f"初始化失败：{e}")
        return
    
    # 提示用户
    print("\n" + "=" * 50)
    print("雷电模拟器找图点击程序")
    print("=" * 50)
    print(f"模板图片：{TEMPLATE_PATH}")
    print(f"'回合'图片：{ROUND_IMAGE_PATH if round_finder else '未找到'}")
    print(f"'跳过'图片：{SKIP_IMAGE_PATH if skip_finder else '未找到'}")
    print(f"置信度阈值：{CONFIDENCE}")
    print(f"点击延迟：{CLICK_DELAY}秒")
    print(f"循环间隔：{LOOP_INTERVAL}秒")
    print(f"最大循环次数：{'无限' if MAX_LOOPS == -1 else MAX_LOOPS}")
    print(f"每轮最大点击次数：{MAX_CLICKS_PER_ROUND}")
    print("=" * 50)
    print("\n按 Ctrl+C 停止程序\n")
    
    # 执行循环
    loop_count = 0
    success_count = 0
    round_count = 0
    
    try:
        while MAX_LOOPS == -1 or loop_count < MAX_LOOPS:
            loop_count += 1
            logger.info(f"\n>>> 第 {loop_count} 次循环 <<<")
            
            # 先执行原有的找图点击逻辑
            if finder and finder.find_and_click():
                success_count += 1
            
            # 检查是否需要自动跳过回合
            if round_finder and skip_finder:
                if auto_skip_round(
                    round_finder=round_finder,
                    skip_finder=skip_finder,
                    max_clicks_per_round=MAX_CLICKS_PER_ROUND,
                    click_interval=SKIP_CLICK_INTERVAL
                ):
                    round_count += 1
                    logger.info(f"已完成第 {round_count} 轮")
            
            # 如果不是最后一次循环，则等待
            if MAX_LOOPS == -1 or loop_count < MAX_LOOPS:
                time.sleep(LOOP_INTERVAL)
    
    except KeyboardInterrupt:
        logger.info("\n用户中断程序")
    
    # 输出统计
    logger.info("=" * 50)
    logger.info("程序结束")
    logger.info(f"总循环次数：{loop_count}")
    logger.info(f"成功点击次数：{success_count}")
    logger.info(f"完成轮数：{round_count}")
    logger.info(f"结束时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"\n程序结束，成功点击 {success_count}/{loop_count} 次，完成 {round_count} 轮")


if __name__ == "__main__":
    main()
