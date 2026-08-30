# EdgeTunnel 本地 AI 工作规则

## 用白话理解这个项目

这个项目分成两部分：

```text
Cloudflare Pages / Worker
  = 页面、代理逻辑、监控逻辑、归档逻辑

GitHub hhhaiai/Picture/data/mysimivv
  = 长期运行数据、历史统计、异常记录、维护证据
```

再准确一点：

```text
KV / D1
  = 线上正在使用的配置和短期热数据

GitHub
  = 需要长期保留、供本地 AI 和人工维护读取的数据仓库
```

Pages/Worker 代码仓库不得保存运行时 Token、密码、Cookie、UUID、代理凭据或长期监控数据。GitHub 归档仓库也不得写入这些秘密。

## 固定地址

生产站点：

```text
https://mysimivv.pages.dev
```

GitHub 数据索引：

```text
https://raw.githubusercontent.com/hhhaiai/Picture/main/data/mysimivv/index.json
```

GitHub 数据目录：

```text
https://github.com/hhhaiai/Picture/tree/main/data/mysimivv
```

生产代码分支：

```text
fork/cf
```

## 线上如何写数据

线上 Worker 通过 Cloudflare Pages encrypted secret：

```text
GITHUB_MONITOR_TOKEN
```

调用 GitHub Contents API 写入 JSONL 和 `index.json`。

规则：

```text
1. Token 只存在 Cloudflare encrypted secret。
2. Token 不写入代码、日志、文档、D1、KV 或 GitHub 数据文件。
3. GitHub 上传和 index 更新都成功后，才能删除对应 D1 热数据。
4. GitHub 写入失败时保留 D1 数据，不能影响代理主链路。
5. 监控、GitHub 和维护功能全部 fail-open，代理稳定性优先。
```

## 本地 AI 每次开始维护时必须做什么

先读取线上数据，不要只看代码猜问题：

```bash
python3 scripts/list-github-anomalies.py \
  --since-hours 72 \
  --files 30 \
  --limit 100
```

需要观察客户端断开时才加：

```bash
python3 scripts/list-github-anomalies.py \
  --include-disconnects
```

默认异常规则：

```text
outcome == error
或 status >= 500
或 archive_parse_error
```

`client_disconnected` 默认不等于服务 Bug。

## AI 排查顺序

固定按以下顺序工作：

```text
1. 读取 GitHub index.json。
2. 生成最近异常列表。
3. 按 kind/outcome/status/colo/node 分组。
4. 先处理最新且重复最多的异常。
5. 找到 _worker.js 中对应入口、catch 路径和状态变化。
6. 建立最小复现。
7. 先增加回归测试。
8. 修复代码。
9. 运行全部测试。
10. 部署预览并验证真实行为。
11. 部署生产并验证稳定域名。
12. 确认相同异常不再出现。
13. 检查 staged diff 和秘密扫描。
14. commit 并 push 到 fork/cf。
```

不能把：

```text
构建成功
单元测试成功
部署命令成功
```

直接写成：

```text
生产功能已经正常
```

必须验证实际生产地址和真实请求行为。

## 异常优先级

### P0：立即处理

```text
WS/gRPC/XHTTP 大量失败
多个用户同时失败
所有 colo 同时失败
连续 HTTP 5xx
代理主链路不可用
AI/海外网站兼容探测全局失败
```

### P1：按线路或服务处理

```text
单一 colo 错误率升高
单个入口或出口集中失败
ChatGPT/Claude/TikTok 某服务集中失败
TCP/TLS 超时增加
出口 IP 兼容性下降
```

### P2：观察后处理

```text
单一用户单次失败
client_disconnected
极短连接
没有重复出现的孤立异常
```

## AI 和海外网站兼容检查

真实链路检查：

```bash
python3 scripts/probe-ai-sites.py --nodes 20 --workers 8
```

检查范围包括：

```text
Google
YouTube
X
Grok / xAI API
ChatGPT / OpenAI API
Claude / Anthropic API
Gemini / Gemini API
TikTok
Instagram
Facebook
Reddit
Discord
```

判定：

```text
pass                 = 2xx/3xx
reachable_restricted = 4xx，网络/TLS可达但需要认证或触发站点限制
fail                 = 隧道、TCP、TLS、超时或 5xx 失败
```

API 未带 Key 返回 401，只能证明网络和鉴权入口可达，不能证明账号、额度或 Key 正常。

TikTok 首页 200 不能代替视频 API、媒体分片和连续播放验收。

## 真实出口检查

不要把 20 个订阅入口当成 20 个出口。

运行：

```bash
python3 scripts/probe-egress-pool.py \
  --nodes 20 \
  --workers 6
```

要求至少 20 个真实出口时：

```bash
python3 scripts/probe-egress-pool.py \
  --nodes 20 \
  --workers 6 \
  --minimum-unique 20
```

唯一正确门槛：

```text
observed_unique_egress_ips >= 20
```

订阅有 20 行、入口有 20 个、代理配置有 20 条，都不能代替真实出口去重结果。

Cloudflare 默认共享出口会动态变化，必须记录观测时间、国家、colo 和数据新鲜度，不能永久绑定入口与出口。

## DNS 和出口切换规则

```text
DNS/目标地址失败
  -> 更换 DoH、刷新 A/AAAA、目标地址竞速

确认出口 IP 被目标服务拒绝
  -> 将该出口对该服务标记 blocked/cooldown
  -> 新会话切换其他兼容出口

账号认证失败
  -> 不盲目切换 DNS 或出口

HTTP 429
  -> 限速、冷却并按服务降低出口权重
```

同一个 WebSocket/TCP 连接不能中途切换出口。AI 账号应按会话保持 30–60 分钟粘滞，只有出口故障时才切换。

## 测试和提交门禁

每次代码修改至少运行：

```bash
node --check _worker.js
node --test tests/*.test.mjs
git diff --check
```

修改 Python 维护脚本时运行：

```bash
python3 -B -c "compile(open('scripts/脚本名.py', encoding='utf-8').read(), 'scripts/脚本名.py', 'exec')"
```

提交前：

```text
1. 检查 git status。
2. 只暂存本次相关文件。
3. 检查 git diff --cached --name-status。
4. 检查 git diff --cached --stat。
5. 运行 git diff --cached --check。
6. 扫描 Token、密码、Cookie、UUID、代理凭据和运行输出。
7. commit。
8. push fork cf。
9. 如果代码影响生产，使用 commit SHA 重新部署并验证 Source。
```

## 维护文档

详细异常维护流程：

```text
docs/AI_MAINTENANCE_RUNBOOK.md
```

动态出口证据和目标架构：

```text
docs/2026-08-30_architecture-edgetunnel-dynamic-egress-report.md
```

## 数据和隐私边界

允许归档：

```text
时间
协议类型
状态码
outcome
上下行字节
持续时间
国家
Cloudflare colo
公开入口/出口 IP
经过清洗的 error_stage/error_code
```

禁止归档：

```text
GitHub Token
ADMIN
完整 UUID
订阅 Token
Cookie
API Key
代理用户名和密码
完整敏感 URL
用户原始 IP
```
