
"""
IBKR Trading Bot with Telegram configuration and TradingView webhook integration.

Workflows:
1. Configure tickers via Telegram (/set): ticker symbol, order size (USD), min profit %
2. Receive TradingView webhook POSTs for Buy/Sell actions
3. On Buy: check available funds, place GTC limit buy order
4. On Sell: check unrealized P/L, place GTC limit sell if profit threshold met
5. DCA enabled: bot buys repeatedly until funds depleted

Requirements:
- python-telegram-bot v20+
- flask
- ib_insync
- python-dotenv

"""