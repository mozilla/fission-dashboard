# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from bmemcached import Client
import os
import time
from . import report
from .logger import logger


_CLIENT = Client(
    os.environ.get('MEMCACHEDCLOUD_SERVERS', 'localhost:11211').split(','),
    os.environ.get('MEMCACHEDCLOUD_USERNAME', ''),
    os.environ.get('MEMCACHEDCLOUD_PASSWORD', ''),
)


def get_client():
    return _CLIENT


def update():
    logger.info('Update the data')
    bcache = get_client()
    bugs = report.get_bugs()
    data = report.get_stats(bugs)
    if not bcache.replace('data', data, time=0, compress_level=0):
        bcache.set('data', data, time=0, compress_level=0)


def get_data():
    bcache = get_client()
    while True:
        data = bcache.get('data')
        if data:
            return data

        time.sleep(0.1)


def clear():
    get_client().flush_all()
