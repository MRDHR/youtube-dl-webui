# !/usr/bin/env python
# coding=utf-8
import copy
import glob
import json
import os
import uuid
from concurrent.futures import ThreadPoolExecutor

import youtube_dl
from tornado import escape
from tornado.concurrent import run_on_executor
from tornado.ioloop import IOLoop
from tornado.web import RequestHandler

downloadQueue = {}
dumbSaveFileName = "tmp/queue.temp"
jsonSaveFileName = "tmp/queue.json"
savedDownloadQueueFile = os.path.join(
    os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir)), jsonSaveFileName
)
dumbSaveFile = os.path.join(
    os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir)), dumbSaveFileName
)
downloadFormatString = "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best"
currentDownloadPercent = 0
youtubelocation = "."
currentDownloadUrl = ""
idCounter = 0


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
        result = '{"state":"ERR"}'
        id = self.get_query_argument('id')
        for url in downloadQueue.keys():
            if str(downloadQueue[url]["id"]) == id:
                if (downloadQueue[url]["status"] != "downloading"
                        or downloadQueue[url]["status"] != "finished"):
                    del downloadQueue[url]
                    saveDownloadQueue()
                    result = '{"state":"OK"}'
                    break
        self.set_header("Content-Type", "application/json; charset=UTF-8")
        self.finish(result)


# 重试下载任务
class RetryHandler(RequestHandler):
    executor = ThreadPoolExecutor(5)

    def get(self):
        result = '{"state":"ERR"}'
        global downloadQueue
        id = self.get_query_argument('id')
        for url in downloadQueue.keys():
            if downloadQueue[url]["id"] == id:
                if (
                        downloadQueue[url]["status"] != "downloading"
                        or downloadQueue[url]["status"] != "finished"
                ):
                    downloadQueue[url]["status"] = "queued"
                    IOLoop.instance().add_callback(self.fireDownloadThread)
                    result = '{"state":"OK"}'
                    break
        self.set_header("Content-Type", "application/json; charset=UTF-8")
        self.finish(result)

    # 激活下载
    @run_on_executor
    def fireDownloadThread(self):
        doDownload()
        return 5


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
        self.set_header("Content-Type", "application/json; charset=UTF-8")
        self.finish('{"state":"OK"}')


# 添加到下载队列
class AddToDownloadQueueHandler(RequestHandler):
    executor = ThreadPoolExecutor(5)

    def post(self):
        global idCounter
        global downloadQueue
        url = self.get_argument('videoUrl')
        path = self.get_argument('videoPaths')
        name = self.get_argument('videoNames')
        for subURL in url.split():
            idCounter = idCounter + 1
            downloadQueue[subURL] = dict(
                [
                    ("status", "queued"),
                    ("url", subURL),
                    ("id", "id_" + generateNewID()),
                    ("mode", "video"),
                    ("path", path),
                    ("name", name)
                ]
            )
        saveDownloadQueue()
        IOLoop.instance().add_callback(self.fireDownloadThread)

        chunk = escape.json_encode(downloadQueue)
        self.set_header("Content-Type", "application/json; charset=UTF-8")
        self.finish(chunk)

    # 激活下载
    @run_on_executor
    def fireDownloadThread(self):
        doDownload()
        return 5


# 生成新的id
def generateNewID():
    newID = str(uuid.uuid4())
    print("New ID: " + newID)
    return newID


# 获取队列的下一个为查询中的item
def getNextQueuedItem():
    saveDownloadQueue()
    # nextItem = getNextStartedItem()
    # if nextItem != "NONE":
    #     return nextItem
    for url in downloadQueue.keys():
        if downloadQueue[url]["status"] == "queued":
            return downloadQueue[url]
    return "NONE"


# 开始下载
def doDownload():
    global downloadQueue
    global currentDownloadUrl
    print(downloadFormatString)
    nextUrl = getNextQueuedItem()
    if nextUrl != "NONE":
        ydl_opts = {
            "logger": MyLogger(),
            "progress_hooks": [MyHook(downloadQueue[nextUrl["url"]]["id"]).hook],
            "prefer_ffmpeg": True,
            "restrictfilenames": False,
            "format": downloadFormatString,
            "outtmpl": ""
        }
        currentDownloadUrl = nextUrl["url"]
        path = nextUrl["path"]
        name = nextUrl["name"]
        if name != "NONE" and name != "":
            ydl_opts['outtmpl'] = path + name
        else:
            ydl_opts['outtmpl'] = path + '%(title)s-%(id)s.%(ext)s'
        print("proceeding to " + currentDownloadUrl)
        try:
            # there's a bug where this will error if your download folder is inside your application folder
            os.chdir(youtubelocation)
            nextUrl["mode"] = "youtube"
            with youtube_dl.YoutubeDL(ydl_opts) as ydl:
                ydl.download([nextUrl["url"]])
            downloadQueue[nextUrl["url"]]["status"] = "completed"
            os.chdir(os.path.dirname(os.path.realpath(__file__)))
        except Exception as e:
            nextUrl["status"] = "error"
            nextUrl["error"] = e
            os.chdir(os.path.dirname(os.path.realpath(__file__)))
        nextUrl = getNextQueuedItem()
        if nextUrl != "NONE":
            doDownload()
    else:
        print("Nothing to do - Finishing Process")


# 自定义日志打印
class MyLogger(object):
    def debug(self, msg):
        pass

    def warning(self, msg):
        print(msg)

    def error(self, msg):
        print(msg)


# youtube-dl自定义拦截器
class MyHook:
    def __init__(self, tid):
        self.tid = tid

    def hook(self, d):
        global currentDownloadPercent
        global downloadQueue
        for url in downloadQueue.keys():
            if str(downloadQueue[url]["id"]) == self.tid:
                if d["status"] == "finished":
                    print("Done downloading, now converting ...")
                    os.utime(d.get("filename", ""))

                if d["status"] == "downloading":
                    currentDownloadPercent = (int(d.get("downloaded_bytes", 0)) * 100) / int(
                        d.get("total_bytes", d.get("downloaded_bytes", 100))
                    )
                    downloadQueue[url]["filename"] = d.get("filename", "?")
                    downloadQueue[url]["tbytes"] = d.get(
                        "_total_bytes_str", d.get("downloaded_bytes", 0)
                    )
                    downloadQueue[url]["dbytes"] = d.get("downloaded_bytes", 0)
                    downloadQueue[url]["time"] = d.get("elapsed", "?")
                    downloadQueue[url]["speed"] = d.get('_speed_str', '?')
                downloadQueue[url]['eta'] = d.get('_eta_str', '?')
                downloadQueue[url]["canon"] = d.get("filename", url)
                downloadQueue[url]["status"] = d.get("status", "?")
                downloadQueue[url]["percent"] = currentDownloadPercent


# 保存下载列表
def saveDownloadQueue():
    global downloadQueue
    dumbSave()
    try:
        with open(savedDownloadQueueFile, "w") as savefile:
            print("Saving: " + str(os.path.abspath(savedDownloadQueueFile)))
            json.dump(downloadQueue, savefile)
    except TypeError:
        for url in downloadQueue.keys():
            downloadQueue[url]["status"] == str(downloadQueue[url]["status"])


# 保存dumb
def dumbSave():
    with open(dumbSaveFile, "w") as savefile2:
        for url in downloadQueue.keys():
            print(url, file=savefile2)
