#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
============================================
  图片压缩工具 - Image Compressor v1.0
============================================

功能:
  - 压缩单张图片、整个文件夹内的图片
  - 保持原图不变，另存到压缩目录
  - 保持原始格式（JPEG→JPEG, PNG→PNG, ...）
  - 智能压缩，保留视觉质量
  - 支持常见图片格式

支持的格式: JPEG, PNG, WebP, GIF, BMP, TIFF, ICO
"""

import argparse
import os
import sys

# 强制 stdout/stderr 使用 UTF-8（解决 Windows GBK 终端中文乱码）
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
import time
import math
import hashlib
from pathlib import Path
from datetime import datetime
from collections import defaultdict

# ---------------------------------------------------------------------------
# 依赖检查
# ---------------------------------------------------------------------------
try:
    from PIL import Image, __version__ as pil_version
except ImportError:
    print("错误: 需要安装 Pillow 库。请运行: pip install Pillow")
    sys.exit(1)

# pillow-heif：可选，用于支持 HEIC/HEIF 格式（苹果 iPhone 默认格式）
try:
    import pillow_heif
    pillow_heif.register_heif_opener()
    HAS_HEIF = True
except ImportError:
    HAS_HEIF = False

# ---------------------------------------------------------------------------
# 常量与配置
# ---------------------------------------------------------------------------

# 支持的图片扩展名（小写）
SUPPORTED_EXTENSIONS = {
    '.jpg', '.jpeg', '.png', '.webp', '.gif',
    '.bmp', '.tiff', '.tif', '.ico', '.heic', '.heif',
}
# 如果 pillow-heif 未安装，去掉 HEIC 支持
if not HAS_HEIF:
    SUPPORTED_EXTENSIONS -= {'.heic', '.heif'}

# 格式化显示名称
FORMAT_DISPLAY = {
    '.jpg': 'JPEG', '.jpeg': 'JPEG', '.png': 'PNG',
    '.webp': 'WebP', '.gif': 'GIF', '.bmp': 'BMP',
    '.tiff': 'TIFF', '.tif': 'TIFF', '.ico': 'ICO',
    '.heic': 'HEIC', '.heif': 'HEIF',
}

# 默认压缩质量（视觉无损阈值）
# JPEG 85 = 视觉无损公认起点; WebP 80 ~= JPEG 85
DEFAULT_QUALITY = {
    '.jpg': 85,   '.jpeg': 85,
    '.png': None,  # PNG 用无损优化
    '.webp': 82,
    '.gif': None,  # GIF 用调色板优化
    '.bmp': None,
    '.tiff': None, # TIFF 用 LZW 无损压缩
    '.ico': None,
    '.heic': 80,  # HEIC 已是高效格式，降低品质可再缩减
    '.heif': 80,
}

# 最大文件尺寸（避免内存溢出），单位：字节 (500 MB)
MAX_FILE_SIZE = 500 * 1024 * 1024

# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------

def sizeof_fmt(num: float) -> str:
    """将字节数转为人类可读格式"""
    for unit in ('B', 'KB', 'MB', 'GB'):
        if abs(num) < 1024.0:
            return f"{num:.2f} {unit}"
        num /= 1024.0
    return f"{num:.2f} TB"


def is_supported_image(file_path: Path) -> bool:
    """检查文件是否为支持的图片格式"""
    return file_path.suffix.lower() in SUPPORTED_EXTENSIONS


def get_output_path(input_path: Path, output_dir: Path, input_base: Path) -> Path:
    """
    在输出目录下保持原目录结构。
    例如: input=C:/Photos/2024/photo.jpg, input_base=C:/Photos
         output=C:/Photos/compressed/2024/photo.jpg
    """
    rel = input_path.relative_to(input_base)
    return output_dir / rel


def file_hash(file_path: Path) -> str:
    """快速计算文件 SHA256 用于判断是否有变化"""
    h = hashlib.sha256()
    with open(file_path, 'rb') as f:
        for chunk in iter(lambda: f.read(65536), b''):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------------------
# 核心压缩函数
# ---------------------------------------------------------------------------

def compress_image(input_path: Path, output_path: Path, quality: int = 85,
                   strip_metadata: bool = True, jpeg_subsampling: int = 0) -> dict:
    """
    压缩单张图片。

    参数:
        input_path:  源图片路径
        output_path: 输出路径
        quality:     JPEG/WebP 质量参数 (1-100)
        strip_metadata: 是否剥离 EXIF/元数据（可节省大量空间）
        jpeg_subsampling: JPEG 色度采样
                         0=4:4:4(最佳色彩), 1=4:2:2, 2=4:2:0(最小体积)

    返回:
        dict: 包含状态、大小变化等信息的字典
    """
    original_size = input_path.stat().st_size
    ext = input_path.suffix.lower()

    # 确保输出目录存在
    output_path.parent.mkdir(parents=True, exist_ok=True)

    result = {
        'path': str(input_path.resolve()),
        'format': FORMAT_DISPLAY.get(ext, ext.upper()),
        'original_size': original_size,
        'status': 'unknown',
    }

    try:
        img = Image.open(input_path)
        # 读取图片时自动完成，不保留缓存
        img.load()

        mode = img.mode
        fmt = img.format  # 真实格式

        # ------- 根据不同格式选择压缩策略 -------

        if ext in ('.jpg', '.jpeg'):
            # --- JPEG 策略 ---
            # 核心：降低质量 + 优化 Huffman 表 + 色彩采样控制
            if mode in ('RGBA', 'LA', 'PA'):
                # 有透明通道 → 合成到白色背景
                bg = Image.new('RGB', img.size, (255, 255, 255))
                bg.paste(img, mask=img.split()[-1] if len(img.split()) > 3 else img.split()[0])
                img = bg
            elif mode not in ('RGB', 'L', 'CMYK'):
                img = img.convert('RGB')

            save_kwargs = {
                'format': 'JPEG',
                'quality': quality,
                'optimize': True,
                'progressive': True,
                'subsampling': jpeg_subsampling,
            }
            if strip_metadata:
                save_kwargs['exif'] = b''

        elif ext == '.png':
            # --- PNG 策略 ---
            # 核心：最大压缩级别 + 颜色模式优化 + 过滤
            # 尝试降低颜色深度
            mode = img.mode

            # 检查 alpha 是否真的被使用
            if mode == 'RGBA':
                alpha = img.getchannel('A')
                bbox = alpha.getbbox()
                if bbox is None:
                    img = img.convert('RGB')
                    mode = 'RGB'
                elif img.getextrema()[-1] == (255, 255):
                    # Alpha 通道全部为 255（完全不透明）
                    img = img.convert('RGB')
                    mode = 'RGB'

            # RGB 且颜色数 ≤ 256 → 转为调色板模式（大幅缩小）
            if mode == 'RGB':
                # 快速采样估算颜色数
                img_quantize = img.quantize(colors=256, method=Image.Quantize.MEDIANCUT)
                # 检查实际使用的颜色数
                palette = img_quantize.getpalette()
                used_colors = len(set(
                    tuple(palette[i:i+3]) for i in range(0, min(len(palette), 256*3), 3)
                ))
                # 去除完全透明色（如果有的话）
                if used_colors <= 200:  # 留有余量
                    img = img_quantize
                    mode = 'P'

            save_kwargs = {
                'format': 'PNG',
                'optimize': True,
                'compress_level': 9,
            }

        elif ext == '.webp':
            # --- WebP 策略 ---
            # 核心：质量参数 + method=6（最佳压缩但最慢）
            if mode not in ('RGB', 'RGBA', 'L', 'LA'):
                img = img.convert('RGBA')

            save_kwargs = {
                'format': 'WEBP',
                'quality': quality,
                'method': 6,
            }

        elif ext == '.gif':
            # --- GIF 策略 ---
            # GIF 本身就是调色板格式，优化调色板和帧参数
            # 保留动画信息
            gif_info = {}
            for key in ('loop', 'duration', 'background', 'transparency'):
                if key in img.info:
                    gif_info[key] = img.info[key]

            save_kwargs = {
                'format': 'GIF',
                'optimize': True,
            }
            save_kwargs.update(gif_info)

        elif ext == '.bmp':
            # --- BMP 策略 ---
            # BMP 无损压缩空间很小。对于 8-bit 以下可用 RLE。
            if mode in ('P', 'L') and mode != 'RGBA':
                save_kwargs = {
                    'format': 'BMP',
                    'compression': 1,  # BI_RLE8
                }
            else:
                # 24/32-bit BMP 无法有效压缩，保持原样
                save_kwargs = {
                    'format': 'BMP',
                }

        elif ext in ('.tiff', '.tif'):
            # --- TIFF 策略 ---
            # 核心：LZW 无损压缩
            save_kwargs = {
                'format': 'TIFF',
                'compression': 'tiff_lzw',
            }
            # 保留必要的分辨率信息
            for key in ('dpi', 'resolution_unit'):
                if key in img.info:
                    save_kwargs[key] = img.info[key]

        elif ext in ('.heic', '.heif'):
            # --- HEIC/HEIF 策略 ---
            # HEIC 基于 HEVC(H.265)，已是高效编码格式。
            # 通过轻度降低质量进一步缩小体积。
            if mode not in ('RGB', 'RGBA', 'L', 'LA'):
                img = img.convert('RGB')
            heif_file = pillow_heif.from_pillow(img)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            heif_file.save(output_path, quality=quality)
            img.close()

            if output_path.exists():
                compressed_size = output_path.stat().st_size
            else:
                compressed_size = original_size
            if compressed_size >= original_size:
                result['status'] = 'no_gain'
                result['compressed_size'] = compressed_size
                result['savings_pct'] = 0.0
            else:
                savings = (1 - compressed_size / original_size) * 100
                result['status'] = 'compressed'
                result['compressed_size'] = compressed_size
                result['savings_pct'] = round(savings, 2)
            return result

        elif ext == '.ico':
            # --- ICO 策略 ---
            # ICO 内部已使用 PNG 或 BMP 压缩，优化空间很小
            save_kwargs = {
                'format': 'ICO',
            }

        else:
            result['status'] = 'skipped'
            result['reason'] = f'不支持的格式: {ext}'
            img.close()
            return result

        # ---- 执行保存 ----
        img.save(output_path, **save_kwargs)
        img.close()

        # ---- 检查结果 ----
        if output_path.exists():
            compressed_size = output_path.stat().st_size
        else:
            compressed_size = original_size  # fallback

        # 如果压缩后反而变大（小图片常见），保留原尺寸的版本
        # 但这里策略是信任用户要"压缩"，对于明显变大的情况，给出标志
        if compressed_size >= original_size:
            result['status'] = 'no_gain'
            result['compressed_size'] = compressed_size
            result['savings_pct'] = 0.0
        else:
            savings = (1 - compressed_size / original_size) * 100
            result['status'] = 'compressed'
            result['compressed_size'] = compressed_size
            result['savings_pct'] = round(savings, 2)

        return result

    except Exception as e:
        result['status'] = 'error'
        result['error'] = str(e)
        return result


# ---------------------------------------------------------------------------
# 批量处理
# ---------------------------------------------------------------------------

def collect_images(paths: list[Path], recursive: bool = False) -> list[Path]:
    """
    收集所有需要处理的图片文件。
    - 如果是文件: 直接添加
    - 如果是目录: 扫描内部图片
    """
    images = []
    for p in paths:
        p = p.resolve()
        if not p.exists():
            print(f"  [!] 路径不存在，跳过: {p}")
            continue
        if p.is_file():
            if is_supported_image(p):
                images.append(p)
            else:
                print(f"  [!] 不支持的文件格式，跳过: {p}")
        elif p.is_dir():
            pattern = '**/*' if recursive else '*'
            found = 0
            for f in sorted(p.glob(pattern)):
                if f.is_file() and is_supported_image(f):
                    images.append(f)
                    found += 1
            if found == 0:
                print(f"  [!] 目录中未找到图片: {p}")
    return images


def batch_compress(image_paths: list[Path], output_dir: Path,
                   quality: int = 85, strip_metadata: bool = True,
                   jpeg_subsampling: int = 0, max_workers: int = 4,
                   dry_run: bool = False) -> dict:
    """
    批量压缩图片。

    返回汇总统计。
    """
    if not image_paths:
        return {'total': 0, 'compressed': 0, 'skipped': 0, 'errors': 0, 'no_gain': 0,
                'original_total': 0, 'compressed_total': 0, 'results': []}

    # 按公共父目录分组（用于保持目录结构）
    # 如果所有图片在同一目录下，以此为 base；否则以各自父目录为 base
    parents = {p.parent for p in image_paths}
    if len(parents) == 1:
        # 所有图片在同一目录
        base_dir = parents.pop()
        # 输出目录为 output_dir
        results = _compress_list(image_paths, output_dir, base_dir,
                                 quality, strip_metadata, jpeg_subsampling,
                                 max_workers, dry_run)
    else:
        # 多目录来源
        # 计算公共前缀
        common = Path(os.path.commonpath([str(p.parent) for p in image_paths]))
        results = _compress_list(image_paths, output_dir, common,
                                 quality, strip_metadata, jpeg_subsampling,
                                 max_workers, dry_run)

    # 汇总
    stats = {
        'total': len(results),
        'compressed': 0,
        'no_gain': 0,
        'skipped': 0,
        'errors': 0,
        'original_total': 0,
        'compressed_total': 0,
        'results': results,
    }

    for r in results:
        if r['status'] == 'compressed':
            stats['compressed'] += 1
            stats['original_total'] += r['original_size']
            stats['compressed_total'] += r.get('compressed_size', r['original_size'])
        elif r['status'] == 'no_gain':
            stats['no_gain'] += 1
            stats['original_total'] += r['original_size']
            stats['compressed_total'] += r.get('compressed_size', r['original_size'])
        elif r['status'] == 'skipped':
            stats['skipped'] += 1
        elif r['status'] == 'error':
            stats['errors'] += 1

    return stats


def _compress_one(args_tuple):
    """用于线程池的包装函数"""
    img_path, out_path, quality, strip_metadata, jpeg_subsampling = args_tuple
    return compress_image(
        input_path=img_path,
        output_path=out_path,
        quality=quality,
        strip_metadata=strip_metadata,
        jpeg_subsampling=jpeg_subsampling,
    )


def _compress_list(image_paths, output_dir, base_dir, quality,
                   strip_metadata, jpeg_subsampling, max_workers, dry_run):
    """压缩文件列表（内部函数）"""
    total = len(image_paths)
    results = [None] * total
    completed = 0
    errors = 0

    # 准备参数
    task_args = []
    for img_path in image_paths:
        out_path = get_output_path(img_path, output_dir, base_dir)
        task_args.append((img_path, out_path, quality, strip_metadata, jpeg_subsampling))

    if dry_run:
        for i, (img_path, out_path, *_) in enumerate(task_args):
            orig_size = img_path.stat().st_size
            print(f"  [模拟] {img_path.name} -> {out_path} ({sizeof_fmt(orig_size)})")
            results[i] = {
                'path': str(img_path),
                'format': FORMAT_DISPLAY.get(img_path.suffix.lower(), ''),
                'original_size': orig_size,
                'compressed_size': orig_size,
                'savings_pct': 0,
                'status': 'dry_run',
            }
        return results

    # 单线程处理（默认）
    if max_workers <= 1:
        for i, args in enumerate(task_args):
            img_path = args[0]
            try:
                # 显示进度（文件名，不换行输出多个文件）
                rel_name = img_path.name
                if len(rel_name) > 50:
                    rel_name = rel_name[:47] + '...'
                print(f"  [{completed+1}/{total}] {rel_name}  ", end='', flush=True)

                result = compress_image(
                    input_path=args[0],
                    output_path=args[1],
                    quality=args[2],
                    strip_metadata=args[3],
                    jpeg_subsampling=args[4],
                )
                results[i] = result

                if result['status'] == 'compressed':
                    saved = sizeof_fmt(result['original_size'] - result['compressed_size'])
                    pct = result['savings_pct']
                    print(f"[OK] 节省 {saved} ({pct:.1f}%)")
                elif result['status'] == 'no_gain':
                    print(f"[-] 无收益 (与原文件大小相近或更大)")
                elif result['status'] == 'error':
                    print(f"[ERR] 错误: {result.get('error', '未知错误')}")
                    errors += 1
                else:
                    print(f"- {result['status']}")

                completed += 1

            except Exception as e:
                print(f"[ERR] 异常: {e}")
                results[i] = {
                    'path': str(img_path),
                    'format': '',
                    'original_size': 0,
                    'status': 'error',
                    'error': str(e),
                }
                errors += 1
                completed += 1

        return results

    # 多线程处理
    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_idx = {
            executor.submit(_compress_one, args): i
            for i, args in enumerate(task_args)
        }

        for future in concurrent.futures.as_completed(future_to_idx):
            idx = future_to_idx[future]
            try:
                result = future.result()
                results[idx] = result
                if result['status'] == 'compressed':
                    saved = sizeof_fmt(result['original_size'] - result['compressed_size'])
                    pct = result['savings_pct']
                    print(f"  [OK] [{completed+1}/{total}] {result['format']} 节省 {saved} ({pct:.1f}%)")
                elif result['status'] == 'error':
                    print(f"  [ERR] [{completed+1}/{total}] 错误: {result.get('error', '')}")
                else:
                    print(f"  - [{completed+1}/{total}] {result['status']}")
            except Exception as e:
                results[idx] = {
                    'path': str(image_paths[idx]),
                    'format': '',
                    'original_size': 0,
                    'status': 'error',
                    'error': str(e),
                }
                print(f"  [ERR] [{completed+1}/{total}] 异常: {e}")

            completed += 1

    return results


# ---------------------------------------------------------------------------
# 报告输出
# ---------------------------------------------------------------------------

def print_summary(stats: dict, elapsed: float):
    """打印压缩结果汇总"""
    total = stats['total']
    compressed = stats['compressed']
    no_gain = stats['no_gain']
    errors = stats['errors']
    skipped = stats['skipped']

    print()
    print("=" * 60)
    print("  压缩完成！汇总报告")
    print("=" * 60)

    if total == 0:
        print("  没有需要处理的图片。")
        return

    print(f"  总文件数:     {total}")
    print(f"  成功压缩:     {compressed}")
    print(f"  无收益:       {no_gain}")
    if skipped > 0:
        print(f"  跳过:         {skipped}")
    if errors > 0:
        print(f"  错误:         {errors}")
    print(f"  耗时:         {elapsed:.2f} 秒")

    if stats['original_total'] > 0 and stats['compressed_total'] > 0:
        orig = stats['original_total']
        comp = stats['compressed_total']
        saved_bytes = orig - comp
        saved_pct = (1 - comp / orig) * 100
        print()
        print(f"  压缩前总大小: {sizeof_fmt(orig)}")
        print(f"  压缩后总大小: {sizeof_fmt(comp)}")
        print(f"  总共节省:     {sizeof_fmt(saved_bytes)}  ({saved_pct:.2f}%)")

    print("=" * 60)


# ---------------------------------------------------------------------------
# 命令行界面
# ---------------------------------------------------------------------------

def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        prog='image_compressor',
        description='Image Compressor -- compress images without visible quality loss',
        epilog='示例:\n'
               '  python image_compressor.py photo.jpg\n'
               '  python image_compressor.py ./my_photos/\n'
               '  python image_compressor.py ./input/ -o ./output/ -q 80 --recursive\n'
               '  python image_compressor.py img1.png img2.jpg ./folder/ -w 2',
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        'input', nargs='*',
        help='输入文件或目录（支持多个，--list-formats 时可不填）',
    )

    parser.add_argument(
        '-o', '--output',
        default=None,
        help='输出目录（默认: 在输入同级创建 compressed 目录）',
    )

    parser.add_argument(
        '-q', '--quality',
        type=int,
        default=85,
        help='JPEG/WebP 压缩质量 1-100（默认: 85，视觉无损）',
    )

    parser.add_argument(
        '--subsampling',
        type=int,
        choices=[0, 1, 2],
        default=0,
        help='JPEG 色度采样: 0=4:4:4(最佳色彩), 1=4:2:2, 2=4:2:0(最小)（默认: 0=4:4:4）',
    )

    parser.add_argument(
        '--no-strip-metadata',
        action='store_true',
        help='保留 EXIF 等元数据（默认: 剥离）',
    )

    parser.add_argument(
        '-r', '--recursive',
        action='store_true',
        help='递归处理子目录中的图片',
    )

    parser.add_argument(
        '-w', '--workers',
        type=int,
        default=1,
        help='并发线程数（默认: 1，多线程可加快批量处理）',
    )

    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='仅模拟，不实际压缩（预览结果）',
    )

    parser.add_argument(
        '--list-formats',
        action='store_true',
        help='列出支持的图片格式',
    )

    return parser.parse_args(argv)


def cmd_list_formats():
    """列出支持的格式及默认参数"""
    print("支持的图片格式:")
    print()
    headers = f"{'格式':<8} {'扩展名':<18} {'默认质量':<12} {'说明'}"
    print(headers)
    print("-" * 70)
    formats_info = [
        ('JPEG',   '.jpg, .jpeg',   '85',   '有损，视觉无损级'),
        ('PNG',    '.png',          '无损',  '无损 + 颜色深度优化'),
        ('WebP',   '.webp',         '82',   '有损，视觉无损级'),
        ('GIF',    '.gif',          '无损',  '调色板优化（支持动画）'),
        ('BMP',    '.bmp',          '无损',  'RLE 压缩（8-bit 以下）'),
        ('TIFF',   '.tiff, .tif',   '无损',  'LZW 无损压缩'),
        ('ICO',    '.ico',          '无损',  '图标格式，保持原样'),
        ('HEIC',   '.heic, .heif',  '80',   f"有损{' (需: pip install pillow-heif)' if not HAS_HEIF else ''}"),
    ]
    for fmt, ext, qual, desc in formats_info:
        print(f"  {fmt:<8} {ext:<18} {qual:<12} {desc}")
    if not HAS_HEIF:
        print()
        print("  * HEIC/HEIF 支持需要安装: pip install pillow-heif")


def main():
    args = parse_args()

    if args.list_formats:
        cmd_list_formats()
        return

    if not args.input:
        print("错误: 请指定要压缩的图片或目录")
        print("使用 --help 查看帮助，使用 --list-formats 查看支持的格式")
        return 1

    # ---- 确定输入路径 ----
    input_paths = [Path(p) for p in args.input]

    # ---- 收集图片 ----
    print("[扫描] 正在扫描图片...")
    images = collect_images(input_paths, recursive=args.recursive)

    if not images:
        print("未找到任何可处理的图片。")
        return

    # 去重
    seen = set()
    unique_images = []
    for img in images:
        s = str(img.resolve())
        if s not in seen:
            seen.add(s)
            unique_images.append(img)
    images = unique_images

    print(f"  找到 {len(images)} 张图片")
    print()

    # ---- 确定输出目录 ----
    if args.output:
        output_dir = Path(args.output).resolve()
    else:
        # 默认：在第一个输入的同级目录下创建 compressed/
        first = input_paths[0].resolve()
        if first.is_file():
            parent = first.parent
        else:
            parent = first
        output_dir = parent / 'compressed'
        # 如果输出已存在，加后缀
        counter = 1
        base_dir = output_dir
        while output_dir.exists() and any(output_dir.iterdir()):
            output_dir = parent / f'compressed_{counter}'
            counter += 1

    strip_meta = not args.no_strip_metadata

    print(f"[输出目录] {output_dir}")
    if strip_meta:
        print("[元数据] 剥离（EXIF 等信息将被移除）")
    else:
        print("[元数据] 保留")
    print(f"[质量] {args.quality}  |  JPEG 采样: {'4:4:4' if args.subsampling == 0 else '4:2:2' if args.subsampling==1 else '4:2:0'}")
    print(f"[线程] {args.workers}")
    print()

    # ---- 执行压缩 ----
    start_time = time.time()

    stats = batch_compress(
        image_paths=images,
        output_dir=output_dir,
        quality=args.quality,
        strip_metadata=strip_meta,
        jpeg_subsampling=args.subsampling,
        max_workers=args.workers,
        dry_run=args.dry_run,
    )

    elapsed = time.time() - start_time

    # ---- 输出汇总 ----
    print_summary(stats, elapsed)

    # ---- 错误详情 ----
    if stats['errors'] > 0:
        print()
        print("错误详情:")
        for r in stats['results']:
            if r['status'] == 'error':
                print(f"  [FAIL] {r['path']}")
                print(f"     原因: {r.get('error', '未知')}")

    # ---- 输出目录提示 ----
    if not args.dry_run and stats['compressed'] > 0:
        print()
        print(f"[保存] 压缩后的文件已保存到: {output_dir}")

    # 返回值方便自动化
    return 1 if stats['errors'] > 0 else 0


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    sys.exit(main())
