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

