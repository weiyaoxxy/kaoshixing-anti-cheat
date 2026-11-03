# 当前实验的 Hook 调用证据分析

`analyze-hook-invocations.py` 只读取指定 JSONL 和独立实验清单，不探测、启动或改变 UU。它回答“这一次已指定的进程生命期和观察窗口里，日志支持什么层级的调用证据”，不会自动把历史文件当作当前 UU 的证据。

```bash
python3 scripts/analyze-hook-invocations.py \
  --log /path/to/closed-hook-log.jsonl \
  --expect /path/to/session-expectation.json \
  --output /path/to/new-invocation-analysis.json

python3 -m unittest discover -s tests -p test_hook_invocations.py
```

输出必须是新文件，父目录须已存在，文件权限为 0600。合法分析退出码为 0；记录无效、不完整或读写失败退出码为 2。`no_evidence` 仍是合法分析结果，不等于检查到 Hook。

## 独立清单

```json
{
  "sessionID": "externally-chosen-session-token",
  "pid": 12345,
  "processStartSeconds": 1800000000,
  "processStartMicroseconds": 123456,
  "executable": "/absolute/path/to/owned-test-host",
  "startHostTime": 123456.0,
  "endHostTime": 123486.0
}
```

由控制器或测试宿主独立记录该清单：会话令牌应在启动前选择；PID、微秒级进程出生时间和路径来自实际进程身份；观察窗口使用与 Hook `CACurrentMediaTime` 同一启动周期、同一单调时钟域的时间。窗口应包含本次库加载和需要关联的初始化记录。不要从同一待分析日志提取这些字段后再宣称验证了关联。分析器无法认证清单由谁生成，只能严格比对。

可选 `uid`、`hookInstanceID` 和 `hookVersion` 可进一步限制身份；版本只能为 `1.3` 或 `1.4`，可由控制器选择已知库版本后填写。可选 `expectedFinalSequence` 必须来自独立结束回执，而不是从待分析日志最后一行反推。没有它时，可以保留已观察到的正证据，但 `coverage.logTailCompletenessVerified=false`：删除末尾若干完整 JSONL 行无法仅靠剩余文件识别。

## 等级与严格关联

| level | 有效证据 |
| --- | --- |
| `no_evidence` | 合法空日志，没有本次加载或调用证据。 |
| `loaded_only` | 当前实验的 `image_loaded`，可能还有安装、初始化、设置、更新或停止；未出现采集入口。 |
| `capture_entry_observed` | Hook 包装函数观察到截图请求、CGDisplayStream 创建调用或 SCStream 开始采集调用；不要求调用成功，也不声称有图像。 |
| `frame_callback_observed` | 关联成功的有效截图结果，或关联成功创建/设置的流收到有效屏幕帧。此固定等级也包括同步截图结果，不代表所有路径都是异步回调。 |
| `invalid_or_incomplete` | 身份、格式、序列、时间窗口或调用/流关系未通过验证；不得用其等级证明当前调用。 |

每条记录必须为 `schemaVersion=2`、`hookVersion="1.3"` 或 `"1.4"`、`identityAvailable=true`、`priorLogWriteFailures=0`，并匹配清单中的 session、PID、出生时间和路径。**一份日志只允许一个 Hook 版本，混合 1.3/1.4 也会拒绝。** UID、Hook 实例及模式同样必须保持一致。`hookInstanceID` 是 UUID；日志序列必须从 `image_loaded` 的 1 开始、逐条连续递增；`hostTime` 必须不递减且位于外部窗口内。输出 `hookVersion` 为有效前缀中已观察到的版本。

拒绝旧 schema、空会话、混合进程/实例、PID 重用、重复键、非有限数值、序列缺口/重复/倒序、损坏 JSON、末行没有换行以及输入超限。遇到无效行后停止，不跨越损坏记录拼接证据。`flags` 保留此前有效前缀，`flagsDescribeValidatedPrefixOnly=true` 且 `evidenceUsable=false`；调用方必须先检查 `level/evidenceUsable`。不能只取前缀里的某个 true 忽略全局失败。

诊断或未来事件的公共身份/序列仍需通过校验，但未知事件只记入 `counts.uninterpretedEvents`，不会凭其名称或 success 字段提升证据等级。

## v1.4 诊断协议

以下新事件只允许出现在 v1.4 日志内，额外校验请求/结果关系；不设置任何采集入口或帧标志，也不能替代已有流的创建/注册证据：

- `shareable_content_request/result`：`api` 必须为 `SCShareableContent.getShareableContentExcludingDesktopWindows:onScreenWindowsOnly:completionHandler:`，`callID` 与所有采集/诊断调用共享唯一命名空间。结果必须匹配先前请求，包含布尔 `success`、字符串错误域、整数错误码和三个非负整数数量；成功结果不得同时带错误。对象内容不会复制进分析结果。
- `display_stream_control_call/result`：`api` 仅为 `CGDisplayStreamStart/Stop`；请求/结果的 `callID+api` 和布尔 `streamProvided` 必须一致。结果的 `success` 必须与整数 `returnCode==0` 一致。不使用这些事件为帧建立 stream 身份。
- 孤立、重复、错配或自相矛盾的诊断结果使整份证据失效。尚未收到结果的请求保留在 `coverage.pendingShareableContentResults` / `pendingDisplayStreamControlResults`；它们不升级证据等级。nil completion 的原调用也可能没有结果。
- 同一份日志同时含旧版与新版时返回 `mixedHookVersions`；外部清单指定版本而日志不匹配时返回 `identityMismatch_hookVersion`。不自动拆分或拼接混合文件。

```bash
python3 scripts/test-hook-diagnostics.py --library build/libCaptureHook-v1.4.dylib \
  --output artifacts/hook-v1.4-diagnostics-new-run
```

这组对照仅使用自有宿主中的合成共享内容和 NULL 流句柄，不采屏、不运行 UU；真实有效流、真实远控及遮蔽效果仍未由这组测试验证。

## 采集和帧协议

- `capture_call` 需要唯一 `callID` 及准确的 `api/operation` 对应。`snapshot_request`、两种 `CGDisplayStreamCreate` 和 `SCStream.startCapture` 是入口证据。`SCStream.init` 只是初始化，`stream_setup/update/stop` 也不提升采集入口等级。
- 截图 `capture_result` 必须关联先前请求的 `callID+api`，需要布尔 `success/validImageOrSample/hasImage/hasSample` 和整数尺寸。只有成功、有效、确有图像或样本且尺寸为正才算帧证据；请求失败或未收到结果只能算入口。
- `stream_create` 携带唯一 `streamID`；随后 `stream_create_result` 必须匹配 `callID+api+streamID` 且成功，才能支持流帧。
- 流的 setup/start/stop/update 携带 `streamID+creationCallID`，后者必须指向已观察到的真实创建调用。SCK 的 `addStreamOutput` 还携带 `outputID+type`；必须存在对应成功 `stream_setup_result`，且是屏幕 type=0，并已观察到 start 调用，才能支持该输出的帧。
- 帧携带 `streamID/outputID/frameID/validScreenFrame/frameCount/screenFrameCount/width/height`。SCK 有效帧还必须 `type=0`、`frameStatus=0`、`sampleValid=true`、`dataReady=true`；CGDisplayStream 有效帧必须 `status=0`。有效帧尺寸必须为正。
- 帧 ID 与每个输出的帧计数不能重复。并发回调可能以不同于计数分配的顺序进入日志锁，因此不要求 frameCount 按日志行递增；按每个 output 的计数顺序验证有效屏幕帧计数不能倒退或发生不可能的增长。日志自己的 sequence/hostTime 仍严格有序。
- `frame_forwarded` 必须匹配此前记录的 `frameID+streamID+outputID+validScreenFrame` 且 `originalCallbackReturned=true`，才设置 `flags.originalCallbackReturnObserved`。这表示原 handler/delegate 返回，不证明编码、网络发送、远端显示或遮蔽。
- stop 调用之后可以有已排队回调，分析器不会仅因观察到 stop 就否认这些回调。异步结果未在窗口内完成时，`coverage.pendingSnapshotResults` 会保留请求数量，不补造结果。

## 结论边界

`captureBlockingVerified=false`、`remoteSessionVerified=false`、`localEvidenceOnly=true`、`logAuthenticityVerified=false` 始终明确保留。日志、清单及结果都是本地可修改材料，不是密码学证明。帧事件有采样，未观察到某个 API 不代表它从未运行，也未证明所有捕获入口都覆盖。

要进一步证明 UU 实际远端输出受控，还需要在授权且可连接的同一会话内，将当前进程映射、这份调用分析、输入/输出像素或遮罩结果、远端连续画面及恢复后的对照共同关联。本工具不会单凭 loaded、start、frame 或 callback-return 事件声称已经完成这些验证。
