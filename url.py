#!/usr/bin/env Python
# coding=utf-8
# the url structure of website

from handlers.index import IndexHandler  # 假设已经有了
from handlers.dllistctl import DownloadQueueHandler, GetFolderHandler, RemoveHandler, RetryHandler

url = [
    (r'/', IndexHandler),
    (r'/downloadQueue', DownloadQueueHandler),
    (r'/getFolder', GetFolderHandler),
    (r'/remove', RemoveHandler),
    (r'/retry', RetryHandler)
]
