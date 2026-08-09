#!/usr/bin/env python3
"""
HWAS .prt 转 PDF 核心库 (v5)
解析 .prt 文件中的题目图片，按题型分章节智能排版生成 A4 PDF。

供 GUI 调用。日志路径由调用方通过 setup_logging(log_dir=...) 指定，
GUI 传入 %APPDATA%\prt2pdf\ (与 config.json 同目录)。

格式说明:
  .prt 头部 63 字节:
    [魔数 qyhisme 7B][零填 12B][ver 1B][cntA 1B][cntB 1B][cntC 1B]
    [每题答案数 各 1B...][首图尺寸 ASCII 5B][零填 16B]
  cntA/cntB/cntC = 选择题/填空题/解答题的道数 (不同试卷值不同)
  每题答案数字节 = 该题需要提交几个答案 (做题软件用, PDF 排版不需要)
  图片按顺序: 前 cntA 张选择, 中间 cntB 张填空, 最后 cntC 张解答
"""

import sys
import struct
import os
import logging
from io import BytesIO
from PIL import Image

logger = logging.getLogger('prt2pdf')


def setup_logging(log_dir=None):
    """配置日志输出到文件。目录不存在时自动创建，失败则静默降级。"""
    if log_dir is None:
        log_dir = os.path.dirname(os.path.abspath(sys.argv[0])) if getattr(sys, 'frozen', False) else os.getcwd()

    try:
        os.makedirs(log_dir, exist_ok=True)
        handler = logging.FileHandler(os.path.join(log_dir, 'prt2pdf.log'), encoding='utf-8')
    except OSError:
        # 无法写日志文件时不影响主程序运行
        handler = logging.NullHandler()

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s',
        datefmt='%H:%M:%S',
        handlers=[handler],
        force=True,
    )

# ═══════════════════════════════════════════════════════════════
#  可调参数
# ═══════════════════════════════════════════════════════════════

A4_W = 1240
A4_H = 1754
MARGIN = 50

# 间距
GAP_CHOICE  =  60   # 选择题之间
GAP_FILL    =  60   # 填空题之间
GAP_COMP    = 600   # 解答题之间
GAP_SECTION = 100   # 章节标题上

# 间距压缩底线: 实际间距不低于目标间距的这个比例
# 低于此比例说明"这页塞不下了", 整个块移到下一页
#
# 分题型设置, 因为压缩的代价不一样:
#   选择/填空的间距本来就小 (60px), 压到 20% = 12px 只是排得紧些, 不影响做题
#   解答题的间距是留给写过程的 (600px), 压得太狠就不够写了, 所以底线抬高,
#   宁可整题挪到下一页也要保住书写空间
MIN_GAP_RATIO_CHOICE = 0.5   # 选择题
MIN_GAP_RATIO_FILL   = 0.5   # 填空题
MIN_GAP_RATIO_COMP   = 0.9   # 解答题
MIN_GAP_RATIO_TITLE  = 0.5   # 章节标题后 (标题和首题贴太近不好看)

# 章节标题样式
TITLE_FONT_PATH = 'C:/Windows/Fonts/simhei.ttf'   # 黑体, 清晰醒目
TITLE_FONT_SIZE = 30
TITLE_HEIGHT    = 50    # 标题文字区域高度
GAP_AFTER_TITLE = 20    # 标题与本节第一道题之间的间距 (~3mm)

# ═══════════════════════════════════════════════════════════════

PNG_MAGIC = b'\x89PNG\r\n\x1a\n'
IEND = b'IEND'

# 题型标签
SEC_LABELS = ['选择题', '填空题', '解答题']
SECTION_NAMES = ['choice', 'fill', 'comp']


def parse_prt(filepath):
    """解析 .prt -> (images, meta_list, title, section_counts)."""
    with open(filepath, 'rb') as f:
        data = f.read()

    fname = os.path.basename(filepath)
    logger.info(f"解析: {fname}  ({len(data):,} bytes)")

    # ── 头部 ──
    png_start = data.find(PNG_MAGIC)
    header = data[:png_start]

    # 验证魔数
    if header[:7] != b'qyhisme':
        logger.warning(f"魔数不匹配: {header[:7]!r}")

    # 题型分布: [cntA, cntB, cntC] = [选择题数, 填空题数, 解答题数]
    section_counts = list(header[21:24])
    # 每题答案数 (做题软件用, PDF 排版不参与)
    answer_counts = list(header[24:])

    # 尾部标题
    last_end = _find_last_png_end(data)
    title = _decode_title(data[last_end:])

    # 提取 PNG
    images, meta = _extract(data, answer_counts, section_counts)

    total = sum(section_counts)
    logger.info(f"{len(images)} 张题目图片")
    if title:
        logger.info(f"标题: {title}")
    logger.info(f"题型分布: 选择 {section_counts[0]} 道, "
                f"填空 {section_counts[1]} 道, 解答 {section_counts[2]} 道 "
                f"(共 {total} 道)")
    logger.debug(f"每题答案数: {answer_counts[:total]}")

    return images, meta, title, section_counts


def quick_scan(filepath):
    """快速扫描 .prt 文件头，不解压 PNG。

    返回 dict: {filename, section_counts, title, total, file_size}
    失败返回 None。
    """
    try:
        with open(filepath, 'rb') as f:
            data = f.read()

        png_start = data.find(PNG_MAGIC)
        if png_start == -1:
            return None

        header = data[:png_start]
        if header[:7] != b'qyhisme':
            return None

        section_counts = list(header[21:24])
        total = sum(section_counts)

        # 尾部标题
        last_end = _find_last_png_end(data)
        title = _decode_title(data[last_end:])

        return {
            'filename': os.path.basename(filepath),
            'filepath': filepath,
            'section_counts': section_counts,
            'title': title or '',
            'total': total,
            'file_size': len(data),
        }
    except Exception:
        return None


def _find_last_png_end(data):
    p = off = 0
    while True:
        p = data.find(PNG_MAGIC, p)
        if p == -1:
            break
        pos = p + 8
        while pos + 8 <= len(data):
            cl = struct.unpack('>I', data[pos:pos + 4])[0]
            ct = data[pos + 4:pos + 8]
            pos += 8 + cl + 4
            if ct == IEND:
                off = pos
                break
        p = pos
    return off


def _decode_title(trailing):
    """从尾部数据解码 UTF-8 标题."""
    for i in range(min(10, len(trailing))):
        if trailing[i] >= 0xE0:
            j, result = i, []
            while j < len(trailing) and trailing[j] != 0:
                if trailing[j] & 0xE0 == 0xC0:
                    sl = 2
                elif trailing[j] & 0xF0 == 0xE0:
                    sl = 3
                elif trailing[j] & 0xF8 == 0xF0:
                    sl = 4
                else:
                    if trailing[j] < 0x80:
                        result.append(chr(trailing[j]))
                    j += 1
                    continue
                if j + sl <= len(trailing):
                    try:
                        result.append(trailing[j:j + sl].decode('utf-8'))
                    except UnicodeDecodeError:
                        break
                    j += sl
                else:
                    break
            title = ''.join(result).strip()
            if any('一' <= c <= '鿿' for c in title):
                return title
            break
    return None


def _extract(data, answer_counts, section_counts):
    """提取所有 PNG 并分配题型."""
    images, meta = [], []
    p = idx = 0
    cnt_a, cnt_b = section_counts[0], section_counts[1]

    while True:
        p = data.find(PNG_MAGIC, p)
        if p == -1:
            break
        w = struct.unpack('>I', data[p + 16:p + 20])[0]
        h = struct.unpack('>I', data[p + 20:p + 24])[0]
        pos = p + 8
        while pos + 8 <= len(data):
            cl = struct.unpack('>I', data[pos:pos + 4])[0]
            ct = data[pos + 4:pos + 8]
            pos += 8 + cl + 4
            if ct == IEND:
                try:
                    img = Image.open(BytesIO(data[p:pos]))
                    if img.mode != 'RGB':
                        img = img.convert('RGB')
                    images.append(img)

                    # 根据 section_counts 动态分配题型
                    if idx < cnt_a:
                        section = 'choice'
                    elif idx < cnt_a + cnt_b:
                        section = 'fill'
                    else:
                        section = 'comp'

                    ac = answer_counts[idx] if idx < len(answer_counts) else 0
                    meta.append({
                        'idx': idx,
                        'section': section,
                        'answer_count': ac,
                        'w': w, 'h': h,
                    })
                    idx += 1
                except Exception as e:
                    logger.warning(f"第 {idx + 1} 张损坏: {e}")
                    idx += 1
                break
        p = pos
    return images, meta


def plan_gaps(meta):
    """计算每张图之后的间距.

    间距完全由题目所属题型决定.
    章节之间的分隔由标题图片处理 (GAP_SECTION 内嵌在标题图的上方留白中).
    """
    gaps = []
    for m in meta:
        if m['section'] == 'comp':
            gaps.append((GAP_COMP, '解答题'))
        elif m['section'] == 'fill':
            gaps.append((GAP_FILL, '填空题'))
        else:
            gaps.append((GAP_CHOICE, '选择题'))
    return gaps


def min_gap_ratio(m):
    """取该块的间距压缩底线, 由所属题型决定.

    m 是 meta 字典, 章节标题块带 is_title=True.
    """
    if m.get('is_title'):
        return MIN_GAP_RATIO_TITLE
    if m['section'] == 'comp':
        return MIN_GAP_RATIO_COMP
    if m['section'] == 'fill':
        return MIN_GAP_RATIO_FILL
    return MIN_GAP_RATIO_CHOICE


def make_section_title(text, width, top_padding=0):
    """创建章节标题图片.

    标题是白色背景的小图片, 上方可选留白用于与前节的间距.
    top_padding > 0 时, 标题文字位于图片偏下方, 上方留白充当章节分隔.
    """
    from PIL import ImageDraw, ImageFont

    h = top_padding + TITLE_HEIGHT
    img = Image.new('RGB', (width, h), 'white')
    draw = ImageDraw.Draw(img)

    # 加载中文字体
    try:
        font = ImageFont.truetype(TITLE_FONT_PATH, TITLE_FONT_SIZE)
    except OSError:
        # 回退: 尝试微软雅黑
        try:
            font = ImageFont.truetype('C:/Windows/Fonts/msyh.ttc', TITLE_FONT_SIZE)
        except OSError:
            font = ImageFont.load_default()

    # 居中绘制
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    x = (width - tw) // 2
    y = top_padding + (TITLE_HEIGHT - (bbox[3] - bbox[1])) // 2
    draw.text((x, y), text, fill='black', font=font)
    return img


def render_pdf(images, meta, title, section_counts, output_path):
    """排版并保存 PDF."""
    usable_w = A4_W - 2 * MARGIN
    gaps = plan_gaps(meta)

    # 缩放
    scaled = []
    for img in images:
        r = usable_w / img.width
        scaled.append(img.resize((usable_w, int(img.height * r)), Image.LANCZOS))

    # ── 构建章节标题 ──
    # 各节首题索引 (e.g. [0, 9, 15] for [9,6,4])
    section_starts = [0]
    cum = 0
    for c in section_counts[:-1]:
        cum += c
        section_starts.append(cum)

    # 动态生成章节标签 (e.g. "选择题", "填空题")
    section_labels = []
    for i, cnt in enumerate(section_counts):
        if cnt > 0:
            section_labels.append(SEC_LABELS[i])

    # 把标题图片插入到题目流中
    # items = [(image, meta_dict, (gap, reason)), ...]
    items = []
    for img, m, gap_info in zip(scaled, meta, gaps):
        idx = m['idx']

        if idx in section_starts:
            sec_i = section_starts.index(idx)
            # 第一节标题无上方留白 (已在页顶), 后续节用 GAP_SECTION 作为章节间隔
            top_pad = 0 if idx == 0 else GAP_SECTION
            title_img = make_section_title(section_labels[sec_i], usable_w, top_pad)
            title_meta = {
                'idx': -1, 'section': 'title', 'is_title': True,
                'answer_count': 0, 'w': usable_w, 'h': title_img.height,
            }
            items.append((title_img, title_meta, (GAP_AFTER_TITLE, '标题')))

        items.append((img, m, gap_info))

    # ── 排版计划表 (写入日志) ──
    sec_short = ['选择', '填空', '解答']

    logger.debug("─" * 50)
    for si, (start, cnt) in enumerate(zip(section_starts, section_counts)):
        if cnt > 0:
            logger.debug(f"── {section_labels[si]} ({cnt}道) " + "─" * 30)
        for i in range(start, start + cnt):
            m = meta[i]
            img = scaled[i]
            gap, reason = gaps[i]
            ac = m['answer_count']
            logger.debug(f"  [{i:2d}] {m['w']:4d}x{m['h']:<4d} -> "
                         f"{img.width:4d}x{img.height:<5d} {sec_short[si]:>4s}"
                         f"  答案×{ac}   后 {gap:3d}px  {reason}")

    # ── 排版到页面 ──
    # 核心概念: 标题图片也是块, 和题目图片一样参与排版,
    # 保证标题不会被单独留在页尾而第一道题在下一页.
    pages = []
    page = Image.new('RGB', (A4_W, A4_H), 'white')
    y = MARGIN
    page_max = A4_H - MARGIN
    page_no = 1

    for img, m, (gap_after, reason) in items:
        is_title = m.get('is_title', False)
        need_h = img.height
        full_block = need_h + gap_after
        remaining = page_max - y
        avail_for_gap = remaining - need_h
        min_gap = int(gap_after * min_gap_ratio(m))

        # 情况1: 整块放得下 → 全额间距
        if y + full_block <= page_max:
            page.paste(img, (MARGIN, y))
            y += full_block

        # 情况2: 图片/标题本身放不下 → 强制换页
        elif need_h > remaining:
            pages.append(page)
            page = Image.new('RGB', (A4_W, A4_H), 'white')
            y = MARGIN
            page.paste(img, (MARGIN, y))
            y += full_block
            page_no += 1
            if is_title:
                logger.debug(f"换页 {page_no}: 标题 放不下 ({need_h}px > {remaining}px)")
            else:
                logger.debug(f"换页 {page_no}: 第{m['idx']+1}题 图片放不下 ({need_h}px > {remaining}px)")

        # 情况3: 图放得下但整块放不下 → 压缩间距收尾
        elif avail_for_gap >= min_gap:
            page.paste(img, (MARGIN, y))
            y += need_h + avail_for_gap
            tag = '标题' if is_title else f"第{m['idx']+1}题"
            logger.debug(f"页尾: {tag} 间距 {gap_after}→{avail_for_gap}px "
                         f"({(1 - avail_for_gap/gap_after)*100:.0f}%压缩)")

        # 情况4: 压缩后间距低于底线 → 整块移到下一页
        else:
            pages.append(page)
            page = Image.new('RGB', (A4_W, A4_H), 'white')
            y = MARGIN
            page.paste(img, (MARGIN, y))
            y += full_block
            page_no += 1
            tag = '标题' if is_title else f"第{m['idx']+1}题"
            logger.debug(f"块迁移 {page_no}: {tag}({reason}) 剩余{avail_for_gap}px "
                         f"< 底线{min_gap}px({min_gap_ratio(m):.0%}), 整块移到新页")

    pages.append(page)

    # ── 保存 ──
    pages[0].save(output_path, 'PDF', save_all=True,
                  append_images=pages[1:], resolution=150.0)

    # ── 统计 (写入日志) ──
    counts = [sum(1 for m in meta if m['section'] == s) for s in SECTION_NAMES]
    logger.info(f"PDF -> {output_path}  |  {len(pages)} 页 A4  |  "
                f"选择 {counts[0]} 填空 {counts[1]} 解答 {counts[2]}")

    return len(pages)
