// pm2 ecosystem config -- Norman Retail System\n// Start everything:  pm2 start ecosystem.config.js
// Stop everything:   pm2 stop all
// Restart everything: pm2 restart all
// View logs:         pm2 logs
// View status:       pm2 status

const path = require("path");
const REPO_ROOT = __dirname;

module.exports = {
  apps: [
    {
      name: "norman-backend",
      script: "python",
      args: "-m uvicorn app.main:app --port 8000",
      cwd: path.join(REPO_ROOT, "backend"),
      autorestart: true,
      max_restarts: 10,
      restart_delay: 2000,
      out_file: path.join(REPO_ROOT, "logs", "backend-out.log"),
      error_file: path.join(REPO_ROOT, "logs", "backend-err.log"),
      merge_logs: true,
      time: true,
      env: {
        PYTHONUNBUFFERED: "1",
      },
    },
    {
      name: "norman-frontend",
      script: "cmd.exe",
      args: "/c npm run dev",
      cwd: path.join(REPO_ROOT, "frontend"),
      autorestart: true,
      max_restarts: 10,
      restart_delay: 2000,
      out_file: path.join(REPO_ROOT, "logs", "frontend-out.log"),
      error_file: path.join(REPO_ROOT, "logs", "frontend-err.log"),
      merge_logs: true,
      time: true,
    },
    {
      name: "norman-ngrok",
      script: "ngrok",
      args: "http 8000 --log stdout",
      autorestart: true,
      max_restarts: 10,
      restart_delay: 5000,
      out_file: path.join(REPO_ROOT, "logs", "ngrok-out.log"),
      error_file: path.join(REPO_ROOT, "logs", "ngrok-err.log"),
      merge_logs: true,
      time: true,
    },
  ],
};
