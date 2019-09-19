# !/usr/bin/env python
# coding=utf-8

from tornado.web import RequestHandler


# 定义视图处理类
class DlListHandler(RequestHandler):
    def get(self):
        global downloadQueue
        # Manually stringify the error object if there is one,
        # because apparently jsonify can't do it automatically
        for url in downloadQueue.keys():
            if downloadQueue[url]["status"] == "error":
                downloadQueue[url]["error"] = str(downloadQueue[url]["error"])
        return jsonify(dict(downloadQueue))
