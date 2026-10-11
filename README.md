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
<!-- updated: 2025-12-07 -->

## Description
A lightweight bot that connects Telegram, Interactive Brokers (IBKR), and TradingView. Users configure ticker‑specific order size and minimum profit via Telegram commands, and the bot executes buy/sell orders based on TradingView webhook signals.

## Features
- Telegram interface for per‑ticker configuration (`/set` command).
- Handles TradingView webhook POST requests to trigger BUY or SELL actions.
- Checks available IBKR funds before placing orders.
- Places Good‑Till‑Cancelled (GTC) limit orders.
- Supports dollar‑cost averaging (DCA) by repeatedly buying until funds are exhausted.

## Requirements
The project depends on the Python packages listed in **req.txt**:
```
flask
ib_insync
python-dotenv
python-telegram-bot>=20.0
```

## Installation
```bash
pip install -r req.txt
```

## Configuration
Create a **.env** file (or set environment variables) with the following keys:
```
IB_HOST=127.0.0.1        # IBKR gateway host
IB_PORT=7497             # IBKR gateway port
IB_CLIENT_ID=1           # IBKR client identifier
```
Values shown are defaults used by the code; replace them as needed.

## Usage
Run the bot with:
```bash
python ibkr_tv_bot.py
```
The script starts a Flask server listening for `/webhook` POST requests and a Telegram bot for configuration commands.

## Project Structure
- **.gitignore** – ignores environment files.
- **LICENSE** – MIT license.
- **README.md** – this documentation.
- **config.json** – static configuration (not used for env vars).
- **ibkr_tv_bot.py** – main application code.
- **req.txt** – Python dependencies.

## License
This project is licensed under the MIT License (see LICENSE file).
