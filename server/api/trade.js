const ctx = require('../context');
ctx.install(global);

module.exports = function() {
  const handleRoute = async function(req, res) {
    const url = new URL(req.url, `http://${req.headers.host}`);

    // Agent C: 交易助手页专属路由写在这里
    // 例如: if (url.pathname === '/api/trade/xxx') { ... }

    return false;
  };
  return handleRoute;
};
