    1  ls
    2  pwd
    3  help
    4  sudo apt update && sudo apt upgrade -y
    5  sudo apt install -y python3 python3-pip python3-venv git
    6  scp -i "trading.pem" trading_2_live4_claude2_v4.py ubuntu@13.60.78.16:~/
    7  ls
    8  python3 -m venv venv
    9  nano .env
   10  source venv/bin/activate
   11  pip install -r requirements.txt 
   12  python 
   13  nano requirements.txt 
   14  pip install -r requirements.txt 
   15  exit
   16  ls
   17  source venv/bin/activate
   18  python3 trading_2_live4_claude2_v4.py --mode backtest --api-key BINANCE_TESTNET_KEY --api-secret BINANCE_TESTNET_SECRET --nassets 30 --timeframe 4h --enable-sell --sell-gauge-pct 100 --tp-mult 7 --sl-widen-mult 1.3 --partial-tp-r 3 --maxcon 7 --workers 4 --history-days 730 --po-wait-s 300 --be-escape --be-escape-move-r 0.30 --be-escape-min-profit-r 0.1 --no-dynamic-trail --heat-max 0.15 --capital 100 --history-days 100 --no-breakeven --opp-tp --no-be-escape-ema --analytics
   19  cat gtt6.log
   20  nano gtt6.log
   21  python3 trading_2_live4_claude2_v4.py --mode backtest --api-key BINANCE_TESTNET_KEY --api-secret BINANCE_TESTNET_SECRET --nassets 30 --timeframe 4h --enable-sell --sell-gauge-pct 100 --tp-mult 7 --sl-widen-mult 1.3 --partial-tp-r 3 --maxcon 7 --workers 4 --history-days 730 --po-wait-s 300 --be-escape --be-escape-move-r 0.30 --be-escape-min-profit-r 0.1 --no-dynamic-trail --heat-max 0.15 --capital 100 --history-days 100 --no-breakeven --opp-tp --no-be-escape-ema --analytics
   22  python3 trading_2_live4_claude2_v4.py --mode backtest --api-key BINANCE_TESTNET_KEY --api-secret BINANCE_TESTNET_SECRET --nassets 10 --timeframe 4h --enable-sell --sell-gauge-pct 100 --tp-mult 7 --sl-widen-mult 1.3 --partial-tp-r 3 --maxcon 7 --workers 4 --history-days 730 --po-wait-s 300 --be-escape --be-escape-move-r 0.30 --be-escape-min-profit-r 0.1 --no-dynamic-trail --heat-max 0.15 --capital 100 --history-days 100 --no-breakeven --opp-tp --no-be-escape-ema --analytics
   23  tar -xvzf market_data.tgz 
   24  ls
   25  python3 trading_2_live4_claude2_v4.py --mode backtest --api-key BINANCE_TESTNET_KEY --api-secret BINANCE_TESTNET_SECRET --nassets 10 --timeframe 4h --enable-sell --sell-gauge-pct 100 --tp-mult 7 --sl-widen-mult 1.3 --partial-tp-r 3 --maxcon 7 --workers 4 --history-days 730 --po-wait-s 300 --be-escape --be-escape-move-r 0.30 --be-escape-min-profit-r 0.1 --no-dynamic-trail --heat-max 0.15 --capital 100 --history-days 100 --no-breakeven --opp-tp --no-be-escape-ema --analytics
   26  ls
   27* rm asset_cache/
   28  python3 trading_2_live4_claude2_v4.py --mode backtest --api-key BINANCE_TESTNET_KEY --api-secret BINANCE_TESTNET_SECRET --nassets 10 --timeframe 4h --enable-sell --sell-gauge-pct 100 --tp-mult 7 --sl-widen-mult 1.3 --partial-tp-r 3 --maxcon 7 --workers 4 --history-days 730 --po-wait-s 300 --be-escape --be-escape-move-r 0.30 --be-escape-min-profit-r 0.1 --no-dynamic-trail --heat-max 0.15 --capital 100 --history-days 100 --no-breakeven --opp-tp --no-be-escape-ema --analytics
   29  sudo nano /etc/systemd/system/tradingbot.service
   30  sudo systemctl daemon-reload
   31  sudo systemctl enable tradingbot.service
   32  sudo systemctl start tradingbot.service
   33  ls
   34  sudo systemctl status tradingbot.service
   35  tail -f /home/ubuntu/bot.log
   36  sudo journalctl -u tradingbot.service -f
   37  sudo fallocate -l 2G /swapfile
   38  sudo chmod 600 /swapfile
   39  sudo mkswap /swapfile
   40  sudo swapon /swapfile
   41  echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
   42  free -h
   43  sudo systemctl edit tradingbot.service
   44  sudo systemctl daemon-reload
   45  sudo systemctl restart tradingbot.service
   46  sudo journalctl -u tradingbot.service -f
   47  tail -f /home/ubuntu/bot.log
   48  sudo systemctl stop tradingbot.service
   49  sudo nano /etc/systemd/system/tradingbot.service
   50  sudo systemctl daemon-reload
   51  sudo systemctl enable tradingbot.service
   52  sudo systemctl start tradingbot.service
   53  sudo systemctl status tradingbot.service
   54  tail -f /home/ubuntu/bot.log
   55  sudo systemctl stop tradingbot.service
   56  sudo systemctl start tradingbot.service
   57  tail -f /home/ubuntu/bot.log
   58  pip install pyarrow
   59  sudo systemctl stop tradingbot.service
   60  sudo systemctl start tradingbot.service
   61  tail -f /home/ubuntu/bot.log
   62  sudo systemctl stop tradingbot.service
   63  sudo nano /etc/systemd/system/tradingbot.service
   64  sudo systemctl daemon-reload
   65  sudo systemctl enable tradingbot.service
   66  sudo systemctl start tradingbot.service
   67  sudo systemctl status tradingbot.service
   68  tail -f /home/ubuntu/bot.log
   69  sudo systemctl stop tradingbot.service
   70  rm market_data_cache/*
   71  tar -xvzf market_data.tgz 
   72  sudo systemctl start tradingbot.service
   73  sudo systemctl status tradingbot.service
   74  tail -f /home/ubuntu/bot.log
   75  nano trading_2_live4_claude2_v4.py 
   76  sudo systemctl stop tradingbot.service
   77  sudo systemctl start tradingbot.service
   78  tail -f /home/ubuntu/bot.log
   79  sudo systemctl stop tradingbot.service
   80  nano trading_2_live4_claude2_v4.py 
   81  sudo systemctl start tradingbot.service
   82  tail -f /home/ubuntu/bot.log
   83  pip uninstall ccxt
   84  pip install ccxt==4.5.85
   85  sudo systemctl stop tradingbot.service
   86  sudo systemctl start tradingbot.service
   87  tail -f /home/ubuntu/bot.log
   88  history 
   89  tail -f /home/ubuntu/bot.log
   90  history >history.txt
