"""4.3.13: chạy thử NBL thật (Qt, cửa sổ ẩn) — dùng trên Windows bằng runtime\\python.exe.

    set QT_QPA_PLATFORM=offscreen
    runtime\\python.exe tests\\smoke_qt4313.py

Máy chạy thử không có micro/loa thật nên luồng âm thanh được thử bằng thiết bị giả
(đúng code pump của PushToTalk). Mỗi mục in OK/FAIL; còn FAIL thì mã thoát 1.
"""
import os
import sys
import tempfile
import time
import traceback
from pathlib import Path

DATA_ROOT = tempfile.mkdtemp(prefix='nbl_smoke_')
os.environ['LOCALAPPDATA'] = DATA_ROOT
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE)); os.chdir(BASE)

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

results = []


def check(name, fn):
    try:
        fn(); results.append((name, True, '')); print('OK   ', name, flush=True)
    except Exception as e:
        results.append((name, False, repr(e))); print('FAIL ', name, '->', repr(e), flush=True); traceback.print_exc()


def spin(sec):
    end = time.time() + sec
    while time.time() < end:
        QApplication.processEvents(); time.sleep(0.01)


app = QApplication(sys.argv); app.setStyle('Fusion')
from theme import STYLE
app.setStyleSheet(STYLE)
import app as nbl
w = nbl.Console(); w.show(); spin(2)


def t_title():
    from diagnostics import VERSION
    assert w.windowTitle() == 'TOOL NBL LIVE • ' + VERSION, w.windowTitle()
    assert 'vá' not in w.windowTitle().lower()


def t_pages():
    names = [w.navigation.itemText(i) for i in range(w.navigation.count())] if hasattr(w.navigation, 'itemText') else [w.tabs.tabText(i) for i in range(w.tabs.count())]
    assert any('Giọng nói' in n for n in names), names
    assert any('Trả lời bình luận AI' in n for n in names), names


def t_ai_engine_ui():
    assert w.ai_engine.findData('openai') >= 0 and w.ai_engine.findData('gemini') >= 0
    w.ai_engine.setCurrentIndex(w.ai_engine.findData('openai')); spin(0.1)
    cfg = w.ai.settings.load(); assert cfg['engine'] == 'openai', cfg.get('engine')
    assert w.oai_voice.count() == 6
    w.ai_engine.setCurrentIndex(w.ai_engine.findData('gemini')); spin(0.1)
    assert w.ai.settings.load()['engine'] == 'gemini'


def t_make_ai():
    import ai_reply as A
    assert isinstance(A.make_ai(dict(engine='openai'), 'sk-x'), A.OpenAI)
    assert isinstance(A.make_ai(dict(engine='gemini'), 'AIza-x'), A.Gemini)


def t_voice_page_widgets():
    assert w.voice_mic.count() >= 1 and w.voice_out.count() >= 1
    assert w.voice_out.itemData(0) == ''
    assert not w.ptt.armed


def t_voice_arm_without_devices_is_clean():
    w.voice_on.setChecked(True); spin(0.3)
    # máy chạy thử không có micro: phải báo lỗi rõ, không văng
    assert w.ptt.armed or w.ptt.error, 'không bật mà cũng không báo lỗi'
    w.voice_on.setChecked(False); spin(0.2)
    assert not w.ptt.armed
    assert w.ptt.settings.load()['enabled'] is False


class FakeIn:
    def __init__(self): self.buf = b''
    def readAll(self):
        d, self.buf = self.buf, b''; return d


class FakeSink:
    def __init__(self, free): self.free = free
    def bytesFree(self): return self.free


class FakeOut:
    def __init__(self): self.data = []
    def write(self, d): self.data.append(bytes(d)); return len(d)


def t_pump_only_while_talking_and_never_lags():
    import array
    from PySide6.QtMultimedia import QAudioFormat
    from ptt import PushToTalk
    p = PushToTalk(w, DATA_ROOT, key_reader=lambda: False)
    fi = QAudioFormat(); fi.setSampleRate(48000); fi.setChannelCount(1); fi.setSampleFormat(QAudioFormat.SampleFormat.Int16)
    fo = QAudioFormat(); fo.setSampleRate(48000); fo.setChannelCount(2); fo.setSampleFormat(QAudioFormat.SampleFormat.Int16)
    p.fi, p.fo = fi, fo; p.inp = FakeIn(); p.sink = FakeSink(100000); p.out = FakeOut()
    from ptt_core import Pipeline
    p.pipe = Pipeline(48000, 1, 'i16', 48000, 2, 'i16')
    p.inp.buf = array.array('h', [1000] * 960).tobytes(); p.pump()
    assert p.out.data == [], 'không giữ phím mà vẫn ghi vào cáp'
    assert p.level > 0.02
    p.talking = True
    p.inp.buf = array.array('h', [1000] * 960).tobytes(); p.pump()
    assert len(p.out.data) == 1 and len(p.out.data[0]) == 960 * 2 * 2, len(p.out.data[0])
    p.sink.free = 1000; p.inp.buf = array.array('h', range(960)).tobytes(); p.pump()
    last = p.out.data[-1]; assert len(last) == 1000, len(last)            # bỏ phần cũ, giữ phần mới nhất
    assert abs(array.array('h', last)[-1] - 959) <= 1
    # 4.3.14: mic 44,1 kHz float stereo -> cáp 48 kHz 16-bit stereo (4.3.13 không mở được ca này)
    p.pipe = Pipeline(44100, 2, 'f32', 48000, 2, 'i16'); p.sink.free = 100000
    fi2 = QAudioFormat(); fi2.setSampleRate(44100); fi2.setChannelCount(2); fi2.setSampleFormat(QAudioFormat.SampleFormat.Float); p.fi = fi2
    p.inp.buf = array.array('f', [0.25] * 882).tobytes(); n0 = len(p.out.data); p.pump()
    got = array.array('h', p.out.data[-1]); assert len(p.out.data) == n0 + 1 and abs(len(got) / 2 - 441 * 48000 / 44100) <= 2, len(got)
    assert abs(got[-1] - 8192) <= 2, got[-1]


def t_gate_with_fake_key():
    from ptt import PushToTalk
    state = {'down': False}
    p = PushToTalk(w, DATA_ROOT, key_reader=lambda: state['down'])
    p.armed = True; p.anywhere = True; p.owner_active = lambda: False
    seen = []
    w_changed = w.ptt_changed
    w.ptt_changed = lambda on: seen.append(on)
    try:
        state['down'] = True; p.tick(); time.sleep(0.1); p.tick()
        assert not p.talking, 'chạm 0,1 giây đã mở mic'
        time.sleep(0.2); p.tick(); assert p.talking
        state['down'] = False; p.tick(); assert p.talking            # còn đuôi 0,15 giây
        time.sleep(0.2); p.tick(); assert not p.talking
        assert seen == [True, False], seen
        p.anywhere = False; state['down'] = True; p.tick(); time.sleep(0.3); p.tick()
        assert not p.talking, 'tắt "nhận phím ở cửa sổ khác" mà vẫn mở'
    finally:
        w.ptt_changed = w_changed


def t_ptt_changed_holds_ai_and_shows_badge():
    stopped = []

    class P:
        def stop(self): stopped.append(1)
    w.ai.player = P()
    w.ptt_changed(True); spin(0.05)
    assert w.ai.hold and stopped and w.talk_badge.w.isVisible()
    w.ai.player = None
    w.ai.voice.append(dict(future=None, session=None, at=time.time()))
    w.ai.play_next()                                   # đang giữ phím: không được đụng tới hàng chờ
    assert len(w.ai.voice) == 1
    w.ai.voice.clear()
    w.ptt_changed(False); spin(0.05)
    assert not w.ai.hold and not w.talk_badge.w.isVisible()


def t_store_upload_and_delete():
    store = w.video_store
    store.folder.mkdir(parents=True, exist_ok=True)
    f = store.folder / 'Video live.mp4'; f.write_bytes(b'\x00' * 2048)
    r = w.video_uploaded(str(f))
    assert r['ok'], r
    assert any(Path(p) == f for p in w.playlist_paths()), w.playlist_paths()
    assert any(Path(p) == f for p in w.current()['playlist'])
    w.refresh_store(); assert w.store_list.count() == 1 and 'trong playlist' in w.store_list.item(0).text()
    text = w.delete_videos([str(f)])
    assert 'Đã xóa khỏi máy' in text, text
    assert not f.exists() and not any(Path(p) == f for p in w.playlist_paths())
    w.refresh_store(); assert w.store_list.count() == 0


def t_store_never_deletes_user_files():
    mine = Path(DATA_ROOT) / 'cua_toi.mp4'; mine.write_bytes(b'x')
    w.add_playlist_items([str(mine)]); w.save_current()
    text = w.delete_videos([str(mine)])
    assert mine.exists(), 'xóa mất file của chủ máy nằm ngoài kho'
    assert 'giữ nguyên' in text, text


def t_phone_server_has_store():
    assert w.phone_server.store is w.video_store


def t_two_talkers_toggle_once():
    seen = []
    orig = w.ai.set_hold
    w.ai.set_hold = lambda on: (seen.append(on), orig(on))
    try:
        w.ptt_changed(True, 'phim'); w.ptt_changed(True, 'dien_thoai')     # cả hai cùng nói
        w.ptt_changed(False, 'phim'); spin(0.05)
        assert w.ai.hold and w.talk_badge.w.isVisible(), 'phím thả mà điện thoại còn nói thì vẫn phải im AI'
        w.ptt_changed(False, 'dien_thoai'); spin(0.05)
        assert not w.ai.hold and not w.talk_badge.w.isVisible()
        assert seen == [True, False], seen
    finally:
        w.ai.set_hold = orig


def t_phone_talk_wired():
    assert w.phone_server.talk is w.remote_talk
    assert w.remote_talk.status() == '' and not w.remote_talk.talking
    assert 'điện thoại' in w.voice_phone.text().lower()


def t_player_hidden_fallback():
    import player
    assert callable(player.paint_hidden) and callable(player._hidden)


for name, fn in [('tiêu đề 4.3.14', t_title), ('có trang Giọng nói + AI', t_pages), ('chọn Gemini/ChatGPT', t_ai_engine_ui),
                 ('make_ai đúng lớp', t_make_ai), ('trang Giọng nói đủ ô', t_voice_page_widgets),
                 ('bật giọng nói khi máy không có micro', t_voice_arm_without_devices_is_clean),
                 ('mic chỉ vào cáp khi đang giữ phím, không trễ dần', t_pump_only_while_talking_and_never_lags),
                 ('giữ phím: chạm nhanh không mở, giữ mới mở, có đuôi', t_gate_with_fake_key),
                 ('đang nói: AI im + nhãn đỏ', t_ptt_changed_holds_ai_and_shows_badge),
                 ('kho video: nhận -> playlist -> xóa', t_store_upload_and_delete),
                 ('kho video không xóa file ngoài kho', t_store_never_deletes_user_files),
                 ('phone API nhận kho video', t_phone_server_has_store),
                 ('phím + điện thoại cùng nói: AI im/nhãn đỏ bật tắt 1 lần', t_two_talkers_toggle_once),
                 ('phone API có đường nói qua điện thoại', t_phone_talk_wired),
                 ('NBL VIDEO có đường vẽ khi bị khuất', t_player_hidden_fallback)]:
    check(name, fn)

ok = all(r[1] for r in results)
print('\nKET QUA: %d/%d OK' % (sum(r[1] for r in results), len(results)), flush=True)
w._force_close = True
try:
    w.close(); spin(0.5)
except Exception:
    traceback.print_exc()
os._exit(0 if ok else 1)
