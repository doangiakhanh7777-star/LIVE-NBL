"""4.3.12 (owner, 31/10/2026): AI trả lời bình luận — Gemini hoặc ChatGPT, chữ/giọng/cả hai.

4.3.12: thêm class OpenAI (ChatGPT gpt-4o-mini + TTS tts-1); Settings lưu thêm engine/openai_keys;
        KeyRing và ai_engine.py dùng engine setting để chọn class đúng. Gemini vẫn giữ nguyên.

Comments come from the NBL extension on the TikTok Shop LIVE page (keyword rules are
tried first there). NBL asks Gemini with the shop description and the products in the
cart, sends the answer back to Chrome (chữ) and/or reads it aloud (giọng) on the sound
device Studio listens to. No Qt here.

The API key is stored on this PC only (Windows DPAPI: unreadable on another PC or by
another Windows user), never in the repo.

Gemini endpoints checked 28/10/2026 (ai.google.dev): Interactions API
POST v1beta/interactions, models gemini-3.8-flash / gemini-3.8-flash-tts (WAV 24 kHz).
The older generateContent call is kept as a fallback for older model names.
"""
import base64
import ctypes
import io
import json
import os
import re
import socket
import struct
import time
import wave
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

API = 'https://generativelanguage.googleapis.com/v1beta/'
TEXT_MODEL = 'gemini-3.8-flash'
TTS_MODEL = 'gemini-3.8-flash-tts'
OLD_TEXT_MODEL = 'gemini-2.5-flash'
OLD_TTS_MODEL = 'gemini-2.5-flash-preview-tts'

# ChatGPT (OpenAI)
OAI_API = 'https://api.openai.com/v1/'
OAI_TEXT_MODEL = 'gpt-4o-mini'
OAI_TTS_MODEL = 'tts-1'
# 6 giọng OpenAI TTS
OAI_VOICES = [('alloy', 'trung tính, rõ ràng'), ('echo', 'trầm, chắc'), ('fable', 'kể chuyện, nhẹ nhàng'),
              ('onyx', 'sâu, uy tín'), ('nova', 'tươi sáng, trẻ trung'), ('shimmer', 'mềm mại, ấm áp')]
MAX_CHARS = 100          # TikTok Shop comment box (NBL extension refuses more)
# The 30 voices of Gemini TTS (ai.google.dev, 28/10/2026) with the style Google gives each.
VOICES = [('Kore', 'chắc, rõ'), ('Puck', 'vui, sôi nổi'), ('Zephyr', 'tươi sáng'), ('Leda', 'trẻ trung'), ('Aoede', 'nhẹ nhàng'), ('Charon', 'trầm, rõ ý'),
          ('Fenrir', 'hào hứng'), ('Orus', 'chắc, vững'), ('Callirrhoe', 'thoải mái'), ('Autonoe', 'sáng'), ('Enceladus', 'thì thầm'), ('Iapetus', 'trong'),
          ('Umbriel', 'thoải mái'), ('Algieba', 'mượt'), ('Despina', 'mượt'), ('Erinome', 'trong'), ('Algenib', 'khàn'), ('Rasalgethi', 'rõ ý'),
          ('Laomedeia', 'vui'), ('Achernar', 'mềm'), ('Alnilam', 'chắc'), ('Schedar', 'đều'), ('Gacrux', 'chín chắn'), ('Pulcherrima', 'thẳng thắn'),
          ('Achird', 'thân thiện'), ('Zubenelgenubi', 'tự nhiên'), ('Vindemiatrix', 'dịu dàng'), ('Sadachbia', 'sôi nổi'), ('Sadaltager', 'hiểu biết'), ('Sulafat', 'ấm áp')]
# speed shown as a number (like the owner asked); Gemini TTS has no speed knob, so it is a style hint.
SPEEDS = {'0.8': 'đọc chậm rãi, rõ từng chữ', '1.0': 'đọc tự nhiên, thân thiện', '1.2': 'đọc nhanh, sôi nổi như đang bán hàng livestream',
          '1.5': 'đọc rất nhanh, dứt khoát như chốt đơn livestream'}
DEFAULT_PROMPT = ('Shop: (tên shop) — bán phụ kiện ô tô.\n'
                  'Giao hàng: (toàn quốc, mấy ngày, phí ship…)\n'
                  'Đổi trả / bảo hành: (…)\n'
                  'Cách xưng hô: xưng "em", gọi khách "anh/chị".\n'
                  'Ghi thêm thông tin thật của shop vào đây; AI chỉ dựa vào những gì có ở đây và danh sách sản phẩm trong giỏ.')
RULES = ('Bạn là nhân viên chốt đơn đang trả lời bình luận trong phiên LIVE bán hàng TikTok Shop.\n'
         'Quy tắc bắt buộc:\n'
         '- Trả lời bằng tiếng Việt, NGẮN dưới 90 ký tự, một câu, thân thiện, không dùng ký tự lạ.\n'
         '- Chỉ dựa vào THÔNG TIN SHOP và DANH SÁCH SẢN PHẨM bên dưới. Không bịa giá, khuyến mãi, thời gian giao hàng hay thông số không có trong đó; '
         'nếu không biết thì mời khách xem giỏ hàng hoặc nhắn shop.\n'
         '- Khuyến khích khách bấm giỏ hàng (giỏ màu cam) khi hỏi mua.\n'
         '- Không trả lời chuyện chính trị, tôn giáo, nội dung thô tục; không xin thông tin cá nhân.\n'
         '- Nếu bình luận không cần trả lời (chỉ chào, thả tim, ký tự vô nghĩa, spam) thì chỉ ghi đúng chữ: SKIP\n')


class AIError(Exception):
    pass


# ---------------- key storage ----------------
class _Blob(ctypes.Structure):
    _fields_ = [('cbData', ctypes.c_uint32), ('pbData', ctypes.POINTER(ctypes.c_char))]


def _dpapi(data, protect):
    from ctypes import wintypes  # noqa: F401  (Windows only)
    src = _Blob(len(data), ctypes.cast(ctypes.create_string_buffer(data, len(data)), ctypes.POINTER(ctypes.c_char)))
    out = _Blob()
    fn = ctypes.windll.crypt32.CryptProtectData if protect else ctypes.windll.crypt32.CryptUnprotectData
    if not fn(ctypes.byref(src), None, None, None, None, 0x1, ctypes.byref(out)):
        raise AIError('Windows không mã hóa/giải mã được API key.')
    try:
        return ctypes.string_at(out.pbData, out.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(out.pbData)


def seal(key):
    raw = key.encode('utf-8')
    if os.name == 'nt':
        return 'dpapi:' + base64.b64encode(_dpapi(raw, True)).decode()
    return 'plain:' + base64.b64encode(raw).decode()


def unseal(value):
    value = str(value or '')
    if value.startswith('dpapi:'):
        return _dpapi(base64.b64decode(value[6:]), False).decode('utf-8')
    if value.startswith('plain:'):
        return base64.b64decode(value[6:]).decode('utf-8')
    return ''


class Settings:
    """ai_reply.json in the NBL data folder."""
    DEFAULTS = dict(enabled=False, mode='chu', voice='Kore', speed='1.0', prompt=DEFAULT_PROMPT, keys='', cooldown=60,
                    text_model=TEXT_MODEL, tts_model=TTS_MODEL, max_per_minute=10, rules='',
                    engine='gemini', openai_keys='', oai_voice='nova', oai_text_model=OAI_TEXT_MODEL, oai_tts_model=OAI_TTS_MODEL)

    def __init__(self, path):
        self.path = Path(path)

    def load(self):
        try:
            data = json.loads(self.path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            data = {}
        return {**self.DEFAULTS, **{k: v for k, v in data.items() if k in self.DEFAULTS}}

    def save(self, data):
        from model import write_json
        clean = {k: data.get(k, v) for k, v in self.DEFAULTS.items()}
        if clean['mode'] not in ('chu', 'giong', 'ca_hai'):
            raise ValueError('Kiểu trả lời không hợp lệ.')
        write_json(self.path, clean)
        return clean

    def api_keys(self, data=None):
        """The Gemini keys (several, comma separated when pasted)."""
        try:
            raw = unseal((data or self.load()).get('keys'))
        except Exception:
            return []
        return [k for k in dict.fromkeys(x.strip() for x in re.split(r'[,;\s]+', raw)) if len(k) > 20]

    def set_keys(self, data, text):
        keys = [k for k in dict.fromkeys(x.strip() for x in re.split(r'[,;\s]+', str(text or ''))) if len(k) > 20]
        data['keys'] = seal(','.join(keys)) if keys else ''
        return keys

    def openai_api_keys(self, data=None):
        """OpenAI keys (several, comma separated when pasted)."""
        try:
            raw = unseal((data or self.load()).get('openai_keys'))
        except Exception:
            return []
        return [k for k in dict.fromkeys(x.strip() for x in re.split(r'[,;\s]+', raw)) if len(k) > 20]

    def set_openai_keys(self, data, text):
        keys = [k for k in dict.fromkeys(x.strip() for x in re.split(r'[,;\s]+', str(text or ''))) if len(k) > 20]
        data['openai_keys'] = seal(','.join(keys)) if keys else ''
        return keys


# ---------------- Gemini calls ----------------
def _post(url, body, key, timeout=30):
    # 4.3.8 (owner 29/10): a slow network gave "The read operation timed out" and killed the
    # reply. Retry a timeout / transient network error once before giving up.
    data = json.dumps(body, ensure_ascii=False).encode('utf-8')
    for attempt in range(2):
        req = Request(url, data=data, headers={'Content-Type': 'application/json', 'x-goog-api-key': key}, method='POST')
        try:
            with urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode('utf-8'))
        except HTTPError as e:
            detail = ''
            try:
                detail = json.loads(e.read().decode('utf-8', 'replace')).get('error', {}).get('message', '')
            except Exception:
                pass
            if e.code == 429:
                raise AIError('Gemini đang giới hạn lượt dùng (gói miễn phí); đợi một lát. ' + detail[:150])
            if e.code in (401, 403):
                raise AIError('API key Gemini không đúng hoặc chưa được bật. ' + detail[:150])
            if e.code == 404:
                raise AIError('404 model: ' + detail[:150])
            raise AIError('Gemini lỗi ' + str(e.code) + ': ' + detail[:200])
        except (TimeoutError, socket.timeout):
            if attempt == 0:
                continue
            raise AIError('Gemini phản hồi chậm quá (mạng chậm?); đã thử lại nhưng chưa được.')
        except URLError as e:
            if isinstance(getattr(e, 'reason', None), (TimeoutError, socket.timeout)) and attempt == 0:
                continue
            raise AIError('Không kết nối được Gemini (mạng?): ' + str(getattr(e, 'reason', e))[:150])
    raise AIError('Gemini không trả lời.')


def _texts(obj, out):
    """Every text block of the model's answer (Interactions: steps[].content[]; generateContent: candidates[].content.parts[])."""
    if isinstance(obj, dict):
        if obj.get('type') in (None, 'text', 'output_text') and isinstance(obj.get('text'), str) and 'role' not in obj:
            out.append(obj['text'])
        for k, v in obj.items():
            if k in ('input', 'system_instruction', 'usage', 'usage_metadata', 'usageMetadata'):
                continue
            _texts(v, out)
    elif isinstance(obj, list):
        for v in obj:
            _texts(v, out)
    return out


def answer_text(resp):
    steps = resp.get('steps') if isinstance(resp, dict) else None
    if isinstance(steps, list) and steps:
        for step in reversed(steps):
            if isinstance(step, dict) and step.get('type') not in ('user_input',):
                found = _texts(step, [])
                if found:
                    return found[-1].strip()
    cands = resp.get('candidates') if isinstance(resp, dict) else None
    if cands:
        return ''.join(p.get('text', '') for p in (cands[0].get('content') or {}).get('parts', []) if isinstance(p, dict)).strip()
    found = _texts(resp, [])
    return found[-1].strip() if found else ''


def _audio(obj):
    if isinstance(obj, dict):
        if obj.get('type') == 'audio' and isinstance(obj.get('data'), str):
            return obj['data'], obj.get('mime_type') or obj.get('mimeType') or 'audio/wav'
        inline = obj.get('inlineData') or obj.get('inline_data')
        if isinstance(inline, dict) and isinstance(inline.get('data'), str):
            return inline['data'], inline.get('mimeType') or inline.get('mime_type') or 'audio/l16'
        for v in obj.values():
            r = _audio(v)
            if r:
                return r
    elif isinstance(obj, list):
        for v in reversed(obj):
            r = _audio(v)
            if r:
                return r
    return None


def pcm_to_wav(pcm, rate=24000):
    buf = io.BytesIO()
    with wave.open(buf, 'wb') as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate); w.writeframes(pcm)
    return buf.getvalue()


def clean_answer(text):
    t = re.sub(r'\s+', ' ', str(text or '')).strip().strip('"“”')
    t = re.sub(r'[*_#`]', '', t)
    if not t or t.upper().startswith('SKIP'):
        return ''
    if len(t) > MAX_CHARS:
        cut = t[:MAX_CHARS]
        for sep in ('. ', '! ', '? ', ', '):
            if sep in cut[40:]:
                cut = cut[:cut.rindex(sep) + 1]
                break
        t = cut.rstrip(' ,')
    return t[:MAX_CHARS]


def build_system(prompt, products):
    items = [str(p).strip() for p in products or [] if str(p).strip()][:80]
    return RULES + '\nTHÔNG TIN SHOP:\n' + (str(prompt or '').strip() or '(chưa có)') + '\n\nDANH SÁCH SẢN PHẨM TRONG GIỎ:\n' + ('\n'.join('- ' + x[:120] for x in items) or '(chưa đọc được giỏ)')


class KeyRing:
    """Several keys: one out of quota (429) rests until the next minute, a wrong one is dropped;
    the next key is used. Keys of the same Google project share the free quota."""
    def __init__(self, keys, clock=time.time):
        self.keys, self.clock, self.rest, self.bad, self.i = list(keys), clock, {}, set(), 0

    def usable(self):
        now = self.clock()
        return [k for k in self.keys if k not in self.bad and self.rest.get(k, 0) <= now]

    def call(self, fn):
        if not self.keys:
            raise AIError('Chưa nhập API key Gemini (trang Trả lời bình luận AI).')
        last = None
        for _ in range(len(self.keys)):
            ok = self.usable()
            if not ok:
                break
            key = ok[self.i % len(ok)]
            try:
                return fn(key)
            except AIError as e:
                last = e
                text = str(e)
                if 'giới hạn' in text:
                    self.rest[key] = self.clock() + 65; self.i += 1; continue
                if 'không đúng' in text:
                    self.bad.add(key); self.i += 1; continue
                raise
        if self.keys and len(self.bad) == len(self.keys):
            raise AIError('Tất cả API key Gemini đều sai hoặc chưa bật. ' + (str(last) if last else ''))
        raise AIError('Gemini hết lượt ở tất cả key (gói miễn phí) — tạm không trả lời được. ' + (str(last)[:80] if last else ''))


def parse_rules(text):
    """'từ khóa;từ khóa 2 | câu trả lời' per line (same as the old Chrome rules)."""
    rules = []
    for line in str(text or '').splitlines():
        if '|' not in line:
            continue
        kw, ans = line.split('|', 1)
        words = [w for w in (plain_words(x) for x in kw.split(';')) if w.strip()]
        if words and ans.strip():
            rules.append(dict(words=words, text=ans.strip()[:MAX_CHARS]))
    return rules


def plain_words(s):
    import unicodedata
    t = unicodedata.normalize('NFD', str(s)); t = ''.join(c for c in t if unicodedata.category(c) != 'Mn').replace('đ', 'd').replace('Đ', 'd').lower()
    return ' ' + ' '.join(re.findall(r'\w+', t)) + ' '


def rule_answer(rules, text):
    """Whole-word match; the most specific keyword wins; a tie = no answer (as in Chrome 4.0)."""
    padded = plain_words(text); best, winners = 0, []
    for r in rules:
        n = max((len(w.split()) for w in r['words'] if w.strip() and w in padded), default=0)
        if not n:
            continue
        if n > best:
            best, winners = n, [r]
        elif n == best and all(x['text'] != r['text'] for x in winners):
            winners.append(r)
    return winners[0]['text'] if len(winners) == 1 else None


class Gemini:
    def __init__(self, key, text_model=TEXT_MODEL, tts_model=TTS_MODEL, post=_post):
        if not key:
            raise AIError('Chưa nhập API key Gemini (trang Trả lời bình luận AI).')
        self.key, self.text_model, self.tts_model, self.post = key, text_model or TEXT_MODEL, tts_model or TTS_MODEL, post

    def ask(self, system, question, user=''):
        text = 'Khách "' + str(user)[:60] + '" bình luận: ' + str(question)[:300]
        try:
            resp = self.post(API + 'interactions', {'model': self.text_model, 'system_instruction': system, 'input': text}, self.key)
        except AIError as e:
            if not str(e).startswith('404'):
                raise
            model = OLD_TEXT_MODEL if self.text_model == TEXT_MODEL else self.text_model
            resp = self.post(API + 'models/' + model + ':generateContent',
                             {'systemInstruction': {'parts': [{'text': system}]}, 'contents': [{'role': 'user', 'parts': [{'text': text}]}],
                              'generationConfig': {'maxOutputTokens': 120, 'temperature': 0.6}}, self.key)
        return clean_answer(answer_text(resp))

    def speak(self, text, voice='Kore', speed='1.0'):
        """WAV bytes (24 kHz mono)."""
        style = SPEEDS.get(str(speed), SPEEDS['1.0'])
        try:
            resp = self.post(API + 'interactions', {'model': self.tts_model,
                             'input': [{'type': 'user_input', 'content': [{'type': 'text', 'text': text, 'annotations': [{'type': 'speech_metadata', 'style': style}]}]}],
                             'response_format': {'type': 'audio'}, 'generation_config': {'speech_config': [{'voice': voice}]}}, self.key, timeout=40)
        except AIError as e:
            if not str(e).startswith('404'):
                raise
            model = OLD_TTS_MODEL if self.tts_model == TTS_MODEL else self.tts_model
            resp = self.post(API + 'models/' + model + ':generateContent',
                             {'contents': [{'parts': [{'text': 'Đọc bằng tiếng Việt, ' + style + ': ' + text}]}],
                              'generationConfig': {'responseModalities': ['AUDIO'], 'speechConfig': {'voiceConfig': {'prebuiltVoiceConfig': {'voiceName': voice}}}}}, self.key, timeout=40)
        found = _audio(resp)
        if not found:
            raise AIError('Gemini không trả âm thanh.')
        data, mime = found
        raw = base64.b64decode(data)
        if raw[:4] == b'RIFF':
            return raw
        rate = int((re.search(r'rate=(\d+)', mime or '') or [0, 24000])[1])
        return pcm_to_wav(raw, rate)


# ---------------- OpenAI (ChatGPT) calls ----------------
def _post_openai(path, body, key, timeout=30, binary=False):
    """POST tới OpenAI API. binary=True → trả bytes (TTS). Ném AIError khi lỗi."""
    data = json.dumps(body, ensure_ascii=False).encode('utf-8')
    req = Request(OAI_API + path, data=data,
                  headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + key}, method='POST')
    for attempt in range(2):
        try:
            with urlopen(req, timeout=timeout) as r:
                return r.read() if binary else json.loads(r.read().decode('utf-8'))
        except HTTPError as e:
            detail = ''
            try:
                detail = json.loads(e.read().decode('utf-8')).get('error', {}).get('message', '')
            except Exception:
                pass
            code = str(e.code)
            if e.code == 429:
                raise AIError('ChatGPT hết lượt hoặc hết tiền tài khoản: ' + detail[:200])
            if e.code in (401, 403):
                raise AIError('ChatGPT key không hợp lệ hoặc không có quyền: ' + detail[:200])
            if e.code == 503 or e.code >= 500:
                if attempt == 0:
                    time.sleep(2); continue
                raise AIError('ChatGPT lỗi ' + code + ' (server quá tải, thử lại sau): ' + detail[:200])
            raise AIError(code + ' ChatGPT: ' + detail[:300])
        except (URLError, OSError, socket.timeout) as e:
            if attempt == 0:
                time.sleep(1.5); continue
            raise AIError('ChatGPT lỗi mạng: ' + str(e)[:200])
    raise AIError('ChatGPT không phản hồi sau 2 lần thử.')


class OpenAI:
    """4.3.12: ChatGPT gpt-4o-mini (text) + tts-1 (giọng đọc MP3)."""
    def __init__(self, key, text_model=OAI_TEXT_MODEL, tts_model=OAI_TTS_MODEL, post=_post_openai):
        if not key:
            raise AIError('Chưa nhập API key ChatGPT (trang Trả lời bình luận AI).')
        self.key = key
        self.text_model = text_model or OAI_TEXT_MODEL
        self.tts_model = tts_model or OAI_TTS_MODEL
        self.post = post

    def ask(self, system, question, user=''):
        text = 'Khách "' + str(user)[:60] + '" bình luận: ' + str(question)[:300]
        body = {
            'model': self.text_model,
            'messages': [{'role': 'system', 'content': system}, {'role': 'user', 'content': text}],
            'max_tokens': 120,
            'temperature': 0.6,
        }
        resp = self.post('chat/completions', body, self.key)
        try:
            answer = (resp.get('choices') or [{}])[0].get('message', {}).get('content', '') or ''
        except Exception:
            answer = ''
        return clean_answer(answer)

    def speak(self, text, voice='nova', speed='1.0'):
        """MP3 bytes. OpenAI TTS speed: 0.25–4.0 (thực sự hỗ trợ, không chỉ là gợi ý style)."""
        try:
            spd = max(0.5, min(4.0, float(speed)))
        except Exception:
            spd = 1.0
        body = {'model': self.tts_model, 'input': text[:4096], 'voice': voice, 'speed': spd, 'response_format': 'mp3'}
        return self.post('audio/speech', body, self.key, timeout=40, binary=True)


def make_ai(cfg, key):
    """4.3.12: tạo Gemini hoặc OpenAI tuỳ engine setting."""
    if (cfg.get('engine') or 'gemini') == 'openai':
        return OpenAI(key, cfg.get('oai_text_model') or OAI_TEXT_MODEL, cfg.get('oai_tts_model') or OAI_TTS_MODEL)
    return Gemini(key, cfg.get('text_model') or TEXT_MODEL, cfg.get('tts_model') or TTS_MODEL)


class Limiter:
    """At most n calls per minute (gói miễn phí của Gemini)."""
    def __init__(self, per_minute=10, clock=time.time):
        self.n, self.clock, self.calls = max(1, int(per_minute)), clock, []

    def allow(self):
        now = self.clock()
        self.calls = [t for t in self.calls if now - t < 60]
        if len(self.calls) >= self.n:
            return False
        self.calls.append(now)
        return True
