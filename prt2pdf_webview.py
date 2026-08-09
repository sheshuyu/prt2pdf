#!/usr/bin/env python3
"""
prt2pdf — HWAS .prt → A4 PDF 转换工具 (pywebview 界面)

前端在 web/ 目录 (Vue 3 + CSS)，本文件是 Python 后端：
  · Api 类的方法自动暴露为 window.pywebview.api.xxx()，前端 await 调用
  · 转换在工作线程跑，用 evaluate_js 把进度推回前端
  · 配置与日志统一放 %APPDATA%\\prt2pdf\\
"""

import json
import os
import sys
import threading
from pathlib import Path

import webview

from prt2pdf import setup_logging, quick_scan, parse_prt, render_pdf

APP_NAME = 'prt2pdf'
CONFIG_DIR = os.path.join(os.environ.get('APPDATA', os.path.expanduser('~')), APP_NAME)
CONFIG_FILE = os.path.join(CONFIG_DIR, 'config.json')

WIN_W, WIN_H = 910, 610
WIN_MIN = (620, 460)


def resource_path(rel):
    """资源路径，兼容 PyInstaller 打包后的临时解压目录."""
    base = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, rel)


def load_config():
    try:
        with open(CONFIG_FILE, encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def save_config(cfg):
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except OSError:
        pass    # 配置存不下不影响使用


class Api:
    """暴露给前端的接口。方法名即 window.pywebview.api.<name>()."""

    def __init__(self):
        # 必须用下划线开头: pywebview 的 get_functions() 会递归遍历 js_api 的
        # 公开属性来生成 JS 绑定, 遇到 window 对象会一路走进 .NET 属性树直到
        # 递归溢出 (util.py:189 会跳过 _ 开头的名字)
        self._window = None      # webview.start() 前由 main() 注入
        self.cfg = load_config()
        self.busy = False

    # ── 供前端调用 ──────────────────────────────────────────

    def on_ready(self):
        """前端 pywebviewready 后回调，恢复上次使用的路径."""
        in_dir = self.cfg.get('last_input_dir', '')
        out_dir = self.cfg.get('last_output_dir', '')
        if not os.path.isdir(in_dir):
            in_dir = ''
        if out_dir and not os.path.isdir(out_dir):
            out_dir = ''
        if in_dir or out_dir:
            self._js('app.restore(?, ?)', in_dir, out_dir)

    def pick_folder(self, title=''):
        r = self._window.create_file_dialog(webview.FileDialog.FOLDER)
        return r[0] if r else None

    def scan_folder(self, directory):
        """只读文件头快速扫描，不解压 PNG."""
        files = []
        for pf in sorted(Path(directory).glob('*.prt')):
            info = quick_scan(str(pf))
            if info is None:
                info = {
                    'filename': pf.name, 'filepath': str(pf),
                    'section_counts': [0, 0, 0], 'title': '',
                    'total': 0, 'file_size': pf.stat().st_size,
                }
            files.append(info)

        self.cfg['last_input_dir'] = directory
        save_config(self.cfg)
        return files

    def convert(self, filepaths, output_dir):
        """启动后台转换。立即返回，进度由 evaluate_js 推送."""
        if self.busy:
            return False
        self.cfg['last_output_dir'] = output_dir
        save_config(self.cfg)

        self.busy = True
        threading.Thread(
            target=self._work, args=(filepaths, output_dir), daemon=True
        ).start()
        return True

    def open_log(self):
        log = os.path.join(CONFIG_DIR, 'prt2pdf.log')
        try:
            if os.path.isfile(log):
                os.startfile(log)
                return log
            os.makedirs(CONFIG_DIR, exist_ok=True)
            os.startfile(CONFIG_DIR)
            return CONFIG_DIR
        except OSError:
            return None

    # ── 内部 ───────────────────────────────────────────────

    def _js(self, tmpl, *args):
        """调用前端方法。参数经 json.dumps 转义，文件名里的引号/反斜杠不会破坏语句.

        tmpl 里用 ? 占位，例如: _js('app.onProgress(?)', 3)
        """
        for a in args:
            tmpl = tmpl.replace('?', json.dumps(a, ensure_ascii=False), 1)
        try:
            self._window.evaluate_js(tmpl)
        except Exception:
            pass    # 窗口已关闭时静默忽略

    def _work(self, filepaths, output_dir):
        total = len(filepaths)
        ok, failed = 0, []

        try:
            for i, fp in enumerate(filepaths):
                name = os.path.basename(fp)
                out = os.path.join(output_dir, os.path.splitext(name)[0] + '.pdf')

                self._js('app.onFileStart(?, ?, ?, ?)', fp, name, i, total)

                try:
                    images, meta, title, counts = parse_prt(fp)
                    if not images:
                        raise ValueError('无图片数据')
                    pages = render_pdf(images, meta, title, counts, out)
                    ok += 1
                    self._js('app.onFileDone(?, ?, ?)', fp, f'✓ {pages} 页', 'success')
                except Exception as e:
                    failed.append(name)
                    self._js('app.onFileDone(?, ?, ?)', fp, '✗ 失败', 'error')
                    import logging
                    logging.getLogger('prt2pdf').error(f'{name} 转换失败: {e}')

                self._js('app.onProgress(?)', i + 1)
        finally:
            self.busy = False
            self._js('app.onAllDone(?, ?)', ok, failed)


def main():
    os.makedirs(CONFIG_DIR, exist_ok=True)
    setup_logging(log_dir=CONFIG_DIR)

    api = Api()
    window = webview.create_window(
        'HWAS → PDF 转换工具',
        resource_path(os.path.join('web', 'index.html')),
        js_api=api,
        width=WIN_W, height=WIN_H,
        min_size=WIN_MIN,
        background_color='#F2F2F7',
    )
    api._window = window

    # 显式指定 edgechromium: 缺 WebView2 时报错而非静默退到 IE11 白屏
    webview.start(gui='edgechromium')


if __name__ == '__main__':
    main()

