#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
============================================
  图片压缩工具 - Image Compressor (GUI版)
============================================
  无需命令行，选择图片/文件夹即可压缩
  支持: JPEG, PNG, WebP, GIF, BMP, TIFF, ICO, HEIC/HEIF
============================================
"""

import os
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from pathlib import Path

# ============================================================
# 核心压缩引擎（直接从 image_compressor.py 提取）
# ============================================================

try:
    from PIL import Image
except ImportError:
    messagebox.showerror("缺少依赖", "未找到 Pillow 库，无法运行。")
    sys.exit(1)

try:
    import pillow_heif
    pillow_heif.register_heif_opener()
    HAS_HEIF = True
except Exception:
    # pillow_heif 在 EXE 中可能因缺少原生 DLL 而失败，不影响核心功能
    HAS_HEIF = False

SUPPORTED_EXTENSIONS = {
    '.jpg', '.jpeg', '.png', '.webp', '.gif',
    '.bmp', '.tiff', '.tif', '.ico', '.heic', '.heif',
}
if not HAS_HEIF:
    SUPPORTED_EXTENSIONS -= {'.heic', '.heif'}

FORMAT_DISPLAY = {
    '.jpg': 'JPEG', '.jpeg': 'JPEG', '.png': 'PNG', '.webp': 'WebP',
    '.gif': 'GIF', '.bmp': 'BMP', '.tiff': 'TIFF', '.tif': 'TIFF',
    '.ico': 'ICO', '.heic': 'HEIC', '.heif': 'HEIF',
}


def sizeof_fmt(num):
    for unit in ('B', 'KB', 'MB', 'GB'):
        if abs(num) < 1024.0:
            return f"{num:.2f} {unit}"
        num /= 1024.0
    return f"{num:.2f} TB"


def is_supported_image(file_path):
    return Path(file_path).suffix.lower() in SUPPORTED_EXTENSIONS


def collect_images(paths, recursive=False):
    images = []
    for p in paths:
        p = Path(p)
        if not p.exists():
            continue
        if p.is_file():
            if is_supported_image(p):
                images.append(p)
        elif p.is_dir():
            pattern = '**/*' if recursive else '*'
            for f in sorted(p.glob(pattern)):
                if f.is_file() and is_supported_image(f):
                    images.append(f)
    # 去重
    seen = set()
    unique = []
    for img in images:
        s = str(img.resolve())
        if s not in seen:
            seen.add(s)
            unique.append(img)
    return unique


def compress_single(input_path, output_path, quality, strip_metadata=True, jpeg_subsampling=0):
    """压缩单张图片，返回结果字典"""
    original_size = input_path.stat().st_size
    ext = input_path.suffix.lower()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    result = {
        'name': input_path.name,
        'original_size': original_size,
        'status': 'unknown',
    }

    # HEIC/HEIF：跳过压缩，不进入 PIL 解码（EXE 中 HEIC 解码器可能有问题）
    if ext in ('.heic', '.heif'):
        result['status'] = 'skipped'
        result['reason'] = 'HEIC/HEIF 已是高效格式，跳过压缩'
        return result

    try:
        img = Image.open(input_path)
        img.load()
        mode = img.mode

        if ext in ('.jpg', '.jpeg'):
            if mode in ('RGBA', 'LA', 'PA'):
                bg = Image.new('RGB', img.size, (255, 255, 255))
                bg.paste(img, mask=img.split()[-1] if len(img.split()) > 3 else img.split()[0])
                img = bg
            elif mode not in ('RGB', 'L', 'CMYK'):
                img = img.convert('RGB')
            kw = {'format': 'JPEG', 'quality': quality, 'optimize': True, 'progressive': True, 'subsampling': jpeg_subsampling}
            if strip_metadata:
                kw['exif'] = b''
            img.save(output_path, **kw)

        elif ext == '.png':
            if mode == 'RGBA':
                alpha = img.getchannel('A')
                if alpha.getbbox() is None:
                    img = img.convert('RGB')
                    mode = 'RGB'
                elif img.getextrema()[-1] == (255, 255):
                    img = img.convert('RGB')
                    mode = 'RGB'
            if mode == 'RGB':
                q = img.quantize(colors=256, method=Image.Quantize.MEDIANCUT)
                palette = q.getpalette()
                used = len(set(tuple(palette[i:i+3]) for i in range(0, min(len(palette), 256*3), 3)))
                if used <= 200:
                    img = q
            img.save(output_path, format='PNG', optimize=True, compress_level=9)

        elif ext == '.webp':
            if mode not in ('RGB', 'RGBA', 'L', 'LA'):
                img = img.convert('RGBA')
            img.save(output_path, format='WEBP', quality=quality, method=6)

        elif ext == '.gif':
            info = {}
            for key in ('loop', 'duration', 'background', 'transparency'):
                if key in img.info:
                    info[key] = img.info[key]
            img.save(output_path, format='GIF', optimize=True, **info)

        elif ext == '.bmp':
            if mode in ('P', 'L') and mode != 'RGBA':
                img.save(output_path, format='BMP', compression=1)
            else:
                img.save(output_path, format='BMP')

        elif ext in ('.tiff', '.tif'):
            kw = {'format': 'TIFF', 'compression': 'tiff_lzw'}
            for key in ('dpi', 'resolution_unit'):
                if key in img.info:
                    kw[key] = img.info[key]
            img.save(output_path, **kw)

        elif ext == '.ico':
            img.save(output_path, format='ICO')

        else:
            result['status'] = 'skipped'
            result['reason'] = f'不支持的格式: {ext}'
            img.close()
            return result

        img.close()
        compressed_size = output_path.stat().st_size if output_path.exists() else original_size
        if compressed_size >= original_size:
            result['status'] = 'no_gain'
            result['compressed_size'] = compressed_size
            result['savings_pct'] = 0.0
        else:
            savings = (1 - compressed_size / original_size) * 100
            result['status'] = 'compressed'
            result['compressed_size'] = compressed_size
            result['savings_pct'] = round(savings, 2)

    except Exception as e:
        result['status'] = 'error'
        result['error'] = str(e)

    return result


# ============================================================
# GUI 界面
# ============================================================

class ImageCompressorApp:
    def __init__(self, root):
        self.root = root
        self.root.title("图片压缩工具 v1.0")
        self.root.geometry("720x620")
        self.root.resizable(True, True)
        self.root.minsize(640, 520)

        # 设置图标（如果有）
        try:
            self.root.iconbitmap(default='')
        except:
            pass

        self.image_paths = []
        self.running = False

        # ---------- 样式 ----------
        style = ttk.Style()
        style.theme_use('vista' if 'vista' in style.theme_names() else 'clam')

        main_frame = ttk.Frame(root, padding=15)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # ---------- 标题 ----------
        title = ttk.Label(main_frame, text="🖼️  图片压缩工具", font=("微软雅黑", 16, "bold"))
        title.pack(pady=(0, 5))

        subtitle = ttk.Label(main_frame, text="保持视觉质量不变，大幅减小文件体积", font=("微软雅黑", 9))
        subtitle.pack(pady=(0, 12))

        # ---------- 选择区域 ----------
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X, pady=5)

        self.btn_select_files = ttk.Button(btn_frame, text="📂 选择图片文件", command=self.select_files, width=18)
        self.btn_select_files.pack(side=tk.LEFT, padx=3)

        self.btn_select_folder = ttk.Button(btn_frame, text="📁 选择文件夹", command=self.select_folder, width=15)
        self.btn_select_folder.pack(side=tk.LEFT, padx=3)

        self.btn_clear = ttk.Button(btn_frame, text="🗑  清空列表", command=self.clear_list, width=12)
        self.btn_clear.pack(side=tk.LEFT, padx=3)

        self.lbl_count = ttk.Label(btn_frame, text="已选: 0 张", font=("微软雅黑", 9))
        self.lbl_count.pack(side=tk.RIGHT, padx=5)

        # ---------- 图片列表 ----------
        list_frame = ttk.LabelFrame(main_frame, text="待压缩的图片", padding=5)
        list_frame.pack(fill=tk.BOTH, expand=True, pady=5)

        list_columns = ('name', 'size', 'format')
        self.tree = ttk.Treeview(list_frame, columns=list_columns, show='headings', height=10)
        self.tree.heading('name', text='文件名')
        self.tree.heading('size', text='大小')
        self.tree.heading('format', text='格式')
        self.tree.column('name', width=350, minwidth=200)
        self.tree.column('size', width=100, minwidth=80, anchor='center')
        self.tree.column('format', width=80, minwidth=60, anchor='center')

        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # ---------- 设置区域 ----------
        settings_frame = ttk.LabelFrame(main_frame, text="压缩设置", padding=10)
        settings_frame.pack(fill=tk.X, pady=8)

        # 第一行：质量和采样
        row1 = ttk.Frame(settings_frame)
        row1.pack(fill=tk.X, pady=2)

        ttk.Label(row1, text="质量:").pack(side=tk.LEFT)
        self.quality_var = tk.IntVar(value=85)
        self.quality_slider = ttk.Scale(row1, from_=50, to=100, orient=tk.HORIZONTAL,
                                         variable=self.quality_var, command=self.update_quality_label,
                                         length=180)
        self.quality_slider.pack(side=tk.LEFT, padx=5)
        self.quality_label = ttk.Label(row1, text="85", width=3, anchor='center')
        self.quality_label.pack(side=tk.LEFT)
        ttk.Label(row1, text="(越高品质越好，85=视觉无损)").pack(side=tk.LEFT, padx=8)

        # 第二行：选项
        row2 = ttk.Frame(settings_frame)
        row2.pack(fill=tk.X, pady=2)

        self.strip_meta_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(row2, text="剥离元数据 (EXIF等，可减小体积)", variable=self.strip_meta_var).pack(side=tk.LEFT)

        ttk.Label(row2, text="  JPEG采样:").pack(side=tk.LEFT, padx=(15, 0))
        self.subsampling_var = tk.StringVar(value='4:4:4 (最佳色彩)')
        subsampling_menu = ttk.Combobox(row2, textvariable=self.subsampling_var,
                                         values=['4:4:4 (最佳色彩)', '4:2:2', '4:2:0 (最小体积)'],
                                         state='readonly', width=20)
        subsampling_menu.pack(side=tk.LEFT, padx=3)
        subsampling_menu.current(0)

        # ---------- 进度条 ----------
        progress_frame = ttk.Frame(main_frame)
        progress_frame.pack(fill=tk.X, pady=3)

        self.progress = ttk.Progressbar(progress_frame, mode='determinate', length=400)
        self.progress.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self.lbl_progress = ttk.Label(progress_frame, text="就绪", font=("微软雅黑", 8), width=20)
        self.lbl_progress.pack(side=tk.RIGHT, padx=5)

        # ---------- 操作按钮 ----------
        action_frame = ttk.Frame(main_frame)
        action_frame.pack(fill=tk.X, pady=5)

        self.btn_start = ttk.Button(action_frame, text="🚀  开始压缩", command=self.start_compress, width=20)
        self.btn_start.pack(side=tk.RIGHT, padx=3)

        self.btn_open = ttk.Button(action_frame, text="📂 打开输出文件夹", command=self.open_output, width=18, state='disabled')
        self.btn_open.pack(side=tk.RIGHT, padx=3)

        self.output_dir = None

    def update_quality_label(self, event=None):
        val = int(self.quality_var.get())
        self.quality_label.config(text=str(val))

    def select_files(self):
        files = filedialog.askopenfilenames(
            title="选择图片文件",
            filetypes=[
                ("图片文件", "*.jpg *.jpeg *.png *.webp *.gif *.bmp *.tiff *.tif *.ico" +
                 (" *.heic *.heif" if HAS_HEIF else "")),
                ("所有文件", "*.*")
            ]
        )
        if files:
            # 预先构建现有路径的 set（O(n)，避免循环中反复构造）
            existing = {str(p.resolve()) for p in self.image_paths}
            added = 0
            for f in files:
                p = Path(f)
                sp = str(p.resolve())
                if is_supported_image(p) and sp not in existing:
                    self.image_paths.append(p)
                    existing.add(sp)
                    added += 1
            if added > 0:
                self._batch_insert_list()

    def select_folder(self):
        folder = filedialog.askdirectory(title="选择包含图片的文件夹")
        if not folder:
            return

        recursive = messagebox.askyesno("包含子目录?", "是否同时扫描子目录中的图片?")

        # 禁用按钮 + 显示扫描状态
        self.btn_select_files.config(state='disabled')
        self.btn_select_folder.config(state='disabled')
        self.lbl_progress.config(text="扫描中...")
        self.root.update_idletasks()

        # 后台线程扫描（防止文件夹文件多时卡死 UI）
        thread = threading.Thread(
            target=self._do_scan_folder,
            args=(folder, recursive),
            daemon=True
        )
        thread.start()

    def _do_scan_folder(self, folder, recursive):
        """后台扫描文件夹（带异常处理，防止线程静默崩溃）"""
        try:
            images = collect_images([folder], recursive=recursive)
            self.root.after(0, self._finish_scan_folder, images, None)
        except Exception as e:
            self.root.after(0, self._finish_scan_folder, [], str(e))

    def _finish_scan_folder(self, images, error):
        """扫描完成，在主线程更新列表"""
        self.btn_select_files.config(state='normal')
        self.btn_select_folder.config(state='normal')
        self.lbl_progress.config(text="就绪")

        if error:
            messagebox.showerror("扫描出错", f"扫描文件夹时发生错误:\n{error}")
            return

        existing = {str(p.resolve()) for p in self.image_paths}
        added = 0
        for img in images:
            sp = str(img.resolve())
            if sp not in existing:
                self.image_paths.append(img)
                existing.add(sp)
                added += 1

        if added > 0:
            self._batch_insert_list()

    def clear_list(self):
        self.image_paths.clear()
        self._batch_insert_list()

    def _batch_insert_list(self):
        """分批插入 treeview，每批之间刷新 UI 防止卡死"""
        # 清空
        for item in self.tree.get_children():
            self.tree.delete(item)

        total = len(self.image_paths)
        batch_size = 50

        for start in range(0, total, batch_size):
            batch = self.image_paths[start:start + batch_size]
            for p in batch:
                ext = p.suffix.lower()
                fmt = FORMAT_DISPLAY.get(ext, ext.upper())
                size = sizeof_fmt(p.stat().st_size)
                self.tree.insert('', tk.END, values=(p.name, size, fmt))
            # 每批插入后让 UI 处理事件（防止长时间无响应）
            self.root.update_idletasks()

        self.lbl_count.config(text=f"已选: {total} 张")

    def start_compress(self):
        if not self.image_paths:
            messagebox.showwarning("提示", "请先选择要压缩的图片或文件夹")
            return

        if self.running:
            return

        # 选择输出目录
        self.output_dir = filedialog.askdirectory(title="选择输出目录（压缩后的图片存放位置）")
        if not self.output_dir:
            return

        self.output_dir = Path(self.output_dir)

        # 禁用按钮
        self.running = True
        self.btn_start.config(state='disabled', text='⏳ 压缩中...')
        self.btn_select_files.config(state='disabled')
        self.btn_select_folder.config(state='disabled')
        self.btn_clear.config(state='disabled')
        self.btn_open.config(state='disabled')
        self.lbl_progress.config(text="准备压缩...")

        self._compress_index = 0
        self._compress_total = len(self.image_paths)
        self._compress_ok = 0
        self._compress_none = 0
        self._compress_err = 0
        self._compress_orig = 0
        self._compress_comp = 0

        quality = int(self.quality_var.get())
        strip_meta = self.strip_meta_var.get()

        # 用 after 链在主线程逐张压缩，避免线程交互问题
        self._compress_quality = quality
        self._compress_strip = strip_meta
        # StringVar → 整数映射
        subsampling_map = {'4:4:4 (最佳色彩)': 0, '4:2:2': 1, '4:2:0 (最小体积)': 2}
        self._compress_sub = subsampling_map.get(self.subsampling_var.get(), 0)
        self.root.after(50, self._do_compress_next)

    def _do_compress_next(self):
        """在主线程逐张压缩（用 after 链，不会卡死主循环）"""
        if not self.running or self._compress_index >= self._compress_total:
            self._finish_compress(
                self._compress_total,
                self._compress_ok,
                self._compress_none,
                self._compress_err,
                self._compress_orig,
                self._compress_comp,
                None,
            )
            return

        i = self._compress_index
        img_path = self.image_paths[i]
        out_path = self.output_dir / img_path.name

        pct = int((i / self._compress_total) * 100)
        self.lbl_progress.config(text=f"正在压缩 ({i+1}/{self._compress_total})")
        self.progress['value'] = pct
        self.root.update_idletasks()

        try:
            result = compress_single(img_path, out_path,
                                     self._compress_quality,
                                     self._compress_strip,
                                     self._compress_sub)
        except Exception as e:
            result = {
                'name': img_path.name,
                'original_size': img_path.stat().st_size,
                'status': 'error',
                'error': str(e),
            }

        self._compress_orig += result.get('original_size', 0)

        if result['status'] == 'compressed':
            self._compress_ok += 1
            self._compress_comp += result.get('compressed_size', 0)
            status_text = f"✓ {result.get('savings_pct', 0):.1f}%"
        elif result['status'] == 'no_gain':
            self._compress_none += 1
            self._compress_comp += result.get('compressed_size', result.get('original_size', 0))
            status_text = '→ 无收益'
        elif result['status'] == 'error':
            self._compress_err += 1
            status_text = '✗ 错误'
        elif result['status'] == 'skipped':
            status_text = '→ 跳过'
        else:
            status_text = result['status']

        self._update_item_status(i, status_text)

        self._compress_index += 1
        self.root.after(10, self._do_compress_next)

    def _update_progress(self, pct, text):
        self.progress['value'] = pct
        self.lbl_progress.config(text=text)

    def _update_item_status(self, index, status_text):
        children = self.tree.get_children()
        if index < len(children):
            item = children[index]
            cur = self.tree.item(item, 'values')
            if cur:
                new_vals = list(cur)
                if len(new_vals) == 3:
                    new_vals.append(status_text)
                    self.tree['columns'] = ('name', 'size', 'format', 'result')
                    self.tree.heading('result', text='结果')
                    self.tree.column('result', width=90, minwidth=70, anchor='center')
                elif len(new_vals) >= 4:
                    new_vals[3] = status_text
                self.tree.item(item, values=tuple(new_vals))

    def _finish_compress(self, total, compressed, no_gain, errors, orig_total, comp_total, error_msg=None):
        self.progress['value'] = 100
        self.running = False

        self.btn_start.config(state='normal', text='🚀  开始压缩')
        self.btn_select_files.config(state='normal')
        self.btn_select_folder.config(state='normal')
        self.btn_clear.config(state='normal')

        # 把窗口提到前台，防止消息框藏在后面
        self._bring_to_front()

        if error_msg:
            self.lbl_progress.config(text="出错!")
            messagebox.showerror("压缩出错", f"压缩过程中出现异常:\n{error_msg}")
            return

        # 汇总
        summary = f"压缩完成!\n\n"
        summary += f"总文件: {total}\n"
        summary += f"成功压缩: {compressed}\n"
        summary += f"无收益: {no_gain}\n"
        if errors > 0:
            summary += f"错误: {errors}\n"
        summary += "\n"

        if orig_total > 0 and comp_total > 0:
            saved = orig_total - comp_total
            pct = (1 - comp_total / orig_total) * 100
            summary += f"原大小: {sizeof_fmt(orig_total)}\n"
            summary += f"现大小: {sizeof_fmt(comp_total)}\n"
            summary += f"节省:   {sizeof_fmt(saved)} ({pct:.1f}%)\n"

        self.lbl_progress.config(text="完成!")

        self._bring_to_front()
        messagebox.showinfo("压缩完成", summary)

        self.btn_open.config(state='normal')

        # 尝试打开输出目录
        try:
            os.startfile(str(self.output_dir))
        except:
            pass

    def _bring_to_front(self):
        """把窗口提到前台"""
        try:
            self.root.lift()
            self.root.attributes('-topmost', True)
            self.root.after(200, lambda: self.root.attributes('-topmost', False))
            self.root.update_idletasks()
        except:
            pass

    def open_output(self):
        if self.output_dir and self.output_dir.exists():
            try:
                os.startfile(str(self.output_dir))
            except:
                pass

    # ============================================================
    # 拖放支持（仅支持拖放到 EXE 图标，窗口拖放需 tkinterDnD 库）
    # ============================================================

    def _process_cli_paths(self, paths):
        """处理命令行参数传入的路径（拖放到 EXE 图标）"""
        try:
            self.root.after(0, self._set_scanning_state)
            images = collect_images(paths, recursive=True)
            self.root.after(0, self._finish_scan_folder, images, None)
        except Exception as e:
            self.root.after(0, self._finish_scan_folder, [], str(e))

    def _set_scanning_state(self):
        """切换到扫描状态"""
        self.btn_select_files.config(state='disabled')
        self.btn_select_folder.config(state='disabled')
        self.lbl_progress.config(text="扫描中...")
        self.root.update_idletasks()


# ============================================================
# 入口
# ============================================================

def main():
    root = tk.Tk()
    app = ImageCompressorApp(root)

    # 处理拖放到 EXE 图标的文件（Windows 把路径作为命令行参数传入）
    if len(sys.argv) > 1:
        paths = [Path(p) for p in sys.argv[1:]]
        thread = threading.Thread(
            target=app._process_cli_paths,
            args=(paths,),
            daemon=True
        )
        thread.start()

    root.mainloop()


if __name__ == '__main__':
    main()
