# SPDX-License-Identifier: GPL-3.0-or-later
import http.client
import json
import shutil
import socket
import tempfile
from pathlib import Path
import threading
import unittest
from vigilcode.workbench import MAX_BODY, make_server

HELLO = 'work main() -> Int:\n    say("hi")\n    return 0\n'


class WorkbenchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.mkdtemp()
        Path(cls.folder, 'lib').mkdir()
        Path(cls.folder, 'lib', 'greet.vigil').write_text('work greeting() -> Text:\n    return "Pax"\n', encoding='utf-8')
        Path(cls.folder, 'lib', 'main.vigil').write_text('use greet\nwork main() -> Int:\n    say(greeting())\n    return 0\n', encoding='utf-8')
        Path(cls.folder, 'notes.txt').write_text('not code', encoding='utf-8')
        cls.server = make_server(0, cls.folder)
        cls.port = cls.server.server_port
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        shutil.rmtree(cls.folder, ignore_errors=True)

    def request(self, method, path, body=None, token=True, host=None, raw=None):
        connection = http.client.HTTPConnection('127.0.0.1', self.port, timeout=30)
        headers = {'Host': host or f'127.0.0.1:{self.port}'}
        if token:
            headers['X-Vigil-Token'] = self.server.token
        data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
        connection.request(method, path, data, headers)
        response = connection.getresponse()
        payload = response.read()
        connection.close()
        return response.status, payload

    def oversized_status(self):
        # Only the declared length matters; the server must refuse before reading any body.
        with socket.create_connection(('127.0.0.1', self.port), timeout=10) as sock:
            head = f'POST /api/run HTTP/1.1\r\nHost: 127.0.0.1:{self.port}\r\nX-Vigil-Token: {self.server.token}\r\nContent-Length: {MAX_BODY + 1}\r\n\r\n'
            sock.sendall(head.encode())
            return int(sock.recv(64).split()[1])

    def api(self, route, **body):
        status, payload = self.request('POST', route, body)
        self.assertEqual(status, 200, payload)
        return json.loads(payload)

    def test_page_carries_token_and_security_headers(self):
        status, page = self.request('GET', '/')
        self.assertEqual(status, 200)
        self.assertIn(self.server.token.encode(), page)
        self.assertNotIn(b'__TOKEN__', page)

    def test_check_reports_location(self):
        result = self.api('/api/check', source='work main() -> Int:\n    say(x)\n    return 0\n')
        self.assertFalse(result['ok'])
        self.assertEqual((result['diagnostics'][0]['line'], result['diagnostics'][0]['column']), (2, 9))
        self.assertTrue(self.api('/api/check', source=HELLO)['ok'])

    def test_run_returns_output_and_failures(self):
        result = self.api('/api/run', source=HELLO)
        self.assertEqual((result['ok'], result['stdout'], result['exit']), (True, 'hi\n', 0))
        result = self.api('/api/run', source='work main() -> Int:\n    witness false, "No."\n    return 0\n')
        self.assertFalse(result['ok'])
        self.assertIn('witness not satisfied: No.', result['stderr'])
        result = self.api('/api/run', source='work main() -> Int:\n    say(arg(0))\n    return 0\n', args=['Maria'])
        self.assertEqual(result['stdout'], 'Maria\n')

    def test_run_compile_error_does_not_execute(self):
        result = self.api('/api/run', source='work main() -> Int:\n    return "no"\n')
        self.assertFalse(result['ok'])
        self.assertTrue(result['diagnostics'])
        self.assertNotIn('stdout', result)

    def test_rejects_missing_token_foreign_host_and_bad_bodies(self):
        self.assertEqual(self.request('POST', '/api/run', {'source': HELLO}, token=False)[0], 403)
        self.assertEqual(self.request('POST', '/api/run', {'source': HELLO}, host='evil.example:80')[0], 403)
        self.assertEqual(self.request('GET', '/', host='evil.example')[0], 403)
        self.assertEqual(self.request('POST', '/api/run', raw=b'not json')[0], 400)
        self.assertEqual(self.request('POST', '/api/run', {'source': 5})[0], 400)
        self.assertEqual(self.request('POST', '/api/run', {'source': 'x', 'args': [1]})[0], 400)
        self.assertEqual(self.oversized_status(), 413)
        self.assertEqual(self.request('POST', '/api/other', {'source': HELLO})[0], 404)
        self.assertEqual(self.request('GET', '/api/run')[0], 404)

    def test_project_files(self):
        listing = self.api('/api/files')
        self.assertLessEqual({'lib/greet.vigil', 'lib/main.vigil'}, set(listing['files']))
        self.assertNotIn('notes.txt', listing['files'])
        source = self.api('/api/open', path='lib/main.vigil')['source']
        # Running a project file resolves its modules beside it.
        self.assertEqual(self.api('/api/run', source=source, path='lib/main.vigil')['stdout'], 'Pax\n')
        self.api('/api/new', path='fresh.vigil', source=HELLO)
        self.assertEqual(self.api('/api/open', path='fresh.vigil')['source'], HELLO)
        self.api('/api/save', path='fresh.vigil', source=HELLO + '# saved\n')
        self.assertTrue(Path(self.folder, 'fresh.vigil').read_text(encoding='utf-8').endswith('# saved\n'))
        self.assertEqual(self.request('POST', '/api/new', {'path': 'fresh.vigil', 'source': ''})[0], 400)
        reader = 'work main() -> Int:\n    match read_file("notes.txt"):\n        ok t:\n            say(t)\n        fail m:\n            say(m)\n    return 0\n'
        self.assertEqual(self.api('/api/run', source=reader, path='lib/reader.vigil')['stdout'], 'not code\n')

    def test_module_errors_name_their_file(self):
        Path(self.folder, 'lib', 'broken.vigil').write_text('work broken() -> Int:\n    return "no"\n', encoding='utf-8')
        result = self.api('/api/check', source='use broken\nwork main() -> Int:\n    return 0\n', path='lib/probe.vigil')
        self.assertEqual(result['diagnostics'][0]['file'], 'lib/broken.vigil')
        self.assertEqual(result['diagnostics'][0]['line'], 2)

    def test_files_stay_inside_the_project(self):
        for path in ('../escape.vigil', '/etc/passwd', 'notes.txt', 'lib', '', 'a\u0000.vigil'):
            with self.subTest(path=path):
                status, _ = self.request('POST', '/api/open', {'path': path})
                self.assertEqual(status, 400)
                status, _ = self.request('POST', '/api/save', {'path': path, 'source': 'x'})
                self.assertEqual(status, 400)
        self.assertFalse(Path(self.folder).parent.joinpath('escape.vigil').exists())
        try:
            Path(self.folder, 'link.vigil').symlink_to(Path(tempfile.gettempdir(), 'outside.vigil'))
        except (OSError, NotImplementedError):
            return
        self.assertEqual(self.request('POST', '/api/save', {'path': 'link.vigil', 'source': 'x'})[0], 400)
        self.assertNotIn('link.vigil', self.api('/api/files')['files'])

    def test_fonts_are_served(self):
        status, data = self.request('GET', '/fonts/VigilSans-Regular.woff2')
        self.assertEqual(status, 200)
        self.assertEqual(data[:4], b'wOF2')
        self.assertEqual(self.request('GET', '/fonts/../workbench.py')[0], 404)

    def test_runaway_program_is_stopped(self):
        source = 'work main() -> Int:\n    while true:\n        pass\n    return 0\n'
        result = self.api('/api/run', source=source)
        self.assertFalse(result['ok'])
        self.assertIn('Execution limit', result['stderr'])


if __name__ == '__main__':
    unittest.main()
