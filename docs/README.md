# EdgeTunnel 运维文档索引

## 项目入口

| 内容 | 位置 | 用途 |
|---|---|---|
| 本地 AI 固定规则 | [`../AGENT.md`](../AGENT.md) | AI 修改、测试、部署和提交前必须读取 |
| 标准 AI 发现入口 | [`../AGENTS.md`](../AGENTS.md) | 自动引导 AI 读取 `AGENT.md` |
| AI 异常维护 | [`AI_MAINTENANCE_RUNBOOK.md`](AI_MAINTENANCE_RUNBOOK.md) | 从 GitHub 归档提取异常并逐项修复 |
| 动态出口报告 | [`2026-08-30_architecture-edgetunnel-dynamic-egress-report.md`](2026-08-30_architecture-edgetunnel-dynamic-egress-report.md) | 当前出口证据、硬门槛和目标架构 |

## 数据入口

长期数据索引：

```text
https://raw.githubusercontent.com/hhhaiai/Picture/main/data/mysimivv/index.json
```

GitHub 数据目录：

```text
https://github.com/hhhaiai/Picture/tree/main/data/mysimivv
```

生产站点：

```text
https://mysimivv.pages.dev
```

## 本地维护脚本

| 脚本 | 命令 | 用途 |
|---|---|---|
| GitHub 异常列表 | `python3 scripts/list-github-anomalies.py` | 获取最近错误和 5xx 事件 |
| AI/海外网站探测 | `python3 scripts/probe-ai-sites.py --nodes 20 --workers 8` | 通过真实 VLESS 链路检查网站/API |
| 真实出口探测 | `python3 scripts/probe-egress-pool.py --nodes 20 --workers 6` | 获取每个入口最终观察到的公网出口 |
| 20 出口硬验收 | `python3 scripts/probe-egress-pool.py --nodes 20 --minimum-unique 20` | 唯一真实出口不足 20 时返回失败 |

## 固定维护顺序

```text
读取 AGENT.md
-> 获取 GitHub 异常列表
-> P0/P1/P2 分类
-> 最小复现
-> 回归测试
-> 修复
-> 全量测试
-> 预览验证
-> 生产验证
-> commit
-> push fork/cf
```

## 数据边界

GitHub 长期保存运行统计、异常和维护证据；KV/D1 保存线上配置和短期热数据；Pages/Worker 保存前端与执行逻辑。

任何仓库和归档都不得保存 GitHub Token、管理员密码、完整 UUID、订阅 Token、Cookie、API Key 或代理凭据。
