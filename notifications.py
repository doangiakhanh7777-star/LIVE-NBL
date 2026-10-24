"""Optional Android alerts via a user-configured Telegram bot."""
import base64
import ctypes
import json
import os
import queue
import re
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from model import write_json


class SecretVault:
    def protect(self, token):
        if sys.platform != 'win32':
            raise RuntimeError('Thiết lập thông báo điện thoại trên máy Windows chạy NBL LIVE.')
        return self._dpapi(token.encode('utf-8'), True)
    def unprotect(self, value):
        if sys.platform != 'win32':
            raise RuntimeError('Không đọc được mã bot đã lưu ngoài máy Windows này.')
        return self._dpapi(base64.b64decode(value), False).decode('utf-8')
    @staticmethod
    def _dpapi(data, protect):
        from ctypes import wintypes
        class Blob(ctypes.Structure):
            _fields_ = [('size', wintypes.DWORD), ('data', ctypes.POINTER(ctypes.c_ubyte))]
        buffer = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
        incoming = Blob(len(data), buffer); outgoing = Blob()
        crypt = ctypes.WinDLL('crypt32', use_last_error=True)
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        function = crypt.CryptProtectData if protect else crypt.CryptUnprotectData
        function.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p,
                             ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD,
                             ctypes.POINTER(Blob)]
        function.restype = wintypes.BOOL
        if not function(ctypes.byref(incoming), None, None, None, None, 1, ctypes.byref(outgoing)):
            raise OSError('Không lưu/đọc được mã bot trên Windows.')
        try:
            result = ctypes.string_at(outgoing.data, outgoing.size)
            return base64.b64encode(result).decode('ascii') if protect else result
        finally:
            kernel.LocalFree.argtypes = [ctypes.c_void_p]
            kernel.LocalFree.restype = ctypes.c_void_p
            kernel.LocalFree(outgoing.data)


class NotificationSettings:
    def __init__(self, path, vault=None):
        self.path = Path(path); self.vault = vault or SecretVault()
    def load(self):
        if not self.path.exists():
            return dict(enabled=False, chat_id='', token='')
        value = json.loads(self.path.read_text(encoding='utf-8'))
        if not isinstance(value, dict) or value.get('schema') != 1:
            raise ValueError('Thiết lập thông báo điện thoại không hợp lệ.')
        if type(value.get('enabled')) is not bool or not isinstance(value.get('chat_id',''),str) or not isinstance(value.get('protected_token',''),str):
            raise ValueError('Thiết lập thông báo điện thoại không hợp lệ.')
        token = self.vault.unprotect(value['protected_token']) if value.get('protected_token') else ''
        return dict(enabled=bool(value.get('enabled')), chat_id=str(value.get('chat_id', '')), token=token)
    def save(self, enabled, chat_id, token):
        chat_id = chat_id.strip(); token = token.strip()
        if enabled and (not re.fullmatch(r'-?\d{1,20}', chat_id) or
                        not re.fullmatch(r'\d{5,20}:[A-Za-z0-9_-]{20,100}', token)):
            raise ValueError('Nhập đúng mã bot Telegram và Chat ID nhận thông báo.')
        value = dict(schema=1, enabled=bool(enabled), chat_id=chat_id,
                     protected_token=self.vault.protect(token) if token else '')
        write_json(self.path, value)
        return dict(enabled=bool(enabled), chat_id=chat_id, token=token)


def telegram_send(config, text, opener=urllib.request.urlopen, api='https://api.telegram.org'):
    if not config.get('enabled'):
        return False
    body = urllib.parse.urlencode(dict(chat_id=config['chat_id'], text=text[:3500])).encode('utf-8')
    request = urllib.request.Request(api + '/bot' + config['token'] + '/sendMessage',
                                     data=body, headers={'Content-Type':'application/x-www-form-urlencoded'})
    with opener(request, timeout=8) as response:
        result = json.loads(response.read(100000))
    if not isinstance(result, dict) or result.get('ok') is not True:
        raise RuntimeError('Telegram chưa xác nhận gửi thông báo.')
    return True


class Notifier:
    def __init__(self, sender=telegram_send, clock=time.monotonic):
        self.sender = sender; self.clock = clock; self.config = dict(enabled=False)
        self.work = queue.Queue(maxsize=10); self.results = queue.Queue()
        self.lock = threading.Lock(); self.last = {}; self.generation = 0; self.closed = False
        self.thread = threading.Thread(target=self.run, daemon=True); self.thread.start()
    def configure(self, config):
        with self.lock:
            self.config = dict(config); self.generation += 1
            while True:
                try:self.work.get_nowait()
                except queue.Empty:break
    def publish(self, key, text, test=False):
        with self.lock:
            if self.closed or not self.config.get('enabled'):
                return False
            now = self.clock()
            if not test and now - self.last.get(key, -1000) < 60:
                return False
            try:self.work.put_nowait((self.generation, dict(self.config), text))
            except queue.Full:return False
            self.last[key] = now
            if len(self.last) > 100:self.last = {key:now}
            return True
    def run(self):
        while not self.closed:
            try:generation, config, text = self.work.get(timeout=.2)
            except queue.Empty:continue
            with self.lock:
                if self.closed or generation != self.generation:continue
            try:
                self.sender(config, text)
                self.results.put('Đã gửi cảnh báo tới Telegram.')
            except Exception as error:
                # Never show the exception URL, which contains the bot token.
                code = getattr(error, 'code', None)
                self.results.put('Gửi Telegram chưa thành công' + (' (HTTP '+str(code)+')' if code else '') + '. Kiểm tra mã bot, Chat ID và kết nối.')
    def drain(self):
        items = []
        while True:
            try:items.append(self.results.get_nowait())
            except queue.Empty:return items
    def close(self):
        with self.lock:self.closed = True; self.generation += 1
