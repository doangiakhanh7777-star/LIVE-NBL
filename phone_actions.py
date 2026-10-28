"""4.3.0: what the phone app can see and do — the same NBL functions the PC window uses.
All methods except screenshot() run on the Qt thread (phone_api.Server.drain)."""
import copy
import socket
import time
from pathlib import Path

from phone_api import ApiError

DONE = ('finished', 'cancelled', 'skipped', 'failed', 'manual_stop')
RUNNING = ('running', 'starting', 'preparing', 'recovering', 'stopping', 'attention', 'stop_retry', 'recovery_review')
PIN_FIELDS = ('pinMin', 'pinMax', 'gapMin', 'gapMax')
AI_FIELDS = ('enabled', 'mode', 'voice', 'speed', 'cooldown', 'max_per_minute', 'prompt', 'rules')


class Actions:
    def __init__(self, app):
        self.app = app

    # ---- helpers ----
    @property
    def panel(self):
        return self.app.studio_panel

    def profile(self):
        p = self.panel.current_profile()
        if not p:
            raise ApiError('Nick chưa kết nối TikTok LIVE Studio (mở Studio, NBL tự kết nối).')
        return p

    def job(self, body):
        j = next((x for x in self.panel.jobs if x['id'] == str(body.get('id', ''))), None)
        if not j:
            raise ApiError('Không thấy lịch này (có thể đã xóa).', 404)
        return j

    def pin_client(self):
        from session_binding import resolve_binding
        s = self.app.current(); clients = self.app.bridge.snapshot()
        bound = resolve_binding(s.get('chrome_binding'), clients) if s.get('chrome_binding') else None
        return bound, clients.get(bound, {}) if bound else {}

    def live(self, p):
        return bool(p) and (p['id'] in getattr(self.panel, 'hand_live', {}) or any(j['profile'] == p['id'] and j['state'] == 'running' for j in self.panel.jobs))

    def view(self, j):
        from studio_panel import STATE_LABELS
        cart = j.get('cart') or {}
        return dict(id=j['id'], start=j['start'], end=j['end'], state=j['state'], label=STATE_LABELS.get(j['state'], j['state']),
                    bundle=j.get('bundle_index'), noSales=bool(j.get('no_sales')), cart=cart.get('state', 'none'),
                    cartVerified=bool(cart.get('verified')), cartAttempts=cart.get('attempts', 0), error=j.get('error', ''),
                    canRetryCart=j['state'] in ('pending', 'start_retry') and not j.get('no_sales') and cart.get('state') in ('failed', 'none'),
                    running=j['state'] in RUNNING)

    # ---- reading ----
    def status(self):
        from diagnostics import VERSION
        p = self.panel.current_profile(); bound, client = self.pin_client()
        pin = (client.get('modules') or {}).get('pin') or {}
        ai = getattr(self.app, 'ai', None); cfg = ai.settings.load() if ai else {}
        now = time.time()
        nxt = min((j for j in self.panel.jobs if j['state'] in ('pending', 'start_retry') and (not p or j['profile'] == p['id'])), key=lambda j: j['start'], default=None)
        return dict(version=VERSION, pc=socket.gethostname(), nick=(p or {}).get('name', ''), studio=self.panel.connection_status(),
                    live=self.live(p), auto=getattr(self.panel, 'auto_enabled', True),
                    pin=dict(on=bool(pin.get('running')), chrome=bool(bound), text=str(pin.get('status') or pin.get('text') or '')[:200]),
                    ai=dict(enabled=bool(cfg.get('enabled')), running=bool(ai and ai.active), summary=ai.summary() if ai else '', mode=cfg.get('mode', 'chu')),
                    emergency=bool(getattr(self.panel, 'emergency_watch', None)), next=self.view(nxt) if nxt else None,
                    running=[self.view(j) for j in self.panel.jobs if j['state'] in RUNNING], now=now)

    def logs(self, after=0):
        after = int(after or 0)
        return [dict(n=n, at=at, text=t) for n, at, t in list(getattr(self.app, 'phone_log', [])) if n > after][-200:]

    def schedules(self):
        p = self.panel.current_profile(); now = time.time()
        jobs = [j for j in self.panel.jobs if (not p or j['profile'] == p['id']) and (j['state'] not in DONE or j['end'] > now - 86400)]
        return [self.view(j) for j in sorted(jobs, key=lambda j: j['start'])][-60:]

    def screenshot_profile(self):
        p = self.profile()
        if not p.get('cdp'):
            raise ApiError('Ảnh Studio cần kết nối tự động (bản 4.3.0).')
        return copy.deepcopy(self.panel.effective_profile(p))

    @staticmethod
    def screenshot(profile):
        from studio_cdp import execute_cdp
        return execute_cdp(profile, 'screenshot')['jpeg']

    def playlist(self):
        self.app.collect()
        return list(self.app.current().get('playlist') or [])

    def clip_path(self, i):
        clips = self.playlist()
        try:
            path = clips[int(i)]
        except (TypeError, ValueError, IndexError):
            raise ApiError('Không thấy clip này trong danh sách NBL VIDEO.', 404)
        if not Path(path).is_file():
            raise ApiError('File clip không còn trên máy: ' + Path(path).name, 404)
        return path

    def clips(self):
        out = []
        for i, path in enumerate(self.playlist()):
            item = self.app.pin_store.get(path) if Path(path).is_file() else {}
            out.append(dict(i=i, name=Path(path).name, exists=Path(path).is_file(), flags=len(item.get('entries') or []), duration=item.get('duration') or 0))
        return out

    def script(self, i):
        path = self.clip_path(i); item = self.app.pin_store.get(path)
        return dict(name=Path(path).name, entries=item.get('entries') or [], duration=item.get('duration') or 0, titles=self.app.cart_titles())

    def pin_settings(self):
        p = self.app.pin_settings(self.app.current())
        return dict(p, titles=self.app.cart_titles())

    def ai_settings(self):
        import ai_reply as A
        cfg = self.app.ai.settings.load()
        out = {k: cfg.get(k) for k in AI_FIELDS}
        out.update(keyCount=len(self.app.ai.settings.api_keys(cfg)), voices=[dict(id=k, text=t) for k, t in A.VOICES], speeds=list(A.SPEEDS),
                   defaultPrompt=A.DEFAULT_PROMPT, summary=self.app.ai.summary())
        return out

    # ---- doing ----
    def add_schedule(self, body):
        from studio_scheduler import add_job
        p = self.profile(); self.panel.check_nick(p)
        start, end = float(body['start']), float(body['end'])
        no_sales = bool(body.get('noSales'))
        bundle = int(body.get('bundle', 1))
        j = add_job(self.panel.jobs, p['id'], start, end, [], '', no_sales, False, bundle)
        self.panel.save(); self.panel.render()
        self.app.log('Điện thoại: thêm lịch ' + time.strftime('%d/%m %H:%M', time.localtime(start)) + ' → ' + time.strftime('%H:%M', time.localtime(end)) + '.')
        return self.view(j)

    def cancel_schedule(self, body):
        j = self.job(body)
        if j['state'] in RUNNING:
            if body.get('end'):
                j['state'] = 'stopping'; self.panel.stop_chrome(j); self.panel.submit(j, 'stop')
                self.app.log('Điện thoại: kết thúc LIVE của lịch ' + time.strftime('%H:%M', time.localtime(j['start'])) + '.')
            else:
                self.panel.drop_job(j)
        elif j['state'] in DONE:
            raise ApiError('Lịch này đã xong.')
        else:
            self.panel.cancel_pending_starts(j); j['state'] = 'cancelled'; j['retry_at'] = 0
            self.app.log('Điện thoại: hủy lịch ' + time.strftime('%d/%m %H:%M', time.localtime(j['start'])) + '.')
        self.panel.save(); self.panel.render()
        return self.view(j)

    def cart_retry(self, body):
        j = self.job(body)
        if j['state'] not in ('pending', 'start_retry') or j.get('no_sales'):
            raise ApiError('Lịch này không cần thêm giỏ lúc này.')
        cart = j.setdefault('cart', dict(state='none', attempts=0, next=0))
        if cart.get('command'):
            raise ApiError('Đang thêm giỏ, đợi kết quả.')
        cart.update(next=0, check_next=0)
        if cart.get('state') == 'failed':
            cart['state'] = 'none'
        self.panel.save(); self.app.log('Điện thoại: thử thêm giỏ lại ngay cho lịch ' + time.strftime('%H:%M', time.localtime(j['start'])) + '.')
        return self.view(j)

    def set_pin(self, body):
        p = self.profile(); on = bool(body.get('on'))
        session, client = self.panel.client(p)
        if on:
            config = self.app.pin_command_config(session)
            self.app.bridge.command(client, dict(action='start', module='pin', config=config, expectedAccount=session.get('chrome_binding', {}).get('account') or p['name']))
        else:
            self.app.bridge.command(client, dict(action='stop', module='pin'))
        self.app.log('Điện thoại: ' + ('BẬT' if on else 'TẮT') + ' ghim.')
        return dict(on=on)

    def set_ai(self, body):
        on = bool(body.get('on'))
        if on and not self.app.ai.settings.api_keys():
            raise ApiError('Chưa có Gemini API key: dán key ở mục AI trước.')
        self.app.ai_on.setChecked(on); self.app.ai_save(quiet=True)
        self.app.log('Điện thoại: ' + ('BẬT' if on else 'TẮT') + ' AI trả lời bình luận.')
        return dict(on=on)

    def set_auto(self, body):
        on = bool(body.get('on'))
        self.panel.set_auto(on); self.app.refresh_auto_btn()
        self.app.log('Điện thoại: ghim + AI tự động ' + ('BẬT' if on else 'TẠM DỪNG') + '.')
        return dict(on=on)

    def emergency(self, body):
        if body.get('confirm') != 'TAT':
            raise ApiError('Thiếu xác nhận tắt khẩn cấp.')
        self.app.log('Điện thoại: TẮT KHẨN CẤP.')
        self.panel.emergency(None)
        return dict(done=True)

    def save_pin_settings(self, body):
        s = self.app.current(); self.app.collect()
        p = dict(self.app.pin_settings(s))
        if 'mode' in body:
            if body['mode'] not in ('number', 'name'):
                raise ApiError('Kiểu ghim không hợp lệ.')
            p['mode'] = body['mode']
        if 'products' in body:
            p['products'] = str(body['products'])[:4000].strip()
        for k in PIN_FIELDS:
            if k in body:
                p[k] = max(0, min(36000, int(body[k])))
        if p['pinMin'] > p['pinMax'] or p['gapMin'] > p['gapMax']:
            raise ApiError('Số giây "từ" phải nhỏ hơn hoặc bằng "đến".')
        s['pin'] = p; s['pins'] = p['products']
        from model import write_json
        write_json(self.app.path, self.app.data); self.app.fill()
        bound, client = self.pin_client()
        if ((client.get('modules') or {}).get('pin') or {}).get('running'):
            self.set_pin(dict(on=True))
        self.app.log('Điện thoại: lưu cài đặt ghim.')
        return self.pin_settings()

    def save_script(self, i, body):
        import pin_scripts
        path = self.clip_path(i)
        entries, warnings = self.app.pin_store.save(path, body.get('entries') or [], float(body.get('duration') or 0) or None)
        self.app.refresh_playlist_labels()
        self.app.log('Điện thoại: lưu ' + str(len(entries)) + ' cờ ghim cho clip ' + Path(path).name + '.')
        return dict(entries=entries, warnings=warnings, missing=pin_scripts.missing(entries, self.app.cart_titles()))

    def save_ai_settings(self, body):
        import ai_reply as A
        st = self.app.ai.settings; cfg = st.load()
        for k in AI_FIELDS:
            if k in body:
                cfg[k] = body[k]
        if str(cfg.get('speed')) not in A.SPEEDS or cfg.get('voice') not in [k for k, _ in A.VOICES] or cfg.get('mode') not in ('chu', 'giong', 'ca_hai'):
            raise ApiError('Giọng / tốc độ / kiểu trả lời không hợp lệ.')
        cfg['cooldown'] = max(15, min(3600, int(cfg['cooldown']))); cfg['max_per_minute'] = max(1, min(60, int(cfg['max_per_minute'])))
        cfg['prompt'] = str(cfg.get('prompt') or A.DEFAULT_PROMPT)[:6000]; cfg['rules'] = str(cfg.get('rules') or '')[:6000]
        if str(body.get('keys') or '').strip():
            if not st.set_keys(cfg, body['keys']):
                raise ApiError('Chưa thấy key Gemini hợp lệ (dạng AIza…).')
        if cfg.get('enabled') and not st.api_keys(cfg):
            raise ApiError('Chưa có Gemini API key: dán key trước khi bật.')
        st.save(cfg)
        a = self.app
        for w, value in ((a.ai_mode, cfg['mode']), (a.ai_voice, cfg['voice']), (a.ai_speed, str(cfg['speed']))):
            w.blockSignals(True); w.setCurrentIndex(max(0, w.findData(value))); w.blockSignals(False)
        for w, value in ((a.ai_cooldown, cfg['cooldown']), (a.ai_rate, cfg['max_per_minute'])):
            w.blockSignals(True); w.setValue(int(value)); w.blockSignals(False)
        a.ai_prompt.setPlainText(cfg['prompt']); a.ai_rules.setPlainText(cfg['rules'])
        a.ai_on.blockSignals(True); a.ai_on.setChecked(bool(cfg['enabled'])); a.ai_on.blockSignals(False)
        if hasattr(a, 'ai_key_count'):
            n = len(st.api_keys(cfg)); a.ai_key_count.setText('Đã lưu ' + str(n) + ' key (mã hóa, chỉ trên máy này)' if n else 'Chưa có key')
        a.ai_save(quiet=True)
        a.log('Điện thoại: lưu cài đặt AI.')
        return self.ai_settings()
