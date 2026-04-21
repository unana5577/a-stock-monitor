本次修复包含：新增板块代理口径接口、支持本地预热缓存并同步到服务器、避免东财封禁导致板块不可用。

更新文件
- server.js
- public/ui.js
- public/index.html
- fetch_sector_data.py

新增/增强接口（后端）
- /api/sector/proxy：读取/写入板块→代理指数/ETF 代码映射（theme/hs300）
- /api/sector/history_proxy：代理口径日线+分时分钟序列
- /api/sector/rotation_proxy：代理口径盘后主线&轮动
- /api/sector/warmup：支持 start/end 回补区间并输出状态
- /api/sector/rotation/intraday：分钟缺失时按代理映射补分钟序列

本地预热与导出缓存（推荐，避免服务器爆）
- 最近60天预热（默认主题口径）
  - python3 fetch_sector_data.py warmup "半导体,云计算,有色金属,通讯设备,新能源,商业航天,创新药" 60
  - 输出：data/sector-history-warmup-<day>-60.json、data/sector-minute-warmup-<day>.json
- 全量区间（2025-05-19→2026-03-02）
  - python3 fetch_sector_data.py proxy_range 半导体 2025-05-19 2026-03-02
  - 其他板块同理
  - 输出：data/sector-history-<板块>-2025-05-19-2026-03-02.json

打包交付
- tar czf sector-data-backup.tar.gz data/sector-*.json

服务器上线流程（cc 执行）
- 上传上述更新文件到 /opt/a-stock-monitor
- docker cp 注入到容器 /app 对应路径并 docker restart
- curl 验证新接口返回 200
