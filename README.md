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
- `virtualenv venv && source venv/bin/activate && pip install -r requirements.txt`
- `cp config.yaml.example config.yaml` and fill in variables

## Run

`python run_bomberman_coins.py 100` 100 is amount per each transaction

I strongly recommend running command within [supervisor](http://supervisord.org/running.html), which restarts command
when error occurs.

## Donate

I made this project for myself, but if it is solving your problem [consider donation](https://revolut.me/jakub20w6)
