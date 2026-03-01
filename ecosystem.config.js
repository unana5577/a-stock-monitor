module.exports = {
  apps: [{
    name: "a-stock-monitor",
    script: "./server.js",
    instances: 1,
    autorestart: true,
    watch: false,
    max_memory_restart: "1G",
    env: {
      NODE_ENV: "production",
      PORT: 8787
    },
    interpreter: "node",
    // 显式指定日志文件位置，方便查看
    error_file: "./logs/err.log",
    out_file: "./logs/out.log",
    merge_logs: true,
    log_date_format: "YYYY-MM-DD HH:mm:ss"
  }]
}
