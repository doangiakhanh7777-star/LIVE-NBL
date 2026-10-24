"""Local HTTP status API for NBL LIVE."""
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


class LocalAPI:
    def __init__(self, owner, host=None, port=None):
        self.owner = owner
        self.host = host or os.environ.get('NBL_LOCAL_API_HOST', '0.0.0.0')
        self.port = int(port or os.environ.get('NBL_LOCAL_API_PORT', '8766'))
        api = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                return

            def reply(self, status, data):
                body = json.dumps(data, ensure_ascii=False).encode('utf-8')
                self.send_response(status)
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                path = self.path.split('?', 1)[0].rstrip('/') or '/'
                if path == '/health':
                    return self.reply(200, {'ok': True, 'app': 'NBL LIVE', 'api': '1.0', 'port': api.port})
                if path == '/api/accounts':
                    panel = getattr(api.owner, 'studio_panel', None)
                    profiles = getattr(panel, 'profiles', []) if panel else []
                    rows = []
                    for session in api.owner.data.get('sessions', []):
                        profile = next((p for p in profiles if p.get('session') == session.get('id')), None)
                        rows.append({
                            'number': session.get('number'),
                            'session_id': session.get('id'),
                            'account': session.get('account') or ('Nick ' + str(session.get('number'))),
                            'studio_connected': bool(profile),
                            'profile_id': (profile or {}).get('id'),
                        })
                    return self.reply(200, {'ok': True, 'data': rows})
                if path == '/api/schedules':
                    panel = getattr(api.owner, 'studio_panel', None)
                    jobs = getattr(panel, 'jobs', []) if panel else []
                    return self.reply(200, {'ok': True, 'data': jobs})
                return self.reply(404, {'ok': False, 'error': 'Not found'})

        self.server = ThreadingHTTPServer((self.host, self.port), Handler)
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True, name='nbl-local-api')
        self.thread.start()
        owner.log('Local API: http://' + self.host + ':' + str(self.port))

    def close(self):
        try:
            self.server.shutdown()
            self.server.server_close()
        except Exception:
            pass
