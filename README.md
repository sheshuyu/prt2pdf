# prt2pdf

山东大学物理作业提交软件 HWAS 练习卷个格式 `.prt` → PDF 转换工具。

解析 `.prt` 二进制格式中的题目图片，按题型（选择题/填空题/解答题）智能排版，生成 A4 PDF。

## 功能

- 🖥️ **现代化界面** — pywebview + Vue 3，深浅色自动跟随系统
- 📄 **A4 排版** — 自动缩放题目图片至适合宽度
- 🏷️ **章节标题** — 自动渲染"选择题""填空题""解答题"，题型分布从文件头动态读取
- 📐 **智能间距** — 选择题紧凑、填空题适中、解答题留足写过程的空间
- 📦 **批量转换** — 扫描整个文件夹，勾选后一次转换，实时进度反馈
- 📝 **日志与路径记忆** — 都存在 `C:\Users\<用户名>\AppData\Roaming\prt2pdf\`，界面上可直接打开

## 使用指北
1. 双击运行 `prt2pdf.exe`
2. 启动后自动定位默认 HWAS 的练习题目录， 默认为 `C:\Users\<用户名>\AppData\Local\Programs\hwas\practice`。 

   点击「浏览」可以更改practice文件夹路径。 
   
   右键hwas图标，点击打开文件所在位置，即可找到practice文件夹

3. 勾选要转换的文件（或全选）
4. 选择 PDF 输出目录（留空则与作业文件夹相同）
5. 点击「开始转换」

PDF 统一存到所选输出目录下的 `practice\` 子文件夹：

```
你选的输出目录\
└── practice\
    ├── practice1.pdf
    ├── practice2.pdf
    └── ...
```

转换完成后界面上会出现「打开输出文件夹」按钮，直接跳到这个目录。
如果选的输出目录本身就叫 `practice`，不会再套一层。

## 运行环境

- Windows 10 / 11
- **WebView2 运行时** — Windows 11 预装；Windows 10 绝大多数机器已随系统更新安装。
  少数老机器若缺失会启动失败，手动装一下即可（约 2MB）：
  [Microsoft Edge WebView2](https://developer.microsoft.com/microsoft-edge/webview2/)

### 打包

- 双击运行 `build.bat` 自动打包

- 产物是 `dist\prt2pdf\` 整个目录，分发时一起拷走。


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
