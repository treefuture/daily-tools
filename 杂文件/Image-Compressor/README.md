# Image Compressor 图片压缩工具

一个智能的图片压缩工具，保持视觉质量不变的同时大幅减小文件体积。

## 功能特点

- **无损视觉质量** — 智能压缩人眼不敏感的图像信息，保留关键细节
- **保持原图不变** — 压缩后的图片保存到新目录，原始文件不受影响
- **支持常见格式** — JPEG, PNG, WebP, GIF, BMP, TIFF, ICO, **HEIC/HEIF**
- **格式保持不变** — 压缩前后格式一致（JPEG→JPEG, PNG→PNG, HEIC→HEIC...）
- **批量处理** — 支持单个文件、多个文件、整个目录
- **递归扫描** — 自动处理子目录中的图片
- **多线程加速** — 批量压缩时并发处理，速度更快
- **元数据剥离** — 可选择剥离 EXIF 等冗余元数据节省空间

## 安装

```bash
# 安装依赖（包含 HEIC/HEIF 支持）
pip install -r requirements.txt
```

## 使用说明

### 基础用法

```bash
# 压缩单张图片
python image_compressor.py photo.jpg

# 压缩整个目录
python image_compressor.py ./my_photos/

# 递归压缩目录（含子目录）
python image_compressor.py ./my_photos/ -r

# 指定输出目录
python image_compressor.py ./input/ -o ./output/

# 同时压缩多个文件或目录
python image_compressor.py img1.jpg img2.png ./folder/
```

### 高级选项

```bash
# 调整压缩质量（1-100，默认 85）
python image_compressor.py photo.jpg -q 80

# 启用多线程加速（批量处理时）
python image_compressor.py ./photos/ -w 4 -r

# 保留元数据（EXIF 信息）
python image_compressor.py photo.jpg --no-strip-metadata

# JPEG 色度采样控制
# 0=4:4:4(最佳色彩), 1=4:2:2, 2=4:2:0(最小体积)
python image_compressor.py photo.jpg --subsampling 1

# 预览模式（不实际压缩）
python image_compressor.py ./photos/ --dry-run

# 查看支持的格式
python image_compressor.py --list-formats

# 查看完整帮助
python image_compressor.py --help
```

### Windows 快捷使用

1. **拖放文件/文件夹到批处理文件**：将文件或文件夹拖到 `compress.bat` 上即可自动压缩
2. **发送到菜单**：将 `compress.bat` 放到 `SendTo` 文件夹，右键菜单直接使用

## 压缩策略

| 格式 | 压缩方式 | 说明 |
|------|---------|------|
| JPEG | 质量调整 + Huffman 优化 + 渐进编码 | `quality=85` 视觉无损，节省 20-50% |
| PNG | 颜色深度优化 + 最大压缩级别 | 自动降低色深，节省 20-80% |
| WebP | 质量参数 + method=6 最佳压缩 | 现代格式，比 JPEG 小 25-35% |
| GIF | 调色板优化 | 保留动画，优化颜色表 |
| BMP | RLE 压缩（8-bit 以下） | 高位深 BMP 压缩空间有限 |
| TIFF | LZW 无损压缩 | 无损，适合存档 |
| ICO | 保持原样 | 图标格式压缩空间有限 |
| HEIC/HEIF | 质量参数压缩 (默认 80) | 苹果 iPhone 格式，需安装 `pillow-heif` |

## 压缩效果参考

| 图片类型 | 原大小 | 压缩后 | 节省 | 质量 |
|---------|--------|--------|------|------|
| 3000×2000 照片 | 545 KB | 124 KB | **77%** | 视觉无损 |
| 2000×2000 带透明 PNG | 55 KB | 43 KB | **23%** | 无损 |
| 1024×768 TIFF | 2.25 MB | 27 KB | **99%** | 无损 |

## 常见问题

**Q: 压缩后图片质量会下降吗？**
A: 默认质量 85 被公认为视觉无损阈值，人眼无法分辨与原图的区别。

**Q: 原图会被修改吗？**
A: 不会。原图始终保持不变，压缩后的图片保存在独立的输出目录中。

**Q: 支持哪些图片格式？**
A: JPEG/JPG, PNG, WebP, GIF, BMP, TIFF/TIF, ICO。
