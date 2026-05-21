# app.py
from flask import Flask, render_template, jsonify
from flask_socketio import SocketIO, emit
import threading
import time
from datetime import datetime

from bybit_scanner import BybitScanner, monitor_new_listings, get_scanner_status
from paper_trader import PaperTrader
from database import (get_active_trades, get_trade_history, get_paper_balance, init_db,
                      get_capital_info, get_trading_stats, save_detected_listing,
                      get_detected_listings, update_detected_listing_status, get_logs, add_log)
from telegram_bot import notify_new_listing, notify_trade_opened, notify_trade_closed, notify_test
import config

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
socketio = SocketIO(app, cors_allowed_origins="*")

# Глобальні змінні
scanner = None
trader = None
monitoring_thread = None


def on_new_listing(listing):
    """Callback при знаходженні нового лістингу"""
    print(f"\n🔔 Виявлено новий лістинг: {listing['symbol']}")

    save_detected_listing(listing, status='pending')

    detected_listings = get_detected_listings(1)
    listing_id = detected_listings[0]['id'] if detected_listings else None

    try:
        notify_new_listing(listing)
    except Exception as e:
        print(f"Telegram помилка: {e}")

    if trader:
        success = trader.execute_buy(listing)
        if success and listing_id:
            update_detected_listing_status(listing_id, 'bought')
            add_log('SUCCESS', f"Куплено {listing['symbol']} за ${listing['price']:.6f}")
        elif listing_id:
            update_detected_listing_status(listing_id, 'rejected', 'Insufficient balance or max trades reached')
            add_log('WARNING', f"Відхилено {listing['symbol']}: недостатньо балансу або забагато угод")

    socketio.emit('new_listing', {
        'symbol': listing['symbol'],
        'price': listing['price'],
        'time': datetime.now().strftime('%H:%M:%S')
    })


def start_bot():
    """Запускає бота в окремому потоці"""
    global scanner, trader, monitoring_thread

    scanner = BybitScanner()
    trader = PaperTrader(scanner)

    monitoring_thread = threading.Thread(
        target=monitor_new_listings,
        args=(on_new_listing,),
        daemon=True
    )
    monitoring_thread.start()

    trader.start()
    add_log('INFO', 'Бот успішно запущено')


@app.route('/')
def index():
    """Головна сторінка"""
    return render_template('index.html')


@app.route('/api/active_trades')
def api_active_trades():
    """API для активних угод"""
    trades = get_active_trades()
    return jsonify([dict(trade) for trade in trades])


@app.route('/api/trade_history')
def api_trade_history():
    """API для історії угод"""
    history = get_trade_history(50)
    return jsonify([dict(trade) for trade in history])


@app.route('/api/detected_listings')
def api_detected_listings():
    """API для виявлених лістингів"""
    listings = get_detected_listings(50)
    return jsonify([dict(listing) for listing in listings])


@app.route('/api/balance')
def api_balance():
    """API для балансу"""
    balance = get_paper_balance()
    return jsonify({'balance': balance})


@app.route('/api/capital_info')
def api_capital_info():
    """API для інформації про капітал"""
    return jsonify(get_capital_info())


@app.route('/api/trading_stats')
def api_trading_stats():
    """API для розширеної статистики"""
    return jsonify(get_trading_stats())


@app.route('/api/scanner_status')
def api_scanner_status():
    """API для статусу сканера"""
    return jsonify(get_scanner_status())


@app.route('/api/logs')
def api_logs():
    """API для отримання логів"""
    logs = get_logs(100)
    return jsonify([dict(log) for log in logs])


@app.route('/api/test_telegram')
def api_test_telegram():
    """Тестовий endpoint для перевірки Telegram"""
    try:
        notify_test()
        add_log('INFO', 'Тестове Telegram сповіщення надіслано')
        return jsonify({'status': 'ok', 'message': 'Тестове сповіщення надіслано'})
    except Exception as e:
        add_log('ERROR', f'Помилка Telegram: {e}')
        return jsonify({'status': 'error', 'message': str(e)})


@app.route('/api/simulate_listing')
def api_simulate_listing():
    """Тестовий endpoint для симуляції нового лістингу"""
    test_listing = {
        'symbol': 'SIMULATEDUSDT',
        'price': 1.0,
        'volume': 10000,
        'spread': 0.1
    }
    add_log('INFO', 'Запущено симуляцію нового лістингу SIMULATEDUSDT')
    thread = threading.Thread(target=on_new_listing, args=(test_listing,))
    thread.start()
    return jsonify({'status': 'ok', 'message': 'Симуляція нового лістингу запущена'})


@app.route('/api/stats')
def api_stats():
    """API для базової статистики"""
    history = get_trade_history(1000)
    total_trades = len(history)
    winning_trades = len([t for t in history if t['profit_usdt'] > 0])
    total_profit = sum([t['profit_usdt'] for t in history])

    return jsonify({
        'total_trades': total_trades,
        'winning_trades': winning_trades,
        'win_rate': (winning_trades / total_trades * 100) if total_trades > 0 else 0,
        'total_profit': total_profit,
        'current_balance': get_paper_balance()
    })


if __name__ == '__main__':
    init_db()
    add_log('INFO', f'Бот запускається з балансом ${config.PAPER_BALANCE}')
    start_bot()
    socketio.run(app, host='0.0.0.0', port=5003, debug=False, allow_unsafe_werkzeug=True)