# DOCX 构建与渲染环境

2026-11-01 本机核验。仅用于文档构建，不属于防截屏实验结果。

## 依赖来源

本轮工具目录没有 workspace dependency loader，也没有列出的 runtime skill；已检查已安装技能包，未找到对应 loader。**并未使用全局 Python 或项目 venv 冒充托管环境**。从本机 Codex runtime 缓存找到实际托管运行时，其 `runtime.json` 说明 bundleVersion 为 `26.426.12240`，与 documents 技能版本匹配，目标为 darwin/arm64。

- manifest：`/Users/weiyao/.cache/codex-runtimes/codex-primary-runtime/runtime.json`
- Python：`/Users/weiyao/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3`
- Python 版本：3.12.13
- 包目录：`/Users/weiyao/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/lib/python3.12/site-packages`
- 已导入核验：python-docx 1.2.0、pdf2image 1.17.0、Pillow 12.2.0、lxml 6.0.2。

这是依据本机 runtime manifest 直接定位现存依赖，**并非 loader 调用返回**。不需要新建 venv，不需要安装依赖。构建文件和输出放在工作区；不向托管依赖目录写入文件。

## 渲染器与字体

- 规范 renderer：`/Users/weiyao/.codex/plugins/cache/openai-primary-runtime/documents/26.426.12240/skills/documents/render_docx.py`
- `soffice`：`/opt/homebrew/bin/soffice`，指向 `/Applications/LibreOffice.app/Contents/MacOS/soffice`，版本 26.8.1.1。
- `pdftoppm`：`/opt/homebrew/bin/pdftoppm`，版本 26.10.0。
- Homebrew fontconfig：`/opt/homebrew/etc/fonts/fonts.conf`，包含系统字体、用户字体和 Apple Font8 asset 字体目录。
- `fc-match 'PingFang SC'`、`fc-match Arial`、`fc-match 'Songti SC'` 均正常。
- 中文建议 PingFang SC，英文建议 Arial。设置 `w:rFonts` 的 `w:eastAsia`，并删除残留 `eastAsiaTheme` 等主题字体属性；对表格、页眉页脚及标题同样设置，避免局部替换。

**本机特定问题：**裸跑规范 renderer 虽返回成功并生成 PDF/PNG，中文却消失或显示方框，PDF 只有 LibreOffice 内置西文字体。为 renderer 进程设置 `FONTCONFIG_FILE=/opt/homebrew/etc/fonts/fonts.conf` 后，中文恢复且 PDF 嵌入 PingFangSC/Arial。没有修改系统字体配置或用户设置。

## 已验证命令

从工作区运行：

```sh
/Users/weiyao/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 scripts/review_report/environment-smoke/build_smoke.py

scripts/review_report/render.sh \
  scripts/review_report/environment-smoke/smoke.docx \
  --output_dir scripts/review_report/environment-smoke/rendered-fontconfig \
  --emit_pdf --verbose
```

包装脚本只为单次进程设置 fontconfig，随后执行技能原版 `render_docx.py`，不替代其转换逻辑。规范 renderer 内部采用临时 LibreOffice profile。

## Smoke 检查结果

`environment-smoke/rendered-fontconfig/page-1.png` 已打开检查：1 页 A4，中文可见，表格文字完整，截图清晰，页脚正常，没有遮挡、截断或溢出。`pdffonts` 确认已嵌入 PingFangSC-Regular、PingFangSC-Semibold、ArialMT、Arial-BoldMT。原版模板仍可能带部分主题字体，因此正式报告应统一样式。

这个 smoke 验证只证明渲染环境可用，**不能替代最终报告逐页 PNG 审阅**。最终 DOCX 任何内容或排版变更后应重新运行 renderer，检查所有页面再交付。内部 QA 文件不应作为正式报告附件交付。
