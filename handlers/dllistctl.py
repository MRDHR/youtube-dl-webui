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

downloadQueue = []
downloadFormatString = "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best"
currentDownloadPercent = 0
youtubelocation = "."
idCounter = 0
jsonStr = ''


# 定义视图处理类
class DownloadQueueHandler(RequestHandler):
    def get(self):
        global downloadQueue
        # Manually stringify the error object if there is one,
        # because apparently jsonify can't do it automatically
        for mission in downloadQueue:
            if mission["status"] == "error":
                mission["error"] = str(mission["error"])
        chunk = escape.json_encode(downloadQueue)
        self.set_header("Content-Type", "application/json; charset=UTF-8")
        self.finish(chunk)


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
        for mission in downloadQueue:
            if str(mission["id"]) == id:
                if (mission["status"] != "downloading"
                        or mission["status"] != "finished"):
                    downloadQueue.remove(mission)
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
        for mission in downloadQueue:
            if mission["id"] == id:
                if (mission["status"] != "downloading" or mission["status"] != "finished"):
                    mission["status"] = "queued"
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
        for mission in downloadQueue:
            if mission["status"] == "completed":
                downloadQueue.remove(mission)
        downloadQueue = newDownloadQueue
        self.set_header("Content-Type", "application/json; charset=UTF-8")
        self.finish('{"state":"OK"}')


# 添加到下载队列
class AddToDownloadQueueHandler(RequestHandler):
    executor = ThreadPoolExecutor(5)

    def post(self):
        global idCounter
        global downloadQueue
        url = self.get_argument('url')
        path = self.get_argument('videoPath')
        name = self.get_argument('videoName')
        for subURL in url.split():
            idCounter = idCounter + 1
            downloadQueue.append(dict(
                [
                    ("status", "queued"),
                    ("url", subURL),
                    ("id", "id_" + generateNewID()),
                    ("mode", "video"),
                    ("path", path),
                    ("name", name),
                    ("percent", 0)
                ]
            ))
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
    for mission in downloadQueue:
        if mission["status"] == "queued":
            return mission
    return "NONE"


# 开始下载
def doDownload():
    global downloadQueue
    print(downloadFormatString)
    nextUrl = getNextQueuedItem()
    if nextUrl != "NONE":
        ydl_opts = {
            "logger": MyLogger(),
            "progress_hooks": [MyHook(nextUrl["id"]).hook],
            "prefer_ffmpeg": True,
            "restrictfilenames": False,
            "format": downloadFormatString,
            "outtmpl": ""
        }
        path = nextUrl["path"]
        name = nextUrl["name"]
        if name != "NONE" and name != "":
            ydl_opts['outtmpl'] = path + name
        else:
            ydl_opts['outtmpl'] = path + '%(title)s-%(id)s.%(ext)s'
        print("proceeding to " + nextUrl["url"])
        try:
            # there's a bug where this will error if your download folder is inside your application folder
            os.chdir(youtubelocation)
            nextUrl["mode"] = "youtube"
            with youtube_dl.YoutubeDL(ydl_opts) as ydl:
                ydl.download([nextUrl["url"]])
            nextUrl["status"] = "completed"
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
        for mission in downloadQueue:
            if str(mission["id"]) == self.tid:
                if d["status"] == "finished":
                    print("Done downloading, now converting ...")
                    os.utime(d.get("filename", ""))

                if d["status"] == "downloading":
                    currentDownloadPercent = (int(d.get("downloaded_bytes", 0)) * 100) / int(
                        d.get("total_bytes", d.get("downloaded_bytes", 100))
                    )
                    mission["filename"] = d.get("filename", "?")
                    mission["tbytes"] = d.get(
                        "_total_bytes_str", d.get("downloaded_bytes", 0)
                    )
                    mission["dbytes"] = d.get("downloaded_bytes", 0)
                    mission["time"] = d.get("elapsed", "?")
                    mission["speed"] = d.get('_speed_str', '?')
                mission['eta'] = d.get('_eta_str', '?')
                mission["canon"] = d.get("filename", mission["url"])
                mission["status"] = d.get("status", "?")
                mission["percent"] = currentDownloadPercent
