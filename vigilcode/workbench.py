# SPDX-License-Identifier: GPL-3.0-or-later
"""Local editor workbench: a small HTTP server on the loopback interface.

It reads and writes .vigil files inside one project folder and compiles and runs the code
it is sent, so every API call must carry the per-session token and a loopback Host header.
It is meant for one person on their own machine.
"""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import secrets
import subprocess
import tempfile
import threading
from . import __version__
from .cli import build
from .compiler import compile_source
from .frontend import Diagnostic

MAX_BODY = 1024 * 1024
MAX_OUTPUT = 64 * 1024
MAX_FILES = 1000
RUN_SECONDS = 10
# The workbench runs code as you type it, so it keeps tighter limits than vigil build.
LIMITS = {'steps': 100_000_000, 'output': 1024 * 1024, 'memory': 256 * 1024 * 1024}
HERE = Path(__file__).parent
PAGE = HERE / 'workbench.html'
FONTS = {name: HERE / 'fonts' / name for name in ('VigilSans-Regular.woff2', 'VigilSans-Bold.woff2')}
SKIP = {'.git', 'node_modules', '.venv', '__pycache__', 'build', 'dist'}


class Refused(Exception):
    pass


class Project:
    """The folder the workbench may read and write. Only .vigil files inside it are reachable."""

    def __init__(self, root):
        self.root = Path(root).resolve()

    def path(self, relative):
        if not isinstance(relative, str) or not relative or '\0' in relative or len(relative) > 400:
            raise Refused('Give a file path inside the project.')
        candidate = (self.root / relative).resolve()
        if candidate != self.root and self.root not in candidate.parents:
            raise Refused('That path is outside the project folder.')
        if candidate.suffix != '.vigil':
            raise Refused('Only .vigil files can be opened or saved here.')
        return candidate

    def files(self):
        found = []
        for folder, dirs, names in os.walk(self.root):
            dirs[:] = sorted(d for d in dirs if d not in SKIP and not d.startswith('.'))
            for name in sorted(names):
                path = Path(folder, name)
                # Leave out links that point outside the project.
                if name.endswith('.vigil') and self.root in path.resolve().parents:
                    found.append(path.relative_to(self.root).as_posix())
                if len(found) >= MAX_FILES:
                    return found
        return found

    def read(self, relative):
        path = self.path(relative)
        try:
            return path.read_text(encoding='utf-8')
        except FileNotFoundError:
            raise Refused('That file does not exist.')
        except (OSError, UnicodeError) as error:
            raise Refused(f'Could not read the file: {getattr(error, "strerror", None) or "not UTF-8 text"}.')

    def write(self, relative, source, create=False):
        path = self.path(relative)
        if create and path.exists():
            raise Refused('A file with that name already exists.')
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            # Write beside the file, then replace it, so a failed save never leaves half a file.
            temporary = path.with_name(f'.{path.name}.saving')
            with open(temporary, 'w', encoding='utf-8', newline='\n') as handle:
                handle.write(source)
            os.replace(temporary, path)
        except OSError as error:
            raise Refused(f'Could not save the file: {error.strerror}.')


def diagnostics_for(error, relative_root=None):
    token = error.token
    file = error.file
    if file and relative_root:
        try:
            file = Path(file).resolve().relative_to(relative_root).as_posix()
        except ValueError:
            pass
    return [{'line': token.line if token else None, 'column': token.column if token else None, 'message': error.message, 'file': file}]


def check(source, project=None, relative=None):
    filename, base = 'workbench', None
    if project and relative:
        path = project.path(relative)
        filename, base = str(path), path.parent
    try:
        compile_source(source, filename, base)
    except Diagnostic as error:
        return {'ok': False, 'diagnostics': diagnostics_for(error, project.root if project else None)}
    return {'ok': True, 'diagnostics': []}


def run(source, args=(), optimize=False, project=None, relative=None):
    """Build and run. Programs run in the project folder, so relative paths start there."""
    result = check(source, project, relative)
    if not result['ok']:
        return result
    filename, base = 'workbench', None
    if project and relative:
        path = project.path(relative)
        filename, base = relative, path.parent
    with tempfile.TemporaryDirectory(prefix='vigil-workbench-') as folder:
        try:
            binary = build(source, Path(folder) / 'program', filename=filename, optimize=optimize, base=base, limits=LIMITS)
        except (RuntimeError, subprocess.TimeoutExpired) as error:
            return {'ok': False, 'diagnostics': [{'line': None, 'column': None, 'message': str(error), 'file': None}]}
        try:
            done = subprocess.run([str(binary), *args], capture_output=True, timeout=RUN_SECONDS, stdin=subprocess.DEVNULL,
                                  cwd=str(project.root) if project else folder)
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

    def reply(self, status, body, kind='application/json', cache=False):
        data = body if isinstance(body, bytes) else json.dumps(body).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', kind + ('; charset=utf-8' if not kind.startswith('font/') else ''))
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'max-age=86400' if cache else 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Content-Security-Policy', "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; font-src 'self'; connect-src 'self'; img-src 'self' data:; base-uri 'none'; form-action 'none'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(data)

    def allowed_host(self):
        return self.headers.get('Host', '') in {f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}'}

    def do_GET(self):
        if not self.allowed_host():
            return self.reply(403, {'error': 'Unexpected Host header.'})
        if self.path.startswith('/fonts/') and self.path[7:] in FONTS:
            return self.reply(200, FONTS[self.path[7:]].read_bytes(), 'font/woff2', cache=True)
        if self.path != '/':
            return self.reply(404, {'error': 'Not found.'})
        page = PAGE.read_text(encoding='utf-8').replace('__TOKEN__', self.server.token).replace('__VERSION__', __version__)
        self.reply(200, page.encode('utf-8'), 'text/html')

    def do_POST(self):
        if not self.allowed_host():
            return self.reply(403, {'error': 'Unexpected Host header.'})
        routes = {'/api/check', '/api/run', '/api/files', '/api/open', '/api/save', '/api/new'}
        if self.path not in routes:
            return self.reply(404, {'error': 'Not found.'})
        if not secrets.compare_digest(self.headers.get('X-Vigil-Token', ''), self.server.token):
            return self.reply(403, {'error': 'Missing or wrong session token.'})
        try:
            length = int(self.headers.get('Content-Length', ''))
        except ValueError:
            return self.reply(411, {'error': 'Content-Length is required.'})
        if not 0 <= length <= MAX_BODY:
            self.close_connection = True
            return self.reply(413, {'error': 'Request is too large.'})
        try:
            body = json.loads(self.rfile.read(length) or b'{}')
            if not isinstance(body, dict):
                raise ValueError
            source, args, path = body.get('source', ''), body.get('args', []), body.get('path')
            if not isinstance(source, str) or not isinstance(args, list) or len(args) > 20 or not all(isinstance(a, str) and '\0' not in a for a in args):
                raise ValueError
            if path is not None and not isinstance(path, str):
                raise ValueError
        except (ValueError, TypeError):
            return self.reply(400, {'error': 'Send JSON like {"source": "..."}.'})
        project = self.server.project
        try:
            if path is not None and project is None:
                raise Refused('The workbench was started without a project folder.')
            if self.path == '/api/files':
                return self.reply(200, {'root': str(project.root) if project else None, 'files': project.files() if project else []})
            if self.path == '/api/open':
                return self.reply(200, {'path': path, 'source': project.read(path)})
            if self.path in ('/api/save', '/api/new'):
                project.write(path, source, create=self.path == '/api/new')
                return self.reply(200, {'path': path, 'saved': True})
            if self.path == '/api/check':
                return self.reply(200, check(source, project, path))
            with self.server.run_lock:
                return self.reply(200, run(source, args, bool(body.get('optimize')), project, path))
        except Refused as refusal:
            return self.reply(400, {'error': str(refusal)})
        except Exception as error:  # Report instead of dropping the connection.
            return self.reply(500, {'error': f'The workbench hit an internal error: {type(error).__name__}: {error}'})


def make_server(port=0, root=None):
    server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    server.token = secrets.token_urlsafe(24)
    server.run_lock = threading.Lock()
    server.project = Project(root) if root else None
    return server


def serve(port=8765, open_browser=True, root=None):
    root = Path(root or Path.cwd()).resolve()
    if not root.is_dir():
        raise RuntimeError(f'{root} is not a folder.')
    server = make_server(port, root)
    url = f'http://127.0.0.1:{server.server_port}/'
    print(f'VigilCode workbench at {url} for {root}  (Ctrl+C to stop)')
    if open_browser:
        import webbrowser
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print()
    finally:
        server.server_close()
