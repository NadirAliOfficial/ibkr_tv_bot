
import os
import logging
import threading
import json
from dotenv import load_dotenv
from flask import Flask, request, jsonify
from ib_insync import IB, LimitOrder, Stock
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    ConversationHandler,
    filters,
)

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Interactive Brokers connection
IB_HOST = os.getenv('IB_HOST', '127.0.0.1')
IB_PORT = int(os.getenv('IB_PORT', 7497))
IB_CLIENT_ID = int(os.getenv('IB_CLIENT_ID', 1))
ib = IB()
ib.connect(IB_HOST, IB_PORT, IB_CLIENT_ID)

# In-memory storage for ticker configurations
# Format: { 'AAPL': { 'order_size': 1000.0, 'min_profit': 2.5 }, ... }
configs = {}

# Telegram conversation states
TICKER, ORDER_SIZE, PROFIT_PCT = range(3)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /start command handler: Welcomes user and shows basic instructions.
    """
    text = (
        "Welcome to the IBKR Trading Bot!\n"
        "Use /set to configure a ticker for automated trading.\n"
        "Use /cancel to abort configuration at any time."
    )
    await update.message.reply_text(text)

async def set_ticker(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Entry point for configuration: asks for ticker symbol.
    """
    await update.message.reply_text("Please enter the ticker symbol (e.g., AAPL):")
    return TICKER

async def ticker_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Stores ticker and asks for order size.
    """
    ticker = update.message.text.strip().upper()
    context.user_data['ticker'] = ticker
    await update.message.reply_text(f"Ticker set to {ticker}.\nEnter order size in USD (e.g., 1000):")
    return ORDER_SIZE

async def order_size_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Stores order size and asks for minimum profit percentage.
    """
    try:
        size = float(update.message.text.strip())
    except ValueError:
        await update.message.reply_text("Invalid number. Please enter a numeric order size in USD:")
        return ORDER_SIZE
    context.user_data['order_size'] = size
    await update.message.reply_text(
        f"Order size set to ${size}.\nNow enter minimum profit percentage (e.g., 2.5):"
    )
    return PROFIT_PCT

async def profit_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Stores profit threshold, saves configuration, and ends conversation.
    """
    try:
        percent = float(update.message.text.strip())
    except ValueError:
        await update.message.reply_text("Invalid percentage. Please enter a numeric profit percentage:")
        return PROFIT_PCT

    ticker = context.user_data['ticker']
    size = context.user_data['order_size']
    configs[ticker] = {
        'order_size': size,
        'min_profit': percent
    }

    await update.message.reply_text(
        f"Configuration saved for {ticker}:\n"
        f" • Order size: ${size}\n"
        f" • Min profit: {percent}%\n"
        "Bot is now ready to handle webhooks for this ticker."
    )
    logger.info(f"Saved config for {ticker}: {configs[ticker]}")
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Cancels the current conversation.
    """
    await update.message.reply_text("Configuration canceled.")
    return ConversationHandler.END

# Flask app for webhook handling
app = Flask(__name__)

@app.route('/webhook', methods=['POST'])
def webhook() -> str:
    """
    Receives TradingView webhooks with JSON payload:
    { "ticker": "AAPL", "action": "BUY" }
    """
    data = request.get_json(force=True)
    ticker = data.get('ticker', '').upper()
    action = data.get('action', '').upper()
    logger.info(f"Webhook received: action={action}, ticker={ticker}")

    if action == 'BUY':
        handle_buy(ticker)
    elif action == 'SELL':
        handle_sell(ticker)
    else:
        logger.warning(f"Unknown action '{action}' for ticker {ticker}")

    return jsonify({'status': 'processed'})


def handle_buy(ticker: str) -> None:
    """
    Process a BUY signal: check funds, calculate qty, place limit order.
    """
    cfg = configs.get(ticker)
    if not cfg:
        logger.warning(f"No configuration found for ticker {ticker}")
        return

    # Fetch available USD funds
    account_values = ib.accountValues()
    available = next(
        (float(v.value) for v in account_values if v.tag == 'AvailableFunds' and v.currency == 'USD'),
        0.0
    )
    logger.info(f"Available funds: ${available:.2f}")

    if available < cfg['order_size']:
        logger.info(
            f"Insufficient funds for {ticker}: need ${cfg['order_size']}, have ${available:.2f}"
        )
        return

    # Prepare contract and market data
    contract = Stock(ticker, 'SMART', 'USD')
    ib.qualifyContracts(contract)
    ticker_data = ib.reqMktData(contract, '', False, False)
    ib.sleep(1)  # wait for data update

    # Choose price: last or mid-price
    price = ticker_data.last if ticker_data.last > 0 else (ticker_data.ask + ticker_data.bid) / 2
    qty = int(cfg['order_size'] / price)
    if qty <= 0:
        logger.warning(f"Calculated quantity is zero for {ticker} at price {price}")
        return

    # Place a Good-Til-Canceled limit order
    order = LimitOrder('BUY', qty, price)
    trade = ib.placeOrder(contract, order)
    logger.info(f"Placed BUY order for {ticker}: qty={qty}, price={price}")


def handle_sell(ticker: str) -> None:
    """
    Process a SELL signal: check unrealized P/L, place limit sell if threshold met.
    """
    cfg = configs.get(ticker)
    if not cfg:
        logger.warning(f"No configuration found for ticker {ticker}")
        return

    # Find open position
    positions = ib.positions()
    position = next(
        (p for p in positions if p.contract.symbol.upper() == ticker and p.position > 0),
        None
    )
    if not position:
        logger.info(f"No open position for {ticker} to sell.")
        return

    # Calculate unrealized P/L percentage
    market_price = position.marketPrice
    avg_cost = position.averageCost
    pnl_value = (market_price - avg_cost) * position.position
    invested = avg_cost * position.position
    pnl_pct = (pnl_value / invested) * 100
    logger.info(f"{ticker} unrealized P/L: {pnl_pct:.2f}%")

    if pnl_pct < cfg['min_profit']:
        logger.info(
            f"Profit {pnl_pct:.2f}% below threshold {cfg['min_profit']}%. No sell executed."
        )
        return

    # Place a Good-Til-Canceled limit sell order
    contract = Stock(ticker, 'SMART', 'USD')
    ib.qualifyContracts(contract)
    order = LimitOrder('SELL', position.position, market_price)
    trade = ib.placeOrder(contract, order)
    logger.info(
        f"Placed SELL order for {ticker}: qty={position.position}, price={market_price}"
    )


def run_flask() -> None:
    """
    Starts the Flask webhook server.
    """
    port = int(os.getenv('WEBHOOK_PORT', 5000))
    app.run(host='0.0.0.0', port=port)


if __name__ == '__main__':
    # Start webhook server in a background thread
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()

    # Start Telegram bot for configuration
    TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
    application = (
        ApplicationBuilder()
        .token(TELEGRAM_TOKEN)
        .build()
    )

    # Conversation handler for /set command
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('set', set_ticker)],
        states={
            TICKER: [MessageHandler(filters.TEXT & ~filters.COMMAND, ticker_received)],
            ORDER_SIZE: [MessageHandler(filters.TEXT & ~filters.COMMAND, order_size_received)],
            PROFIT_PCT: [MessageHandler(filters.TEXT & ~filters.COMMAND, profit_received)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )

    application.add_handler(CommandHandler('start', start))
    application.add_handler(conv_handler)

    logger.info("Telegram bot started. Waiting for commands...")
    application.run_polling()
