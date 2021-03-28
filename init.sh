#!/bin/sh

apt-get update
apt-get upgrade -y
apt-get install -y gcc python3.8 python3-pip git supervisor
ufw allow ssh
ufw enable
#mkdir /var/python/
#cd /var/python
git clone https://github.com/paradox02/trader20_automation.git

cd trader20_automation

pip3 install -r requirements.txt

WriteToConfig() {
  #  remove exist file
  rm -f config.yaml

  #  yaml template
  template="app:
  market_type: SPOT  # SPOT / FUTURES

  spot:
    trade_amount:
      USDT: 100
      BTC: 0.002

  futures:
    trade_amount:
      USDT: 100
    leverage: SMART  # 1-125 / SMART
    max_leverage: 10  # for SMART leverage
    margin_type: ISOLATED  # ISOLATED / CROSS

binance_api:
  key: $binanceApi
  secret: $binanceSecret

discord:
  #channel: 759070661888704613  # official Trader 2.0 channel
  channel: 819957153476378634  # testing channel https://discord.gg/9rpkqBfArk
  token: $discordToken
  #test_user: name#123  # discord user

email:
  recipient: $recipient
  host: $mailHost
  user: $mailUser
  password: $mailPassword"
  echo "$template" >config.yaml
}

ConfirmData() {
  while true; do
    printf "Je údaj vyplnený správne $* ? \n áno - [jj] ; nie - [ee] + [ENTER]\n"
    read -p "" yn

    case $yn in
    [Yy]*)
      break
      ;;
    [jj]*)
      break
      ;;
    [Nn]*)
      echo "Ukončené užívateľom "
      exit
      ;;
    [ee]*)
      echo "Ukončené užívateľom"
      exit
      ;;
    *) echo "použí [jj] alebo [ee] + [ENTER]" ;;
    esac
  done
}

officalDiscord=true

#printf "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!\n"
#printf "!!! nepoužívaj skratku      [CTRL] + [V] - ukončí program!!                                 !!!\n"
#printf "!!! radšej použi  [SHIFT] + [CTRL] + [V]                                                    !!!\n"
#printf "!!! alebo klikni na koliečko myši, prípadne pravé tlačidlo a z možností zvol vložiť (paste) !!!\n"
#printf "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!! \n \n"

printf "Vlož BINANCE_API a stlač [ENTER]\n"
read -r binanceApi
ConfirmData "BINANCE_API = $binanceApi "

printf "Vlož BINANCE_SECRET a stlač [ENTER]\n"
read -r binanceSecret
ConfirmData "BINANCE_SECRET = $binanceSecret"

printf "Vlož DISCORD_TOKEN a stlač [ENTER]\n"
read -r discordToken
ConfirmData "DISCORD_TOKEN = $discordToken"

printf "Vlož príjemcu emailov a stlač [ENTER]\n"
read -r recipient
ConfirmData "príjemca emailov = $recipient\n"

printf "Vlož odosielatela vo formáte xzy@abc.px a stlač [ENTER]\n"
read -r mailUser
ConfirmData "odosielatel emailov = $mailUser\n"

printf "Vlož heslo k emailu $mailUser a stlač [ENTER]\n"
read -r mailPassword
ConfirmData "heslo k $mailUser -> $mailPassword\n"

printf "Vlož smtp serveru k emailu $mailUser a stlač [ENTER]\n"
printf "malo by to mať formát smtp.abc.px [ENTER]\n"
read -r mailHost
ConfirmData "smtp server k $mailUser je $mailHost\n"

printf "Chceš počúvať oficiálny discord? [jj/ee]\n"
read -r officalDiscordInput
ConfirmData "použiť oficiálny discord = $officalDiscordInput\n"

if [ $officalDiscordInput == "jj" ]; then
  officalDiscord=true;
else
  officalDiscord=false;
fi

if $officalDiscord; then
  #    live
  discordAddress="759070661888704613"
else
  #    test
  discordAddress="819957153476378634"
fi
printf "discord Address = $discordAddress\n"

WriteToConfig

echo "[program:trader20_automation]
command=/bin/bash -c 'python3.8 /var/python/trader20_automation/run_bomberman_coins.py'
autostart=true
autorestart=true
numprocs=1
stderr_logfile=/var/python/trader20_automation/log/supervisor.err.log
stdout_logfile=/var/python/trader20_automation/log/supervisor.out.log" >>/etc/supervisor/conf.d/trader20_automation.conf
supervisorctl reread && supervisorctl update

# supervisorctl reread && sudo supervisorctl update

python3.8 run_bomberman_coins.py
