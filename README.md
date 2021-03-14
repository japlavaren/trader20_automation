# Trader 2.0 Automation

## Disclaimer

- This project is for my personal needs. You are free to use it on your own responsibility.
- API calls used in this project are against Discord terms and can cause disabling your Discord account.

## Setup

- `virtualenv venv && source venv/bin/activate && pip install -r requirements.txt`
- `cp config.yaml.example config.yaml` and fill in variables

## Run

`python run_bomberman_coins.py 100` 100 is amount per each transaction

I strongly recommend running command within [supervisor](http://supervisord.org/running.html), which restarts command
when error occurs.

## Donate

I made this project for myself, but if it is solving your problem [consider donation](https://revolut.me/jakub20w6)
