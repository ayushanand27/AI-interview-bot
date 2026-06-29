/**
 * PM2 process manager config for the FastAPI backend on AWS EC2.
 *
 * Start:  pm2 start deploy/ecosystem.config.js
 * Logs:   pm2 logs ai-interview-bot-backend
 * Save:   pm2 save && pm2 startup
 */
const path = require("path");

const appDir = path.resolve(__dirname, "..");
const venvUvicorn = path.join(appDir, ".venv", "bin", "uvicorn");

module.exports = {
  apps: [
    {
      name: "ai-interview-bot-backend",
      cwd: appDir,
      script: venvUvicorn,
      args: "app.main:app --host 127.0.0.1 --port 8080 --workers 1",
      interpreter: "none",
      autorestart: true,
      max_restarts: 10,
      min_uptime: "10s",
      env: {
        APP_ENV: "production",
      },
    },
  ],
};
