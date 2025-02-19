'''
Copyright (C) 2017-2019  Bryant Moscon - bmoscon@gmail.com

Please see the LICENSE file for the terms and conditions
associated with this software.
'''
import uuid
from typing import Tuple

from cryptofeed.callback import Callback
from cryptofeed.standards import pair_std_to_exchange, feed_to_exchange, load_exchange_pair_mapping
from cryptofeed.defines import TRADES, TICKER, L2_BOOK, L3_BOOK, VOLUME, FUNDING, BOOK_DELTA, INSTRUMENT, BID, ASK
from cryptofeed.util.book import book_delta, depth


class Feed:
    id = 'NotImplemented'

    def __init__(self, address, pairs=None, channels=None, config=None, callbacks=None, max_depth=None, book_interval=1000):
        self.hash = str(uuid.uuid4())
        self.uuid = self.id + self.hash
        self.config = {}
        self.address = address
        self.book_update_interval = book_interval
        self.updates = 0
        self.do_deltas = False
        self.pairs = []
        self.channels = []
        self.max_depth = max_depth
        load_exchange_pair_mapping(self.id)

        if config is not None and (pairs is not None or channels is not None):
            raise ValueError("Use config, or channels and pairs, not both")

        if config is not None:
            for channel in config:
                chan = feed_to_exchange(self.id, channel)
                self.config[chan] = {pair_std_to_exchange(pair, self.id) for pair in config[channel]}

        if pairs:
            self.pairs = [pair_std_to_exchange(pair, self.id) for pair in pairs]
        if channels:
            self.channels = [feed_to_exchange(self.id, chan) for chan in channels]

        self.l3_book = {}
        self.l2_book = {}
        self.callbacks = {TRADES: Callback(None),
                          TICKER: Callback(None),
                          L2_BOOK: Callback(None),
                          L3_BOOK: Callback(None),
                          VOLUME: Callback(None),
                          FUNDING: Callback(None),
                          INSTRUMENT: Callback(None)}

        if callbacks:
            for cb_type, cb_func in callbacks.items():
                self.callbacks[cb_type] = cb_func
                if cb_type == BOOK_DELTA:
                    self.do_deltas = True

        for key, callback in self.callbacks.items():
            if not isinstance(callback, list):
                self.callbacks[key] = [callback]

    async def book_callback(self, book, book_type, pair, forced, delta, timestamp):
        if self.do_deltas and self.updates < self.book_update_interval and not forced:
            if self.max_depth:
                delta, book = await self.apply_depth(book, True)
                if not (delta[BID] or delta[ASK]):
                    return
            self.updates += 1
            await self.callback(BOOK_DELTA, feed=self.id, pair=pair, delta=delta, timestamp=timestamp)

        if self.updates >= self.book_update_interval or forced or not self.do_deltas:
            if self.max_depth:
                _, book= await self.apply_depth(book, False)
            self.updates = 0
            if book_type == L2_BOOK:
                await self.callback(L2_BOOK, feed=self.id, pair=pair, book=book, timestamp=timestamp)
            else:
                await self.callback(L3_BOOK, feed=self.id, pair=pair, book=book, timestamp=timestamp)

    async def callback(self, data_type, **kwargs):
        for cb in self.callbacks[data_type]:
            await cb(**kwargs)

    async def apply_depth(self, book: dict, do_delta: bool) -> Tuple[list, dict]:
        ret = depth(book, self.max_depth)
        if not do_delta:
            self.previous_book = ret
            return {BID: [], ASK: []}, ret

        delta = []
        delta = book_delta(self.previous_book, ret)
        self.previous_book = ret
        return delta, ret

    async def message_handler(self, msg: str, timestamp: float):
        raise NotImplementedError


class RestFeed(Feed):
    async def message_handler(self):
        raise NotImplementedError
