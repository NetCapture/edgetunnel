# AI 异常维护规则

> 线上 Worker 使用 Cloudflare 加密 Secret `GITHUB_MONITOR_TOKEN` 通过 GitHub Contents API 写入归档；AI 或维护脚本从公开 Raw 地址只读，不需要持有写入 Token。

## 获取异常列表

稳定索引地址：

```text
https://raw.githubusercontent.com/hhhaiai/Picture/main/data/mysimivv/index.json
```

归档目录：

```text
https://github.com/hhhaiai/Picture/tree/main/data/mysimivv
```

直接生成最近 72 小时异常列表：

```bash
python3 scripts/list-github-anomalies.py
```

常用参数：

```bash
# 最近 24 小时，最多 50 条
python3 scripts/list-github-anomalies.py \
  --since-hours 24 \
  --limit 50

# 同时把客户端主动断开纳入观察
python3 scripts/list-github-anomalies.py \
  --include-disconnects

# CI/自动维护：发现异常时返回退出码 1
python3 scripts/list-github-anomalies.py \
  --fail-on-anomaly
```

## 线上写入规则

Cloudflare Worker：

```text
monitor_events D1 热数据
  -> 定时或容量触发归档
  -> GitHub Contents API 上传 JSONL
  -> 更新 data/mysimivv/index.json
  -> 上传和索引成功后才删除对应 D1 行
```

写入 Token：

```text
Cloudflare Pages encrypted secret: GITHUB_MONITOR_TOKEN
```

代码、文档、JSONL、订阅和 AI 读取脚本中都不保存该 Token。

## 异常判定规则

默认计入异常：

```text
outcome == "error"
或 status >= 500
或 archive_parse_error
```

默认不把以下状态直接当作服务 Bug：

```text
client_disconnected
```

客户端断开可能来自：

```text
用户切换节点
网络变化
客户端退出
页面关闭
移动网络切换
```

需要观察断开时，显式使用：

```bash
python3 scripts/list-github-anomalies.py --include-disconnects
```

## AI 维护流程

每次维护按以下顺序执行：

```text
1. 读取 index.json
2. 下载最新 JSONL
3. 生成异常列表
4. 按 kind/outcome/status/colo/node 分组
5. 选择最新且重复最多的异常
6. 回到 _worker.js 定位对应请求和错误路径
7. 建立最小复现
8. 先写回归测试
9. 修复代码
10. 运行全部测试
11. 预览部署
12. 生产部署
13. 验证相同异常不再出现
14. commit 并 push 到 fork/cf
```

推荐的读取命令：

```bash
python3 scripts/list-github-anomalies.py \
  --since-hours 72 \
  --files 30 \
  --limit 100
```

## 排查优先级

### P0：代理主链路

```text
ws/grpc/xhttp 大量 error
连续 HTTP 5xx
所有 colo 同时失败
多个匿名用户同时失败
出口兼容探测全局失败
```

### P1：局部线路或出口

```text
单一 colo 错误率升高
单一入口/出口集中失败
ChatGPT/Claude/TikTok 某服务集中异常
TCP/TLS 超时上升
```

### P2：客户端或一次性错误

```text
单一用户单次失败
client_disconnected
极短连接
没有重复出现的异常
```

## 输出字段

异常列表统一输出：

```text
id
ts/time
kind
method
status
outcome
requests
bytes_up/bytes_down
duration_ms
country
colo
node_ip/node_port/node_group
archive_path
```

这些字段足以定位：

```text
什么协议失败
何时失败
哪个 Cloudflare colo
哪个入口节点
失败是否重复
对应原始归档文件
```

## 当前限制

当前监控事件主要记录结构化状态，并不保证每个异常都包含完整 JavaScript 堆栈或底层 socket 错误文本。

因此异常列表可以可靠回答：

```text
哪里失败、什么时候失败、失败多少次
```

但某些问题仍需结合：

```text
Cloudflare 实时日志
最小复现探针
目标网站响应
对应代码 catch 路径
```

后续如需更精确，可在不记录凭据、UUID、Cookie、完整目标 URL 的前提下增加：

```text
error_stage
error_code
sanitized_error
service_category
egress_observation_id
```

## AI 提示词入口

后续让 AI 维护时，可以直接说明：

```text
读取 https://raw.githubusercontent.com/hhhaiai/Picture/main/data/mysimivv/index.json，
使用 scripts/list-github-anomalies.py 生成最近 72 小时异常列表，
按 P0/P1/P2 分类，从重复最多的异常开始复现和修复。
不要把 client_disconnected 默认当成服务 Bug；
不要输出或保存任何 Token、UUID、Cookie 或代理凭据。
```
