const fs = require('fs');
const path = require('path');

const LOG_DIR = path.join(__dirname, 'logs');

function getLogFile() {
  const date = new Date().toISOString().split('T')[0];
  return path.join(LOG_DIR, `debug-${date}.log`);
}

function formatTime() {
  return new Date().toISOString().replace('T', ' ').slice(0, 19);
}

function write(level, apiName, url, message, extra = {}) {
  const timestamp = formatTime();
  const logLine = `[${timestamp}] [${level}] ${apiName} ${url} - ${message}`;

  const logEntry = extra && Object.keys(extra).length > 0
    ? `${logLine} | ${JSON.stringify(extra)}\n`
    : `${logLine}\n`;

  fs.appendFileSync(getLogFile(), logEntry);
}

const logger = {
  request: (apiName, url) => write('INFO', apiName, url, 'REQUEST_START'),
  success: (apiName, url, status, latency) =>
    write('INFO', apiName, url, `SUCCESS ${status}`, { latencyMs: latency }),
  error: (apiName, url, err, context = {}) =>
    write('ERROR', apiName, url, err.message, {
      code: err.code,
      stack: err.stack?.split('\n').slice(0, 3).join(' | '),
      ...context
    })
};

module.exports = logger;
