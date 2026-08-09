# prt2pdf

HWAS 软件 `.prt` 作业试卷 → A4 PDF 转换工具。

解析 `.prt` 二进制格式中的题目图片，按题型（选择题/填空题/解答题）分章节智能排版，生成适合打印的 A4 PDF。

## 功能

- 🖥️ **图形界面** — 批量选择、一键转换，无需命令行
- 📄 **A4 排版** — 150 DPI，自动缩放题目图片至适合宽度，50px 页边距
- 🏷️ **章节标题** — 自动渲染"选择题""填空题""解答题"标题，题型分布从文件头动态读取
- 📐 **智能间距** — 不同题型使用不同间距：选择紧凑、填空适中、解答题留足写过程空间
- 📝 **日志文件** — 转换详情写入 `%APPDATA%\prt2pdf\prt2pdf.log`，界面上点「查看日志」可直接打开
- 💾 **路径记忆** — 上次用的输入/输出目录存在 `%APPDATA%\prt2pdf\config.json`，下次启动自动填入

## 使用指北

1. 点击「浏览」选择作业文件夹（存放 `.prt` 文件的目录）
2. 勾选要转换的文件（或全选）
3. 选择 PDF 输出目录
4. 点击「转换选中文件」

## 开发

```bash
pip install pillow customtkinter
python prt2pdf_gui.py
```

### 打包

```bash
build.bat
```

产物是 `dist\prt2pdf\` 整个目录，分发时一起拷走。

用 onedir 而非 onefile：onefile 每次启动都要把压缩包解压到 `%TEMP%`，实测约 2.1s；
onedir 免去这一步，约 0.33s。代价是发布形式从单文件变成一个文件夹。

## 项目结构

| 文件 | 说明 |
|------|------|
| `prt2pdf.py` | 核心库：解析 `.prt`、排版、生成 PDF。不依赖任何 GUI |
| `prt2pdf_gui.py` | CustomTkinter 界面 |
| `build.bat` | PyInstaller 打包脚本 |
| `icon.ico` | 应用图标（窗口 + EXE，含 16~256px 六种尺寸） |

核心库与界面完全解耦，`prt2pdf.py` 只暴露四个函数：
`setup_logging` / `quick_scan` / `parse_prt` / `render_pdf`。换界面框架不需要动它。

## 可调参数

编辑 `prt2pdf.py` 顶部的常量：

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `GAP_CHOICE` | 60px | 选择题之间间距 |
| `GAP_FILL` | 60px | 填空题之间间距 |
| `GAP_COMP` | 550px | 解答题之间间距（留写过程空间） |
| `GAP_SECTION` | 100px | 章节标题上方留白 |
| `GAP_AFTER_TITLE` | 20px | 标题与本节首题的间距 |
| `MIN_GAP_RATIO` | 0.4 | 间距压缩底线，低于此比例则整块移到下一页 |
| `TITLE_FONT_SIZE` | 30 | 章节标题字号 |
| `A4_W` / `A4_H` | 1240×1754 | A4 画布尺寸（150 DPI） |
| `MARGIN` | 50px | 页边距 |

界面配色改 `prt2pdf_gui.py` 顶部的 `ORANGE` / `CLR_*` 常量，每个是 `[浅色, 深色]` 两个值。

## 文件存放位置

程序不在 EXE 旁边写任何文件（EXE 可能放在无写权限的目录），配置和日志统一放在：

```
%APPDATA%\prt2pdf\
├── config.json     上次使用的输入/输出目录
└── prt2pdf.log     转换日志
```

展开就是 `C:\Users\<用户名>\AppData\Roaming\prt2pdf\`。界面右上角「查看日志」可直接打开。

## 许可

MIT
