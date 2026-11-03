# 全量进程身份检测（schema v2）

本原生工具对所有枚举到的 PID 尝试查询运行代码身份；名称和路径只作线索及检查优先级，不再作为候选、验证或汇总的准入条件。可识别目录中仍保留有效原厂身份的改名/搬移程序。未知、重签、未签名代码不能自动归为某家远控，也不自动允许。

本目录及 `detect-remote-processes.py` 是独立只读诊断入口：不终止受检目标、不更改远控启动任务、不采集屏幕/键盘内容。为限制同步 Security API 耗时，监督进程可以终止自己的工作子进程；不能把这项内部清理描述为“没有任何信号调用”。考试门禁、管理员处置、上报与恢复由其他模块实现，不由本 CLI 执行。

## 构建与使用

在 `Hook新方案_20261101` 目录执行：

```bash
INVENTORY_BINARY="$(bash scripts/build-remote-process-inventory.sh)"
DETECTION_RUN_DIR="$(mktemp -d "${TMPDIR:-/tmp}/exam-remote-detection.XXXXXX")"
python3 -B scripts/detect-remote-processes.py \
  --inventory "$INVENTORY_BINARY" \
  --output "$DETECTION_RUN_DIR/results" --samples 3 --interval 1 --budget 12
```

构建生成新目录，并复制固定的 `policy.json` 到二进制旁边；手动指定已有产物或已有策略位置会拒绝覆盖。原生接口：

```text
RemoteProcessInventory [--pid POSITIVE_PID] [--policy PATH] [--budget SECONDS]
                       [--skip-static] [--allow-test-policy]
```

默认查询全部 PID，并对匹配目录的组件分别执行动态身份与静态严格核验。`--pid` 对任何 PID 查询，不要求名字像远控。`--skip-static` 用于独立的动态复查，静态结果明确记为 `notRequested`，不能当作通过。整体预算默认 12 秒，允许 (0,120]；超时保留已完成行，将未完成项记录为缺口。扫描后才等待 `--interval`，不是每秒保证一次完整检查。

返回码 0 表示本轮声明的观察检查完成；2 表示有效 JSON 中有检查缺口；64 表示选项/策略错误。两者均不能承诺原子系统快照、全时段无远控或无未知远控。生产集成必须处理 2，不能将它当空清单。

## 核验与字段

每行保留 PID、UID、出生时间、实际路径（可空）、名称线索、内核状态及前后文件身份。`codeIdentity` 包含：

- `metadata`：签名 ID、Team ID、CDHash、格式等；读取成功本身不是验证。
- `dynamicValidation`：`SecCodeCopyGuestWithAttributes` 按 PID 取得运行代码对象，再以签名要求执行动态验证；另有 `dynamicRevalidationOSStatus` 和结束时元数据重读。
- `staticValidation`：独立的静态严格校验，声明运行架构对应静态对象的范围，不声称递归核验所有嵌套代码。资源损坏与动态身份失败分别显示。
- `requirement`、策略版本和摘要：用于追溯此次实际要求。向日葵泛化 Helper ID 还要求已登记 CDHash，不仅匹配厂商和模板 ID。

仅当出生身份稳定、动态要求通过并重查一致，输出 `status=verifiedComponentRunning`、`category=knownRemoteIdentityVerified` 及 `verifiedVendor/verifiedRole`。**这代表已知组件身份在本轮观察中成立，不代表活动远控会话、完整运行内存证明或此前画面没有泄露。** 静态资源失败仍保留，不被动态通过覆盖。

其他分类包括 `unknownSignedCode`、`unsignedOrAdHocCode`、`inspectionUnavailable`、`knownMetadataButValidationFailed`、`processExitedOrChanged`。Apple 签名程序可能没有 Team ID，不能据此归为未签名；临时签名分类使用签名标志。不认识的代码是否允许由考试策略另定。

若前后两次内核进程状态均为 `SZOMB`，且出生身份稳定，记录 `nonExecutingZombie`：该进程已经退出、等待父进程回收，不再执行代码。这是基于内核状态的有证据排除，保留 PID、原查询错误和计数；不以名字或“系统进程”猜测排除其他不可读对象。

覆盖字段分别记录 PID 枚举、元数据可用数、不可读路径、身份缺口、僵尸数、未检查数、超时及静态检查范围。`PID + UID + birthTime + path` 不能保证识别同 PID、同路径再次执行同一映像；`samePIDExecCoverageGuaranteed=false`，未伪造 `pidversion`。没有身份缓存跨扫描复用，处置端仍须重新核验。

## 预算与故障处理

Security 同步调用在 `posix_spawn` 创建的工作进程执行。父进程读取逐行结果并以统一截止预算监管；超时只向自己尚未回收的子进程发送 SIGKILL，再回收它，不使用搜索得到的目标 PID 清理。工作进程另有独立截止计时及父进程存活监测，上层意外退出时会退出自身。未完成观察不被补成干净结果。

输出保存实际读取策略的 SHA-256，并检查原策略文件是否变化。Python 为一次调用创建只读语义的策略快照，核对原生回传的摘要与测试策略标志；输入变化或绑定失败会清除确认结果。**这不是服务器签发策略的验签，也不是对恶意 root 的远程证明**；`policyCryptographicallyAuthenticated=false`。全量诊断产物包含进程路径与签名元数据，不包含命令行参数、环境变量、屏幕或输入内容。

## 验证

```bash
python3 -B -m unittest discover -s tests -p test_remote_process_detection.py -v
python3 -B tests/remote-identity/run-integration.py \
  --inventory "$INVENTORY_BINARY" --output "$DETECTION_RUN_DIR/identity-fixtures"
```

逻辑回归覆盖四处过滤/汇总、同厂其他产品、泛化 ID 指纹、权限/生命周期、动态与静态分离、模式与策略摘要绑定。原生集成使用自有无联网/无采集程序，验证随机改名搬移、全量发现、同名假冒、同 PID exec、僵尸/退出、预算超时、父监督进程故障与策略输入错误。

没有本项目发行证书时，自有改名实验使用显式 `testOnly` 策略、精确 CDHash 和 `--allow-test-policy`。生产目录仍要求 Apple 签名锚；默认拒绝测试策略，Python 生产汇总也拒绝测试策略结果。**测试签名通过不能当作真实远控改名运行验证。** 不重签或启动真实远控副本。

[历史 v1 只读测试](../../../docs/远控软件运行检测测试_20261103.md)保留原结果；新增 v2 证据见项目 `artifacts/remote-identity-v2-20261103/`，设计背景见[管控详细方案](../../../docs/远控伪装识别与考试管控详细方案_20261103.md)。

## 官方依据

- [Apple 运行代码查询](https://developer.apple.com/documentation/security/seccodecopyguestwithattributes(_:_:_:_:))：按属性获取宿主代码对象；本机 SDK 的 `SecCode.h` 同时说明动态验证范围及静态对象转换边界。
- [Apple Code Signing Services](https://developer.apple.com/documentation/security/code-signing-services)：动态与静态验证分别提供，元数据不是验证结果。
- [Apple SecCodeStatus](https://developer.apple.com/documentation/security/seccodestatus)：动态状态与静态完整性不是同一概念。
- 本机 SDK `sys/proc.h`、`sys/proc_info.h`：`SZOMB` 表示已退出待回收；只有稳定的前后内核状态才用于本工具的非执行对象分类。
