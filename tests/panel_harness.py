"""Run the REAL StudioPanel schedule methods (taken from studio_panel.py by AST)
without Qt, against fake Studio / Chrome / video objects."""
import ast, copy, json, sys, tempfile, time, types
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import studio_scheduler as S
import studio_vision_logic as L
from video_commands import same_file

# 4.1.2: a schedule replays the nick's own NBL VIDEO playlist, so it must exist.
CLIP = tempfile.NamedTemporaryFile(suffix='.mp4', delete=False).name

METHODS = ('tick', 'notify', 'action_failed', 'start_video', 'warn_shared_audio', 'on_started', 'resume_automation',
           'on_stopped', 'watch_dark', 'poll_chrome_modules', 'start_chrome_modules', 'cart_ready', 'cart_ok', 'poll_cart',
           'cart_failed', 'close_chrome_summary', 'stop_owned_video', 'stop_chrome', 'drop_job', 'end_hand_live', 'postpone', 'watch_summary', 'poll_summary', 'poll_clip', 'reset_done', 'reset_failed', 'poll_captcha', 'emergency', 'poll_emergency', 'publish', 'cancel_pending_starts')


def panel_class():
    tree = ast.parse((ROOT/'studio_panel.py').read_text(encoding='utf-8'))
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'StudioPanel')
    body = [copy.deepcopy(n) for n in cls.body if isinstance(n, ast.FunctionDef) and n.name in METHODS]
    reports = []
    ns = dict(uuid=__import__('uuid'), copy=copy, json=json, re=__import__('re'), time=time, Path=Path, NotTouched=L.NotTouched, same_file=same_file,
              decisions=S.decisions, execute=lambda *a, **k: None, ACTIVE=S.ACTIVE, START_MARGIN=S.START_MARGIN,
              RETRY_GAP=S.RETRY_GAP, STOP_TRIES=S.STOP_TRIES, report=lambda *a: reports.append(a))
    helpers = [copy.deepcopy(n) for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in ('vision_missing', 'video_problem', 'now_due')]
    # Module-level rules of the app itself (POSTPONE, PROBE_GAP, RESET_EVERY, RESET_HOLD, NO_RESET…).
    helpers += [copy.deepcopy(n) for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'ChromeWait']   # 4.3.4
    helpers += [copy.deepcopy(n) for n in tree.body if isinstance(n, ast.Assign) and all(isinstance(t, ast.Name) and t.id in ('POSTPONE', 'PROBE_GAP', 'RESET_EVERY', 'RESET_HOLD', 'NO_RESET') for t in n.targets)]
    mod = ast.Module(body=helpers + [ast.ClassDef(name='Panel', bases=[], keywords=[], body=body, decorator_list=[])], type_ignores=[])
    exec(compile(ast.fix_missing_locations(mod), str(ROOT/'studio_panel.py'), 'exec'), ns)
    return ns['Panel'], reports


class Bridge:
    def __init__(self):
        self.commands = []; self.control = {}; self.modules = {}; self.down = False
    def command(self, client, payload):
        if self.down: raise ValueError('Chưa có đúng tab Chrome/nick kết nối.')
        self.commands.append(payload); return 'cmd%d' % len(self.commands)
    def snapshot(self):
        return {'client': dict(control=self.control, modules=self.modules)}


def make(jobs, profiles=None, sessions=None):
    Panel, reports = panel_class()
    p = Panel()
    p.jobs = jobs; p.futures = {}; p.stopped = False
    p.profiles = profiles or [dict(id='p1', name='Khánh Car Auto', session='s1', vision=dict(enabled=True, regions=dict(clock=[1, 1, 50, 20])),
                                   exePath='x', windowTitle='TikTok LIVE Studio', accountAnchor='a', interaction={})]
    sessions = sessions or {'s1': dict(id='s1', device='', mute=False, playlist=[CLIP])}
    p.alerts = []; p.alarms = []; p.played = []; p.submitted = []; p.enabled = []; p.logs = []
    p.owner = types.SimpleNamespace(log=lambda s: p.logs.append(s), notifier=types.SimpleNamespace(publish=lambda k, t: p.alerts.append(t), alarm=lambda k, t: (p.alarms.append((k, t)), True)[1]),
                                    bridge=Bridge(), command=lambda action, save, session: p.played.append((action, session['id'])),
                                    path=types.SimpleNamespace(parent=Path('/nonexistent')),
                                    studio_chat=types.SimpleNamespace(engine=types.SimpleNamespace(enable=lambda prof, kind, cfg: p.enabled.append(kind), stop=lambda pid, kind: None)))
    p.status = types.SimpleNamespace(setText=lambda s: None)
    p.poll_connection = lambda: None; p.save = lambda: None; p.render = lambda: None
    p.profile = lambda key: next((x for x in p.profiles if x['id'] == key), None)
    p.session = lambda prof: sessions[prof['session']]
    p.client = lambda prof: (sessions[prof['session']], 'client')
    p.effective_profile = lambda prof: prof
    p.submit = lambda j, action, payload=None: p.submitted.append((j['id'], action))
    p.reports = reports
    p.poll_hand_live = p.auto_connect = p.poll_studio_captcha = p.poll_chat_dock = lambda now: None   # watchers: tested on their own
    return p


def job(**kw):
    now = time.time()
    j = dict(id='j1', profile='p1', start=now+600, end=now+4200, clips=['/a.mp4'], bundle='', bundle_index=2, no_sales=False,
             shuffle=False, state='pending', error='', cart=dict(state='none', attempts=0, next=0, probe=dict(at=now, live=False), reloaded_at=now - 60))
    j.update(kw); return j
