# known-issues（踩坑记忆）

每条问题必须三行格式，按时间倒序追加。开始做任何新工作流前，先逐条确认不会复现。

Symptom: n8n HTTP Request 报 Invalid URL: undefined/api/runner/run
Root cause: n8n 版本/执行语义导致表达式引用前置节点变量失败，URL 拼接得到 undefined
Fix: HTTP Request 节点 URL 写死完整 http(s) 地址（M0 默认用 http://127.0.0.1:8787/api/runner/run），不使用变量拼接

Symptom: n8n HTTP Request 报 The service refused the connection - perhaps it is offline（访问 127.0.0.1:8787）
Root cause: Node 服务默认监听 IPv6（::），n8n 走 IPv4（127.0.0.1）导致连接被拒
Fix: server.js 强制监听 127.0.0.1（server.listen(PORT, '127.0.0.1', ...)）并重启服务

Symptom: n8n IF 节点报 compareOperationFunctions[compareData.operation] is not a function
Root cause: 旧版 n8n 不支持 operation=isTrue 等较新比较操作
Fix: IF 条件改用 equals true；交易时段计算避免依赖 $now.setZone，改用 Intl.DateTimeFormat(timeZone='Asia/Shanghai')

Symptom: n8n IF 节点报 compareOperationFunctions[compareData.operation] is not a function (equals)
Root cause: IF 节点配置中使用了 'equals' 而非官方早期支持的 'equal'
Fix: 将 IF 节点 JSON 中的 'operation': 'equals' 统一替换为 'operation': 'equal'

Symptom: 发现 data/index_daily/index_000001.jsonl 中 4-16 数据缺失且近期 amount 数量级异常（东财接口被封导致错乱）。
Root cause: 历史代码直接依赖了失效接口并写入旧文件。
Fix: TODO(M1/M2) 评估历史数据迁移与覆盖方案，暂时不动该文件，新逻辑（M0）产生的数据已隔离到 data/market/market-amount-daily.jsonl。

