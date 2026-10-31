"""4.3.0 (owner, 28/10/2026): AI trả lời bình luận trong TikTok LIVE Studio.

Reads Studio's chat from the inside (no mouse), answers with the keyword rules first and
Gemini otherwise, then writes the answer in Studio's comment box and/or reads it aloud
on the sound device of the nick's NBL VIDEO (the video is turned down while it speaks).
Switched on/off by the StudioPanel together with pinning (LIVE on = on).
"""
import collections
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, QUrl

import ai_reply as A

READ_EVERY = 2.5      # seconds between two reads of the chat
SEND_GAP = 6          # seconds between two answers written in the chat
MAX_AGE = 60          # an answer that would come later than this is dropped
QUEUE = 10            # comments waiting for the AI
VOICE_QUEUE = 3       # answers waiting to be read aloud
DUCK = 0.3            # NBL VIDEO volume while the AI speaks


class AIEngine(QObject):
    def __init__(self, owner, data_dir):
        super().__init__(owner)
        self.owner = owner
        self.settings = A.Settings(Path(data_dir) / 'ai_reply.json')
        self.pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix='nbl-ai')
        self.active = {}            # profile id -> state
        self.stats = dict(comments=0, replied=0, voiced=0, skipped=0, dropped=0, errors=0)
        self.status = 'Đang tắt'
        self.ring = None
        self.ring_keys = ()
        self.limiter = A.Limiter(10)
        self.voice = collections.deque()
        self.player = None
        self.ducked = None
        self.preview = None
        self.timer = QTimer(self); self.timer.timeout.connect(self.tick); self.timer.start(500)

    # ---------- on / off ----------
    def start(self, profile):
        cfg = self.settings.load()
        if not cfg.get('enabled'):
            return
        pid = profile['id']
        if pid in self.active:
            self.active[pid]['profile'] = profile; return
        self.active[pid] = dict(profile=profile, seen=set(), baseline=False, read=None, read_at=0, queue=collections.deque(),
                                asking=None, sending=None, sent_at=0, last_user={})
        self.status = 'Đang trả lời bình luận · ' + str(profile.get('name', ''))
        self.owner.log('AI trả lời bình luận: BẬT (' + {'chu': 'chữ', 'giong': 'giọng đọc', 'ca_hai': 'chữ + giọng đọc'}.get(cfg.get('mode'), 'chữ') + ')')

    def stop(self, pid):
        if self.active.pop(pid, None) is not None:
            self.owner.log('AI trả lời bình luận: TẮT')
            self.status = 'Đang tắt'
        if not self.active:
            self.voice.clear()

    def running(self):
        return bool(self.active)

    # ---------- helpers ----------
    def keyring(self, cfg):
        # 4.3.12: chọn key theo engine (gemini / openai)
        engine = cfg.get('engine') or 'gemini'
        if engine == 'openai':
            keys = tuple(self.settings.openai_api_keys(cfg))
        else:
            keys = tuple(self.settings.api_keys(cfg))
        if keys != self.ring_keys or engine != getattr(self, '_ring_engine', ''):
            self.ring, self.ring_keys, self._ring_engine = A.KeyRing(keys), keys, engine
        self.limiter.n = max(1, int(cfg.get('max_per_minute') or 10))
        return self.ring

    def session_of(self, profile):
        return next((s for s in self.owner.data['sessions'] if s['id'] == profile.get('session')), None)

    def products(self, profile):
        try:
            session = self.session_of(profile)
            from session_binding import resolve_binding
            snap = self.owner.bridge.snapshot()
            client = resolve_binding(session.get('chrome_binding'), snap)
            return list((snap.get(client) or {}).get('cartTitles') or [])
        except Exception:
            return []

    def fail(self, text):
        self.stats['errors'] += 1; self.status = '⚠ ' + text
        self.owner.log('AI: ' + text)
        kind = 'quota' if 'hết lượt' in text or 'giới hạn' in text else 'key' if 'key' in text.lower() else 'loi'
        try:
            self.owner.notifier.publish('ai:' + kind, '⚠ AI trả lời bình luận: ' + text[:200])
        except Exception:
            pass

    # ---------- main loop ----------
    def tick(self):
        if not self.active:
            return
        cfg = self.settings.load()
        now = time.time()
        for pid, st in list(self.active.items()):
            p = st['profile']
            pool = self.owner.studio_panel.pool
            from studio_scheduler import execute
            # 1. read the chat
            if st['read'] is None and now - st['read_at'] >= READ_EVERY:
                st['read_at'] = now
                try:
                    st['read'] = pool.submit_priority(35, execute, dict(p), 'chat_read', 0, None)
                except Exception:
                    pass
            elif st['read'] is not None and st['read'].done():
                f, st['read'] = st['read'], None
                try:
                    rows = (f.result() or {}).get('comments') or []
                except Exception:
                    rows = []
                self.take(st, rows, cfg, now)
            # 2. answer the oldest waiting comment
            if st['asking'] is None and st['queue']:
                c, at = st['queue'].popleft()
                if now - at > MAX_AGE:
                    self.stats['dropped'] += 1
                else:
                    self.ask(st, c, cfg)
            elif st['asking'] is not None and st['asking'].done():
                f, st['asking'] = st['asking'], None
                try:
                    c, answer = f.result()
                except A.AIError as e:
                    self.fail(str(e)); continue
                except Exception as e:
                    self.fail('lỗi: ' + str(e)[:120]); continue
                if not answer:
                    self.stats['skipped'] += 1; continue
                self.deliver(st, c, answer, cfg)
            # 3. writing in the chat
            if st['sending'] is not None and st['sending'].done():
                f, st['sending'] = st['sending'], None
                try:
                    f.result(); self.stats['replied'] += 1
                except Exception as e:
                    self.owner.log('AI: chưa gửi được bình luận: ' + str(e)[:150])
        self.play_next()

    def take(self, st, rows, cfg, now):
        name = A.plain_words(st['profile'].get('name') or st['profile'].get('accountName') or '')
        fresh = [r for r in rows if r.get('id') and r['id'] not in st['seen']]
        for r in fresh:
            st['seen'].add(r['id'])
        if len(st['seen']) > 5000:
            st['seen'] = set(list(st['seen'])[-2000:])
        if not st['baseline']:          # comments already there when the AI was switched on are not answered
            st['baseline'] = True; return
        for r in fresh:
            if A.plain_words(r.get('user', '')) == name:      # the shop's own comments (also the AI's)
                continue
            self.stats['comments'] += 1
            if now - st['last_user'].get(r['user'], 0) < int(cfg.get('cooldown') or 60):
                continue
            if len(st['queue']) >= QUEUE:
                st['queue'].popleft(); self.stats['dropped'] += 1
            st['queue'].append((r, now))

    def ask(self, st, c, cfg):
        rules = A.parse_rules(cfg.get('rules') or '')
        hit = A.rule_answer(rules, c['text'])
        st['last_user'][c['user']] = time.time()
        if hit:
            self.deliver(st, c, hit, cfg); return
        ring = self.keyring(cfg)
        engine = cfg.get('engine') or 'gemini'
        if not ring.keys:
            label = 'ChatGPT' if engine == 'openai' else 'Gemini'
            self.fail('Chưa nhập API key ' + label + ' (trang Trả lời bình luận AI).'); return
        if not self.limiter.allow():
            self.stats['dropped'] += 1; return
        system = A.build_system(cfg.get('prompt'), self.products(st['profile']))

        def work():
            return c, ring.call(lambda key: A.make_ai(cfg, key).ask(system, c['text'], c['user']))
        st['asking'] = self.pool.submit(work)

    def deliver(self, st, c, answer, cfg):
        mode = cfg.get('mode') or 'chu'
        self.owner.log('AI trả lời ' + c['user'] + ': ' + answer)
        if mode in ('chu', 'ca_hai') and st['sending'] is None:
            wait = max(0, SEND_GAP - (time.time() - st['sent_at']))
            st['sent_at'] = time.time() + wait
            from studio_scheduler import execute

            def later(profile=dict(st['profile']), text=answer):
                if wait:
                    time.sleep(wait)
                return execute(profile, 'send', 0, {'text': text})
            st['sending'] = self.pool.submit(later)
        if mode in ('giong', 'ca_hai'):
            if len(self.voice) >= VOICE_QUEUE:
                self.stats['dropped'] += 1; self.owner.log('AI: hàng chờ giọng đọc đầy — bỏ câu này'); return
            ring = self.keyring(cfg)
            engine = cfg.get('engine') or 'gemini'
            # 4.3.12: giọng và speed tuỳ engine
            if engine == 'openai':
                voice = cfg.get('oai_voice') or 'nova'
                speed = cfg.get('speed') or '1.0'
            else:
                voice = cfg.get('voice') or 'Kore'
                speed = cfg.get('speed') or '1.0'
            session = self.session_of(st['profile'])

            def speak(cfg=cfg, voice=voice, speed=speed):
                return ring.call(lambda key: A.make_ai(cfg, key).speak(answer, voice, speed))
            self.voice.append(dict(future=self.pool.submit(speak), session=session, at=time.time()))

    # ---------- voice ----------
    def play_next(self):
        if self.player is not None or not self.voice:
            return
        item = self.voice[0]
        if not item['future'].done():
            return
        self.voice.popleft()
        try:
            wav = item['future'].result()
        except Exception as e:
            self.fail('giọng đọc: ' + str(e)[:150]); return
        if time.time() - item['at'] > MAX_AGE + 30:
            self.stats['dropped'] += 1; return
        self.play(wav, item.get('session'), duck=True)
        self.stats['voiced'] += 1

    def device_for(self, session):
        from PySide6.QtMultimedia import QMediaDevices
        want = (session or {}).get('device') or ''
        for d in QMediaDevices.audioOutputs():
            if want and bytes(d.id()).hex() == want:
                return d
        return QMediaDevices.defaultAudioOutput()

    def play(self, wav, session, duck=False, preview=False):
        from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
        path = Path(tempfile.gettempdir()) / ('nbl_ai_%d.wav' % int(time.time() * 1000))
        path.write_bytes(wav)
        player = QMediaPlayer(self); out = QAudioOutput(self.device_for(None if preview else session), self); out.setVolume(1.0)
        player.setAudioOutput(out); player.setSource(QUrl.fromLocalFile(str(path)))
        if duck and session and not session.get('mute'):
            self.ducked = session
            try:
                self.owner.command('settings', False, {**session, 'volume': int(session.get('volume', 80) * DUCK)})
            except Exception:
                self.ducked = None

        def done(state):
            if state == QMediaPlayer.PlaybackState.StoppedState:
                self.finish(player, path)
        player.playbackStateChanged.connect(done)
        if preview:
            self.preview = player
        else:
            self.player = player
        player.play()

    def finish(self, player, path):
        if self.ducked is not None and player is self.player:
            try:
                self.owner.command('settings', False, self.ducked)
            except Exception:
                pass
            self.ducked = None
        if player is self.player:
            self.player = None
        if player is self.preview:
            self.preview = None
        player.deleteLater()
        try:
            path.unlink(missing_ok=True)
        except Exception:
            pass

    # ---------- buttons of the AI page ----------
    def preview_voice(self, cfg, done):
        ring = self.keyring(cfg)
        engine = cfg.get('engine') or 'gemini'
        voice = cfg.get('oai_voice') if engine == 'openai' else cfg.get('voice') or 'Kore'
        speed = cfg.get('speed') or '1.0'
        f = self.pool.submit(lambda: ring.call(lambda key: A.make_ai(cfg, key).speak(
            'Xin chào cả nhà, em là trợ lý của shop. Anh chị xem sản phẩm trong giỏ hàng màu cam nha.', voice or 'nova', speed)))
        return f

    def stop_preview(self):
        if self.preview is not None:
            self.preview.stop()

    def test_ask(self, cfg, question, profile=None):
        ring = self.keyring(cfg)
        system = A.build_system(cfg.get('prompt'), self.products(profile) if profile else [])
        rules = A.parse_rules(cfg.get('rules') or '')
        hit = A.rule_answer(rules, question)
        if hit:
            return self.pool.submit(lambda: 'Từ khóa: ' + hit)
        return self.pool.submit(lambda: 'AI: ' + (ring.call(lambda key: A.make_ai(cfg, key).ask(system, question, 'Khách')) or '(AI bỏ qua câu này)'))

    def summary(self):
        s = self.stats
        return (self.status + ' · ' + str(s['comments']) + ' bình luận, đã trả lời ' + str(s['replied']) + (' (chữ)' if s['voiced'] else '')
                + (', đọc ' + str(s['voiced']) + ' câu' if s['voiced'] else '') + ', bỏ qua ' + str(s['skipped']) + ', bỏ do quá tải ' + str(s['dropped'])
                + (', lỗi ' + str(s['errors']) if s['errors'] else ''))

    def shutdown(self):
        self.timer.stop(); self.active.clear()
        self.pool.shutdown(wait=False, cancel_futures=True)
