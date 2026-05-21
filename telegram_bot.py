# telegram_bot.py
import requests
import json
import config


# Простий HTTP клієнт для Telegram замість асинхронного
def send_telegram_message(message):
    """Надсилає повідомлення в Telegram через простий HTTP запит"""
    if not config.TELEGRAM_BOT_TOKEN or not config.TELEGRAM_CHAT_ID:
        print(f"📱 [Telegram - не налаштовано] {message}")
        return

    try:
        url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {
            'chat_id': config.TELEGRAM_CHAT_ID,
            'text': message,
            'parse_mode': 'HTML'
        }
        response = requests.post(url, json=payload, timeout=5)
        if response.status_code == 200:
            print("✅ Telegram повідомлення надіслано")
        else:
            print(f"❌ Telegram помилка: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"❌ Telegram помилка: {e}")


def init_telegram():
    """Перевіряє налаштування Telegram"""
    if config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_CHAT_ID:
        print("✅ Telegram бот налаштовано")
        return True
    else:
        print("ℹ️ Telegram не налаштовано (пропускаємо)")
        return False


def notify_new_listing(listing):
    """Сповіщення про новий лістинг"""
    message = f"""
🚀 НОВИЙ ЛІСТИНГ НА BYBIT 🚀

Токен: {listing['symbol']}
Ціна: ${listing['price']:.8f}
Об'єм 24h: ${listing['volume']:.2f}
Спред: {listing.get('spread', 0):.4f}%

Paper trade угода відкривається...
    """
    send_telegram_message(message)


def notify_trade_opened(listing, amount, quantity, takeprofit, stoploss):
    """Сповіщення про відкриття угоди"""
    message = f"""
🚀 НОВА УГОДА ВІДКРИТА 🚀

Токен: {listing['symbol']}
Ціна входу: ${listing['price']:.8f}
Сума угоди: ${amount:.2f}
Кількість: {quantity:.6f}

🎯 Цілі:
• Тейк-профіт (+30%): ${takeprofit:.8f}
• Стоп-лосс (-10%): ${stoploss:.8f}

Активна угода, відстежуємо ціну...
    """
    send_telegram_message(message)


def notify_trade_closed(trade, profit_usdt, profit_percent):
    """Сповіщення про закриття угоди"""
    from database import get_paper_balance
    emoji = "✅" if profit_usdt > 0 else "❌"
    status = "ПРИБУТОК" if profit_usdt > 0 else "ЗБИТОК"

    message = f"""
{emoji} УГОДУ ЗАКРИТО - {status} {emoji}

Токен: {trade['symbol']}
Ціна купівлі: ${trade['buy_price']:.8f}
Ціна продажу: ${trade['sell_price']:.8f}
Прибуток: {profit_percent:.2f}% (${profit_usdt:.4f})
Причина: {trade['reason']}

💰 Поточний капітал: ${get_paper_balance():.2f}
    """
    send_telegram_message(message)


def notify_error(error_message, details=""):
    """Сповіщення про помилку"""
    message = f"""
⚠️ ПОМИЛКА БОТА ⚠️

{error_message}
{details}

Перевірте логи.
    """
    send_telegram_message(message)


def notify_test():
    """Тестове сповіщення для перевірки Telegram"""
    message = """
🧪 ТЕСТОВЕ СПОВІЩЕННЯ 🧪

Telegram бот працює коректно!
Бот готовий до моніторингу нових лістингів.

📊 Поточні налаштування:
• Баланс: $100 (paper trading)
• Тейк-профіт: +30%
• Стоп-лосс: -10%
• Максимум угод: 2
    """
    send_telegram_message(message)


# Ініціалізація
init_telegram()