# paper_trader.py
import time
import threading
from datetime import datetime
from database import save_active_trade, get_active_trades, close_trade, get_paper_balance, get_db, get_capital_info
import config


class PaperTrader:
    def __init__(self, scanner):
        self.scanner = scanner
        self.active_monitoring = {}
        self.running = True
        self.max_concurrent_trades = config.MAX_CONCURRENT_TRADES

    def execute_buy(self, listing):
        """Віртуальна купівля нового токена з детальним логуванням"""
        try:
            print(f"\n{'=' * 60}")
            print(f"📊 АНАЛІЗ УГОДИ: {listing['symbol']}")
            print(f"{'=' * 60}")

            # Перевіряємо скільки активних угод
            active_trades = get_active_trades()
            if len(active_trades) >= self.max_concurrent_trades:
                print(f"❌ Відхилено: Забагато активних угод ({len(active_trades)}/{self.max_concurrent_trades})")
                return False

            symbol = listing['symbol']
            price = listing['price']

            # Отримуємо інформацію про капітал
            capital_info = get_capital_info()
            print(f"💰 Капітал:")
            print(f"   Вільний: ${capital_info['free']:.2f}")
            print(f"   Заблоковано: ${capital_info['blocked']:.2f}")
            print(f"   Загальний: ${capital_info['total']:.2f}")

            # Перевіряємо чи вистачає балансу
            if capital_info['free'] < config.MIN_BALANCE_TO_TRADE:
                print(
                    f"❌ Відхилено: Недостатньо вільного балансу (${capital_info['free']:.2f} < ${config.MIN_BALANCE_TO_TRADE})")
                return False

            # Розраховуємо суму угоди (50% від ВІЛЬНОГО балансу)
            amount = capital_info['free'] * config.TRADE_SIZE_PERCENT
            quantity = amount / price

            print(f"📈 Параметри угоди:")
            print(f"   Токен: {symbol}")
            print(f"   Ціна: ${price:.8f}")
            print(f"   Сума: ${amount:.2f}")
            print(f"   Кількість: {quantity:.6f}")

            # Враховуємо комісію
            commission_cost = quantity * price * config.COMMISSION
            total_cost = (quantity * price) + commission_cost

            print(f"💰 Витрати:")
            print(f"   Сума купівлі: ${quantity * price:.2f}")
            print(f"   Комісія (0.1%): ${commission_cost:.4f}")
            print(f"   Всього витрачено: ${total_cost:.2f}")

            # Розраховуємо цілі
            takeprofit_price = price * (1 + config.TAKEPROFIT_PERCENT / 100)
            stoploss_price = price * (1 - config.STOPLOSS_PERCENT / 100)

            print(f"🎯 Цілі:")
            print(f"   Тейк-профіт (+{config.TAKEPROFIT_PERCENT}%): ${takeprofit_price:.8f}")
            print(f"   Стоп-лосс (-{config.STOPLOSS_PERCENT}%): ${stoploss_price:.8f}")

            # Зберігаємо угоду
            token = symbol.replace('USDT', '')
            save_active_trade(token, symbol, price, amount, quantity)

            # Оновлюємо баланс
            new_balance = capital_info['free'] - total_cost
            with get_db() as conn:
                cursor = conn.cursor()
                cursor.execute('INSERT INTO paper_balance (balance, timestamp) VALUES (?, ?)',
                               (new_balance, datetime.now()))

            print(f"✅ УГОДА ВІДКРИТА!")
            print(f"   Новий вільний баланс: ${new_balance:.2f}")
            print(f"   Заблоковано в угоді: ${amount:.2f}")
            print(f"{'=' * 60}\n")

            return True

        except Exception as e:
            print(f"❌ ПОМИЛКА ВИКОНАННЯ BUY: {e}")
            import traceback
            traceback.print_exc()
            return False

    def monitor_prices(self):
        """Моніторить ціни активних угод"""
        while self.running:
            try:
                active_trades = get_active_trades()

                for trade in active_trades:
                    trade_id = trade['id']
                    symbol = trade['symbol']
                    buy_price = trade['buy_price']
                    takeprofit = trade['takeprofit']
                    stoploss = trade['stoploss']
                    highest_price = trade['highest_price'] or buy_price

                    # Отримуємо поточну ціну
                    if self.scanner:
                        orderbook = self.scanner.get_orderbook(symbol, limit=1)
                        if orderbook and orderbook.get('asks') and len(orderbook['asks']) > 0:
                            current_price = orderbook['asks'][0][0]

                            # Оновлюємо максимальну ціну для трейлінг стопу
                            if current_price > highest_price:
                                highest_price = current_price
                                with get_db() as conn:
                                    cursor = conn.cursor()
                                    cursor.execute('UPDATE active_trades SET highest_price = ? WHERE id = ?',
                                                   (highest_price, trade_id))

                            # Перевіряємо умови продажу
                            profit_percent = ((current_price - buy_price) / buy_price) * 100

                            # Тейк-профіт
                            if config.TAKEPROFIT_PERCENT and profit_percent >= config.TAKEPROFIT_PERCENT:
                                self.execute_sell(trade_id, current_price, f"Take profit +{config.TAKEPROFIT_PERCENT}%")

                            # Стоп-лосс
                            elif profit_percent <= -config.STOPLOSS_PERCENT:
                                self.execute_sell(trade_id, current_price, f"Stop loss -{config.STOPLOSS_PERCENT}%")

                            # Трейлінг стоп (якщо впало на 5% від максимуму)
                            elif hasattr(config,
                                         'TRAILING_STOP') and config.TRAILING_STOP and highest_price > buy_price:
                                trailing_drawdown = (highest_price - current_price) / highest_price * 100
                                if trailing_drawdown >= 5 and profit_percent > 5:
                                    self.execute_sell(trade_id, current_price,
                                                      f"Trailing stop (drawdown {trailing_drawdown:.1f}%)")

                time.sleep(config.PRICE_CHECK_INTERVAL)

            except Exception as e:
                print(f"Помилка моніторингу цін: {e}")
                time.sleep(10)

    def execute_sell(self, trade_id, sell_price, reason):
        """Віртуальний продаж з детальним логуванням"""
        try:
            print(f"\n{'=' * 60}")
            print(f"📊 ЗАКРИТТЯ УГОДИ #{trade_id}")
            print(f"   Причина: {reason}")
            print(f"{'=' * 60}")

            profit_usdt, profit_percent = close_trade(trade_id, sell_price, reason)

            print(f"💰 Результат:")
            print(f"   Ціна продажу: ${sell_price:.8f}")
            print(f"   Прибуток: {profit_percent:.2f}%")
            print(f"   Прибуток в USDT: ${profit_usdt:.4f}")

            # Отримуємо оновлену інформацію про капітал
            capital_info = get_capital_info()
            print(f"   Новий вільний баланс: ${capital_info['free']:.2f}")
            print(f"   Загальний капітал: ${capital_info['total']:.2f}")

            if profit_usdt > 0:
                print(f"✅ УГОДА ПРИБУТКОВА!")
            else:
                print(f"❌ УГОДА ЗБИТКОВА!")

            print(f"{'=' * 60}\n")

            return True

        except Exception as e:
            print(f"❌ ПОМИЛКА ВИКОНАННЯ SELL: {e}")
            import traceback
            traceback.print_exc()
            return False

    def start(self):
        """Запускає paper trading"""
        print(f"\n🎮 Paper Trading режим активовано")
        print(f"   Початковий баланс: ${config.PAPER_BALANCE}")
        print(f"   Комісія: {config.COMMISSION * 100}%")
        print(f"   Тейк-профіт: +{config.TAKEPROFIT_PERCENT}%")
        print(f"   Стоп-лосс: -{config.STOPLOSS_PERCENT}%")
        print(f"   Максимум активних угод: {self.max_concurrent_trades}")
        print(f"   Розмір угоди: {config.TRADE_SIZE_PERCENT * 100}% від вільного балансу")
        if hasattr(config, 'TRAILING_STOP'):
            print(f"   Трейлінг стоп: {'Увімкнено' if config.TRAILING_STOP else 'Вимкнено'}\n")

        # Запускаємо моніторинг цін в окремому потоці
        monitor_thread = threading.Thread(target=self.monitor_prices, daemon=True)
        monitor_thread.start()