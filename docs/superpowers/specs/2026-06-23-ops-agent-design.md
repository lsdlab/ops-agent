# ops-agent 设计文档（Design Spec）

- **日期**: 2026-06-23
- **状态**: Draft（待用户 review）
- **作者**: brainstorming session
- **相关 SDK**: `claude-agent-sdk` 0.1.81（已在本机验证 API）

---

## 1. 背景与目标

用 `claude-agent-sdk-python` 构建一个**集中式运维 agent**：在一台中心机上，通过自然语言对话 + 定时任务，对**所有**被管 Linux 机器执行远程命令、巡检与告警。

**核心问题（用户原始诉求）**：
1. 一个客户端集中管理所有机器。
2. 远程执行命令、巡检。
3. 各端之间是什么关系？
4. 应该开发什么、安装什么？
5. 给出**最小**方案。

**答案的一句话总纲**：中心机一台 = 大脑 + 执行器；被管机器 = 哑的 SSH 目标，**什么都不装**。系统是单向 push。

## 2. 目标（v1 in-scope）

- 静态 inventory 管理（`hosts.yaml`）。
- 交互式对话远程执行命令（带人工审批）。
- 定时巡检（只读白名单，无人值守，确定性）。
- 阈值告警（webhook）。
- 全量远程操作审计（SQLite）。
- 纯 Linux 被管机器。

## 3. 非目标（YAGNI，明确不做，留 v2）

- 多用户 / 登录 / RBAC。
- Web UI / 控制台。
- 动态 inventory 发现（自动扫描网段、云 API 同步）。
- agent 驱动的定时巡检（LLM 不参与无人值守巡检）。
- Windows / WinRM。
- 分布式 / HA daemon。
- 密钥管理系统（v1 私钥 `0600` 落盘）。
- 自动修复（auto-remediation）执行——agent 可「建议」修复命令，但仍走人工审批。

## 4. 约束（已确认的四个分歧点）

| 维度 | 选择 | 影响 |
|---|---|---|
| 连通模型 | **Push**（中心 → SSH → 机器） | 被管机器不装任何 agent；复用 sshd |
| 形态 | **daemon（定时巡检/告警/状态）+ 交互客户端** | 两进程，共享 SQLite 解耦 |
| 安全 | **交互审批 + 巡检只读白名单** | LLM 不参与无人值守执行 |
| 系统 | **纯 Linux** | 远程执行 = SSH + bash，无需跨平台抽象 |

## 5. 架构总览

### 5.1 拓扑

```
                ┌──────────────────── central box（仅此 1 台）────────────────────┐
                │                                                                  │
  你 ──对话──▶ ops_client ─▶ claude-agent-sdk ──MCP(in-process)──▶ ops_mcp ─▶ ops_core │
                │                                                     │            │
                │            ops_daemon（cron 定时，无 LLM）───────────┘            │
                │                     │                                            │
                │               SQLite（command_audit / inspection_runs / hosts）  │
                └──────────────────────────┬───────────────────────────────────────┘
                                           │ SSH（push，密钥登录，纯 Linux）
              ┌──────────┬─────────────────┼──────────────┬──────────┐
              ▼          ▼                 ▼              ▼          ▼
           host-A     host-B            host-C         host-D     host-N
     （仅 sshd + 普通账号 + authorized_keys 公钥；不装任何东西）
                                                       │ webhook 告警
                                                       ▼
                                            钉钉 / 企业微信 / Slack / 自定义
```

### 5.2 端点关系（直接回答「各端之间是什么关系」）

- **central box**（1 台）：运行 `ops-daemon` 与 `ops-client`，是唯一的发起方。
- **被管机器**（N 台）：纯被动 SSH 目标。不发起任何连接，不装任何 agent / daemon。
- **方向**：严格单向。central box → 被管机器（SSH）；central box → 告警渠道（webhook 出站）。
- **被管机器之间**：彼此无任何关系、无互联。
- **daemon 与 client 之间**：v1 不做 IPC，通过**共享同一个 SQLite 文件**解耦（daemon 写巡检结果，client 读历史 + 自己执行交互命令）。未来如需「让 daemon 立即重跑某巡检」再加 Unix socket / 本地 HTTP。

## 6. 组件设计（一个包 `ops-agent`，四个入口）

| 组件 | 类型 | 职责 | 用 LLM |
|---|---|---|---|
| **ops_core** | 纯库 | 所有运维能力的实现（无 IO 副作用以外的状态） | 否 |
| **ops_mcp** | MCP server（薄壳） | 把 ops_core 包成 MCP 工具给 agent 调 | 否 |
| **ops_daemon** | 常驻进程 | 定时巡检 + 告警 | 否 |
| **ops_client** | 交互进程 | claude-agent-sdk agent 循环 + 终端对话 | **是** |

### 6.1 ops_core（纯库，无 LLM）

模块划分（每个单一职责、可独立测试）：

- `inventory.py` — 加载 `hosts.yaml` → `Host(alias, address, port, user, ssh_key, tags, bastion?)` 列表；按 tag/alias 过滤。
- `remote_exec.py` — 基于 `asyncssh` 的异步执行：`run(host, command, timeout) -> ExecResult(stdout, stderr, rc)`；并发扇出用 `asyncio.Semaphore`（默认并发上限 16）；支持 `ProxyJump` bastion。
- `allowlist.py` — **只读命令白名单**匹配器（argv 前缀 / fnmatch 模式）；**危险黑名单**匹配器（破坏性模式）。
- `policy.py` — 审批裁决：`decide(command, context) -> AutoAllow | RequireApproval | Deny(reason)`。规则：黑名单命中→Deny；白名单命中→AutoAllow；其余→RequireApproval。
- `inspection.py` — 巡检 = 数据驱动定义：`Check(name, command, parser, thresholds)`；`run_check(host, check) -> CheckResult(status, value)`。
- `store.py` — SQLite 读写（标准库 `sqlite3`）：审计、巡检结果、主机画像。
- `alerting.py` — 通知器：`webhook(url, payload)`（通用，覆盖钉钉/企微/Slack）+ 落库 + stdout。
- `config.py` — 加载 `config.yaml`（inventory 路径、调度、阈值、告警端点、白名单覆盖、SQLite 路径、并发数、SSH 超时）。

### 6.2 ops_mcp（MCP server，薄壳）

把 ops_core 能力暴露为 MCP 工具（agent 通过 server name `ops` 调用，工具名形如 `mcp__ops__<tool>`）：

| MCP 工具 | 入参 | 返回 | 审批 |
|---|---|---|---|
| `list_hosts` | `filter?: {tag?, alias?}` | `Host[]` | 自动 |
| `run_remote` | `hosts: str[], command: str, timeout?` | `ExecResult`（按 host 聚合） | **经 policy 裁决** |
| `run_inspection` | `hosts: str[], checks: str[]` | `CheckResult[]` | 自动（只读） |
| `get_inspection_history` | `host, check?, since?` | `inspection_runs[]` | 自动 |
| `get_host_facts` | `host` | 画像 dict | 自动 |

实现方式：作为 **in-process MCP server**（`McpSdkServerConfig`）直接接入 client，无需子进程；daemon 不用 MCP，直接 import ops_core。

### 6.3 ops_daemon（常驻，无 LLM）

- 用 `APScheduler`（cron 触发器）调度每个巡检 job。
- **启动时强校验**：加载巡检定义后，对每条 check command 跑 `allowlist` 匹配；任一未命中白名单或命中黑名单 → **fail-fast，daemon 拒绝启动**。这是「daemon 永不执行非白名单命令」的强制点（不依赖运行时审批，因为 daemon 无人工）。
- 每个 tick：遍历目标主机 → 经 `ops_core` 跑巡检命令 → 解析 → 阈值 → 写 `inspection_runs` → 命中阈值则 `alerting` 发告警。
- **永不执行非白名单命令**（job 集合在配置期固定为只读检查，并由启动校验兜底）。

### 6.4 ops_client（交互，用 LLM）

- `claude_agent_sdk.query()` / `ClaudeSDKClient`，配置 `ClaudeAgentOptions`：
  - `mcp_servers={"ops": McpSdkServerConfig(...)}` 接入 ops_mcp。
  - `can_use_tool` 回调 = 审批门（拦截 `mcp__ops__run_remote`，按 `policy.decide()` 裁决：AutoAllow 放行 / Deny 拒绝 / RequireApproval 在终端弹 `y/n`）。
  - `system_prompt` = 运维助手人设（谨慎、最小权限、危险操作必须确认）。
  - `disallowed_tools` = 屏蔽内置危险工具（如原生 Bash/Write），只留 MCP 工具，避免 agent 绕过 SSH 层直接改中心机。
- 终端对话：你输入「查所有 db 标签机器的磁盘」→ agent 调 `list_hosts` + `run_inspection` → 返回结果并解读。

## 7. 数据流

- **交互执行**：你 → client(agent) → `mcp__ops__run_remote` → `policy.decide` →（AutoAllow 自动 / RequireApproval 终端审批 / Deny 拒绝）→ `ops_core.remote_exec` SSH → host → `ExecResult` → 写 `command_audit` → 回 agent → 你。
- **定时巡检**：daemon → scheduler → 巡检 job（白名单）→ `ops_core` SSH → host → 解析/阈值 → 写 `inspection_runs` + `alerting`。
- **只读回看**：agent → `mcp__ops__get_inspection_history` → 读 SQLite → agent 总结。

## 8. 安全模型（核心：审批 + 白名单 + 黑名单）

三档裁决（`policy.decide(command, context)`）：

1. **危险黑名单 → Deny**（即便审批也默认拒绝，需 CLI 显式 `--i-know-its-dangerous` 才放行）：
   - `rm -rf`, `rm -rf /`, `mkfs`, `dd of=/dev/`, `reboot`, `shutdown`, `halt`, `init 0/6`
   - `systemctl stop/disable`, `iptables -F`, `chmod -R 000`, `> /etc/*` 覆盖, `:(){:|:&};:` fork bomb, `curl ... | sh`
   - 通配 `> 关键配置文件` 覆盖写入。
2. **只读白名单 → AutoAllow**（daemon 巡检 + agent 安全路径）：
   - `uptime`, `free`, `df`, `ps`, `ss -tlnp`, `ip a`, `hostname`, `uname -a`, `last`
   - `systemctl status <unit>`, `systemctl list-units --failed`, `journalctl -u <unit> --since`
   - `cat /etc/<file>`（限定只读路径），`docker ps`, `docker stats --no-stream`
   - 匹配方式：argv[0] + 参数前缀 / fnmatch，禁止 shell 元字符注入（`;`, `&&`, `|`, `` ` ``, `$()`）——含元字符一律降级为 RequireApproval。
3. **其它一切 → RequireApproval**（仅 client 上下文；daemon 不可达）。

审计：**每一次** `run_remote` 无论放行与否都写 `command_audit`（含发起者、审批人、rc、输出摘要）。

## 9. 配置与 Inventory

### 9.1 `hosts.yaml`（静态，最小）

```yaml
hosts:
  - alias: web-1
    address: 10.0.0.11
    port: 22
    user: ops
    ssh_key: ~/.ssh/ops_ed25519
    tags: [web, prod]
  - alias: db-1
    address: 10.0.0.21
    tags: [db, prod]
    bastion: jump-1        # 可选，ProxyJump
```

### 9.2 `config.yaml`

```yaml
inventory: ./hosts.yaml
sqlite_path: ./data/ops.db
concurrency: 16
ssh:
  connect_timeout: 8
  exec_timeout: 30
schedule:
  - check: disk_usage
    cron: "*/10 * * * *"
    hosts: [tag:prod]
  - check: failed_services
    cron: "*/5 * * * *"
    hosts: [tag:prod]
alerts:
  webhook: https://oapi.dingtalk.com/robot/send?access_token=XXX   # 待用户填
  on: [warn, crit]
allowlist_overrides:        # 可在默认白名单上增删
  add: []
  remove: []
```

## 10. 巡检定义 + 默认项

巡检为数据驱动（`Check{name, command(只读), parser, thresholds}`），默认内置：

| check | 命令（只读白名单） | 阈值 |
|---|---|---|
| `disk_usage` | `df -P` | warn>85%, crit>92%（任一挂载点） |
| `memory_usage` | `free -b` | warn>85%, crit>95% |
| `load_avg` | `cat /proc/loadavg` | warn>核数×1.0, crit>核数×2.0 |
| `failed_services` | `systemctl list-units --failed` | 任一 failed → crit |
| `zombie_procs` | `ps -eo stat,pid` | count>0 → warn |
| `uptime_reboot` | `uptime -s` | 记录；可选：近 1h 重启 → warn |

均为只读，无需 root（少数如 `ss -tlnp` 按需配 sudo 规则）。新增巡检 = 加一条数据，不改代码。

## 11. 告警（最小）

- 通知器：通用 `webhook`（POST JSON），覆盖钉钉 / 企业微信 / Slack / 自定义（各厂商消息体适配器）。
- 必写 SQLite + stdout（即使 webhook 未配置也有本地留痕）。
- 严重度 → 渠道路由留 v2。

## 12. 状态存储（SQLite，三张表够 v1）

```sql
CREATE TABLE command_audit (
  id INTEGER PRIMARY KEY,
  ts TEXT NOT NULL,
  host TEXT NOT NULL,
  command TEXT NOT NULL,
  rc INTEGER,
  initiated_by TEXT NOT NULL,   -- agent | daemon | user
  approved_by TEXT,             -- user 名 / 'auto' / NULL(denied)
  verdict TEXT NOT NULL,        -- auto_allow | approved | denied
  stdout_excerpt TEXT,
  stderr_excerpt TEXT
);

CREATE TABLE inspection_runs (
  run_id TEXT NOT NULL,         -- 一次巡检批次
  ts TEXT NOT NULL,
  host TEXT NOT NULL,
  check_name TEXT NOT NULL,
  status TEXT NOT NULL,         -- ok | warn | crit
  value_json TEXT NOT NULL
);

CREATE TABLE hosts (            -- 可选缓存画像
  alias TEXT PRIMARY KEY,
  facts_json TEXT,
  updated_ts TEXT
);

CREATE INDEX idx_audit_ts ON command_audit(ts);
CREATE INDEX idx_insp_ts ON inspection_runs(ts, host);
```

## 13. claude-agent-sdk 集成（基于已验证 API）

```python
from claude_agent_sdk import (
    query, ClaudeAgentOptions, McpSdkServerConfig,
    PermissionResultAllow, PermissionResultDeny,
)

async def can_use_tool(tool_name: str, tool_input: dict, context) -> PermissionResult:
    # 审批门：只拦截远程执行工具
    if tool_name == "mcp__ops__run_remote":
        verdict = policy.decide(tool_input["command"], context="interactive")
        if verdict.is_auto_allow:
            return PermissionResultAllow(updatedInput=tool_input)
        if verdict.is_deny:
            return PermissionResultDeny(reason=verdict.reason)
        # RequireApproval → 终端交互 y/n
        if await prompt_user_yes_no(tool_input):
            return PermissionResultAllow(updatedInput=tool_input)
        return PermissionResultDeny(reason="user declined")
    return PermissionResultAllow()   # 其它工具默认放行

opts = ClaudeAgentOptions(
    mcp_servers={"ops": McpSdkServerConfig(server=ops_mcp_server)},
    can_use_tool=can_use_tool,
    permission_mode="default",
    system_prompt=OPS_SYSTEM_PROMPT,
    disallowed_tools=["Bash", "Write", "Edit"],  # 防绕过
    max_turns=40,
)
async for msg in query(prompt=user_input, options=opts):
    render(msg)
```

> 说明：`PermissionResultAllow/Deny` 的确切字段、`McpSdkServerConfig` 的构造签名、`ToolPermissionContext` 形态，在实现计划阶段以本机 `claude_agent_sdk/types.py` 为准做最终核对（已确认这些符号存在）。

## 14. 开发什么 / 安装什么（直接回答原始问题）

### 14.1 开发（一个仓库 `ops-agent`）

```
ops-agent/
  pyproject.toml
  config.yaml
  hosts.yaml
  ops_core/      # inventory, remote_exec, allowlist, policy, inspection, store, alerting, config
  ops_mcp/       # MCP server（包 ops_core）
  ops_daemon/    # APScheduler 定时巡检入口
  ops_client/    # claude-agent-sdk 交互入口
  tests/
  docs/superpowers/specs/2026-06-23-ops-agent-design.md
```

### 14.2 安装

- **central box**（能 SSH 到所有 host 的那台，通常你的工作站或一台跳板）：
  - Python 3.11+，用 `uv` 建项目。
  - 依赖：`claude-agent-sdk`、`asyncssh`、`apscheduler`、`mcp`、`pyyaml`、`httpx`（webhook）、`sqlite3`（标准库）。
  - 配 `ANTHROPIC_API_KEY`（或订阅鉴权）。
  - 放好 SSH 私钥（`chmod 600`），确认能 SSH 到所有 host。
  - 跑两个进程：`ops-daemon`（常驻）+ `ops-client`（交互时起）。
- **被管 Linux 机器**：**什么都不装**。
  - 只要 `sshd` 在跑、有普通账号、你的公钥进了 `authorized_keys`。
  - 少数巡检（如 `ss -tlnp`）按需配 `sudoers` 规则。

### 14.3 端点关系小结

| 端点 | 数量 | 角色 | 装什么 |
|---|---|---|---|
| central box | 1 | 大脑 + 执行发起方 | Python + ops-agent + SSH 私钥 |
| 被管机器 | N | 哑 SSH 目标（被动） | 仅 sshd + 公钥 |
| 告警渠道 | 1+ | 出站通知 | webhook endpoint |

## 15. 测试策略

- **ops_core 纯函数单测**（mock `asyncssh`）：`allowlist` / `policy`（含黑名单、元字符降级、AutoAllow/RequireApproval/Deny 三档）/ `inspection` 解析与阈值。**黑名单与元字符注入是重点**。
- **集成测试**：起一个带 `sshd` 的 docker 容器当假 host，端到端验证 SSH 远程执行 + 巡检 + 审计落库。
- **MCP 工具测试**：校验工具 schema + 假 agent 调用返回。
- **daemon 测试**：scheduler 触发 → 写 `inspection_runs` → 阈值突破 → 告警（用假 webhook 端点拦截断言）。
- **client 测试**：mock `query()`，验证 `can_use_tool` 对白名单/黑名单/RequireApproval 的裁决路径。

## 16. 风险与假设

- **假设**：central box 能 SSH 到所有被管机器（push 前提）；任何一台 NAT/墙后即失效（已与用户确认当前全部可达）。
- **风险**：LLM 生成破坏性命令 → 由黑名单 + 审批 + 审计三层缓解。
- **风险**：SSH 扇出打满中心机/目标 → `Semaphore` 并发上限 + 超时。
- **风险**：私钥落盘 → `0600` + 单租户可信环境（v1 接受，v2 上密钥管理）。
- **假设**：单操作者，无需并发写 SQLite 冲突处理（WAL 模式即可）。

## 17. 待决策项（已代选默认值，可改）

1. **巡检默认项**：用上表 6 项；可增删。（数据驱动，改数据不改代码。）
2. **告警渠道**：默认通用 webhook，示例按**钉钉**（用户语境偏阿里系）；用户可指定企微/Slack/邮件，`config.yaml` 一行改。**webhook URL 待用户填。**
3. **危险黑名单**：默认严格（上表），CLI `--i-know-its-dangerous` 放行。可按需放宽。

## 18. 未来 / 延期（v2+）

多用户与 RBAC、Web 控制台、动态 inventory、agent 辅助的巡检结果智能解读与根因建议（只读，仍可触发）、WinRM、HA daemon、密钥管理、严重度→渠道路由、auto-remediation（经审批）。

---

**下一步**：用户 review 本 spec → 通过后进入 `writing-plans` skill 生成实现计划。
