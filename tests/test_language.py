# SPDX-License-Identifier: GPL-3.0-or-later
import subprocess
import tempfile
from pathlib import Path
import random
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
        expected = {'hello': 'Peace be with you.\n', 'stewardship': 'All shares accounted for.\n', 'fibonacci': '55\n', 'ledger': 'Ana holds harvest\n7\nPlanting\n'}
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

    def test_recursion_is_bounded(self):
        source = 'work f(n: Int) -> Int:\n    return f(n + 1)\n\nwork main() -> Int:\n    say(f(0))\n    return 0\n'
        for optimize in (False, True):
            result = self.program(source, optimize=optimize)
            self.assertEqual(result.returncode, 1)
            self.assertIn('Call depth limit', result.stderr)
        # Depth returns to zero after calls complete, including Unit works that fall off the end.
        source = 'work ping() -> Unit:\n    pass\n\nwork main() -> Int:\n    for i in range(5000):\n        ping()\n    return 0\n'
        self.assertEqual(self.program(source).returncode, 0)

    def test_deep_but_allowed_recursion(self):
        source = 'work down(n: Int) -> Int:\n    discern n == 0:\n        return 0\n    return 1 + down(n - 1)\n\nwork main() -> Int:\n    say(down(1900))\n    return 0\n'
        self.assertEqual(self.program(source).stdout, '1900\n')

    def test_unicode_bom_and_line_endings(self):
        result = self.program('\ufeffwork main() -> Int:\r\n    say("caf\\u00e9 \\ud83d\\ude4f")\r\n    return 0\r\n')
        self.assertEqual(result.stdout, 'caf\u00e9 \U0001f64f\n')
        self.reject('work main() -> Int:\n    say("\\ud800")\n    return 0\n', 'valid UTF-8')

    def test_literal_and_syntax_errors(self):
        self.reject('work main() -> Int:\n    say(99999999999999999999)\n    return 0\n', 'too large')
        self.reject('work main() -> Int:\n    say(1e3)\n    return 0\n', "Expected '\\)'")
        self.reject('', 'entry point')

    def test_mutated_sources_only_raise_diagnostics(self):
        seeds = [path.read_text() for path in sorted(Path('examples').glob('*.vigil'))]
        alphabet = list(' \n():,->+*/%=<>"\\#\t0123456789abcwork vow let \u00e9.')
        rnd = random.Random(1)
        for _ in range(3000):
            text = list(rnd.choice(seeds))
            for _ in range(rnd.randint(1, 4)):
                position = rnd.randrange(len(text) + 1)
                if rnd.random() < 0.4 and text:
                    del text[min(position, len(text) - 1)]
                else:
                    text.insert(position, rnd.choice(alphabet))
            source = ''.join(text)
            try:
                compile_source(source)
            except Diagnostic:
                pass
            except Exception as error:
                self.fail(f'{type(error).__name__}: {error} for {source!r}')

    def test_records_are_immutable_and_typed(self):
        head = 'record Share:\n    owner: Text\n    amount: Int\n\nwork main() -> Int:\n'
        self.reject(head + '    vow s = Share("Ana", 5)\n    s.amount = 6\n    return 0\n', 'cannot change')
        self.reject(head + '    let s = Share("Ana", 5)\n    s = Share("Bo", 1)\n    s.owner = "x"\n    return 0\n', 'cannot change')
        self.reject(head + '    vow s = Share("Ana", "5")\n    return 0\n', 'Expected Int')
        self.reject(head + '    vow s = Share("Ana")\n    return 0\n', 'one for each field')
        self.reject(head + '    vow s = Share("Ana", 5)\n    say(s.missing)\n    return 0\n', 'no field')
        self.reject(head + '    vow s = Share("Ana", 5)\n    say(s)\n    return 0\n', 'Print a record field')
        self.reject(head + '    vow s = Share("Ana", 5)\n    say(s == s)\n    return 0\n', 'does not accept')
        self.reject(head + '    say(1.amount)\n    return 0\n', 'Only a record')

    def test_record_declarations(self):
        self.reject('record A:\n    x: B\n\nwork main() -> Int:\n    return 0\n', 'declare it before')
        self.reject('record A:\n    x: A\n\nwork main() -> Int:\n    return 0\n', 'declare it before')
        self.reject('record A:\n    x: Int\n    x: Int\n\nwork main() -> Int:\n    return 0\n', 'twice')
        self.reject('record A:\n\nwork main() -> Int:\n    return 0\n', 'Expected')
        self.reject('record Int:\n    x: Int\n\nwork main() -> Int:\n    return 0\n', 'already in use')
        self.reject('record A:\n    x: Int\n\nwork A() -> Int:\n    return 0\n\nwork main() -> Int:\n    return 0\n', 'already in use')

    def test_nested_records_and_covenants(self):
        source = ('record Point:\n    x: Int\n    y: Int\n\nrecord Line:\n    start: Point\n    end: Point\n\n'
                  'work width(line: Line) -> Int:\n    covenant line.end.x >= line.start.x, "The line must run rightwards."\n'
                  '    return line.end.x - line.start.x\n\n'
                  'work main() -> Int:\n    say(width(Line(Point(1, 2), Point(4, 9))))\n    say(width(Line(Point(4, 0), Point(1, 0))))\n    return 0\n')
        result = self.program(source, optimize=True)
        self.assertEqual(result.stdout, '3\n')
        self.assertIn('covenant not satisfied: The line must run rightwards.', result.stderr)

    def test_enums(self):
        head = 'enum Mode:\n    Open\n    Closed\n\nwork main() -> Int:\n'
        result = self.program(head + '    say(Mode.Open == Mode.Closed)\n    say(Mode.Closed != Mode.Open)\n    say(Mode.Closed)\n    return 0\n')
        self.assertEqual(result.stdout, 'false\ntrue\nClosed\n')
        self.reject(head + '    say(Mode.Ajar)\n    return 0\n', 'no variant')
        self.reject(head + '    say(Mode.Open < Mode.Closed)\n    return 0\n', 'does not accept')
        self.reject(head + '    say(Mode.Open == 0)\n    return 0\n', 'does not accept')
        self.reject('enum Mode:\n    Open\n    Open\n\nwork main() -> Int:\n    return 0\n', 'twice')
        self.reject(head + '    vow Mode = 1\n    return 0\n', 'reserved')

if __name__ == '__main__':
    unittest.main()
