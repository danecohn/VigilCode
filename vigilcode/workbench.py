# SPDX-License-Identifier: GPL-3.0-or-later
"""Local editor workbench: a small HTTP server on the loopback interface.

It compiles and runs the code it is sent, so every API call must carry the per-session
token and a loopback Host header. It is meant for one person on their own machine.
"""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import secrets
import subprocess
import tempfile
import threading
from .cli import build
from .compiler import compile_source
from .frontend import Diagnostic

MAX_BODY = 256 * 1024
MAX_OUTPUT = 64 * 1024
RUN_SECONDS = 10
PAGE = Path(__file__).with_name('workbench.html')


def diagnostics_for(error):
    token = error.token
    return [{'line': token.line if token else None, 'column': token.column if token else None, 'message': error.message}]


def check(source):
    try:
        compile_source(source, 'workbench')
    except Diagnostic as error:
        return {'ok': False, 'diagnostics': diagnostics_for(error)}
    return {'ok': True, 'diagnostics': []}


def run(source, args=(), optimize=False):
    result = check(source)
    if not result['ok']:
        return result
    with tempfile.TemporaryDirectory(prefix='vigil-workbench-') as folder:
        try:
            binary = build(source, Path(folder) / 'program', filename='workbench', optimize=optimize)
        except (RuntimeError, subprocess.TimeoutExpired) as error:
            return {'ok': False, 'diagnostics': [{'line': None, 'column': None, 'message': str(error)}]}
        try:
            done = subprocess.run([str(binary), *args], capture_output=True, timeout=RUN_SECONDS)
            exit_code, note = done.returncode, ''
            stdout, stderr = done.stdout, done.stderr
        except subprocess.TimeoutExpired as expired:
            exit_code, note = None, f'Stopped after {RUN_SECONDS} seconds.'
            stdout, stderr = expired.stdout or b'', expired.stderr or b''
    clip = lambda data: data[:MAX_OUTPUT].decode('utf-8', 'replace') + ('\n[output cut]' if len(data) > MAX_OUTPUT else '')
    return {'ok': exit_code == 0, 'diagnostics': [], 'stdout': clip(stdout), 'stderr': clip(stderr) + note, 'exit': exit_code}


class Handler(BaseHTTPRequestHandler):
    server_version = 'VigilCodeWorkbench'

    def log_message(self, *args):
        pass

    def reply(self, status, body, kind='application/json'):
        data = body if isinstance(body, bytes) else json.dumps(body).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', kind + '; charset=utf-8')
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Security-Policy', "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; base-uri 'none'; form-action 'none'")
        self.end_headers()
        self.wfile.write(data)

    def allowed_host(self):
        return self.headers.get('Host', '') in {f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}'}

    def do_GET(self):
        if not self.allowed_host():
            return self.reply(403, {'error': 'Unexpected Host header.'})
        if self.path != '/':
            return self.reply(404, {'error': 'Not found.'})
        page = PAGE.read_text(encoding='utf-8').replace('__TOKEN__', self.server.token)
        self.reply(200, page.encode('utf-8'), 'text/html')

    def do_POST(self):
        if not self.allowed_host():
            return self.reply(403, {'error': 'Unexpected Host header.'})
        if self.path not in ('/api/check', '/api/run'):
            return self.reply(404, {'error': 'Not found.'})
        if not secrets.compare_digest(self.headers.get('X-Vigil-Token', ''), self.server.token):
            return self.reply(403, {'error': 'Missing or wrong session token.'})
        try:
            length = int(self.headers.get('Content-Length', ''))
        except ValueError:
            return self.reply(411, {'error': 'Content-Length is required.'})
        if not 0 <= length <= MAX_BODY:
            self.close_connection = True
            return self.reply(413, {'error': 'Source is too large.'})
        try:
            body = json.loads(self.rfile.read(length))
            source, args = body['source'], body.get('args', [])
            if not isinstance(source, str) or not isinstance(args, list) or not all(isinstance(a, str) and '\0' not in a for a in args[:20]) or len(args) > 20:
                raise ValueError
        except (ValueError, KeyError, TypeError):
            return self.reply(400, {'error': 'Send JSON like {"source": "..."}.'})
        if self.path == '/api/check':
            return self.reply(200, check(source))
        with self.server.run_lock:
            self.reply(200, run(source, args, bool(body.get('optimize'))))


def make_server(port=0):
    server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    server.token = secrets.token_urlsafe(24)
    server.run_lock = threading.Lock()
    return server


def serve(port=8765, open_browser=True):
    server = make_server(port)
    url = f'http://127.0.0.1:{server.server_port}/'
    print(f'VigilCode workbench at {url}  (Ctrl+C to stop)')
    if open_browser:
        import webbrowser
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print()
    finally:
        server.server_close()
