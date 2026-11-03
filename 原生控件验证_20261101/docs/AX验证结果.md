# AX 验证结果（v0.3 主矩阵、中文输入及历史对照）

日期：2026-11-01。本次只读取已保存的 NativeControlDemo 合成数据，没有重新发起 AX 查询，没有查看其他应用的 AX 内容，也未启动 GUI、切换窗口或发送输入。统计产物为 [research/ax-audit.json](../research/ax-audit.json)，保留原有 7 条记录并追加 7 条，按批次和版本区分。

**已取得有效的原生直显 AX 阳性对照：** v0.3 `direct` 可以返回题目、编辑标签、实际输入值和滚动文本。中文提交后的 `raster-protected` 中可读到公共标题，但本次树遍历没有读到题目或输入“你好”。`raster-baseline` 同样没有读到敏感文字，所以这一差异不能归因于 `preventsCapture`；更不能据此宣称已阻止所有 AX 访问或完成了无障碍支持。

## 1. 解析方法与证据范围

解析分两层：先解析 `*-input.json` 的 CLI 调用封装，再解析其中 `stdout` 的 JSON；**只遍历 `axTree` 下的 title、value、description、selectedText、help 字符串属性**。命令参数、路径、文件名、外层说明及应用 state 中的 currentText 均不参与匹配。匹配时将文字转为大写并移除非 ASCII 字母数字，分别检查 `EXAMSECRET`、`NATIVEEDIT`、`INPUTSECRET`、`SCROLLSECRET`。次数按返回属性里的出现次数计算，不代表独立泄漏次数。

新增两项辅助匹配：`PUBLIC-CONTROL` 用相同 ASCII 规则检查公共标题；中文 `你好` 直接做原文字面匹配，不经过 ASCII 清洗。`*-observation.json` 中 AX 查询前后的 Demo 状态仅用来判断样本状态，不计入 AX 命中。14 条保存记录均正常退出、`AXIsProcessTrusted=true`、`axTreeTruncated=false`，但仍有属性查询错误码；JSON 摘要保留错误码分布和来源文件 SHA-256。没有截断的树遍历不等于穷尽全部 AX 属性或入口。

## 2. v0.3 有效主模式与一次状态受限观察

批次：[native-final-v03-20261101T133147Z](../artifacts/native-final-v03-20261101T133147Z)。三种主模式均完成 8/8 项交互状态检查；这不自动决定 AX 查询阶段是否处于相同前台状态。

| 模式 | 节点 | EXAM | NATIVE-EDIT | INPUTSECRET | SCROLL | PUBLIC | AX 查询时状态 |
|---|---:|---:|---:|---:|---:|---:|---|
| direct | 119 | 1 | 1 | 1 | 35 | 1 | 活跃、key window、非最小化 |
| raster-baseline | 104 | 0 | 0 | 0 | 0 | 1 | 活跃、key window、非最小化 |
| raster-protected | 95 | 0 | 0 | 0 | 0 | 0 | 非活跃、非 key window；visible=true，非最小化 |

`direct` 的敏感值明确来自 AX 属性：`AXStaticText.value` 含 `EXAM-SECRET-7K9Q` 与 `NATIVE-EDIT-6T2W`；`AXTextField.value` 为 `INPUTSECRETFINAL7H5T`；`AXTextArea.value` 中有 35 行 `SCROLL-SECRET-9J4V`。这证明已有授权的独立 AX 客户端能读取当前原生直显内容。

主矩阵保护模式的 AX 前后观察均为 `appActive=false`、`windowKey=false`，并且连公共标题也没有命中。这条记录可保留为当时的观察，**不能作为“完整目标 UI 已被遍历但敏感值全被屏蔽”的证据**。后面的中文批次补充了处于活跃状态且公共标题阳性的保护模式记录。

同批 `mixed` 只通过 3/8 交互检查，AX 查询时也非活跃且没有公共标题；它的 95 节点、四种秘密标记均 0 的结果已保留在 JSON 中，但不纳入这组三种有效主模式的验收结论，也不将其作为普通 overlay 已获得安全性的证据。

## 3. v0.3 中文提交后的 AX

批次：[native-ime-20261101T134127Z](../artifacts/native-ime-20261101T134127Z)。AX 在空格提交“你好”之后执行；三个模式查询前后均为 `appActive=true`、`windowKey=true`、`windowVisible=true`、未最小化。它们和上述 v0.3 主矩阵的 Demo 二进制 SHA-256 均为 `0cbe3e4fafc0cc30b2877940f7c4f814815d2e2748365a5e571f79020a6b4aa1`。

| 模式 | 节点 | EXAM | NATIVE-EDIT | SCROLL | PUBLIC | 中文“你好” |
|---|---:|---:|---:|---:|---:|---:|
| direct | 119 | 1 | 1 | 35 | 1 | 1 |
| raster-baseline | 104 | 0 | 0 | 0 | 1 | 0 |
| raster-protected | 104 | 0 | 0 | 0 | 1 | 0 |

`direct` 的 `你好` 来自 `AXTextField.value`，不是命令参数、截图 OCR 或 Demo state。两个 raster 模式本次均可读公共蓝条标题、公共提示和录制按钮等外壳内容，而未命中合成题目、原生编辑标签、滚动内容或已提交的“你好”。本轮 `INPUTSECRET` 三行均为 0，因为控件值已经换成中文，不能把英文标记阴性直接当成中文输入保密的证据。

**可支持的有限判断：** 在所记录的 v0.3 源窗口从未上屏状态下，本次常规 AX 子树遍历没有返回 raster 画布中这些文字，同时直显对照能读到相同类型的内容。由于无保护的 `raster-baseline` 也如此，证据更符合离屏控件/呈现结构造成的可访问性差异；它没有证明视频 Layer 的捕获策略能管控 AX。

**不能支持的判断：** 本次 AX 不包含中文组合期候选窗查询，不能否定候选内容在其他 AX 入口或其他时刻可读。已确认的显示器/矩形截图候选泄露仍然成立；参见 [中文输入法验证结果.md](中文输入法验证结果.md)。没有对所有参数化属性、焦点入口、菜单入口、延迟更新及任意 AX 客户端行为作穷举验证，也没有通过关闭 AX 来完成无障碍功能验收。

批次 `native-keyboard-20261101T133448Z` 的两种 raster 模式共保存 16 个 `01–08` 输入调用记录，**没有 `ax-*-input.json` 或 `axTree`**。该批次仅能提供双击、拖选、Tab/Shift-Tab、空格/Return 等交互证据，AX 应标记“该批次未测试”，不能计为 0 次泄露。

## 4. 历史记录保留，不与 v0.3 混算

| 已保存的 AX 观察 | 遍历节点 | EXAM-SECRET | NATIVE-EDIT | INPUTSECRET | SCROLL-SECRET |
|---|---:|---:|---:|---:|---:|
| 源窗口从未显示 | 87 | 0 | 0 | 0 | 0 |
| 源窗口主动显示 | 104 | 1 | 1 | 1 | 35 |
| 源窗口显示后隐藏 | 88 | 0 | 0 | 0 | 0 |
| 初批矩阵 direct | 78 | 0 | 0 | 0 | 0 |
| 初批矩阵 raster-baseline | 78 | 0 | 0 | 0 | 0 |
| 初批矩阵 raster-protected | 87 | 0 | 0 | 0 | 0 |
| 初批矩阵 mixed | 88 | 0 | 0 | 0 | 0 |

前三行来自 `source-exposure-control-20261101T132024Z/ax-*-input.json`，后四行来自 v0.2 的 `native-matrix-20261101T132323Z/<mode>/ax-input.json`。原始文件与此前统计数均保留，没有用新结果覆盖旧结果。

**局部阳性已经确认：** 主动显示原生源窗口时，AX 返回了合成题目标记、原生编辑标签、输入内容和滚动文本。35 次滚动标记出现在同一个文本属性中，不是 35 次独立读取试验。它说明原生源控件在这个显示状态下，可以通过已有授权的辅助功能通道提供文字，即使另一呈现窗口使用受保护视频图层，也不能因此认为这些 AX 文字被一起保护。

**阴性不能扩大解释：** 隐藏源窗口的两次遍历没有命中这些标记；但同一“显示后隐藏”阶段的 SCK 源窗口截图实际可读。AX 阴性与像素捕获阳性可以同时出现，两条通道必须分开评价。初批矩阵的 direct 和 raster-baseline 存在前台/可见性与输入检查问题；这两行不能充当完整有效的原生可见窗口 AX 负对照，更不能因 direct 也未命中而宣布所有模式都禁止了 AX 访问。

早期样本存在 Edit 菜单/选择行为问题及前台或可见性变化；运行期间的桌面操作干扰也使部分样本无法维持同等条件。日志能够证明事件被拒绝、失去前台或检查失败，但仅凭这些日志不能把每项变化的责任都归到用户操作。v0.2 初批、v0.3 主矩阵中的不完整 mixed，以及有效 v0.3 主模式与 IME，应按上表分别使用。

此结果不能证明完整无障碍功能可用，也不能证明任意 AX 访问都读不到隐藏内容。生产方案仍须独立决定可访问文本范围，并验证读屏、焦点和输入体验。像素捕获与 AX 文本访问必须各自评估。
