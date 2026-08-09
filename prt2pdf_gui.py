#!/usr/bin/env python3
"""
prt2pdf GUI — HWAS .prt → PDF 图形界面
CustomTkinter 实现，支持批量选择和转换。
"""

import customtkinter as ctk
from tkinter import filedialog
import os
import sys
import json
import threading
from pathlib import Path

from prt2pdf import setup_logging, quick_scan, parse_prt, render_pdf

# ── 配置 ──
APP_NAME = 'prt2pdf'
CONFIG_DIR = os.path.join(os.environ.get('APPDATA', os.path.expanduser('~')), APP_NAME)
CONFIG_FILE = os.path.join(CONFIG_DIR, 'config.json')


def resource_path(relative):
    """获取资源文件路径, 兼容 PyInstaller 打包后的临时解压目录."""
    base = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, relative)

# ── 橘黄主题 ──
# CustomTkinter 内置主题只有 blue/dark-blue/green/gold, 没有橘色, 这里手动覆盖。
# 每个颜色是 [浅色模式, 深色模式] 两个值。
ORANGE       = ['#FB8C00', '#C2410C']   # 主色: 浅色模式用亮橘, 深色模式用深橘
ORANGE_HOVER = ['#E07B00', '#9A3412']
ORANGE_TEXT  = ['#1A1A1A', '#FFFFFF']   # 橘底上的文字: 亮橘配深字 7.3x, 深橘配白字 5.2x

# 状态栏语义色 (已验证在两种背景下对比度均 ≥4.5x, 符合 WCAG AA)
CLR_SUCCESS = ('#166534', '#4ADE80')
CLR_WARNING = ('#854D0E', '#FCD34D')
CLR_ERROR   = ('#B91C1C', '#F87171')
CLR_RUNNING = ('#9A3412', '#FB923C')
CLR_NORMAL  = ('gray10', 'gray90')


def apply_orange_theme():
    """把内置主题的蓝色替换成橘黄色。必须在创建窗口前调用."""
    ctk.set_default_color_theme('blue')
    t = ctk.ThemeManager.theme

    for widget in ('CTkButton', 'CTkCheckBox', 'CTkSwitch', 'CTkRadioButton',
                   'CTkSegmentedButton', 'CTkSlider', 'CTkOptionMenu', 'CTkComboBox'):
        if widget in t:
            t[widget]['fg_color'] = list(ORANGE)
            if 'hover_color' in t[widget]:
                t[widget]['hover_color'] = list(ORANGE_HOVER)
            if 'button_color' in t[widget]:
                t[widget]['button_color'] = list(ORANGE)
            if 'button_hover_color' in t[widget]:
                t[widget]['button_hover_color'] = list(ORANGE_HOVER)

    t['CTkButton']['text_color'] = list(ORANGE_TEXT)
    t['CTkCheckBox']['checkmark_color'] = list(ORANGE_TEXT)
    t['CTkProgressBar']['progress_color'] = list(ORANGE)
    t['CTkSlider']['progress_color'] = list(ORANGE)
    t['CTkEntry']['border_color'] = ['#C9A227', '#8A5A2B']


ctk.set_appearance_mode('system')
apply_orange_theme()


def load_config():
    """加载持久化配置 (上次使用的路径)."""
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def save_config(cfg):
    """保存配置."""
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


class App(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title('HWAS → PDF 转换工具')
        self._center_window(910, 610)
        self.minsize(580, 420)

        # 窗口图标 (覆盖 CustomTkinter 默认 logo)
        try:
            self.iconbitmap(resource_path('icon.ico'))
        except Exception:
            pass    # 图标缺失不影响功能

        # 状态
        self.config = load_config()
        self.files = []          # quick_scan 结果列表
        self.checkboxes = {}     # filepath -> (BooleanVar, CTkCheckBox)
        self.row_status = {}     # filepath -> CTkLabel (每行状态指示)
        self.select_all_var = ctk.BooleanVar(value=True)
        self.converting = False

        # 设置日志
        setup_logging(log_dir=CONFIG_DIR)

        self._build_ui()

        # 自动加载上次目录
        last_dir = self.config.get('last_input_dir', '')
        if last_dir and os.path.isdir(last_dir):
            self.input_var.set(last_dir)
            self._scan_files(last_dir)

    # ═══════════════════════════════════════════════════════════════
    #  UI 构建
    # ═══════════════════════════════════════════════════════════════

    def _build_ui(self):
        # ── 顶部: 输入文件夹 ──
        top_frame = ctk.CTkFrame(self)
        top_frame.pack(fill='x', padx=12, pady=(12, 6))

        ctk.CTkLabel(top_frame, text='作业文件夹:', width=80).pack(side='left', padx=(8, 4))
        self.input_var = ctk.StringVar()
        ctk.CTkEntry(top_frame, textvariable=self.input_var, width=340).pack(side='left', padx=4)
        ctk.CTkButton(top_frame, text='浏览...', width=70, command=self._browse_input).pack(side='left', padx=4)

        # ── 输出目录 ──
        out_frame = ctk.CTkFrame(self)
        out_frame.pack(fill='x', padx=12, pady=(6, 6))

        ctk.CTkLabel(out_frame, text='输出目录:', width=80).pack(side='left', padx=(8, 4))
        self.output_var = ctk.StringVar(value=self.config.get('last_output_dir', ''))
        ctk.CTkEntry(out_frame, textvariable=self.output_var, width=340).pack(side='left', padx=4)
        ctk.CTkButton(out_frame, text='浏览...', width=70, command=self._browse_output).pack(side='left', padx=4)

        # ── 文件列表头部 ──
        list_header = ctk.CTkFrame(self)
        list_header.pack(fill='x', padx=12, pady=(6, 0))

        self.select_all_cb = ctk.CTkCheckBox(
            list_header, text='全选 / 取消全选', variable=self.select_all_var,
            command=self._toggle_select_all
        )
        self.select_all_cb.pack(side='left', padx=(8, 12))

        self.file_count_label = ctk.CTkLabel(list_header, text='')
        self.file_count_label.pack(side='right', padx=8)

        # 日志入口: 配置和日志都在 %APPDATA%\prt2pdf\, 不在 EXE 旁边
        ctk.CTkButton(
            list_header, text='查看日志', width=70, height=24,
            fg_color='transparent', border_width=1,
            text_color=CLR_NORMAL, hover_color=('gray80', 'gray30'),
            command=self._open_log
        ).pack(side='right', padx=4)

        # ── 可滚动文件列表 ──
        self.file_list = ctk.CTkScrollableFrame(self, height=280)
        self.file_list.pack(fill='both', expand=True, padx=12, pady=(4, 6))

        # ── 状态栏: 界面内提示, 取代弹窗 ──
        self.status_label = ctk.CTkLabel(
            self, text='选择作业文件夹开始', anchor='w', height=22
        )
        self.status_label.pack(fill='x', padx=20, pady=(2, 0))

        # ── 底部: 进度 + 按钮 ──
        bottom_frame = ctk.CTkFrame(self)
        bottom_frame.pack(fill='x', padx=12, pady=(4, 12))

        self.progress = ctk.CTkProgressBar(bottom_frame, width=260)
        self.progress.pack(side='left', padx=(12, 8))
        self.progress.set(0)

        self.progress_label = ctk.CTkLabel(bottom_frame, text='', width=60)
        self.progress_label.pack(side='left', padx=4)

        self.convert_btn = ctk.CTkButton(
            bottom_frame, text='▶ 转换选中文件', width=130,
            command=self._start_conversion
        )
        self.convert_btn.pack(side='right', padx=(4, 12))

        self.open_btn = ctk.CTkButton(
            bottom_frame, text='📂 打开输出目录', width=120,
            command=self._open_output
        )
        self.open_btn.pack(side='right', padx=4)

    def _center_window(self, w, h):
        """把窗口摆到屏幕正中。

        geometry() 只给尺寸时 Tk 用系统默认位置(左上偏移), 必须连坐标一起给。
        纵向略微上移: 减去任务栏高度的一半, 视觉上才是居中。
        """
        self.update_idletasks()     # 确保能拿到真实屏幕尺寸
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        x = max(0, (sw - w) // 2)
        y = max(0, (sh - h) // 2 - 24)
        self.geometry(f'{w}x{h}+{x}+{y}')

    def _set_status(self, text, color=None):
        """更新状态栏文字。color=None 使用主题默认色."""
        self.status_label.configure(
            text=text,
            text_color=color if color else CLR_NORMAL
        )

    # ═══════════════════════════════════════════════════════════════
    #  事件处理
    # ═══════════════════════════════════════════════════════════════

    def _browse_input(self):
        path = filedialog.askdirectory(title='选择作业文件夹 (practice)')
        if path:
            self.input_var.set(path)
            self._scan_files(path)

    def _browse_output(self):
        path = filedialog.askdirectory(title='选择 PDF 输出目录')
        if path:
            self.output_var.set(path)

    def _scan_files(self, directory):
        """扫描目录下所有 .prt 文件，快速读取头部信息."""
        # 清空
        for w in self.file_list.winfo_children():
            w.destroy()
        self.checkboxes.clear()
        self.row_status.clear()
        self.files.clear()
        self.progress.set(0)
        self.progress_label.configure(text='')

        prt_files = sorted(Path(directory).glob('*.prt'))
        if not prt_files:
            ctk.CTkLabel(self.file_list, text='未找到 .prt 文件').pack(pady=30)
            self.file_count_label.configure(text='')
            self.select_all_var.set(False)
            self._set_status('该文件夹下没有 .prt 文件', CLR_WARNING)
            return

        for pf in prt_files:
            info = quick_scan(str(pf))
            if info is None:
                info = {
                    'filename': pf.name,
                    'filepath': str(pf),
                    'section_counts': [0, 0, 0],
                    'title': '',
                    'total': 0,
                    'file_size': pf.stat().st_size,
                }
            self.files.append(info)

        self._build_file_list()
        self.file_count_label.configure(text=f'共 {len(self.files)} 个文件')
        self.select_all_var.set(True)
        self._update_selection_status()

    def _build_file_list(self):
        """绘制文件列表."""
        for info in self.files:
            row = ctk.CTkFrame(self.file_list)
            row.pack(fill='x', padx=4, pady=2)

            var = ctk.BooleanVar(value=True)
            cb = ctk.CTkCheckBox(row, text='', variable=var, width=24,
                                 command=self._on_check_changed)
            cb.pack(side='left', padx=(4, 8))
            self.checkboxes[info['filepath']] = (var, cb)

            # 文件名
            name_label = ctk.CTkLabel(row, text=info['filename'], width=170, anchor='w')
            name_label.pack(side='left', padx=4)

            # 题型分布
            sc = info['section_counts']
            sec_text = f"选择 {sc[0]}  填空 {sc[1]}  解答 {sc[2]}"
            sec_label = ctk.CTkLabel(row, text=sec_text, width=170, anchor='w')
            sec_label.pack(side='left', padx=4)

            # 标题
            title_text = info.get('title', '') or ''
            if len(title_text) > 18:
                title_text = title_text[:16] + '…'
            title_label = ctk.CTkLabel(row, text=title_text, width=190, anchor='w')
            title_label.pack(side='left', padx=4)

            # 每行状态指示 (转换时更新)
            status_label = ctk.CTkLabel(row, text='', width=70, anchor='e')
            status_label.pack(side='right', padx=(4, 8))
            self.row_status[info['filepath']] = status_label

            # 文件大小
            size_kb = info['file_size'] / 1024
            size_label = ctk.CTkLabel(row, text=f'{size_kb:.0f} KB', width=55, anchor='e')
            size_label.pack(side='right', padx=4)

            # 损坏文件标红
            if info['total'] == 0:
                name_label.configure(text_color=CLR_ERROR)
                sec_label.configure(text='⚠ 无法识别', text_color=CLR_ERROR)
                status_label.configure(text='⚠ 损坏', text_color=CLR_ERROR)

    def _toggle_select_all(self):
        state = self.select_all_var.get()
        for var, _ in self.checkboxes.values():
            var.set(state)
        self._update_selection_status()

    def _on_check_changed(self):
        """单个勾选变化时，同步全选复选框状态并刷新状态栏."""
        all_vars = [var.get() for var, _ in self.checkboxes.values()]
        if all(all_vars):
            self.select_all_var.set(True)
        elif not any(all_vars):
            self.select_all_var.set(False)
        self._update_selection_status()

    def _update_selection_status(self):
        """勾选变化时刷新状态栏。转换过程中不覆盖进度提示."""
        if self.converting or not self.files:
            return

        total = len(self.files)
        selected = self._get_selected_files()
        n = len(selected)
        bad = sum(1 for f in selected if f['total'] == 0)

        if n == 0:
            self._set_status(f'共 {total} 个文件，未勾选任何文件', CLR_WARNING)
        elif bad:
            self._set_status(f'已选 {n}/{total} 个，其中 {bad} 个无法识别（将跳过）', CLR_WARNING)
        elif n == total:
            self._set_status(f'已选全部 {total} 个文件')
        else:
            self._set_status(f'已选 {n}/{total} 个文件')

    def _get_selected_files(self):
        return [info for info in self.files
                if self.checkboxes.get(info['filepath'], (None,))[0].get()]

    # ═══════════════════════════════════════════════════════════════
    #  转换
    # ═══════════════════════════════════════════════════════════════

    def _start_conversion(self):
        if self.converting:
            return

        selected = self._get_selected_files()
        if not selected:
            self._set_status('请至少勾选一个 .prt 文件', CLR_WARNING)
            return

        output_dir = self.output_var.get().strip()
        if not output_dir:
            # 默认输出到输入目录
            output_dir = self.input_var.get().strip()
            self.output_var.set(output_dir)

        if not output_dir:
            self._set_status('请先选择输出目录', CLR_WARNING)
            return

        if not os.path.isdir(output_dir):
            try:
                os.makedirs(output_dir, exist_ok=True)
            except OSError as e:
                self._set_status(f'无法创建输出目录: {e}', CLR_ERROR)
                return

        # 保存路径配置
        self.config['last_input_dir'] = self.input_var.get()
        self.config['last_output_dir'] = output_dir
        save_config(self.config)

        # 清空上轮的行状态
        for fp, label in self.row_status.items():
            info = next((f for f in self.files if f['filepath'] == fp), None)
            if info and info['total'] == 0:
                continue    # 保留损坏标记
            label.configure(text='', text_color=CLR_NORMAL)

        # 后台线程执行
        self.converting = True
        self.convert_btn.configure(text='转换中...', state='disabled')
        self.progress.set(0)
        self.progress_label.configure(text=f'0/{len(selected)}')
        self._set_status('开始转换...')

        thread = threading.Thread(target=self._convert_all, args=(selected, output_dir), daemon=True)
        thread.start()

    def _convert_all(self, selected, output_dir):
        total = len(selected)
        success = 0
        failed = []

        for i, info in enumerate(selected):
            filepath = info['filepath']
            out_name = os.path.splitext(info['filename'])[0] + '.pdf'
            out_path = os.path.join(output_dir, out_name)

            self.after(0, self._mark_converting, filepath, info['filename'], i, total)

            try:
                images, meta, title, section_counts = parse_prt(filepath)
                if not images:
                    raise ValueError('无图片数据')
                pages = render_pdf(images, meta, title, section_counts, out_path)
                success += 1
                self.after(0, self._mark_row, filepath, f'✓ {pages} 页', CLR_SUCCESS)
            except Exception as e:
                failed.append((info['filename'], str(e)))
                self.after(0, self._mark_row, filepath, '✗ 失败', CLR_ERROR)

            self.after(0, self._update_progress, i + 1, total)

        self.after(0, self._conversion_done, total, success, failed)

    def _mark_converting(self, filepath, filename, current, total):
        """标记当前正在转换的文件."""
        label = self.row_status.get(filepath)
        if label:
            label.configure(text='转换中', text_color=CLR_RUNNING)
        self._set_status(f'正在转换 ({current + 1}/{total}): {filename}')

    def _mark_row(self, filepath, text, color):
        label = self.row_status.get(filepath)
        if label:
            label.configure(text=text, text_color=color)

    def _update_progress(self, done, total):
        self.progress.set(done / total if total > 0 else 0)
        self.progress_label.configure(text=f'{done}/{total}')

    def _conversion_done(self, total, success, failed):
        self.converting = False
        self.convert_btn.configure(text='▶ 转换选中文件', state='normal')
        self.progress.set(1.0)

        if not failed:
            self._set_status(f'✓ 全部完成: {success} 个 PDF 已生成', CLR_SUCCESS)
        elif success == 0:
            names = ', '.join(n for n, _ in failed[:3])
            more = f' 等 {len(failed)} 个' if len(failed) > 3 else ''
            self._set_status(f'✗ 全部失败: {names}{more}（详见 prt2pdf.log）', CLR_ERROR)
        else:
            self._set_status(
                f'完成 {success} 个，失败 {len(failed)} 个（详见 prt2pdf.log）', CLR_WARNING
            )

    def _open_output(self):
        path = self.output_var.get().strip()
        if path and os.path.isdir(path):
            os.startfile(path)
        else:
            self._set_status('输出目录不存在，请先选择', CLR_WARNING)

    def _open_log(self):
        """打开日志文件。配置和日志都在 %APPDATA%\\prt2pdf\\."""
        log_path = os.path.join(CONFIG_DIR, 'prt2pdf.log')
        if os.path.exists(log_path):
            os.startfile(log_path)
            self._set_status(f'日志位置: {log_path}')
        else:
            os.makedirs(CONFIG_DIR, exist_ok=True)
            os.startfile(CONFIG_DIR)
            self._set_status(f'日志尚未生成，已打开目录: {CONFIG_DIR}', CLR_WARNING)


if __name__ == '__main__':
    app = App()
    app.mainloop()
