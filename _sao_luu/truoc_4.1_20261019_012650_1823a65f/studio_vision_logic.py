"""Image-reader decisions; no Windows, input, network or OCR side effects.

4.0: fuzzy text matching (the bundled OCR model has no Vietnamese letters, so
reads are compared after stripping accents and with a similarity threshold),
multi-line chat messages, warning detection that ignores the chat area, and a
NotTouched error type that tells the scheduler a failure happened before any
click or keystroke reached Studio (safe to retry later).
"""
import difflib
import re
import unicodedata

_revoked_guards = set()

# Lines below this OCR confidence are ignored. Text decisions use fuzzy matching,
# so this can be lower than 3.9's 0.90, which rejected most Vietnamese reads.
TEXT_SCORE = 0.80
CLOCK_SCORE = 0.90
MATCH_RATIO = 0.88
PLACEHOLDERS = ('thembinhluan', 'addcomment', 'addacomment', 'nhapbinhluan', 'saycomething')
ALERT_WORDS = ('vi pham', 'han che hien thi', 'captcha', 'xac minh bao mat', 'live violation',
               'phien live da bi han che', 'security verification')


class NotTouched(Exception):
    """Raised when an action failed before any input reached Studio."""


class StudioAttention(ValueError):
    """A real warning, changed account or invalid setup; never retry automatically."""


class CommandExpired(NotTouched):
    """Queue/action deadline elapsed before any input: safe to retry later."""


class NotSentCleaned(NotTouched):
    """Send was never clicked and the owned draft was cleared and verified."""


class InteractionCancelled(ValueError):
    """The caller stopped the action, revoked permission, or revoked permission."""


def revoke_guard(token):
    _revoked_guards.add(token)


def guard_revoked(token):
    return token in _revoked_guards


def normalize(text):
    text = str(text).replace('Đ', 'D').replace('đ', 'd')
    return ' '.join(''.join(c for c in unicodedata.normalize('NFD', text)
                            if unicodedata.category(c) != 'Mn').casefold().split())


def compact(text):
    """Accent-free, case-free, punctuation-free form used for comparisons."""
    return re.sub(r'[\W_]+', '', normalize(text))


def similar(a, b, ratio=MATCH_RATIO):
    # OCR tolerance must never change quantities, money, telephone numbers or IDs.
    if re.findall(r'\d+(?:[.,]\d+)*', normalize(a)) != re.findall(r'\d+(?:[.,]\d+)*', normalize(b)):
        return False
    a, b = compact(a), compact(b)
    if not a or not b:
        return False
    if a == b:
        return True
    # Short strings must match exactly; one wrong letter in 4 is too much.
    if min(len(a), len(b)) < 6:
        return False
    return difflib.SequenceMatcher(None, a, b, autojunk=False).ratio() >= ratio


def message_key(text):
    return compact(text)


def _currency_text(text):
    text=normalize(text)
    # Currency glyphs absent from the model are normalized explicitly. They are
    # never guessed from a changed number or from a different explicit currency.
    codes=[]
    for glyph,code in [('₫','vnd'),('€','eur'),('£','gbp'),('¥','jpy'),('$','usd')]:
        if glyph in text:codes.extend([code]*text.count(glyph));text=text.replace(glyph,' ')
    for code,pat in [('vnd',r'(?<=\d)\s*d\b|\b(?:vnd|dong)\b'),('eur',r'\beur\b'),('gbp',r'\bgbp\b'),('jpy',r'\b(?:jpy|yen)\b'),('usd',r'\busd\b')]:
        found=re.findall(pat,text)
        codes.extend([code]*len(found));text=re.sub(pat,' ',text)
    return text,sorted(codes)


def _message_parts(text):
    text,currencies=_currency_text(text)
    quantities=re.findall(r'[+-]?\d+(?:[.,]\d+)*(?:k|trieu|tr|ty|m)?|[@%]',text)
    tokens=re.findall(r'[a-z]+|[+-]?\d+(?:[.,]\d+)*|[@%]',text)
    return quantities,tokens,currencies


def exact_message(a,b):
    """Exact numeric/sign/unit checks, with a small word-level OCR allowance.

    Never insert/delete words, alter negatives or use similarity for numbers.
    Missing unsupported currency glyphs are tolerated; two explicit different
    currencies are never equivalent.
    """
    qa,wa,ca=_message_parts(a);qb,wb,cb=_message_parts(b)
    if qa!=qb or not wa or len(wa)!=len(wb):return False
    if ca!=cb:
        if ca and cb:return False
        if 'usd' in ca+cb:return False
    errors=0
    protected={'khong','ko','no','not','never','k','co','chua'}
    for x,y in zip(wa,wb):
        if x==y:continue
        if x in protected or y in protected or any(c.isdigit() for c in x+y):return False
        # rn/m is a common glyph confusion (Xern -> Xem), including short words.
        if x.replace('rn','m')==y.replace('rn','m'):errors+=1;continue
        # Long words may differ by one character only, not a broad sentence ratio.
        if min(len(x),len(y))<6 or abs(len(x)-len(y))>1:return False
        if not similar(x,y,.83):return False
        edits=difflib.SequenceMatcher(None,x,y,autojunk=False).get_opcodes()
        cost=sum(max(i2-i1,j2-j1) for tag,i1,i2,j1,j2 in edits if tag!='equal')
        if cost!=1:return False
        errors+=1
    return errors<=min(2,max(1,len(wa)//6))


def author_key(text):
    # Remove emoji/symbol decoration, preserving letters, digits and identity
    # punctuation. Names reduced to no meaningful text must never match.
    clean=''.join(c if unicodedata.category(c)[0] not in ('S','C') else ' ' for c in normalize(text))
    return ' '.join(clean.split()).strip()


def same_author(a,b):
    return bool(author_key(a)) and author_key(a)==author_key(b)


def clock_seconds(text):
    match = re.fullmatch(r'(\d{1,3}):(\d{2}):(\d{2})', text.strip())
    if not match:
        return None
    h, m, s = map(int, match.groups())
    return h * 3600 + m * 60 + s if m < 60 and s < 60 else None


def _clock_text(text):
    # Common OCR confusions inside a digital clock.
    table = str.maketrans({'：': ':', ';': ':', 'O': '0', 'o': '0', 'l': '1', 'I': '1', '|': '1'})
    return text.replace(' ', '').translate(table)


def clock_advancing(first, second, elapsed):
    """Timer moved forward by about the real time between the two screenshots."""
    a, b = clock_seconds(first), clock_seconds(second)
    return a is not None and b is not None and 0 < b-a <= elapsed+2 and b-a >= elapsed-3


def clock_reading(lines, min_score=0.5):
    """4.0.3: find HH:MM:SS anywhere in the clock box, tolerate OCR look-alikes.

    4.0.2 needed one OCR line that was exactly the clock with score >= 0.90, so
    the LIVE button around the timer (icon, border, 'Kết thúc' label) or a
    colon read as '.' made every status check fail. Two readings must still
    advance 1-3 s apart before NBL believes LIVE is on, so a looser read here
    cannot turn a frozen or wrong picture into "LIVE".
    """
    found = []
    for line in lines:
        if line.get('score', 0) < min_score:
            continue
        value = find_clock(line['text'])
        if value:
            found.append(value)
    if not found:
        joined = find_clock(''.join(line['text'] for line in lines if line.get('score', 0) >= min_score))
        found = [joined] if joined else []
    found = list(dict.fromkeys(found))
    return found[0] if len(found) == 1 else ''


_LOOKALIKE = str.maketrans({'O': '0', 'o': '0', 'D': '0', 'Q': '0', 'l': '1', 'I': '1', '|': '1', 'i': '1',
                            '!': '1', 'S': '5', 's': '5', 'B': '8', 'Z': '2', 'z': '2', 'g': '9', 'q': '9',
                            '：': ':', ';': ':', '.': ':', ',': ':', '·': ':', "'": ':', '∶': ':'})


def find_clock(text):
    t = str(text).translate(_LOOKALIKE).replace(' ', '')
    m = re.search(r'(?<!\d)(\d{1,3}):(\d{2}):(\d{2})(?!\d)', t)
    if not m:
        m = re.search(r'(?<!\d)(\d{2})(\d{2})(\d{2})(?!\d)', re.sub(r'[^0-9]', '', t) if len(re.sub(r'[^0-9]', '', t)) == 6 else '')
    if not m:
        return ''
    value = '%02d:%s:%s' % (int(m[1]), m[2], m[3])
    return value if clock_seconds(value) is not None else ''


def is_placeholder(text):
    """The empty-box hint text, allowing a blinking caret before it and icon
    noise after it ("|Thêm bình luận...", "IThêm bình luận VAA")."""
    variants = [text, re.sub(r'^\s*[|Il1i!\[\]]+\s*', '', text)]
    variants += [re.sub(r'(?:\s*[VAIl|/\\^<>]{2,}\s*)+$', '', v.rstrip()) for v in variants]
    for v in variants:
        if compact(v) in PLACEHOLDERS or compact(v.replace('I', 'l')) in PLACEHOLDERS:
            return True
    return False


def faint_placeholder(lines):
    """4.0.3: the hint text read at LOW confidence (0.4-0.8), as happens while
    the caret blinks in front of it after a send. One such read is not proof
    of an empty box; the caller requires it twice in a row."""
    return bool(lines) and all(line['score'] >= .4 for line in lines) and \
        is_placeholder(' '.join(line['text'] for line in lines))


def draft_state(lines, expected=None):
    # Missing OCR is UNKNOWN, never evidence of an empty input.
    if not lines:
        return 'unknown'
    if any(line['score'] < TEXT_SCORE for line in lines):
        return 'unknown'
    text = ' '.join(line['text'] for line in lines)
    if is_placeholder(text):
        return 'empty'
    if expected is not None and exact_message(text, expected):
        return 'expected'
    # 4.0.3: icon glyphs at the right edge of the box (pink Send arrow, emoji)
    # are read as capital-letter noise such as "VAAAIAAA" / "VAAA IAA". Ignore
    # only trailing words made of those shapes; the rest must still match exactly.
    if expected is not None:
        trimmed = re.sub(r'(?:\s*[VAIl|/\\^<>]{2,}\s*)+$', '', text.rstrip())
        if trimmed != text.rstrip() and trimmed.strip() and exact_message(trimmed, expected):
            return 'expected'
    return 'occupied'


def validate_regions(config, required):
    if not isinstance(config, dict) or not config.get('enabled'):
        raise StudioAttention('Bấm Thiết lập đọc bằng ảnh trước.')
    w, h = config.get('width', 0), config.get('height', 0)
    if not all(type(v) is int and 100 <= v <= 10000 for v in (w, h)):
        raise StudioAttention('Kích thước ảnh Studio không hợp lệ.')
    for key in required:
        rect = config.get('regions', {}).get(key)
        if not isinstance(rect, list) or len(rect) != 4 or any(type(v) is not int for v in rect):
            raise StudioAttention('Chưa khoanh đủ vùng: '+key)
        x, y, rw, rh = rect
        if min(x, y) < 0 or min(rw, rh) < 8 or x+rw > w or y+rh > h:
            raise StudioAttention('Vùng đã chọn nằm ngoài Studio: '+key)
    return True


def _usable(lines):
    return sorted((x for x in lines if x['score'] >= TEXT_SCORE), key=lambda x: (x['y'], x['x']))


def own_message_hits(lines, account, message):
    """Y positions of messages by `account` whose text matches `message`.

    Accepts the author on the line above (message may wrap over up to 3 lines)
    or `Name: message` / `Name message` on the same line.
    """
    owner, wanted = author_key(account), message_key(message)
    if not owner or not wanted:
        return []
    lines = _usable(lines)
    hits = []
    for index, author in enumerate(lines):
        text = normalize(author['text'])
        # Only explicit separators establish an inline author boundary. A prefix
        # such as "Nick 1" must not own messages written by "Nick 12".
        inline = re.fullmatch(r'(.+?)\s*[:：]\s*(.+)', text)
        if inline and same_author(inline[1],account):
            if exact_message(inline[2], message):
                hits.append(author['y'])
                continue
        if not same_author(author['text'], account):
            continue
        body, last_y = '', author['y']
        for line in lines[index+1:index+4]:
            gap = line['y'] - last_y
            if gap <= 0 or gap > max(45, line['h']*3) or line['x'] < author['x'] - 40:
                break
            if same_author(line['text'], account):
                break
            body += line['text'] + ' '
            last_y = line['y']
            if exact_message(body, message):
                hits.append(author['y'])
                break
            if len(message_key(body)) > len(wanted) + 6:
                break
    return hits


def own_message_count(lines, account, message):
    return len(own_message_hits(lines, account, message))


def message_confirmed(before_lines, after_lines, account, message, chat_height):
    """Sent if the count grew, or (old copy scrolled away) a match sits at the newest end."""
    before = own_message_hits(before_lines, account, message)
    after = own_message_hits(after_lines, account, message)
    if len(after) > len(before):
        return True
    if not after:
        return False
    def near_end(hits, lines):
        if not hits:
            return False
        newest = max(hits)
        later = [x for x in _usable(lines) if x['y'] > newest + 2]
        return len(later) <= 3 and newest >= chat_height * .5
    # If the same text was already at the end before sending, the picture after a
    # failed send would look the same, so that case stays unconfirmed.
    return near_end(after, after_lines) and not near_end(before, before_lines)


def greeting_key(lines):
    """Visible display name is a conservative dedupe label, not a unique user ID."""
    candidates = []
    for line in lines:
        if line['score'] < TEXT_SCORE:
            continue
        text = normalize(line['text'])
        match = re.fullmatch(r'(.+?)\s+(?:joined|da tham gia|vua tham gia|da vao phong)', text)
        if match and len(match[1]) >= 2:
            candidates.append(re.sub(r'[^\w]+', ' ', match[1]).strip())
    return candidates[0] if len(candidates) == 1 else None


def lines_beside(lines, x, y, height):
    """OCR lines on the same row as a button centred at (x, y), left of it."""
    top, bottom = y - height, y + height / 2
    return [line for line in lines
            if line['x'] < x and top <= line['y'] + line['h'] / 2 <= bottom]


def alert_lines(lines):
    return [line for line in lines if line['score'] >= .85 and
            any(word in normalize(line['text']) for word in ALERT_WORDS)]


def alert_texts(lines):
    return [line['text'] for line in alert_lines(lines)]


# 4.0.3: Studio popups are closed with their own harmless button (OK, Đã hiểu,
# Đóng...) so messages and greetings keep running; each close is reported.
# Never clicked: captcha / security checks (they need a person) and anything
# that would end, delete or log out.
DISMISS_BUTTONS = ('ok', 'dahieu', 'toidahieu', 'gotit', 'dong', 'close', 'boqua', 'desau', 'notnow', 'later')
NEVER_DISMISS = ('captcha', 'xac minh', 'verification', 'verify', 'ket thuc', 'end live', 'xoa ', 'delete',
                 'dang xuat', 'log out', 'thanh toan', 'payment')


def dismiss_button(lines):
    """Centre (x, y) of the one closing button of a popup, else None.

    A popup = a closing button with a sentence (4+ words) above it. Every line
    of that popup must be free of NEVER_DISMISS words.
    """
    found = []
    for b in lines:
        if b['score'] < .8 or compact(b['text']) not in DISMISS_BUTTONS:
            continue
        inside = [l for l in lines if l is not b and b['y'] - 450 <= l['y'] <= b['y'] + 20
                  and b['x'] - 500 <= l['x'] <= b['x'] + b['w'] + 300]
        if not any(len(normalize(l['text']).split()) >= 4 and l['y'] < b['y'] for l in inside):
            continue
        if any(word in ' ' + normalize(l['text']) + ' ' for l in inside + [b] for word in NEVER_DISMISS):
            return None
        found.append(b)
    if len(found) != 1:
        return None
    b = found[0]
    return (b['x'] + b['w'] / 2, b['y'] + b['h'] / 2)


class SeenNames:
    """Insertion-ordered set with a size cap: the oldest names are forgotten."""

    def __init__(self, limit=5000):
        self.limit, self.items = limit, {}

    def __contains__(self, key):
        return key in self.items

    def __len__(self):
        return len(self.items)

    def add(self, key):
        self.items.pop(key, None)
        self.items[key] = True
        while len(self.items) > self.limit:
            self.items.pop(next(iter(self.items)))

    def update(self, keys):
        for key in keys:
            self.add(key)

    def clear(self):
        self.items.clear()

    def __iter__(self):
        return iter(self.items)
