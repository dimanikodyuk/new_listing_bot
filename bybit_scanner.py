# bybit_scanner.py
import requests
import time
from datetime import datetime
from database import is_listing_scanned, mark_listing_scanned, add_log

# Глобальний статус сканера
scanner_status = {
    'last_scan': None,
    'total_pairs': 0,
    'new_found': 0,
    'error': None,
    'is_running': True,
    'scan_count': 0
}


class BybitScanner:
    def __init__(self):
        self.base_url = "https://api.bybit.com"
        self.known_symbols = set()
        self.load_all_symbols()

    def load_all_symbols(self):
        """Завантажує всі поточні пари"""
        global scanner_status
        try:
            response = requests.get(f"{self.base_url}/v5/market/tickers?category=spot", timeout=10)
            data = response.json()
            if data['retCode'] == 0:
                for item in data['result']['list']:
                    symbol = item['symbol']
                    if symbol.endswith('USDT'):
                        self.known_symbols.add(symbol)
            scanner_status['total_pairs'] = len(self.known_symbols)
            scanner_status['last_scan'] = datetime.now().isoformat()
            scanner_status['error'] = None
            add_log('INFO', f"Завантажено {len(self.known_symbols)} пар з Bybit")
            print(f"📊 Завантажено {len(self.known_symbols)} існуючих пар")
        except Exception as e:
            scanner_status['error'] = str(e)
            add_log('ERROR', f"Помилка завантаження пар: {e}")
            print(f"Помилка завантаження пар: {e}")

    def get_new_listings(self):
        """Отримує нові спотові пари"""
        global scanner_status
        try:
            response = requests.get(f"{self.base_url}/v5/market/tickers?category=spot", timeout=10)
            data = response.json()

            if data['retCode'] != 0:
                scanner_status['error'] = f"API error: {data}"
                return []

            current_symbols = set()
            new_listings = []

            for item in data['result']['list']:
                symbol = item['symbol']
                if symbol.endswith('USDT') and not any(x in symbol for x in ['USDC', 'BUSD', 'DAI']):
                    current_symbols.add(symbol)

                    if symbol not in self.known_symbols and not is_listing_scanned(symbol):
                        volume_24h = float(item['volume24h'])
                        price = float(item['lastPrice'])

                        if volume_24h < 500000 and price > 0.0001 and symbol not in ['USDTUSDT', 'USDUSDT']:
                            new_listings.append({
                                'symbol': symbol,
                                'price': price,
                                'volume': volume_24h,
                                'change': float(item['price24hPcnt']) * 100 if item['price24hPcnt'] else 0
                            })
                            mark_listing_scanned(symbol)

            self.known_symbols.update(current_symbols)

            scanner_status['last_scan'] = datetime.now().isoformat()
            scanner_status['total_pairs'] = len(self.known_symbols)
            scanner_status['new_found'] = len(new_listings)
            scanner_status['error'] = None
            scanner_status['is_running'] = True

            return new_listings

        except requests.exceptions.Timeout:
            scanner_status['error'] = "Timeout - API не відповідає"
            add_log('ERROR', "Timeout API Bybit")
            return []
        except Exception as e:
            scanner_status['error'] = str(e)
            add_log('ERROR', f"Помилка сканування: {e}")
            return []

    def get_orderbook(self, symbol, limit=10):
        """Отримує склянку заявок"""
        try:
            response = requests.get(
                f"{self.base_url}/v5/market/orderbook?category=spot&symbol={symbol}&limit={limit}", timeout=5)
            data = response.json()
            if data['retCode'] == 0:
                bids = [[float(x[0]), float(x[1])] for x in data['result']['b']]
                asks = [[float(x[0]), float(x[1])] for x in data['result']['a']]
                return {'bids': bids, 'asks': asks}
        except:
            pass
        return None


def monitor_new_listings(callback):
    """Моніторить нові лістинги"""
    global scanner_status
    scanner = BybitScanner()

    while True:
        try:
            scanner_status['scan_count'] += 1
            scan_num = scanner_status['scan_count']

            print(f"\n🔍 Скан #{scan_num} - {datetime.now().strftime('%H:%M:%S')}")
            add_log('INFO', f"Початок сканування #{scan_num}")

            new_listings = scanner.get_new_listings()

            print(f"   Всього пар: {scanner_status['total_pairs']}")
            print(f"   Знайдено нових: {len(new_listings)}")

            if scanner_status['error']:
                print(f"   ⚠️ Помилка: {scanner_status['error']}")
                add_log('WARNING', f"Помилка сканера: {scanner_status['error']}")

            for listing in new_listings:
                print(f"\n🚀 НОВИЙ ЛІСТИНГ: {listing['symbol']}")
                print(f"   Ціна: ${listing['price']:.8f}")
                print(f"   Об'єм 24h: ${listing['volume']:.2f}")

                orderbook = scanner.get_orderbook(listing['symbol'])
                if orderbook:
                    spread = ((orderbook['asks'][0][0] - orderbook['bids'][0][0]) / orderbook['bids'][0][0]) * 100
                    print(f"   Спред: {spread:.4f}%")
                    listing['spread'] = spread

                callback(listing)

            if len(new_listings) == 0:
                print("   📭 Нових лістингів не знайдено")

            time.sleep(60)

        except Exception as e:
            scanner_status['error'] = str(e)
            add_log('ERROR', f"Помилка моніторингу: {e}")
            print(f"❌ Помилка моніторингу: {e}")
            time.sleep(60)


def get_scanner_status():
    """Повертає статус сканера"""
    global scanner_status
    return scanner_status