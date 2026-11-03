# 本次深度调研（2026-11-01）

本文件夹独立保存本轮工作，父目录上一轮文档、源码及原始证据保留。最终可供他人独立审阅的Word报告在：

**[macOS考试窗口防截屏_深度技术预研与验证报告_v2.0.docx](交付报告/macOS考试窗口防截屏_深度技术预研与验证报告_v2.0.docx)**

报告包含真实截图、版本与权限表、五模式基础矩阵、扩展捕获入口、同进程回采、动态切换/最小化恢复、ClearKey有效加密媒体、AAC及系统路线、复现与未验证事项。图已嵌入Word，审阅报告无需访问本地截图文件。

本轮新增12个渲染/捕获case，17条流、1644张流PNG逐帧分析；另有5组ClearKey媒体对照，共205张图核验。自录与系统录屏共15个视频完整解码无输入时间戳倒退，内容语义仍限于代表帧。上一轮463张流帧另列，不混为本轮新增样本。

## 详细证据

- [深度测试结果](docs/深度测试结果.md)
- [Clear Key有效媒体实验](docs/ClearKey有效媒体实验.md)
- [深度复核与审阅问题](docs/深度复核与审阅问题.md)
- [证据审计](docs/证据审计.md)
- [实验设计独立审阅](docs/实验设计独立审阅.md)
- [视频完整性校验说明](docs/视频完整性校验说明.md)

`artifacts/latest-deep-matrix.txt` 指向最终有效矩阵。最早扩展探针的JSON崩溃目录保留为无效记录；不参与成功样本统计。PNG、CSV、JSON、MP4/MOV均在artifacts。官方快照、SDK摘录、测试媒体及生成工具证据在research。

## 构建与复现

```bash
bash scripts/build-demo.sh
bash scripts/build-probe.sh
open build/ExamCaptureDeepDemo.app
python3 scripts/run-deep-tests.py
python3 scripts/analyze-deep-tests.py artifacts/deep-matrix-实际时间戳
```

媒体检查器可按脚本头部说明编译；本机已提供build/InspectMedia。ClearKey复现见其专题文档。运行矩阵会按预定时间切换测试窗口/保护模式，仅用合成内容。需要新的屏幕捕获权限时，由用户通过系统正规授权；不修改TCC数据库。

`交付报告/内部排版检查/` 是Word渲染QA中间文件，不是另一份新增测试证据。报告构建与规范渲染脚本在scripts/review_report；依赖与字体配置已记录。
