# 中文输入法候选窗：离线区域核验

本文件只分析已保存图片，不启动 App、不操作桌面、不注入输入、不新增捕获。原始 IME 测试目录为 `artifacts/native-ime-20261101T134127Z`。所有模式各 16 张原始 PNG（7 张外部截图、6 张源画布参考、3 张自身录像代表帧），合计 48 张。这里的 18 个裁剪及其 18 个 2 倍放大版本是派生检查材料，不是额外实验样本。

## 关键结果

`raster-protected` 的原生画布在已检查截图中被遮蔽，但是**中文输入法独立候选窗仍会被桌面和区域捕获**。候选词“你好”“你好吗”可从 SCK display、SCK rectangle、系统 display 三条路径读取。这是窗口范围之外的真实泄露，不能把原生输入框转为受保护视频帧等同于整个输入交互受到保护。

| 原图路径（各模式内） | direct 字段内容 | raster-baseline 字段内容 | raster-protected 字段内容 | 独立候选窗（三个模式一致） |
|---|---|---|---|---|
| capture-composition/sck-screenshot-display.png | 可读 ni hao | 可读 ni hao | 未读到字段拼音 | 可读你好 |
| capture-composition/sck-screenshot-rectangle.png | 可读 ni hao | 可读 ni hao | 未读到字段拼音 | 可读你好 |
| capture-composition/sck-screenshot-window.png | 可读 ni hao | 可读 ni hao | 未读到字段拼音 | 未包含候选窗 |
| system-composition-display.png | 可读 ni hao | 可读 ni hao | 未读到字段拼音 | 可读你好 |
| capture-committed/sck-screenshot-display.png | 可读你好 | 可读你好 | 未读到字段中文 | 已提交，不作候选窗判断 |
| capture-committed/sck-screenshot-rectangle.png | 可读你好 | 可读你好 | 未读到字段中文 | 已提交，不作候选窗判断 |
| capture-committed/sck-screenshot-window.png | 可读你好 | 可读你好 | 未读到字段中文 | 已提交，不作候选窗判断 |

每个模式 7/7 张外部截图均在本 Demo 页眉范围识别到 PUBLIC-CONTROL；direct 与 raster-baseline 各 7/7 在画布内识别到 EXAM/NATIVE-EDIT；protected 两项均 0/7。protected 候选窗文字在 3/4 条组合输入截图路径可读，已提交字段内容在 3 条路径均未读取到。这里的计数只描述图片结果，不能作为所有输入法状态和所有取屏 API 的完整通过率。

三个模式各自的 `03-commit-source.png`、`ax-ime-source.png`、`final-source.png` 均读取到“你好”；自身录像的 end 代表帧也读取到“你好”。因此本次“外部未读到提交后的中文”有对应源像素和自身录像的阳性参照。自身录像代表帧不属于外部截图。

## 定位与可复核方法

已保存窗口元数据给出的 presentation Quartz 全局范围为 x=306, y=103, width=900, height=622；画布范围为 x=306, y=225, width=900, height=500；输入字段范围为 x=330, y=333, width=840, height=38。独立候选窗范围为 x=320, y=369, width=397, height=28，layer=20。窗口元数据将候选窗 owner 记为 NativeControlDemo / 同一 App PID；只能称其为独立候选窗，不能据此说它属于另一进程。

Vision observation 的归一化边界框以左下角为原点，分析将其中心映射为原图像素，再结合截图原点、2x 缩放映射到 Quartz 左上角全局坐标。候选窗区域优先于画布区域归类，输入字段单列。presentation 之外的背景观察值保留在明细中，但不计入本 Demo 的秘密标记结论。画布内偶见其他软件浮层文字，不能解释为原生题目透出。

- 桌面图 3024×1964：候选窗 cropPixels = [640, 738, 1434, 794]。
- 目标窗口/区域图 1800×1244：候选窗 cropPixels = [28, 532, 822, 588]。
- 源画布和自身录像代表帧 1800×1000：输入字段 cropPixels = [48, 216, 1728, 292]。

`roi-manifest.json` 为 18 个裁剪记录来源路径、来源 SHA256、裁剪坐标、原始候选窗 bounds、派生图路径和 RGB extrema。protected 的 SCK window 候选窗裁剪纯黑；其他三条 composition 路径的裁剪可直接目视中文字。

## OCR 语言设置的限制与修正

通用 InspectMedia 使用 en-US 优先的语言顺序，曾漏识别阳性参照图里的所有“你好”；这个 OCR 阴性不能解释为保护成功。因此新增独立离线分析器 `ChineseROIOCR.swift` / `ChineseROIOCR`，Vision accurate、recognitionLanguages=[zh-Hans]、usesLanguageCorrection=false、revision=3。它识别出源图、录像帧和泄露候选窗中的中文，与目视检查一致。原始通用分析结果保留，没有覆盖其记录。

- `full-images-ocr-zh-Hans.jsonl`：48 张原图的中文专项结果。
- `roi-ocr-zh-Hans.jsonl`：36 张派生裁剪图的中文专项结果。
- `ime-scoped-observations.json`：21 张外部原图的区域归属、标记结果、来源 SHA256、观察框及三模式汇总。
- `roi-ocr.jsonl`：原语言顺序的裁剪 OCR，作为漏识别问题的可复核记录。

离线专项分析没有测量未取样视频帧，也没有验证 UU/ToDesk 新远程会话；以上结论仅适用于已有本机测试路径和已有输入状态。
