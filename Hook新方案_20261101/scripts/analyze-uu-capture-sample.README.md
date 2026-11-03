# UU 外部 sample 调用树分析

`analyze-uu-capture-sample.py` 只分析已经存在的 `/usr/bin/sample` 文本，不运行采样、不读取窗口或图像、不更改 UU。

```sh
python3 scripts/analyze-uu-capture-sample.py \
  --sample /path/to/server-sample.txt \
  --expect /path/to/external-expect.json \
  --output /path/to/new-analysis.json
```

输出必须是新文件，权限为 `0600`。有效的阳性／阴性分析退出码为 0，输入或证据不完整为 2。也可用 `importlib` 导入后调用 `analyze(sample_text, expect)`，文本参数接受 `str` 或 UTF-8 `bytes`。

外部 expectation 示例：

```json
{
  "pid": 12345,
  "executable": "/Applications/UURemote.app/Contents/Helpers/UURemoteServer",
  "identityMatchedBeforeAfter": true,
  "sampleExitCode": 0,
  "sampleTimedOut": false,
  "sampleOutputTruncated": false,
  "sampleOutputComplete": true
}
```

仅 `pid`（正整数）和 `executable`（绝对路径）必需。采样报头中的 PID、Path 必须精确匹配，不进行路径别名猜测。其余字段必须来自采集器，不能从待分析日志反推；未知额外字段不会写入结果。

- `identityMatchedBeforeAfter: false`：直接判为 `invalid_or_incomplete`，`pathObserved=false`。缺少此字段允许历史离线分析，但 `identityContinuityVerified=false`。
- 非零 `sampleExitCode`、超时、输出截断或 `sampleOutputComplete: false` 均判为不完整。
- 四项工具状态齐全且成功时，`outputCompletenessVerified=true`，含义是外部采集器声明完成；分析器不验证声明真实性。
- 可选 `expectedSampleSHA256` 校验外部留存的输入摘要。没有可靠结束哨兵，尾部换行与完整 Binary Images 行仍无法发现整行或整段尾删。

只有 `Call graph:` 中同一线程分组、同一祖先链上的以下两个确切来源可产生 `pathObserved=true`：

1. `ScreenCaptureKit` 中 `SCStream(SCContentSharing) startRemoteVideoReceiveQueue:` 的 block 回调。
2. 其后代 `libstreamer.dylib` 中 `streamer::capture::ScreenCapturerSck::OnReceiveVideoSampleBuffer`。

调用树按 sample 的两列缩进解析，保留匿名中间节点，遇到不支持或缺失的树结构则判不完整。兄弟分支、不同线程、泛型 `SCStream` 回调、错误 image、Binary Images 与平铺统计不能拼成捕获链。采样报头、完整调用树边界、Binary Images 段和末尾换行均检查。

输出状态是 `path_observed`、`path_not_observed`、`invalid_or_incomplete`。编码、IOSurface 是独立旁证；`iosurfaceOnCapturePathObserved` 和 `encoderToVideoToolboxChainObserved` 仅在相应祖先关系真实存在时成立。它们不建立采集帧到编码帧的一一对应关系。

输出只保留固定类别、经过核对的规范符号、来源行号、线程序号与必要的匿名桥接节点。不写原始线程名、其他符号、地址、函数参数或完整 sample。数字统计指解析到的行／路径，**不代表视频帧数、调用次数或帧率**。

`captureHookHitVerified`、`validFrameVerified`、`remoteSessionVerified` 和 `captureBlockingVerified` 始终为 false。历史 sample 的阳性结果可以定位实际运行路径，不能替代 Hook 事件、完整帧状态或远端验收。

测试：`python3 tests/test_uu_capture_sample.py -v`。测试只使用合成文本与已保存的历史样本，不启动或采样 UU。
