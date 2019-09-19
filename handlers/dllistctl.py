# !/usr/bin/env python
# coding=utf-8
import copy
import glob
import json
import os

from tornado import escape
from tornado.web import RequestHandler

downloadQueue = {}
dumbSaveFileName = "queue.temp"
jsonSaveFileName = "queue.json"
savedDownloadQueueFile = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), jsonSaveFileName
)
dumbSaveFile = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), dumbSaveFileName
)


# 定义视图处理类
class DownloadQueueHandler(RequestHandler):
    def get(self):
        global downloadQueue
        # Manually stringify the error object if there is one,
        # because apparently jsonify can't do it automatically
        for url in downloadQueue.keys():
            if downloadQueue[url]["status"] == "error":
                downloadQueue[url]["error"] = str(downloadQueue[url]["error"])
        chunk = escape.json_encode(downloadQueue)
        self.set_header("Content-Type", "application/json; charset=UTF-8")
        self.finish(chunk)


jsonStr = ''


# 获取文件夹列表json
def fun(id, path):
    global jsonStr
    for i, fn in enumerate(glob.glob(path + os.sep + '*')):
        if os.path.isdir(fn):
            jsonStr += '{"id":"' + str(id) + '","name":"' + os.path.basename(fn) + '","children":['
            id += 1
            for j, li in enumerate(glob.glob(fn + os.sep + '*')):
                if os.path.isdir(li):
                    jsonStr += '{"id":"' + str(id) + '","name":"' + os.path.basename(li) + '","children":['
                    id += 1
                    fun(id, li)
                    jsonStr += "]}"
                    if j < len(glob.glob(fn + os.sep + '*')) - 1:
                        jsonStr += ","
            jsonStr += "]}"
            if i < len(glob.glob(path + os.sep + '*')) - 1:
                jsonStr += ","


# 清空空数据
def clean_empty(d):
    if not isinstance(d, (dict, list)):
        return d
    if isinstance(d, list):
        return [v for v in (clean_empty(v) for v in d) if v]
    return {k: v for k, v in ((k, clean_empty(v)) for k, v in d.items()) if v}


# 获取文件夹列表
class GetFolderHandler(RequestHandler):
    def post(self):
        global jsonStr
        folderName = self.get_argument('folderName')
        id = 0
        jsonStr = '['
        fun(id, folderName)
        jsonStr += "]"
        jsonStr = jsonStr.replace('},]', '}]')
        jsonStr = jsonStr.replace('\n', '').replace('\n', '')
        jsonStr = jsonStr.replace('\r', '').replace('\r', '')
        jsonStr = jsonStr.replace("\t", "").strip()
        dictMap = json.loads(jsonStr)
        dictMap = clean_empty(dictMap)
        chunk = escape.json_encode(dictMap)
        self.set_header("Content-Type", "application/json; charset=UTF-8")
        self.finish(chunk)


# 移除下载任务
class RemoveHandler(RequestHandler):
    def get(self):
        global downloadQueue
        id = self.get_query_arguments('id')
        for url in downloadQueue.keys():
            if str(downloadQueue[url]["id"]) == id:
                if (
                        downloadQueue[url]["status"] != "downloading"
                        or downloadQueue[url]["status"] != "finished"
                ):
                    del downloadQueue[url]
                    saveDownloadQueue()
                    return "OK"
        return "ERR"


# 重试下载任务
class RetryHandler(RequestHandler):
    def get(self):
        global downloadQueue
        id = self.get_query_arguments('id')
        for url in downloadQueue.keys():
            if downloadQueue[url]["id"] == id:
                if (
                        downloadQueue[url]["status"] != "downloading"
                        or downloadQueue[url]["status"] != "finished"
                ):
                    downloadQueue[url]["status"] = "queued"
                    fireDownloadThread()
                    return "OK"
        return "ERR"


# 清空已完成
class ClearCompleteHandler(RequestHandler):
    def get(self):
        global downloadQueue
        newDownloadQueue = copy.copy(downloadQueue)
        for url in downloadQueue.keys():
            if downloadQueue[url]["status"] == "completed":
                del newDownloadQueue[url]
        downloadQueue = newDownloadQueue
        saveDownloadQueue()
        return "OK"


# 激活下载
def fireDownloadThread():
    doDownload()


# 保存下载列表
def saveDownloadQueue():
    global downloadQueue
    dumbSave()
    try:
        with open(savedDownloadQueueFile, "w") as savefile:
            print("Saving: " + str(os.path.abspath(savedDownloadQueueFile)))
            print(json.dumps(downloadQueue, ensure_ascii=False), file=savefile)
    except TypeError:
        for url in downloadQueue.keys():
            downloadQueue[url]["status"] == str(downloadQueue[url]["status"])


# 保存dumb
def dumbSave():
    with open(dumbSaveFile, "w") as savefile2:
        for url in downloadQueue.keys():
            print(url, file=savefile2)
