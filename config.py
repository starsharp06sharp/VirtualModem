# -*- coding: utf-8 -*-
import logging

log_level = logging.DEBUG

modems = [
    {
        'address': r'\\.\pipe\86Box\Win98',
        'phone': '4805698',
        'bps': 33600,
    },
    {
        'address': ('localhost', 8888),
        'phone': '7891234',
        'bps': 33600,
    },
]
