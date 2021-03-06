import os
import logging

import numpy as np
import pandas as pd

import matplotlib
from abc import ABCMeta, abstractmethod


class _Order(metaclass=ABCMeta):
    def __init__(self, broker):
        self._broker = broker
        self._is_long = None
        self._entry = None

    @abstractmethod
    def _update(self):
        pass
    
    @abstractmethod
    def cancel(self):
        pass

    @property
    def entry(self):
        return self._entry

    @property
    def is_long(self):
        return self._is_long

class _Broker(metaclass=ABCMeta):
    def __init__(self, trading_env, data, symbol, use_adj_close):
        self._trading_env = trading_env
        self._data = data
        self._symbol = symbol
        self._position = 0

        self._close = self._data.Adj_Close if use_adj_close \
                        else self._data.Close[self._current]

        self._order = _Order

    @abstractmethod
    def reset(self):
        pass

    @abstractmethod
    def buy(self, price=None):
        pass
    
    @abstractmethod
    def sell(self, price=None):
        pass

    @property
    def pos(self):
        return self._position
    
    @pos.setter
    def pos(self, position):
        self._position = position
        return self

    @property
    def _current(self):
        return self._trading_env._broker_current_day

    @property
    def next_close(self):
        return self._close[self._current + 1]

    @property 
    def last_close(self):
        return self._close[self._current]

    @property
    def next_open(self):
        return self._data.Open[self._current + 1]

    @property
    def last_open(self):
        return self._data.Open[self._current]
    
    @property
    def last_volumne(self):
        return self._data.Volume[self._current]

    @property 
    def last_day(self):
        return self._data.Date[self._current]

class _Order_Ratio(_Order):
    def __init__(self, *args, **kwargs):
        super(_Order_Ratio, self).__init__(*args, **kwargs)

    def _update(self, entry, is_long=True):
        self._entry = entry
        self._is_long = is_long

    def cancel(self):
        self._entry = self._is_long = None

class _Broker_Ratio(_Broker):
    def __init__(self, *args, **kwargs):
        super(_Broker_Ratio, self).__init__(*args, **kwargs)
        self._order = _Order_Ratio(self)

    def reset(self):
        self._position = 0
        self._order.cancel()

    def buy(self, price):
        self._order._update(price, is_long=True)
    
    def sell(self, price):
        self._order._update(price, is_long=False)


ENV_NAME_FOR_CLASS = {
    'ratio_trade' : _Broker_Ratio
}
BUY, HOLD, SELL = 0, 1, 2

class Log:
    def __init__(self, length):
        self.length = length

    def reset(self):
        self.datetimes         = []
        self.returns_diff      = []
        self.returns_ratio     = []
        self.returns           = []
        self.entry_cashs       = []
        self.entrys            = []
        self.longs             = []
        self.cashes            = []
    def __repr__(self):
        log_out =   '=======================================================\n' +\
                    'Period              : {}\n'.format(len(self.returns)) +\
                    'Date                : {}\n'.format(self.datetimes[-1]) +\
                    'Equity              : {}\n'.format(self.returns[-1]) +\
                    'Entry price         : {}\n'.format(np.sum(self.entry_cashs[-1])) +\
                    'Cash                : {}\n'.format(self.cashes[-1]) +\
                    'Number of Buyers    : {}\n'.format(np.sum(np.sum([ i == BUY for i in self.longs[-1]]))) +\
                    'Number of Sellers   : {}\n'.format(np.sum(np.sum([ i == SELL for i in self.longs[-1]]))) +\
                    '=======================================================' 
        return log_out

    __str__ = __repr__


class Trading_env():
    def __init__(self, env, data, cash, fee, leverage=1.0, adj_close=None):
        assert 0 < cash, "cash shosuld be >0, is {}".format(cash)
        assert 0 <= fee < .1, "commission should be between 0-10%, is {}".format(fee)
        # assert 0 < margin <= 1, "margin should be between 0 and 1, is {}".format(margin)
        
        self._d = 0
        self._lenght = data.length
        self._symbols = data.symbols
        self._features = data.features
        
        self._cash = cash
        self._fee = fee
        self._leverage = leverage
        
        self._log = Log(self._lenght)
        self._brokers = {}

        # Sometimes this will be changed
        BROKER = ENV_NAME_FOR_CLASS[env]

        if adj_close is None:
            adj_close = [False] * len(self._symbols)
        assert len(self._symbols) == len(adj_close)

        for symbol, _adj_close in zip(data.symbols, adj_close):
            self._brokers[symbol] = BROKER(self, data[symbol], symbol, _adj_close)

        ####  For Reset()  ####
        self.__cash = cash
        self._log.reset()

    def reset(self, init_state=None):
        self._d = 0
        self._cash = self.__cash
        self._log.reset()

        if init_state is None:
            init_state = [0] * len(self._symbols)
        for broker in self._brokers_generater:
            broker.reset()
        self.portfolio_pos(init_state)

    def step(self):
        next_d = self._d + 1
        done = True if next_d == self._lenght - 1 else False
        

        day            = False
        returns_diff   = []
        returns_ratio  = []
        entry_cashs    = []
        entrys         = []
        longs          = []
        cashes         = []

        for broker in self._brokers_generater:
            cur_pos = broker.pos
            ratio = broker.next_close / broker.last_close
            is_long = broker._order.is_long
            entry = broker._order.entry

            entry = entry if entry else 0

            if is_long is None:
                entry_cash = 0
                next_cash = self._cash
                next_pos   = cur_pos * ratio
                _long = HOLD
            elif is_long:
                entry_cash = entry * (1 + self._fee)
                next_cash = self._cash - entry_cash
                next_pos   = (cur_pos + entry) * ratio
                _long = BUY
            else:
                entry_cash = -entry * (1 - self._fee)
                next_cash  = self._cash - entry_cash
                next_pos   = (cur_pos - entry) * ratio
                _long = SELL

            next_pos_diff = next_pos - cur_pos
            next_pos_ratio = (next_cash + next_pos) / (self._cash + cur_pos)


            returns_diff.append(next_pos_diff)
            returns_ratio.append(next_pos_ratio)
            entry_cashs.append(entry_cash)
            entrys.append(entry)
            longs.append(_long)

            if day is False: day = broker.last_day

            broker.pos = next_pos
            broker._order.cancel()

        self._cash = self._cash - np.sum(entry_cashs)
        self._d = self._d + 1

        self._log.datetimes.append(day)
        self._log.returns_diff.append(returns_diff)
        self._log.returns_ratio.append(returns_ratio)
        self._log.returns.append(self.equity)
        self._log.entry_cashs.append(entry_cashs)
        self._log.entrys.append(entrys)
        self._log.longs.append(longs)
        self._log.cashes.append(self._cash)

        return self.get_brokers_close, returns_ratio, done, self._log

    def action(self, portfolio, cash_per=0.0, lt=0.0, st=0.0):
        self.portfolio_pos(portfolio, cash_per=cash_per, lt=lt, st=st)

    def render(self):
        pass

    def get_brokers_close(self):
        return [ broker.last_close for broker in self._brokers_generater ]

    @property
    def equity(self):
        return self._cash + np.sum([broker.pos for broker in self._brokers_generater])

    @property
    def _broker_current_day(self):
        return self._d

    @property
    def _brokers_generater(self):
        for symbol in self._symbols:
            yield self._brokers[symbol]

    def __is_portfolio_format(self, portfolio):
        return isinstance(portfolio, list) and (np.sum([p < .0 for p in portfolio]) == 0)

    def portfolio_pos(self, portfolio, cash_per=0.0, lt=0.0, st=0.0):
        """
            lt : long position threshold
            st : shot position threshold
        """
        assert self.__is_portfolio_format(portfolio) 
        if np.sum(portfolio) == 0: cash_per = 1.0

        ratio_sum = np.sum(portfolio) + cash_per

        portfolio = [self._cash * p / ratio_sum for p in portfolio]
        cash =  self._cash * cash_per / ratio_sum # ????

        brokers_cur_pos = [ broker.pos for broker in self._brokers_generater ]
        
        for broker, broker_cur_pos, order_pos in zip(self._brokers_generater, brokers_cur_pos, portfolio):
            pos = order_pos - broker_cur_pos
            if pos > lt:
                broker.buy(price=pos)
            elif pos < st:
                broker.sell(price=-pos)