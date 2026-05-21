# config.py
import os
from dotenv import load_dotenv

load_dotenv()

# Bybit API
BYBIT_API_KEY = os.getenv('BYBIT_API_KEY', '')
BYBIT_API_SECRET = os.getenv('BYBIT_API_SECRET', '')
BYBIT_TESTNET = True

# Telegram
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID', '')

# Торгові параметри
PAPER_BALANCE = 100.0
COMMISSION = 0.001
TAKEPROFIT_PERCENT = 30
STOPLOSS_PERCENT = 10
TRAILING_STOP = True

# Сканер
SCAN_INTERVAL_SECONDS = 60
PRICE_CHECK_INTERVAL = 10

# Ризик-менеджмент
MAX_CONCURRENT_TRADES = 2
TRADE_SIZE_PERCENT = 0.5
MIN_BALANCE_TO_TRADE = 20