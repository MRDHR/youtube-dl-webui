#!/usr/bin/env Python
# coding=utf-8
# the url structure of website

from handlers.index import IndexHandler
from handlers.dllistctl import DownloadQueueHandler, GetFolderHandler, RemoveHandler, RetryHandler, \
    AddToDownloadQueueHandler, ClearCompleteHandler

url = [
    (r'/', IndexHandler),
    (r'/downloadQueue', DownloadQueueHandler),
    (r'/getFolder', GetFolderHandler),
    (r'/remove', RemoveHandler),
    (r'/retry', RetryHandler),
    (r'/addToQueue', AddToDownloadQueueHandler),
    (r'/removeFinished', ClearCompleteHandler)
]
