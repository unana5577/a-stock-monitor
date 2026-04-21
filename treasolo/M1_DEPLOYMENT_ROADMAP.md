# A股智能监控系统：本地向服务器演进的改造路线图 (Roadmap)

本文档记录了将本项目从“纯本地离线运行”向“云端 Docker 化部署”平滑演进的核心改造步骤，确保在服务器和域名准备就绪前，本地开发与运行完全不受影响。

## 核心原则
- **坚持本地离线数据驱动**：坚决不使用外部 DBaaS（如 Supabase），避免极高的网络延迟与写入失败风险。所有数据继续以 `.json` 和 `.jsonl` 形式落在 `data/` 目录下。
- **向下兼容的渐进式改造**：所有改造必须保证 `npm run dev` 和本地 n8n 能够继续完美运行，最后再平滑切换到 Docker 环境。

---

## 阶段一：代码级的“环境自适应”改造（近期在本地做）
*目标：让代码既认识你 Mac 的绝对路径，也认识未来 Docker 的相对路径。*

1. **消除硬编码的绝对路径**
   - **Python 层**：清理所有类似 `/Users/una5577/...` 的路径，统一使用 `pathlib.Path(__file__).parent` 往上推导项目根目录。
   - **Node.js 层**：在 `server.js` 中使用 `__dirname` 或 `process.cwd()` 动态拼接文件路径。
2. **前端接口相对化**
   - 在 `public/ui_m1.js` 等前端文件中，将硬编码的 `http://localhost:8787/api/...` 修改为相对路径 `/api/...`，以便线上访问域名时能正确路由。
3. **环境变量抽离**
   - 将 DeepSeek API Key、n8n Webhook 地址等易变配置抽离到 `.env` 文件中。本地读取本地的 `.env`，线上通过 Docker 注入线上的配置。

## 阶段二：容器化打包与本地测试（搞定代码后在本地做）
*目标：把 Node+Python 混合环境封进 Docker，确保在 Mac 的 Docker Desktop 里能跑通。*

1. **环境梳理与锁定**
   - 生成标准的 `requirements.txt`，锁定 AKShare、Pandas 等 Python 依赖的版本。
2. **编写 Dockerfile (业务容器)**
   - 以 Node.js 为基础镜像，在内部安装 `python3` 和 `pip`，并安装 `requirements.txt` 中的依赖。
   - 暴露 `8787` 端口供外部访问。
3. **编写 docker-compose.yml (编排容器)**
   - 定义两个主要服务：
     - `app`：你的业务容器（运行 `server.js`），挂载本地 `data/` 目录。
     - `n8n`：官方 n8n 容器，挂载 `n8n-workflows/` 目录，用于跑定时抓取。
4. **本地验证**
   - 在 Mac 上执行 `docker-compose up` 测试。如果容器内能正常抓取数据并渲染前端，说明打包成功（测试完可随时关掉，继续用本地裸跑）。

## 阶段三：服务器基建与数据迁移（买好服务器后做）
*目标：把验证过的系统搬到云端，继承历史数据。*

### 预期线上部署目录结构
部署到云服务器后（以 `/opt/a-stock-monitor` 为例），最终挂载与运行结构应如下所示：

```text
/opt/a-stock-monitor/
├── docker-compose.yml          # Docker 编排配置（管理 app 和 n8n 容器）
├── Dockerfile                  # 构建包含 Node+Python 环境的业务镜像
├── .env                        # 生产环境变量（如 DeepSeek API Key, Webhook URL）
├── data/                       # ⚠️ 宿主机核心数据卷（从 Mac rsync 同步过来，不进 Git）
│   ├── market/
│   ├── etf/
│   ├── index/
│   ├── warmup/
│   └── lifecycle/
├── src_code/                   # 从 Git 仓库 clone 下来的代码（挂载到 app 容器）
│   ├── server.js
│   ├── public/                 # 前端静态页面
│   ├── treasolo/               # Python 业务逻辑脚本（抓取、聚合、AI 播报等）
│   └── scripts/
│       └── legacy/             # ⚠️ M1-Lifecycle 核心分析逻辑（如 sector_lifecycle.py）
└── n8n-workflows/              # 工作流定义文件（映射到 n8n 容器的 import 目录，可选）
```

1. **服务器准备**
   - 推荐配置：2核 4G（应对 AKShare 和 Pandas 的内存消耗）。
   - 安装基础设施：仅需安装 Docker 和 Nginx。
2. **历史数据迁移 (核心)**
   - 使用 `rsync` 或 `scp` 将 Mac 本地的 `data/` 目录完整传到服务器的指定目录（如 `/opt/a-stock-monitor/data`）。这能让你上线首日就拥有 60 天的完整历史曲线。
3. **时区强制锁定**
   - 在 `docker-compose.yml` 中为所有容器注入环境变量 `TZ=Asia/Shanghai`，防止服务器默认的 UTC 时区导致定时任务和 `datetime.now()` 错乱。
4. **服务启动与 Nginx 反向代理**
   - 在服务器 `git clone` 代码并启动容器。
   - 配置 Nginx 监听你的域名（80/443 端口），将请求转发给内部的 `8787` 端口。

## 阶段四：n8n 调度迁移与正式切流
1. **工作流迁移**
   - 将本地 n8n 中的工作流导出（Export），导入到服务器上的 n8n 容器中。
2. **内部调用地址替换**
   - 将工作流中请求后端的 HTTP 节点地址，从 `localhost:8787` 改为 Docker 的内部服务名（如 `http://app:8787`）。
3. **彻底切流**
   - 关闭本地 Mac 的 n8n 自动调度，由服务器全权接管定时抓取与复盘任务。
