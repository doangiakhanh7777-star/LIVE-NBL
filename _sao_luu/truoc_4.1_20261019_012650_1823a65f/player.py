"""One process per numbered source. No TikTok session control.

4.0: the 3-retry limit counts only stalls close together (it resets after a
minute of clean playback, so a 6-hour LIVE is not killed by three unrelated
hiccups), and playlist edits keep the current clip on Windows paths.
"""
import json
import random
import sys
import time
from pathlib import Path
from PySide6.QtGui import QIcon
from PySide6.QtCore import QTimer, QUrl, Qt
from PySide6.QtWidgets import QApplication, QMainWindow, QLabel
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer, QMediaDevices
from PySide6.QtMultimediaWidgets import QVideoWidget
from model import write_json
from video_commands import same_file


HEALTHY_SECONDS = 60

class Output(QMainWindow):
    def __init__(self, folder):
        super().__init__(); self.folder = folder; self.token = ''; self.last_error = ''; self.config = {}; self.order = []; self.index = -1
        self.wanted = 'stopped'; self.generation = 0; self.end_pending = False
        self.stopped_since = None; self.recovery_count = 0; self.playing_since = None
        self.setWindowIcon(QIcon(str(Path(__file__).parent/'assets/logo_38.ico')));self.setWindowTitle('NBL VIDEO'); self.resize(405, 720)
        self.video = QVideoWidget(); self.setCentralWidget(self.video)
        self.audio = QAudioOutput(self); self.audio.setMuted(True)
        self.player = QMediaPlayer(self); self.player.setAudioOutput(self.audio); self.player.setVideoOutput(self.video)
        self.player.mediaStatusChanged.connect(self.media_status)
        self.player.errorOccurred.connect(self.media_error)
        self.devices = QMediaDevices(self); self.devices.audioOutputsChanged.connect(self.refresh_audio)
        self.timer = QTimer(self); self.timer.timeout.connect(self.poll); self.timer.start(250)
        self.heartbeat = QTimer(self); self.heartbeat.timeout.connect(self.maintain); self.heartbeat.start(1000)
        self.poll()
    def maintain(self):
        state = self.player.playbackState()
        media = self.player.mediaStatus()
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self.stopped_since = None
            if self.playing_since is None: self.playing_since = time.monotonic()
            elif self.recovery_count and time.monotonic() - self.playing_since >= HEALTHY_SECONDS:
                self.recovery_count = 0
                if self.last_error.startswith('Video dừng ngoài ý muốn'): self.last_error = ''
        elif (self.wanted == 'playing' and not self.end_pending
              and media in (QMediaPlayer.MediaStatus.LoadedMedia, QMediaPlayer.MediaStatus.BufferedMedia)):
            self.playing_since = None
            if self.stopped_since is None: self.stopped_since = time.monotonic()
            elif time.monotonic() - self.stopped_since >= 5:
                self.stopped_since = None
                if self.recovery_count < 3:
                    self.recovery_count += 1
                    self.player.play()
                    self.status('Video dừng ngoài ý muốn; đã thử tiếp tục ('+str(self.recovery_count)+'/3).')
                else:
                    self.wanted = 'stopped'
                    self.status('Video không tiếp tục được sau 3 lần thử. Kiểm tra file và thiết bị.')
        else: self.stopped_since = None
        self.status()
    def status(self, error=''):
        if error: self.last_error = error
        write_json(self.folder/'status.json', dict(time=time.time(), state=self.player.playbackState().name, position=self.player.position(), duration=self.player.duration(), path=self.player.source().toLocalFile(), error=self.last_error, title=self.windowTitle(), muted=self.audio.isMuted(), device=self.audio.device().description()))
    def refresh_audio(self):
        if not self.config: return
        devices = QMediaDevices.audioOutputs()
        device_id = self.config['device']
        selected = next((d for d in devices if bytes(d.id()).hex() == device_id), None) if device_id else QMediaDevices.defaultAudioOutput()
        if selected is None or selected.isNull():
            self.audio.setMuted(True)
            self.status('Thiết bị âm thanh đã mất. Video vẫn chạy; chọn lại đầu ra âm thanh.')
            return
        if self.last_error.startswith('Thiết bị âm thanh đã mất'): self.last_error = ''
        if self.audio.device() != selected: self.audio.setDevice(selected)
        self.audio.setVolume(self.config['volume']/100)
        self.audio.setMuted(self.config['mute'])
    def apply(self, config):
        old_playlist = self.config.get('playlist', [])
        current_path = self.player.source().toLocalFile()
        self.config = dict(config)
        if old_playlist != config['playlist']:
            self.order = list(range(len(config['playlist'])))
            if config['shuffle']: random.shuffle(self.order)
            matching = next((i for i in self.order if same_file(config['playlist'][i], current_path)), None)
            self.index = self.order.index(matching) if matching is not None else -1
            # Keep the current clip running; edited playlist is used at the next boundary.
        self.setWindowTitle(f"NBL VIDEO {config['number']:02d}" + (f" — {config['account']}" if config['account'] else ''))
        self.refresh_audio()
        return True
    def cancel_transition(self):
        self.generation += 1
        self.end_pending = False
    def media_error(self, *args):
        self.wanted = 'stopped'; self.cancel_transition()
        self.status(self.player.errorString() or 'Không đọc được video.')
    def poll(self):
        try:
            files=sorted((self.folder/'commands').glob('*.json'))
            if not files:return
            try:command=json.loads(files[0].read_text(encoding='utf-8'))
            except (ValueError,UnicodeError):
                files[0].rename(files[0].with_suffix('.invalid'));raise
            files[0].unlink()
            if command.get('deadline',time.time()+1)<time.time():return
            if command['token'] == self.token: return
            self.token = command['token']; self.last_error = ''
            action = command['action']
            if action not in ('play','next','pause','stop','close','settings'):raise ValueError('Lệnh không hợp lệ')
            if action == 'stop':
                self.wanted='stopped';self.cancel_transition();self.player.stop();self.status();return
            if action == 'close':self.close();return
            if not self.apply(command['config']): return
            if action == 'play':
                self.cancel_transition(); self.wanted = 'playing'; self.recovery_count = 0
                self.order = list(range(len(self.config['playlist'])))
                if self.config['shuffle']: random.shuffle(self.order)
                self.index = -1; self.next()
            elif action == 'next':
                self.cancel_transition(); self.wanted = 'playing'; self.next()
            elif action == 'pause':
                self.cancel_transition()
                if self.wanted == 'playing':
                    self.wanted = 'paused'; self.player.pause()
                else:
                    self.wanted = 'playing'
                    if self.player.mediaStatus() == QMediaPlayer.MediaStatus.EndOfMedia: self.next()
                    else: self.player.play()
            elif action == 'stop':
                self.wanted = 'stopped'; self.cancel_transition(); self.player.stop()
            elif action == 'close': self.close()
            self.status()
        except (OSError, ValueError, KeyError, TypeError) as e:
            self.status('Lỗi đọc lệnh: '+str(e))
    def next(self):
        if not self.order:
            self.wanted = 'stopped'; self.player.stop(); self.status('Playlist trống.'); return
        self.index += 1
        if self.index >= len(self.order):
            if not self.config['loop']:
                self.wanted = 'stopped'; self.player.stop(); return
            previous = self.order[-1]
            if self.config['shuffle']:
                random.shuffle(self.order)
                if len(self.order)>1 and self.order[0] == previous: self.order[0], self.order[1] = self.order[1], self.order[0]
            self.index = 0
        path = Path(self.config['playlist'][self.order[self.index]])
        if not path.is_file(): self.wanted = 'stopped'; self.player.stop(); self.status('Không tìm thấy video: '+str(path)); return
        source = QUrl.fromLocalFile(str(path.resolve()))
        self.cancel_transition()
        if self.player.source() == source:
            self.player.setPosition(0)
        else:
            self.player.setSource(source)
        self.player.play()
    def media_status(self, state):
        if state == QMediaPlayer.MediaStatus.EndOfMedia and self.wanted == 'playing' and not self.end_pending:
            self.end_pending = True
            generation = self.generation
            QTimer.singleShot(0, lambda: self.finish_clip(generation))
    def finish_clip(self, generation):
        if generation != self.generation or self.wanted != 'playing': return
        self.end_pending = False
        self.next()
    def closeEvent(self, event):
        self.wanted = 'stopped'; self.cancel_transition(); self.player.stop(); self.status('Cửa sổ đã đóng.'); super().closeEvent(event)

if __name__ == '__main__':
    app = QApplication(sys.argv); window = Output(Path(sys.argv[1])); window.show(); sys.exit(app.exec())
