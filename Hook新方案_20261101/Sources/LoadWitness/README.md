# LoadWitness：纯 C 动态库加载见证器

该库用于区分“目标进程根本没有加载外部 dylib”和“完整 CaptureHook 安装或运行出现问题”。它不是取屏 hook，也不修改捕获结果。

## 实现与副作用

构造器只读取 `HOOK_DEMO_LOG`，获取自己的 PID、UID、可执行文件路径与单调时钟，然后向指定文件追加一条 JSONL：

```json
{"event":"image_loaded","component":"LoadWitness","version":"1.0","pid":1234,"uid":501,"executable":"/path/to/host","monotonicSeconds":100,"monotonicNanoseconds":200,"clockAvailable":true}
```

没有 Objective-C 代码，没有 Foundation、AppKit、ScreenCaptureKit、CoreGraphics 依赖，没有 `__interpose`，没有 swizzle，没有 task-port / 屏幕捕获 / 网络访问，没有退出或启动其他进程的逻辑。`otool -L` 核验仅依赖系统 `libSystem.B.dylib`。

日志路径未设置、父目录不存在或写入失败时安静返回，不调用 abort/exit，不抛出异常。可执行文件路径中的引号、反斜杠和控制字符进行 JSON 转义。不会记录远程连接 ID、密码、输入内容或屏幕像素。

## 构建

```bash
bash scripts/build-load-witness.sh
```

生成：

- `build/libLoadWitness.dylib`：arm64，最低 macOS 11，本地 ad-hoc 签名。
- `build/LoadWitnessHost`：自有纯 C 短生命周期测试宿主；自身不加载或引用见证库。

自有宿主加载验证示意：

```bash
HOOK_DEMO_LOG=/absolute/writable/directory/witness.jsonl \
DYLD_INSERT_LIBRARIES=/absolute/path/build/libLoadWitness.dylib \
/absolute/path/build/LoadWitnessHost
```

仅通过新进程环境注入，不修改应用原文件、不重新签名第三方应用，也不安装任何持久启动项。受测程序是否允许该方式，仍由原版签名、entitlement、系统安全机制和启动方式决定。

## 本机自测

记录：`artifacts/load-witness-selftest-20261101T135819Z/summary.json`。

五项均通过：

1. 不设置 DYLD 注入，仅给日志路径：宿主正常结束，没有见证日志。
2. 设置 DYLD 注入和有效日志路径：恰好一条 image_loaded，PID 与宿主输出一致，可执行文件路径正确。
3. 已注入但未设置日志路径：宿主正常结束，无错误输出。
4. 已注入但日志父目录不存在：宿主正常结束，无错误输出。
5. 宿主路径含中文、空格、引号及反斜杠：日志能被 JSON 解析，路径逐字符还原正确。

自测过程中没有启动、停止或改动 UU、ToDesk。CaptureHook v1.2 源码与二进制没有改变。

## 证据解读

`image_loaded` 证明这个具体 PID 执行过见证库构造器，不能证明任何取屏调用被拦截。

单纯没有日志不足以证明系统阻止加载：还需确认新进程确实启动、注入环境属于该进程、日志路径对目标 UID 可写、程序没有立即转交给已存在实例、目标库架构匹配，并对照启动错误与签名条件。该工具用于提供最小差异实验，不能替代这些检查。
