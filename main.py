import math
import re
import requests
import auths
import threading
import time
import discord
from fuzzywuzzy import fuzz

VERBATIM = False


def calc_risk(shares: list, prices: list, bin: int) -> float:
    """
    Calculate the profit of a spread of purchase amounts and no prices
    :param shares: list of number of shares to buy for each contract
    :param prices: list of price of each contract
    :return: dollar profit amount
    """
    share_value = [shares[i] * prices[i] for i in range(len(prices))]
    if_no = [round((shares[i] - share_value[i]) - 0.1 * (shares[i] - share_value[i]), 3) for i in
             range(len(prices))]
    if_yes = [-(share_value[i]) for i in range(len(prices))]
    risk = [round(if_yes[i] + sum(if_no[0:i]) + sum(if_no[i + 1:]), 3) for i in range(len(prices))]
    return 1 - risk[bin]


def calc_profit(shares: list, prices: list) -> float:
    """
    Calculate the profit of a spread of purchase amounts and no prices
    :param shares: list of number of shares to buy for each contract
    :param prices: list of price of each contract
    :return: dollar profit amount
    """
    share_value = [shares[i] * prices[i] for i in range(len(prices))]
    if_no = [round((shares[i] - share_value[i]) - 0.1 * (shares[i] - share_value[i]), 3) for i in
             range(len(prices))]
    if_yes = [-(share_value[i]) for i in range(len(prices))]
    risk = [round(if_yes[i] + sum(if_no[0:i]) + sum(if_no[i + 1:]), 3) for i in range(len(prices))]
    profit = min(risk)
    return profit


def sum_prices(prices: list) -> float:
    """
    Sum the potential profit of each contract
    :param prices: list of price of each contract
    :return: sum of potential profit
    """
    total = sum([1 - price for price in prices if price is not None])
    return round(total, 2)


def convert(lst: list) -> str:
    """
    convert list to string
    :param lst: list
    :return: string
    """
    string = ""
    for n in lst:
        string += str(n)
    return string


def optShares(cost: float) -> float:
    return 1.0 / (1.0 - (1.0 - float(cost)) * 0.1)


def best_amount(prices: list, max_shares: int, test) -> list:
    costliest = max(prices)
    share_multiplier = (max_shares / costliest) / optShares(costliest)
    best_holds = []
    for i in prices:
        if not test:
            best_holds.append([i, math.floor(share_multiplier * optShares(i))])
        else:
            best_holds.append([i, 850])
    return best_holds


def optimize_spread(prices: list, max_shares: int, minimum: bool = True, test=False) -> tuple:
    maximum = max_shares
    max_profit = 0
    max_spread = []
    while maximum > 0:
        spread = []
        for i in best_amount(prices, maximum, test):
            if i[0] != 1:
                spread.append(i[1])
            else:
                spread.append(0)
        maximum -= 1
        if not minimum:
            max_spread = spread
            max_profit = calc_profit(spread, prices)
            break
        elif max(spread) <= max_shares:
            if calc_profit(spread, prices) > max_profit:
                max_spread = spread
                max_profit = calc_profit(spread, prices)
    return max_spread, max_profit


class Api:
    def __init__(self):
        login_info = {'email': auths.username, 'password': auths.password, 'grant_type': 'password',
                      'rememberMe': 'false'}
        r = requests.post('https://www.predictit.org/api/Account/token', login_info)
        self.token = r.json()['access_token']
        self.data = requests.get('https://www.predictit.org/api/marketdata/all').json()
        self.watch = []
        self.messages = []
        run_thread = threading.Thread(target=self.run, daemon=True)
        run_thread.start()

    def log_alert(self, user, market, bin, value):
        self.watch.append({'user': user, 'market': market, 'bin': bin, 'value': value})
        print(self.watch)

    def get_messages(self):
        return self.messages

    def check_alerts(self):
        for i, wat in enumerate(self.watch):
            for market in self.data['markets']:
                market_id = str(market['id'])
                if market_id == str(wat['market']):
                    contract = market['contracts'][wat['bin']]
                    if wat['value'] < 0:
                        if contract['bestBuyYesCost'] * 100 <= abs(wat['value']):
                            msg = wat['user'] + " Market " + market_id + " just dropped below " + str(
                                -wat['value']) + '\n'
                            msg += "Currently at " + str(int(contract['bestBuyYesCost'] * 100)) + '¢'
                            self.messages += [msg]
                            self.watch.pop(i)
                    else:
                        if contract['bestBuyYesCost'] * 100 >= wat['value']:
                            msg = wat['user'] + " Market " + market_id + " just went above " + str(wat['value']) + '\n'
                            msg += "Currently at " + str(int(contract['bestBuyYesCost'] * 100)) + '¢'
                            self.messages += [msg]
                            self.watch.pop(i)

    def run(self):
        while True:
            time.sleep(60)
            self.reload()
            self.check_alerts()

    def reload(self):
        response = requests.get('https://www.predictit.org/api/marketdata/all')
        if response.status_code == 503:
            print('server down')
        else:
            self.data = response.json()

    def get_auth(self):
        login_info = {'email': auths.username, 'password': auths.password, 'grant_type': 'password',
                      'rememberMe': 'false'}
        r = requests.post('https://www.predictit.org/api/Account/token', login_info)
        self.token = r.json()['access_token']

    def get_orderbook(self, id):
        return requests.get('https://www.predictit.org/api/Trade/' + str(id) + '/OrderBook',
                            headers={'Authorization': 'Bearer ' + self.token}).json()

    def get_market_name(self, id):
        id = str(id)
        for market in self.data['markets']:
            if str(market['id']) == id:
                return str(market['name'])
        return 'Market Not Found'

    def get_market_url(self, id):
        id = str(id)
        for market in self.data['markets']:
            if str(market['id']) == id:
                return str(market['url'])
        return 'Market Not Found'

    def get_market_id(self, guess):
        guess = re.sub(r'[^\w\s]', '', guess).lower()
        guess_words = guess.split()
        most_matches = 0
        best_diff = 0
        best_diff_id = 0
        for market in self.data['markets']:
            short_name = re.sub(r'[^\w\s]', '', market['shortName']).lower()
            long_name = re.sub(r'[^\w\s]', '', market['name']).lower()
            matches = sum([word in short_name or word in long_name for word in guess_words])
            if guess == short_name or guess == long_name:
                return market['id']
            diff1 = fuzz.token_sort_ratio(guess, short_name)
            diff2 = fuzz.token_sort_ratio(guess, long_name)
            if matches > most_matches or (matches >= most_matches and (diff1 > best_diff or diff2 > best_diff)):
                best_diff = max(diff1, diff2)
                best_diff_id = market['id']
            if matches > most_matches:
                most_matches = matches
        return best_diff_id

    def get_contract_offers(self, id, top=False):
        book = self.get_orderbook(id)
        offers = {'yes': {}, 'no': {}}
        try:
            yes_orders = book['yesOrders']
            no_orders = book['noOrders']
        except KeyError:
            self.get_auth()
            return self.get_contract_offers(id, top)
        if not top:
            for order in yes_orders:
                offers['yes'][order['pricePerShare']] = order['quantity']
            for order in no_orders:
                offers['no'][order['pricePerShare']] = order['quantity']
        else:
            if no_orders:
                yes = yes_orders[0]
                offers['yes'][yes['pricePerShare']] = yes['quantity']
                no = no_orders[0]
                offers['no'][no['pricePerShare']] = no['quantity']
        return offers

    def get_market_orderbooks(self, id, top=False):
        bins = {}
        id = str(id)
        for market in self.data['markets']:
            if str(market['id']) == id:
                for contract in market['contracts']:
                    id = contract['id']
                    if top and contract['bestBuyNoCost']:
                        offers = self.get_contract_offers(id, top)
                        name = contract['name']
                        bins[name] = {}
                        bins[name]['yes'] = list(offers['yes'].items())
                        bins[name]['no'] = list(offers['no'].items())
        return bins

    def get_all_offers(self, id):
        try:
            market_data = requests.get('https://www.predictit.org/api/Market/' + str(id) + '/Contracts').json()
        except:
            assert True, "market not found"
        bins = {}
        for contract in market_data:
            name = contract['contractName']
            bins[name] = {}
            bins[name]['yes_cost'] = contract['bestYesPrice']
            if contract['bestNoPrice'] is not None:
                bins[name]['no_cost'] = contract['bestNoPrice']
            else:
                bins[name]['no_cost'] = 1
        return bins

    def get_all_short(self, bins):
        short = []
        for name, bin in bins.items():
            short.append(bin['no_cost'])
        return short

    def get_all_long(self, bins):
        long = []
        for name, bin in bins.items():
            long.append(bin['yes_cost'])
        return long

    def sum_market_shorts(self, market):
        bins = self.get_all_offers(market)
        return sum_prices(self.get_all_short(bins))

    def optimize_all(self, max_shares=850, minimum=False, compressed=True):
        title = "There are {} markets with negative risk.\n"
        n = 0
        msg = '```'
        for market in self.data['markets']:
            if len(market['contracts']) > 1:
                short = []
                for contract in market['contracts']:
                    price = contract['bestBuyNoCost']
                    if price is not None:
                        short += [price]
                    else:
                        short += [1]
                potential = sum_prices(short)
                optimal, profit = optimize_spread(short, max_shares, minimum)
                market_id = market['id']
                if profit > 0:
                    n += 1
                    if not compressed:
                        msg += "Market " + str(market_id) + '\n'
                        msg += "   Sum of 1 minus no is " + str(potential) + "\n"
                        msg += "   Potential profit is $" + str(profit) + " with the ideal spread\n"
                    else:
                        msg += "Market " + str(market_id) + ' (' + str(potential) + ' / $' + str(profit) + ')\n'
        msg += '```'
        return title.format(str(n)), msg

    def opt_neg_risk(self, market, max_shares, minimum):
        assert max_shares > 0, 'Max shares must be positive'
        self.reload()
        VERBATIM and print()
        VERBATIM and print('Optimizing negative risk')
        bins = self.get_all_offers(market)
        short = self.get_all_short(bins)
        spread, risk = optimize_spread(short, max_shares, minimum)
        VERBATIM and print('Profit:' + str(risk))
        VERBATIM and print(spread)
        return spread, risk

    def discord_orderbook(self, market_id):
        input = str(market_id)
        try:
            int(market_id)
            name = self.get_market_name(market_id)
        except:
            market_id = self.get_market_id(market_id)
            name = self.get_market_name(market_id)
        if name == 'Market Not Found':
            return 'Market "' + str(input) + '" Not Found'
        title = 'Orderbook for "' + name + '"\n'
        url = self.get_market_url(market_id)
        offers = self.get_market_orderbooks(market_id, top=True)
        max_len = 0
        for name, book in offers.items():
            if len(name) > max_len:
                max_len = len(name)
        msg = ''
        msg += '```'
        msg += ' ' * (max_len + 2) + 'YES  OFFERS  NO  OFFERS\n'
        for name, book in offers.items():
            yes = book['yes']
            no = book['no']
            msg += ' ' * (max_len - len(name)) + str(name)
            longest = max(len(yes), len(no))
            for i in range(longest):
                msg += '  ' + str(int(yes[i][0] * 100)) + (' ' * (3 - len(str(int(yes[i][0] * 100))))) + '  ' + str(
                    yes[i][1]) + ' ' * (6 - len(str(yes[i][1])))
                msg += '  ' + str(int(no[i][0] * 100)) + (' ' * (3 - len(str(int(no[i][0] * 100))))) + '  ' + str(
                    no[i][1]) + '\n'
        msg += '```'
        return title, msg, url

    def get_market_risk(self, market, max_shares=850, minimum=True):
        input = str(market)
        market = input
        try:
            int(market)
            name = self.get_market_name(market)
        except:
            market = self.get_market_id(market)
            name = self.get_market_name(market)
        url = self.get_market_url(market)
        if name == 'Market Not Found':
            return 'Market "' + str(input) + '" Not Found'
        info = ''
        title = 'Market risk for "' + name + '"\n'
        bins = self.get_all_offers(market)
        short = self.get_all_short(bins)
        spread, risk = optimize_spread(short, max_shares, minimum)
        if risk < 0:
            info += 'No negative risk available at ' + str(max_shares) + ' shares'
        else:
            info += 'Negative risk found!!!\n'
            spread = list(filter(lambda x: x != 0, spread))
            info += 'Sum of 1 minus no is ' + str(self.sum_market_shorts(market)) + '\n'
            info += 'Potential profit w/ below spread is ' + str(risk) + '\n'
            info += 'Ideal spread is ' + str(spread) + '\n'
        return title, info, url

    def get_market_bins(self, market_id):
        input = str(market_id)
        try:
            int(market_id)
            name = self.get_market_name(market_id)
        except:
            market_id = self.get_market_id(market_id)
            name = self.get_market_name(market_id)
        if name == 'Market Not Found':
            return 'Market "' + str(input) + '" Not Found'
        info = ''
        title = ''
        title += 'Market bins for "' + name + '"\n'
        for market in self.data['markets']:
            if str(market['id']) == str(market_id):
                url = market['url']
                max_len = 0
                for contract in market['contracts']:
                    if len(contract['name']) > max_len:
                        max_len = len(contract['name'])
                info += '```'
                rest = []
                info += ' ' * (max_len + 2) + 'YES NO\n'
                for contract in market['contracts']:
                    if contract['bestBuyNoCost'] is not None:
                        info += ' ' * (max_len - len(contract['name'])) + str(contract['name']) + '  '
                        info += ' ' * (2 - len(str(int(contract['bestBuyYesCost'] * 100)))) + str(
                            int(contract['bestBuyYesCost'] * 100)) + '  '
                        info += ' ' * (2 - len(str(int(contract['bestBuyNoCost'] * 100)))) + str(
                            int(contract['bestBuyNoCost'] * 100)) + '\n'
                    else:
                        rest.append(str(contract['name']))
                n = 0
                for contract in rest:
                    if n < 2:
                        info += contract + ', '
                    n += 1
                if rest:
                    info = info[:-2] + ' and ' + str(n - 2) + ' more @ 0'

                info += '```'
        return title, info, url

    def value_buy(self, market_id, bin):
        input = str(market_id)
        try:
            int(market_id)
            name = self.get_market_name(market_id)
        except:
            market_id = self.get_market_id(market_id)
            name = self.get_market_name(market_id)
        if name == 'Market Not Found':
            return 'Market "' + str(input) + '" Not Found'
        info = 'Finding value buy for "' + name + '"\n'
        bins = self.get_all_offers(market_id)
        short = self.get_all_short(bins)
        long = self.get_all_long(bins)
        if len(long) <= 1:
            info += "This market only has one bin"
        else:
            if bin == -1:
                bin = long.index(max(long))
            info += "Buying B" + str(bin + 1) + " Yes costs " + str(int(long[bin] * 100)) + '¢\n'
            buys = [1 if i != bin and j != 1 else 0 for i, j in enumerate(short)]
            info += "Buying No on everything else would cost " + str(int(calc_risk(buys, short, bin) * 100)) + '¢'
        return info

    def get_related_market_bins(self, bin_name):
        bin_name = bin_name.lower()
        msg = 'Looking for markets containing "' + bin_name + '" as a bin\n'
        n = 0
        m = 1
        for letter in bin_name:
            if letter == '+':
                m += 1
        bin_name = bin_name.strip('+')
        bin_name_words = bin_name.split()
        for market in self.data['markets']:
            for contract in market['contracts']:
                if all([bin_name in contract['name'].lower() for bin_name in bin_name_words]):
                    if (20 * m) > n >= (20 * (m - 1)):
                        msg += market['shortName'] + ' (' + str(market['id']) + ') ' + str(
                            int(contract['lastTradePrice'] * 100)) + '¢\n'
                    n += 1
        if n == 0:
            msg += "No markets found!"
        elif n >= 15 * m:
            msg += "Only displaying the first twenty markets, to get twenty more, run '. " + bin_name + "+" * m + ' bin'
        return msg

    def get_related_markets(self, name_frag):
        name_frag = name_frag.lower()
        msg = 'Looking for markets containing "' + name_frag + '" in the title\n'
        n = 0
        m = 1
        for letter in name_frag:
            if letter == '+':
                m += 1
        name_frag = name_frag.strip('+')
        name_frag_words = name_frag.split()
        for market in self.data['markets']:
            if all([name_frag in market['name'].lower() or name_frag in market['shortName'].lower() for name_frag in
                    name_frag_words]):
                if (20 * m) > n >= (20 * (m - 1)):
                    msg += market['shortName'] + ' (' + str(market['id']) + ')\n'
                n += 1
        if n == 0:
            msg += "No markets found!"
        elif n >= 15 * m:
            msg += "Only displaying the first twenty markets, to get twenty more, run '- " + name_frag + "+" * m
        return msg

    def get_prices(self, market_id):
        prices = {}
        for market in self.data["markets"]:
            if str(market['id']) == str(market_id):
                for contract in market['contracts']:
                    prices[contract['shortName']] = {'yes': contract['bestBuyYesCost'], 'no': contract['bestBuyNoCost']}
        return prices

    def divide_bins(self, market1, market2):
        self.reload()
        market1_prices = self.get_prices(market1)
        market2_prices = self.get_prices(market2)
        divided_prices = {}
        for name, prices in market1_prices.items():
            try:
                if prices['yes'] >= 0.02:
                    divided_prices[name] = int(prices['yes'] / market2_prices[name]['yes'] * 100)
            except KeyError:
                pass
        print('Getting Difference')
        msg = ""
        for name, div in divided_prices.items():
            msg += name + ": " + str(div) + "%\n"
        return msg
