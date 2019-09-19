# !/usr/bin/env python
# coding=utf-8

from tornado.web import RequestHandler


# 定义视图处理类
class IndexHandler(RequestHandler):
    def get(self):
        self.render("index.html")
