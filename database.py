# database.py
import sqlite3
from datetime import datetime
from contextlib import contextmanager
import config

DB_PATH = 'trades.db'


@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_db() as conn:
        cursor = conn.cursor()

        # Активні угоди
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS active_trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                token TEXT NOT NULL,
                symbol TEXT NOT NULL,
                buy_price REAL NOT NULL,
                buy_time TIMESTAMP NOT NULL,
                amount REAL NOT NULL,
                quantity REAL NOT NULL,
                takeprofit REAL NOT NULL,
                stoploss REAL NOT NULL,
                highest_price REAL,
                status TEXT DEFAULT 'active'
            )
        ''')

        # Закриті угоди
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS closed_trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                token TEXT NOT NULL,
                symbol TEXT NOT NULL,
                buy_price REAL NOT NULL,
                buy_time TIMESTAMP NOT NULL,
                sell_price REAL NOT NULL,
                sell_time TIMESTAMP NOT NULL,
                quantity REAL NOT NULL,
                profit_percent REAL NOT NULL,
                profit_usdt REAL NOT NULL,
                reason TEXT,
                status TEXT
            )
        ''')

        # Скановані лістинги (щоб не дублювати)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS scanned_listings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT UNIQUE NOT NULL,
                detected_time TIMESTAMP NOT NULL
            )
        ''')

        # Виявлені лістинги
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS detected_listings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                price REAL NOT NULL,
                volume REAL NOT NULL,
                spread REAL,
                detected_time TIMESTAMP NOT NULL,
                status TEXT DEFAULT 'pending',
                reject_reason TEXT,
                viewed INTEGER DEFAULT 0
            )
        ''')

        # Логи
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS system_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                level TEXT NOT NULL,
                message TEXT NOT NULL,
                timestamp TIMESTAMP NOT NULL
            )
        ''')

        # Баланс paper trading
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS paper_balance (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                balance REAL NOT NULL,
                timestamp TIMESTAMP NOT NULL
            )
        ''')

        # Додаємо початковий баланс, якщо порожньо
        cursor.execute('SELECT COUNT(*) FROM paper_balance')
        if cursor.fetchone()[0] == 0:
            cursor.execute('''
                INSERT INTO paper_balance (balance, timestamp)
                VALUES (?, ?)
            ''', (config.PAPER_BALANCE, datetime.now()))


def add_log(level, message):
    """Додає запис в логи"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO system_logs (level, message, timestamp)
            VALUES (?, ?, ?)
        ''', (level, message, datetime.now()))


def get_logs(limit=100):
    """Отримує останні логи"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT * FROM system_logs 
            ORDER BY timestamp DESC 
            LIMIT ?
        ''', (limit,))
        return cursor.fetchall()


def save_active_trade(token, symbol, buy_price, amount, quantity):
    """Зберігає активну угоду"""
    with get_db() as conn:
        cursor = conn.cursor()
        takeprofit = buy_price * (1 + config.TAKEPROFIT_PERCENT / 100)
        stoploss = buy_price * (1 - config.STOPLOSS_PERCENT / 100)
        cursor.execute('''
            INSERT INTO active_trades 
            (token, symbol, buy_price, buy_time, amount, quantity, takeprofit, stoploss, highest_price)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (token, symbol, buy_price, datetime.now(), amount, quantity, takeprofit, stoploss, buy_price))
    add_log('INFO', f"Відкрито угоду: {symbol} на суму ${amount:.2f}")


def get_active_trades():
    """Отримує всі активні угоди"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM active_trades WHERE status = "active"')
        return cursor.fetchall()


def close_trade(trade_id, sell_price, reason):
    """Закриває угоду і переносить в історію"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM active_trades WHERE id = ?', (trade_id,))
        trade = cursor.fetchone()

        if trade:
            profit_percent = ((sell_price - trade['buy_price']) / trade['buy_price']) * 100
            profit_usdt = (trade['quantity'] * sell_price * (1 - config.COMMISSION)) - (
                    trade['quantity'] * trade['buy_price'] * (1 + config.COMMISSION))

            cursor.execute('''
                INSERT INTO closed_trades 
                (token, symbol, buy_price, buy_time, sell_price, sell_time, quantity, profit_percent, profit_usdt, reason, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (trade['token'], trade['symbol'], trade['buy_price'], trade['buy_time'],
                  sell_price, datetime.now(), trade['quantity'], profit_percent, profit_usdt, reason, 'closed'))

            cursor.execute('UPDATE active_trades SET status = "closed" WHERE id = ?', (trade_id,))

            cursor.execute('SELECT balance FROM paper_balance ORDER BY timestamp DESC LIMIT 1')
            current_balance = cursor.fetchone()[0]
            new_balance = current_balance + profit_usdt
            cursor.execute('INSERT INTO paper_balance (balance, timestamp) VALUES (?, ?)',
                           (new_balance, datetime.now()))

            add_log('INFO' if profit_usdt > 0 else 'WARNING',
                    f"Закрито угоду {trade['symbol']}: {reason}, прибуток: ${profit_usdt:.2f} ({profit_percent:.2f}%)")

            return profit_usdt, profit_percent
    return 0, 0


def is_listing_scanned(symbol):
    """Перевіряє, чи вже сканували цей лістинг"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT 1 FROM scanned_listings WHERE symbol = ?', (symbol,))
        return cursor.fetchone() is not None


def mark_listing_scanned(symbol):
    """Позначає лістинг як просканований"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('INSERT OR IGNORE INTO scanned_listings (symbol, detected_time) VALUES (?, ?)',
                       (symbol, datetime.now()))


def save_detected_listing(listing, status='pending', reject_reason=None):
    """Зберігає виявлений лістинг в БД"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO detected_listings (symbol, price, volume, spread, detected_time, status, reject_reason)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (listing['symbol'], listing['price'], listing['volume'],
              listing.get('spread', 0), datetime.now(), status, reject_reason))
    add_log('INFO', f"Виявлено новий лістинг: {listing['symbol']} за ціною ${listing['price']:.6f}")


def get_detected_listings(limit=50):
    """Отримує всі виявлені лістинги"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT * FROM detected_listings 
            ORDER BY detected_time DESC 
            LIMIT ?
        ''', (limit,))
        return cursor.fetchall()


def update_detected_listing_status(listing_id, status, reject_reason=None):
    """Оновлює статус виявленого лістингу"""
    with get_db() as conn:
        cursor = conn.cursor()
        if reject_reason:
            cursor.execute('''
                UPDATE detected_listings 
                SET status = ?, reject_reason = ? 
                WHERE id = ?
            ''', (status, reject_reason, listing_id))
        else:
            cursor.execute('''
                UPDATE detected_listings 
                SET status = ? 
                WHERE id = ?
            ''', (status, listing_id))


def get_paper_balance():
    """Отримує поточний баланс paper trading"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT balance FROM paper_balance ORDER BY timestamp DESC LIMIT 1')
        result = cursor.fetchone()
        return result['balance'] if result else config.PAPER_BALANCE


def get_trade_history(limit=50):
    """Отримує історію закритих угод"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT * FROM closed_trades 
            ORDER BY sell_time DESC 
            LIMIT ?
        ''', (limit,))
        return cursor.fetchall()


def get_capital_info():
    """Отримує інформацію про капітал: вільний, заблокований, загальний"""
    with get_db() as conn:
        cursor = conn.cursor()

        cursor.execute('SELECT balance FROM paper_balance ORDER BY timestamp DESC LIMIT 1')
        current_balance = cursor.fetchone()
        free_balance = current_balance['balance'] if current_balance else 0

        cursor.execute('SELECT SUM(amount) as blocked FROM active_trades WHERE status = "active"')
        blocked_result = cursor.fetchone()
        blocked = blocked_result['blocked'] if blocked_result['blocked'] else 0

        total = free_balance + blocked

        return {
            'free': free_balance,
            'blocked': blocked,
            'total': total,
            'free_percent': (free_balance / total * 100) if total > 0 else 0,
            'blocked_percent': (blocked / total * 100) if total > 0 else 0
        }


def get_trading_stats():
    """Отримує розширену статистику торгівлі"""
    with get_db() as conn:
        cursor = conn.cursor()

        cursor.execute('''
            SELECT 
                COUNT(*) as total_trades,
                SUM(CASE WHEN profit_usdt > 0 THEN 1 ELSE 0 END) as winning_trades,
                SUM(CASE WHEN profit_usdt <= 0 THEN 1 ELSE 0 END) as losing_trades,
                AVG(profit_percent) as avg_profit_percent,
                MAX(profit_percent) as best_trade,
                MIN(profit_percent) as worst_trade,
                SUM(profit_usdt) as total_profit
            FROM closed_trades
        ''')
        stats = cursor.fetchone()

        cursor.execute('''
            SELECT symbol, profit_percent, profit_usdt, sell_time, reason
            FROM closed_trades 
            ORDER BY sell_time DESC 
            LIMIT 5
        ''')
        recent_trades = cursor.fetchall()

        return {
            'total_trades': stats['total_trades'] or 0,
            'winning_trades': stats['winning_trades'] or 0,
            'losing_trades': stats['losing_trades'] or 0,
            'win_rate': (stats['winning_trades'] / stats['total_trades'] * 100) if stats['total_trades'] > 0 else 0,
            'avg_profit_percent': stats['avg_profit_percent'] or 0,
            'best_trade': stats['best_trade'] or 0,
            'worst_trade': stats['worst_trade'] or 0,
            'total_profit': stats['total_profit'] or 0,
            'recent_trades': [dict(t) for t in recent_trades]
        }