# 考试状态与安全事件组件

实现日期：2026-11-03。这里的组件不发送进程信号、不修改 launchd，也不安装管理员服务。进程身份、处置和系统恢复由调用方的受限服务负责。

## 接口与接入

```python
from guardlib import ExamSessionCoordinator, DurableOutbox

session = ExamSessionCoordinator("example-session")
session.update_checks(0, clean=True, coverage_complete=True,
                      guard_healthy=True, evidence_healthy=True)
# 调用方必须已验证准入授权；本机参考测试授权须明确标为测试。
session.authorize(30, "unique-reference-authorization-1", server_authorized=True)
assert session.snapshot()["mayStart"]
session.start()

session.update_checks(1, clean=False, coverage_complete=True,
                      guard_healthy=True, evidence_healthy=True)
assert not session.snapshot()["mayDisplayQuestions"]
# 处置后新的干净观察不自动续考；必须新授权且显式 resume()。
session.update_checks(2, clean=True, coverage_complete=True,
                      guard_healthy=True, evidence_healthy=True)
session.authorize(30, "unique-reference-authorization-2", server_authorized=True)
session.resume()
session.begin_finish("examEnded")
# 只有外部恢复已经验证成功后，才传入 True。
session.complete_restore(True)
```

`observation_id` 是调用方生成的递增整数。旧/重复观察不能覆盖新状态；第一次检查失败、检测变旧、租约到期都会阻止显示试题。`ready` 需要新鲜、合格的四项检查及有效授权；`start()` 才进入考试。手动暂停后也必须有暂停之后的新观察和新授权，单次扫描干净不会自动续考。

默认检查有效期 10 秒，最大租约 120 秒，都是可配置上限，不是检测性能保证。macOS 通过 `mach_continuous_time` 与 `mach_timebase_info` 计算包含休眠的单调时间；不使用排除休眠的时钟延长租约。租约已经到期后不可在原会话事后续租，`requiresRecovery=true`，调用方应结束并恢复；新对象始终从准备态开始，不能靠持久化状态恢复考试。

`snapshot()`/`tick()` 会检查到期；调用方须持续调用并将状态发布给 GUI。GUI 还必须有独立的状态失联/过期处理。此 Python 对象不替代系统守护的租约与恢复事务；它被停止后不能自行隐藏其他进程的窗口。`epoch` 在暂停/结束时失效旧操作参考值，真正处置仍必须由受限服务在同一串行控制点检查自己的代次、权限和租约。

状态变更可通过 `drain_events()` 取出，再由调用方投递到 outbox；内存事件队列溢出会显式失效，不悄悄清空后恢复正常。这里的 `server_authorized=True` 是调用方传入的事实，不验证远程签名，也不代表已经实现正式考试授权服务器。

## 持久队列与回执

```python
outbox = DurableOutbox(
    "/private/path/to/new-outbox", "example-session",
    device_id="registered-device", boot_id="actual-boot-session",
    policy_version="reactive-policy-v1",
)
event = outbox.append("forbiddenComponentObserved", {
    "pid": 123, "vendor": "synthetic-fixture", "actor": "unknown",
})
assert event["serverReported"] is False
# endpoint 必须绑定同一 sessionId；Bearer token 从私有配置取得，不写入日志。
delivery = outbox.deliver_once(endpoint, token)
# 只有 accepted + 会话/事件/序号/内容摘要匹配且回执落盘，才返回 True。
reported = delivery["serverReported"]
outbox.close()
```

队列目录要求当前用户拥有且权限 0700，数据库要求私有普通文件，拒绝符号链接。SQLite 使用事务、完整同步及 macOS fullfsync；事件包含单调序号和前一事件摘要。重开时检查序列、内容和已有回执关联，异常不作为干净队列。默认保留本会话最多 10000 个事件、16 MiB 事件正文，并有数据库页面预算；已确认事件也计入保留上限，不无限写盘。达到上限或写入失败必须由调用方使证据健康失效，不能继续宣称完整留证。队列只用于本会话，切换会话/设备/启动/策略身份需要新目录。

事件证据采用字段允许列表、深度/长度限制，不接收 `answer`、`question`、`password`、完整命令行等字段，也不读取原 Demo 的答案状态文件。调用方仍不能把题目内容塞进 `reason` 等文本字段；字段过滤不是语义脱敏器。

网络默认只接受 HTTPS，验证证书和主机名，拒绝不验证 TLS 的上下文；不跟随重定向、不继承环境代理。HTTP 仅在显式 `allow_loopback_http=True` 且地址为字面量回环 IP 时启用。调用有整体等待预算及有限退避，单个仍未退出的网络工作线程存在时不无限新增线程；过期响应不提交 ACK，后续用同一个 eventId 重试。`ignore_backoff=True` 只用于受控测试，不应成为生产轮询策略。

本地提交、接收端持久化、客户端收到并保存回执是不同状态。断网、401、错误/不匹配回执、重定向、超时和回执写入失败均保留未确认。接收端已收到但客户端没保存 ACK 时重试，服务器按 eventId 和内容摘要返回原回执。已接收记录说明服务器收到该内容，不证明客户端报告的本机事实必然真实。

## 本机参考接收端

`scripts/security-event-receiver.py` 仅绑定 `127.0.0.1`，需要当前用户拥有且权限私有的 token 文件，不打印 token。无外网监听选项。示例：

```bash
python3 -B scripts/security-event-receiver.py \
  --directory /private/path/to/new-receiver-state \
  --session-id example-session \
  --token-file /private/path/to/token-file \
  --ready-file /private/path/to/new-ready.json
```

启动输出给出动态端口的 `endpoint`，端点为 `/v1/exam-sessions/{sessionId}/security-events`。它只验证身份令牌、事件格式、内容摘要、序列与重复请求，并持久化回执，所有回执标明 `referenceServer=true`、`attestsClientTruth=false`。它**不是正式考试服务器，不发正式考试准入许可，不实现正式服务端发题和心跳租约政策**。

同 ID 不同内容或序号/前项摘要冲突返回冲突，错误 token 拒绝；请求正文和并发量有界。状态存储失败不返回成功回执。HTTP 参考模式必须显式启用；这项测试不能替代真实生产 HTTPS、身份接入、部署与灾难恢复验收。

## 验证结果

在项目 `Hook新方案_20261101` 下运行：

```bash
python3 -B -m unittest discover -s tests -p 'test_exam_guard_core.py' -v
python3 -B -W error::ResourceWarning -m unittest discover -s tests -p 'test_security_outbox.py' -v
```

本轮 44 项测试通过：20 项状态机及连续时钟测试，24 项持久队列/真实本机 HTTP 接收测试。覆盖无检查/无授权不能开考、各健康条件失败、过期/乱序观察、暂停不自动恢复、旧授权重放、过期不能事后续租、结束与观察并发、恢复失败、事件溢出、写入故障、容量耗尽、数据及回执损坏、认证失败、内容冲突、序列缺口、回执丢失后的重复请求、端点与 TLS 约束、重定向、网络拒绝和有界超时。

另外启动真实 CLI 接收进程，验证错误 token 不上报成功、有效 token 得到持久化回执、客户端和接收端都重启后继续投递下一条事件。两次参考服务均已退出，临时 token 文件已删除，未改动任何真实远控程序。原始日志、源码摘要及结果见[本轮证据](../../artifacts/guard-state-outbox-20261103T045001Z/summary.json)。

SQLite 写入失败用 `query_only` 注入，资源容量通过配置上限验证；没有填满本机磁盘或进行实际断电。休眠时钟机制使用本机 API 验证，租约跳时用注入时钟模拟，未让本机实际休眠。未连接正式外部服务器，生产 HTTPS 成功链路尚未验证。测试身份和进程编号均为合成数据。

依据：[Python SQLite 事务](https://docs.python.org/3/library/sqlite3.html)、[SQLite 同步与 fullfsync 配置](https://www.sqlite.org/pragma.html#pragma_synchronous)、[Python urllib 超时、重定向和代理行为](https://docs.python.org/3/library/urllib.request.html)。休眠时间语义已核对本机 SDK `usr/include/mach/mach_time.h`。本模块不把本机日志链或设备身份当作对抗最高权限对手的可信硬件证明。
