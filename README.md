# Trader 2.0 Automation

## Disclaimer

- This project is for my personal needs. You are free to use it on your own responsibility.
- API calls used in this project are against Discord terms and can cause disabling your Discord account.

## Known problems

- Market sell order message will **cancel all** existing OCO orders and **sell total amount for market price**. It does
  not understand selling just first target and keeping second. This is non-standard situation that happened just few
  times in history and it is not easy to handle to automatically because message format is not standardized.

## Setup

- You need to  python 3.8 and higher for this project. 
- `pip3 install -r requirements.txt`
- `cp config.yaml.example config.yaml` and fill in variables

## Run

`python3 run_bomberman_coins.py`

I strongly recommend running command within [supervisor](http://supervisord.org/running.html), which restarts command
when error occurs. Example supervisor config `/etc/supervisor/conf.d/trader20_automation.conf`:

```
[program:trader20_automation]
command=/bin/bash -c 'python3 /var/python/trader20_automation/run_bomberman_coins.py'
autostart=true
autorestart=true
numprocs=1
stderr_logfile=/var/python/trader20_automation/log/supervisor.err.log
stdout_logfile=/var/python/trader20_automation/log/supervisor.out.log
```

## Donate

I made this project for myself, but if it is solving your problem consider donation:
- ETH BEP20: 0xa51eeabe839542620302c8d4218f49310f137a23
- BNB BEP20: 0xa51eeabe839542620302c8d4218f49310f137a23
- [Revolut](https://revolut.me/jakub20w6)
