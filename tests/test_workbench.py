# SPDX-License-Identifier: GPL-3.0-or-later
import http.client
import json
import socket
import threading
import unittest
from vigilcode.workbench import make_server

HELLO = 'work main() -> Int:\n    say("hi")\n    return 0\n'


class WorkbenchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = make_server(0)
        cls.port = cls.server.server_port
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

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
            head = f'POST /api/run HTTP/1.1\r\nHost: 127.0.0.1:{self.port}\r\nX-Vigil-Token: {self.server.token}\r\nContent-Length: {256 * 1024 + 1}\r\n\r\n'
            sock.sendall(head.encode())
            return int(sock.recv(64).split()[1])

    def api(self, path, **body):
        status, payload = self.request('POST', path, body)
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

    def test_runaway_program_is_stopped(self):
        source = 'work main() -> Int:\n    while true:\n        pass\n    return 0\n'
        result = self.api('/api/run', source=source)
        self.assertFalse(result['ok'])
        self.assertIn('Execution limit', result['stderr'])


if __name__ == '__main__':
    unittest.main()
