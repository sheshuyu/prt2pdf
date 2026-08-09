# prt2pdf

HWAS 软件 `.prt` 作业试卷 → A4 PDF 转换工具。

解析 `.prt` 二进制格式中的题目图片，按题型（选择题/填空题/解答题）分章节智能排版，生成适合打印的 A4 PDF。

## 功能

- 🖥️ **现代化界面** — pywebview + Vue 3，Apple 风格设计，深浅色自动跟随系统
- 📄 **A4 排版** — 150 DPI，自动缩放题目图片至适合宽度，50px 页边距
- 🏷️ **章节标题** — 自动渲染"选择题""填空题""解答题"，题型分布从文件头动态读取
- 📐 **智能间距** — 选择题紧凑、填空题适中、解答题留足写过程的空间
- 🧱 **块级排版** — 题目 + 题后空白视为不可分割的块，不会被截断在页尾
- 📦 **批量转换** — 扫描整个文件夹，勾选后一次转换，实时进度反馈
- 📝 **日志与路径记忆** — 都存在 `%APPDATA%\prt2pdf\`，界面上可直接打开

## 使用指北

1. 点击「浏览」选择作业文件夹（存放 `.prt` 文件的目录）
2. 勾选要转换的文件（或全选）
3. 选择 PDF 输出目录（留空则与作业文件夹相同）
4. 点击「开始转换」

## 运行环境

- Windows 10 / 11
- **WebView2 运行时** — Windows 11 预装；Windows 10 绝大多数机器已随系统更新安装。
  少数老机器若缺失会启动失败，手动装一下即可（约 2MB）：
  [Microsoft Edge WebView2](https://developer.microsoft.com/microsoft-edge/webview2/)

## 开发

```bash
pip install pillow pywebview
python prt2pdf_webview.py
```

前端在 `web/` 目录，改完刷新窗口即可，没有构建步骤。Vue 和 Inter 字体都已 vendor 到本地，离线可用。

### 打包

```bash
build.bat
```

产物是 `dist\prt2pdf\` 整个目录，分发时一起拷走。

用 onedir 而非 onefile：onefile 每次启动都要把压缩包解压到 `%TEMP%`，实测 1542ms；
onedir 免去这一步，527ms，快约 3 倍。代价是发布形式从单文件变成一个文件夹。

## 项目结构

| 文件 | 说明 |
|------|------|
| `prt2pdf.py` | 核心库：解析 `.prt`、排版、生成 PDF。不依赖任何 GUI |
| `prt2pdf_webview.py` | 界面后端：`Api` 类的方法暴露给前端调用 |
| `web/index.html` | 前端：Vue 3 应用 |
| `web/app.css` | 样式：Apple 风格，CSS 变量管理主题色 |
| `build.bat` | PyInstaller 打包脚本 |

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

界面配色改 `web/app.css` 顶部的 CSS 变量（`--accent` 等），深色模式在 `@media (prefers-color-scheme: dark)` 里。

## 文件存放位置

程序不在 EXE 旁边写文件（EXE 可能放在无写权限的目录），配置和日志统一放在：

```
%APPDATA%\prt2pdf\
├── config.json     上次使用的输入/输出目录
└── prt2pdf.log     转换日志
```

展开就是 `C:\Users\<用户名>\AppData\Roaming\prt2pdf\`。界面上点「查看日志」可直接打开。

## .prt 文件格式

```
头部 63 字节:
  [魔数 qyhisme 7B][零填 12B][版本 1B]
  [选择题数 1B][填空题数 1B][解答题数 1B]   ← 每份试卷不同，动态读取
  [每题答案数 19B]                          ← 做题软件用，排版忽略
  [首图尺寸 ASCII 5B][零填 16B]

随后: 顺序排列的 PNG（前 cntA 张选择 → 中 cntB 张填空 → 后 cntC 张解答）
      每张之间有 20 字节间隔块

尾部: UTF-8 中文试卷标题 + 二进制元数据
```

## 许可

MIT
