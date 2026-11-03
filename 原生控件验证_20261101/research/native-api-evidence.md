# 原生控件离屏渲染：Apple API 与本机 SDK 依据

> 执行状态补充：本文件保留设计阶段的API/实验要求口径。现已完成有限交互、捕获、源窗口及真实IME实验，实际成功、失败和待验证项请以[专项验证报告](../docs/原生控件验证报告.md)为准；不得把下文设计阶段的“待验证”误认为最终执行统计。
核验日期：2026-11-01。范围：本轮原生控件验证的接口语义与实验设计依据。此文件不记载尚未完成的实验结果，也不把旧版自绘画布验证结果迁移为原生编辑控件已验证。

本机使用 `/Library/Developer/CommandLineTools/SDKs/MacOSX.sdk`，`SDKSettings.plist` 的 `Version=26.5`、`CanonicalName=macosx26.5`。在线 Apple 文档与本机头文件均只证明公开接口存在及其说明，不能证明其组合达到防捕获目标。部分历史 AppKit API 的在线 availability 只显示 `macOS: -`，对应 SDK 声明也没有更细的引入版本标注；本轮不据此编造精确最低系统版本。

## 1. 视图绘制到位图

- [Apple：NSView.cacheDisplay(in:to:)](https://developer.apple.com/documentation/appkit/nsview/cachedisplay%28in%3Ato%3A%29)：将指定视图区域及其后代的绘制结果放入传入的 `NSBitmapImageRep`。没有绘制内容的位置可以保持透明。Apple 建议使用配套方法分配位图，以匹配像素格式。
- [Apple：bitmapImageRepForCachingDisplay(in:)](https://developer.apple.com/documentation/appkit/nsview/bitmapimagerepforcachingdisplay%28in%3A%29)：建立适合缓存指定视图区域的位图；可能返回 `nil`。
- SDK：`AppKit.framework/Headers/NSView.h:207` 声明 `displayRectIgnoringOpacity:inContext:`；`:209` 声明 `bitmapImageRepForCachingDisplayInRect:`；`:210` 声明 `cacheDisplayInRect:toBitmapImageRep:`。`:191` 的旧 focus API 弃用说明指向 `displayRectIgnoringOpacity:inContext:` 作为将视图子树绘入上下文的方法。

**可支持的判断：** 可以用公开 AppKit 绘制 API 探索复用原生控件外观，不必预先把全部控件外观手写成绘图命令。

**不能推出的判断：** 单次调用成功不证明所有控件、所有图层、正在编辑的文字、光标、弹窗或输入法候选都进入位图；不保证隐藏窗口的控件可以完整交互；不保证任意现有窗口可直接变成受保护视频。需要逐项检查图像内容，并有同一离屏绘制链路的无保护对照。

## 2. NSTextField 的编辑器不等于标签自身

- [Apple：NSWindow.fieldEditor(_:for:)](https://developer.apple.com/documentation/appkit/nswindow/fieldeditor%28_%3Afor%3A%29)：窗口可以按需建立并返回 field editor。
- [Apple：NSControl.currentEditor()](https://developer.apple.com/documentation/appkit/nscontrol/currenteditor%28%29)：查询当前控件使用的编辑器；没有编辑器时返回 `nil`。
- [Apple：Text Fields, Text Views, and the Field Editor](https://developer.apple.com/library/archive/documentation/TextFonts/Conceptual/CocoaTextArchitecture/TextFieldsAndViews/TextFieldsAndViews.html)：窗口内的轻量文本控件通常共享一个 `NSTextView` field editor。开始编辑后，它加入视图/响应链并承担文字编辑与选择状态。
- [Apple：Intercepting Key Events](https://developer.apple.com/library/archive/documentation/Cocoa/Conceptual/TextEditing/Tasks/InterceptKeys.html)：按键会经过输入上下文处理，随后产生文本插入、命令或 marked text 更新。Return/Tab 等在 field editor 中还具有结束编辑或移动焦点的语义。
- SDK：`NSWindow.h:344` 为 `fieldEditor:forObject:`；`:387–389` 为 `makeFirstResponder:` 和 `firstResponder`；`NSControl.h:88` 为 `currentEditor`。

**实验要求：** 同时记录 `NSTextField.stringValue`、`currentEditor()?.string`、编辑器类名、`selectedRange`、`markedRange`、窗口 `firstResponder` 类名及实际输出图像。编辑尚未提交时不能只看控件最终 `stringValue`，也不能把原生标签的可见性实验等同于可编辑输入框实验。若编辑器由适配器额外绘制，必须明确标注其来源与坐标处理，不能把补画的字符串称为“整个原生控件树已自动捕获”。

## 3. 中文输入法需要完整文本输入协议与坐标适配

- [Apple：NSTextInputClient](https://developer.apple.com/documentation/appkit/nstextinputclient)：自定义文字视图与系统文本输入管理交互的协议；可继承 `NSTextView`，或让自定义 `NSView` 实现该协议。
- SDK `NSTextInputClient.h:37`：`insertText:replacementRange:`；`:45`：`setMarkedText:selectedRange:replacementRange:`；`:53`：`selectedRange`；`:61`：`hasMarkedText`；`:73`：`firstRectForCharacterRange:actualRange:`；`:77`：`characterIndexForPoint:`。
- 该头文件对 marked text 的说明要求组合中的文字有可区分的呈现；字符范围与位置查询涉及实际显示位置。离屏源与屏幕上的受保护呈现不是同一坐标空间。

**实验要求：** 标记文字、候选选择、提交、取消、组合中退格/光标移动分别观察。程序直接调用 `setMarkedText`/`insertText` 只能证明协议代理或编辑器状态的一部分；CGEvent 直接投递 Unicode 字符也可能跳过真实输入法组合，不能据此宣称中文 IME 已验收。要验证真实中文输入法，还必须观察候选界面的位置、可见性以及外部捕获结果。输入法候选或辅助窗口不能假定属于源视图的缓存图像。

## 4. 隐藏窗口只是可见性状态，不是安全策略

- [Apple：NSWindow.orderOut(_:)](https://developer.apple.com/documentation/appkit/nswindow/orderout%28_%3A%29)：将窗口从屏幕列表移除以隐藏它，但不因此释放窗口对象。
- [Apple：NSWindow.isVisible](https://developer.apple.com/documentation/appkit/nswindow/isvisible)：判断窗口是否在屏幕上；即便被其他窗口遮住，也可能为真。
- [Apple：NSWindow.occlusionState](https://developer.apple.com/documentation/appkit/nswindow/occlusionstate-swift.property)：反映遮挡状态。可见性/遮挡信息与禁止捕获不是同一类接口。
- SDK：`NSWindow.h:339` 为 `windowNumber`；`:425` 为 `orderOut:`；`:435–437` 为 visible/key/main 状态。
- [Apple：SCShareableContent](https://developer.apple.com/documentation/screencapturekit/scshareablecontent)：枚举可共享来源，后续用 filter 选择捕获范围。SDK `SCShareableContent.h:158` 明确 `onScreenWindowsOnly` 是“仅在屏窗口”的筛选选项；把它设为 true 会主动限制枚举范围。

**实验要求：** 保存源窗口 ID、源窗口状态、显示窗口 ID；用不限制在屏窗口的枚举检查源窗口，再按源 ID 进行独立 CG 及可用的 SCK 捕获。当前源窗口不能枚举、没有有效 ID、API 返回空图、权限失败，都要保存为该条路径的观察状态；不能记作 protected Layer 的成功。

“隐藏源窗口可能仍有需要评估的捕获入口”是本轮测试假设，不是已经确认隐藏源窗口必然泄露。反过来，文档也没有给出“orderOut 即防捕获”的保证。禁止用未经测试的窗口移出屏幕、透明度或隐藏状态替代这项验证。

## 5. Accessibility 是另一条内容访问通道

- SDK `NSAccessibilityProtocols.h:242` 的 `accessibilityElement` 控制元素是否作为 AX 元素暴露；`:266` 的 `accessibilityValue` 表示元素值。这两个现代属性形式标注 macOS 10.10。
- [Apple：AXIsProcessTrusted](https://developer.apple.com/documentation/applicationservices/1460720-axisprocesstrusted)：查询调用进程是否为受信任的辅助功能客户端。
- [Apple：AXUIElementCopyAttributeValue](https://developer.apple.com/documentation/applicationservices/1462085-axuielementcopyattributevalue)：读取指定辅助功能对象的属性值，失败有明确错误码。

**实验要求：** 若本机已经具有相应权限，只查询本轮合成 Demo PID 的 AX 树与文本属性，不扫描其他应用内容。分别报告“像素捕获是否含敏感内容”和“AX 是否能读取合成文本”。把所有 AX 元素隐藏并不等于完成了无障碍支持；把 AX 文字可读也不能误写成截图 API 泄露。权限缺失则记录未验证，不修改 TCC。

## 6. 防捕获仍属于显示端

- [Apple：AVSampleBufferDisplayLayer.preventsCapture](https://developer.apple.com/documentation/avfoundation/avsamplebufferdisplaylayer/preventscapture)：描述该 Layer 的屏幕捕获保护。
- [Apple：NSWindow.SharingType.none](https://developer.apple.com/documentation/appkit/nswindow/sharingtype-swift.enum/none)：当前说明不推荐用该旧常量隐藏或排除被捕获内容。

因此，主对照必须保持相同的原生离屏绘制链路，只改变 `preventsCapture`。主路线不同时叠加 `.none`，避免无法归因。原生控件不因成为普通 overlay 而自动继承视频保护，旧轮 mixed 测试已提供反例；但新轮能否安全完成真实原生编辑，需要独立结果。

## 7. 依据的证据等级

| 类别 | 本文件的状态 |
|---|---|
| Apple 接口说明及本机 SDK 声明 | 已核验，可作为设计依据 |
| 上一轮 mixed 原生标签泄露 | 已有旧实验，仅覆盖标签叠加；见上一轮结果 |
| 本轮离屏原生编辑、选择、中文 IME 的完整交互 | 尚待本轮实验结果，不由文档调用方式推定成功 |
| 源窗口捕获、AX、菜单/候选窗覆盖 | 尚待本轮实验逐项记录 |
| 跨 macOS、Intel、多显示器、多缩放、长时稳定性 | 本文件没有提供实测证据 |
