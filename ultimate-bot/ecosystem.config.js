module.exports = {
  apps: [
    {
      name: 'ultimate-bot',
      script: 'main.py',
      interpreter: './venv/bin/python3',
      cwd: __dirname,
      max_memory_restart: '2G',
      watch: false,
      env: {
        NODE_ENV: 'production'
      },
      error_file: './logs/pm2-error.log',
      out_file: './logs/pm2-out.log',
      log_file: './logs/pm2-combined.log',
      time: true
    },
    {
      name: 'bot-web-monitor',
      script: 'status.py',
      args: '--web 3000',
      interpreter: './venv/bin/python3',
      cwd: __dirname,
      watch: false,
      error_file: './logs/web-error.log',
      out_file: './logs/web-out.log',
      time: true
    }
  ]
};
