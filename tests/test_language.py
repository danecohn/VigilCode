# SPDX-License-Identifier: GPL-3.0-or-later
import subprocess
import tempfile
from pathlib import Path
import unittest
from vigilcode.cli import build
from vigilcode.compiler import compile_source
from vigilcode.frontend import Diagnostic

class LanguageTests(unittest.TestCase):
    def program(self, source, optimize=False, args=()):
        with tempfile.TemporaryDirectory() as folder:
            binary = build(source, Path(folder)/'program', optimize=optimize)
            return subprocess.run([str(binary), *args], capture_output=True, text=True, timeout=5)

    def reject(self, source, message):
        with self.assertRaisesRegex(Diagnostic, message):
            compile_source(source)

    def test_examples_native(self):
        expected = {'hello': 'Peace be with you.\n', 'stewardship': 'All shares accounted for.\n', 'fibonacci': '55\n'}
        for name, output in expected.items():
            with self.subTest(name=name):
                result = self.program(Path('examples/'+name+'.vigil').read_text())
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout, output)

    def test_vow_is_immutable(self):
        self.reject('work main() -> Int:\n    vow x = 1\n    x = 2\n    return 0\n', 'cannot change')

    def test_types_are_checked(self):
        self.reject('work main() -> Int:\n    vow x: Int = "text"\n    return 0\n', 'Expected Int')
        self.reject('work main() -> Int:\n    discern 1:\n        return 0\n    otherwise:\n        return 1\n', 'Expected Bool')

    def test_contract_precedes_effects(self):
        source = 'work main() -> Int:\n    covenant false, "Not ready."\n    say("must not run")\n    return 0\n'
        result = self.program(source, optimize=True)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, '')
        self.assertIn('covenant not satisfied: Not ready.', result.stderr)
        self.reject('work main() -> Int:\n    say("hello")\n    covenant true\n    return 0\n', 'beginning')
        self.reject('work main() -> Int:\n    covenant arg_count() == 0\n    return 0\n', 'pure')

    def test_witness_survives_optimization(self):
        result = self.program('work main() -> Int:\n    witness false, "Proof missing."\n    return 0\n', optimize=True)
        self.assertEqual(result.returncode, 1)
        self.assertIn('witness not satisfied', result.stderr)

    def test_short_circuit(self):
        source = 'work main() -> Int:\n    say(false and (1 // 0 == 1))\n    say(true or (1 // 0 == 1))\n    return 0\n'
        result = self.program(source)
        self.assertEqual(result.stdout, 'false\ntrue\n')
        self.assertEqual(result.returncode, 0)

    def test_numeric_limits(self):
        for expression in ['9223372036854775807 + 1', '-9223372036854775808 - 1', '-(-9223372036854775808)', '-9223372036854775808 // -1', '9223372036854775807 * 2', '1 / 0']:
            with self.subTest(expression=expression):
                result = self.program('work main() -> Int:\n    say('+expression+')\n    return 0\n', optimize=True)
                self.assertEqual(result.returncode, 1)
                self.assertIn('VigilCode:', result.stderr)

    def test_floor_arithmetic(self):
        result = self.program('work main() -> Int:\n    say(-7 // 3)\n    say(-7 % 3)\n    say(7 % -3)\n    return 0\n')
        self.assertEqual(result.stdout, '-3\n2\n-2\n')

    def test_argument_order(self):
        source = 'work report(n: Int) -> Int:\n    say(n)\n    return n\n\nwork sum(a: Int, b: Int) -> Int:\n    return a + b\n\nwork main() -> Int:\n    say(sum(report(1), report(2)))\n    return 0\n'
        self.assertEqual(self.program(source, optimize=True).stdout, '1\n2\n3\n')

    def test_text_and_arguments(self):
        source = 'work main() -> Int:\n    say("Ave, " + arg(0))\n    say(length("abc"))\n    say(arg_count())\n    return 0\n'
        result = self.program(source, args=['Maria'])
        self.assertEqual(result.stdout, 'Ave, Maria\n3\n1\n')
        self.assertEqual(result.returncode, 0)
        self.assertIn('out of range', self.program(source).stderr)

    def test_no_missing_return_or_scope_leak(self):
        self.reject('work main() -> Int:\n    pass\n', 'every path')
        self.reject('work main() -> Int:\n    discern true:\n        vow x = 1\n    say(x)\n    return 0\n', 'not been declared')

    def test_bad_indentation_and_text(self):
        self.reject('work main() -> Int:\n\treturn 0\n', 'tabs')
        self.reject('work main() -> Int:\n    say("\\u0000")\n    return 0\n', 'NUL')

if __name__ == '__main__':
    unittest.main()
