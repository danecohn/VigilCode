# SPDX-License-Identifier: GPL-3.0-or-later
"""Lists, Option/Result and match, text and conversion built-ins, files, modules, and limits."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from vigilcode.cli import build
from vigilcode.compiler import compile_source
from vigilcode.frontend import Diagnostic

ROOT = Path(__file__).resolve().parent.parent


def main(body, head=''):
    return head + 'work main() -> Int:\n' + ''.join('    ' + line + '\n' for line in body.strip('\n').split('\n'))


class FeatureTests(unittest.TestCase):
    def program(self, source, args=(), stdin=None, limits=None, base=None, optimize=False):
        with tempfile.TemporaryDirectory() as folder:
            binary = build(source, Path(folder) / 'program', limits=limits, base=base, optimize=optimize)
            return subprocess.run([str(binary), *args], input=stdin, capture_output=True, encoding='utf-8', timeout=20)

    def output(self, source, **options):
        result = self.program(source, **options)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

    def reject(self, source, message):
        with self.assertRaisesRegex(Diagnostic, message):
            compile_source(source)

    # Lists ---------------------------------------------------------------

    def test_list_basics(self):
        out = self.output(main('''
vow xs = [10, 20, 30]
say(length(xs))
say(xs[0] + xs[2])
let total = 0
for x in xs:
    total = total + x
say(total)
vow empty: List[Text] = []
say(length(empty))
return 0'''))
        self.assertEqual(out, '3\n40\n60\n0\n')

    def test_lists_are_immutable_values(self):
        # push and set return new lists; the originals never change, even when storage is shared.
        out = self.output(main('''
vow a = [1]
vow b = push(a, 2)
vow c = push(a, 3)
vow d = set(b, 0, 9)
say(length(a))
say(b[1])
say(c[1])
say(b[0])
say(d[0])
return 0'''))
        self.assertEqual(out, '1\n2\n3\n1\n9\n')

    def test_push_is_amortized(self):
        # 200,000 appends would be about 20 billion copies if each push copied the list.
        out = self.output(main('''
let xs: List[Int] = []
for i in range(200000):
    xs = push(xs, i)
say(xs[199999])
return 0'''), optimize=True)
        self.assertEqual(out, '199999\n')

    def test_list_errors(self):
        result = self.program(main('vow xs = [1, 2]\nsay(xs[2])\nreturn 0'))
        self.assertEqual(result.returncode, 1)
        self.assertIn('List index is out of range', result.stderr)
        self.assertIn('out of range', self.program(main('vow xs = [1]\nvow ys = set(xs, -1, 0)\nreturn 0')).stderr)
        self.reject(main('vow xs = []\nreturn 0'), 'empty list needs a known type')
        self.reject(main('vow xs = [1, "two"]\nreturn 0'), 'Expected Int')
        self.reject(main('vow xs = [1]\nxs[0] = 2\nreturn 0'), 'cannot change in place')
        self.reject(main('vow xs = [1]\nvow ys = push(xs, "a")\nreturn 0'), 'Expected Int')
        self.reject(main('say(5[0])\nreturn 0'), 'Only a List')
        self.reject(main('for x in 5:\n    pass\nreturn 0'), 'for can walk')
        self.reject(main('vow xs: List = [1]\nreturn 0'), 'needs an item type')
        self.reject(main('vow xs: Map[Int] = [1]\nreturn 0'), 'not a type')

    def test_nested_and_record_lists(self):
        head = 'record Person:\n    name: Text\n    tags: List[Text]\n\n'
        out = self.output(main('''
vow people = [Person("Ana", ["a", "b"]), Person("Bo", [])]
for p in people:
    say(p.name + " " + to_text(length(p.tags)))
vow grid = [[1, 2], [3, 4]]
say(grid[1][0])
return 0''', head))
        self.assertEqual(out, 'Ana 2\nBo 0\n3\n')

    # Option, Result, match ------------------------------------------------

    def test_option_and_match(self):
        source = main('''
for t in ["42", "-7", "x", "", "9223372036854775807", "9223372036854775808", "-9223372036854775808"]:
    match parse_int(t):
        some n:
            say(n)
        none:
            say("not a number")
return 0''')
        self.assertEqual(self.output(source), '42\n-7\nnot a number\nnot a number\n9223372036854775807\nnot a number\n-9223372036854775808\n')

    def test_user_results(self):
        head = 'work half(n: Int) -> Result[Int]:\n    discern n % 2 != 0:\n        return fail("odd")\n    return ok(n // 2)\n\n'
        source = main('''
for n in [4, 5]:
    match half(n):
        ok value:
            say(value)
        fail message:
            say(message)
vow maybe: Option[Text] = none
match maybe:
    some t:
        say(t)
    none:
        say("empty")
return 0''', head)
        self.assertEqual(self.output(source), '2\nodd\nempty\n')

    def test_match_on_enum_is_exhaustive(self):
        head = 'enum Light:\n    Red\n    Amber\n    Green\n\nwork next(l: Light) -> Light:\n    match l:\n        Light.Red:\n            return Light.Green\n        Light.Green:\n            return Light.Amber\n        Light.Amber:\n            return Light.Red\n\n'
        self.assertEqual(self.output(main('say(next(Light.Red))\nsay(next(Light.Amber))\nreturn 0', head)), 'Green\nRed\n')
        enum = 'enum Light:\n    Red\n    Amber\n    Green\n\n'
        self.reject(main('match Light.Red:\n    Light.Red:\n        pass\nreturn 0', enum), 'does not handle: Amber, Green')
        self.reject(main('match Light.Red:\n    Light.Red:\n        pass\n    Light.Red:\n        pass\n    otherwise:\n        pass\nreturn 0', enum), 'appears twice')
        self.reject(main('match Light.Red:\n    Light.Red:\n        pass\n    Light.Amber:\n        pass\n    Light.Green:\n        pass\n    otherwise:\n        pass\nreturn 0', enum), 'already covered')
        self.reject(main('match Light.Red:\n    Light.Blue:\n        pass\n    otherwise:\n        pass\nreturn 0', enum), 'not a case')
        self.reject(main('match Light.Red:\n    Red:\n        pass\n    otherwise:\n        pass\nreturn 0', enum), 'Light.Variant')
        self.assertEqual(self.output(main('match Light.Amber:\n    Light.Red:\n        say("stop")\n    otherwise:\n        say("go on")\nreturn 0', enum)), 'go on\n')

    def test_match_errors(self):
        self.reject(main('match parse_int("1"):\n    some:\n        pass\n    none:\n        pass\nreturn 0'), 'Name the value')
        self.reject(main('match parse_int("1"):\n    some n:\n        pass\n    none x:\n        pass\nreturn 0'), 'carries no value')
        self.reject(main('match 3:\n    otherwise:\n        pass\nreturn 0'), 'match works on')
        self.reject(main('match parse_int("1"):\n    some n:\n        pass\nreturn 0'), 'does not handle: none')
        self.reject(main('match parse_int("1"):\n    otherwise:\n        pass\n    some n:\n        pass\nreturn 0'), 'last case')
        self.reject(main('vow x = none\nreturn 0'), 'none needs a known Option')
        self.reject(main('vow r = fail("x")\nreturn 0'), 'fail needs a known Result')
        # A match where every case returns counts as returning.
        self.output('work f(x: Option[Int]) -> Int:\n    match x:\n        some n:\n            return n\n        none:\n            return 0\n\n' + main('say(f(some(3)))\nreturn 0'))
        self.reject('work f(x: Option[Int]) -> Int:\n    match x:\n        some n:\n            return n\n        none:\n            pass\n\n' + main('return 0'), 'every path')

    # Text and conversions ---------------------------------------------------

    def test_text_builtins(self):
        out = self.output(main('''
say(slice("Benedictus", 0, 4))
say(find("ora et labora", "labora"))
say(find("abc", "z"))
say("[" + trim("  pax \\n") + "]")
vow parts = split("a,b,,c", ",")
say(length(parts))
say(join(parts, "+"))
say(to_text(3) + to_text(true) + to_text(0.5))
say(to_int(-2.9))
say(to_real(3) / 2)
match parse_real("2.5e1"):
    some r:
        say(r)
    none:
        say("bad")
return 0'''))
        self.assertEqual(out, 'Bene\n7\n-1\n[pax]\n4\na+b++c\n3true0.5\n-2\n1.5\n25\n')

    def test_text_errors(self):
        self.assertIn('split a UTF-8 character', self.program(main('say(slice("\\u00e9", 0, 1))\nreturn 0')).stderr)
        self.assertIn('Slice is out of range', self.program(main('say(slice("abc", 2, 9))\nreturn 0')).stderr)
        self.assertIn('non-empty separator', self.program(main('vow x = split("abc", "")\nreturn 0')).stderr)
        self.assertIn('does not fit in Int', self.program(main('say(to_int(100000000000000000000.0))\nreturn 0')).stderr)
        for bad in ('" 1"', '"1x"', '"inf"', '"nan"', '"1e999"', '""'):
            self.assertEqual(self.output(main(f'match parse_real({bad}):\n    some r:\n        say(r)\n    none:\n        say("none")\nreturn 0')), 'none\n', bad)

    # Input and files ----------------------------------------------------------

    def test_read_line(self):
        source = main('let n = 0\nwhile true:\n    match read_line():\n        some line:\n            n = n + length(line)\n        none:\n            say(n)\n            return 0\nreturn 0')
        self.assertEqual(self.output(source, stdin='ab\r\ncd\n\nefg'), '7\n')

    def test_files(self):
        with tempfile.TemporaryDirectory() as folder:
            path = str(Path(folder) / 'note.txt').replace('\\', '/')
            source = main(f'''
match write_file("{path}", "Laudate\\n"):
    ok n:
        say(n)
    fail message:
        say(message)
match read_file("{path}"):
    ok text:
        say(trim(text))
    fail message:
        say(message)
match read_file("{path}.missing"):
    ok text:
        say(text)
    fail message:
        say(slice(message, 0, 19))
return 0''')
            self.assertEqual(self.output(source), '8\nLaudate\nCould not open file\n')
            Path(folder, 'bin.dat').write_bytes(b'a\0b')
            Path(folder, 'latin.txt').write_bytes(b'caf\xe9')
            for name, message in (('bin.dat', 'NUL'), ('latin.txt', 'UTF-8')):
                probe = main(f'match read_file("{folder}/{name}"):\n    ok text:\n        say(text)\n    fail message:\n        say(message)\nreturn 0'.replace('\\', '/'))
                self.assertIn(message, self.output(probe))

    def test_io_is_not_pure(self):
        self.reject('work f(p: Text) -> Int:\n    covenant length(p) > 0\n    covenant read_file(p) == read_file(p)\n    return 0\n\n' + main('return 0'), 'pure')
        self.output('work f(p: Text) -> Int:\n    covenant find(p, "/") >= 0, "Needs a slash."\n    return 0\n\n' + main('say(f("a/b"))\nreturn 0'))

    def test_results_must_be_used(self):
        self.reject(main('write_file("x", "y")\nreturn 0'), 'Bind or return')

    # Modules ----------------------------------------------------------------

    def test_modules(self):
        out = self.program((ROOT / 'examples/tally/main.vigil').read_text(encoding='utf-8'), base=ROOT / 'examples/tally',
                           args=[str(ROOT / 'examples/tally/words.vigil')])
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn('words', out.stdout)
        with self.assertRaisesRegex(Diagnostic, 'file on disk'):
            compile_source('use words\n' + main('return 0'))
        with tempfile.TemporaryDirectory() as folder:
            Path(folder, 'a.vigil').write_text('use b\nwork twice(n: Int) -> Int:\n    return n * 2\n', encoding='utf-8')
            Path(folder, 'b.vigil').write_text('use a\nwork thrice(n: Int) -> Int:\n    return n * 3\n', encoding='utf-8')
            Path(folder, 'bad.vigil').write_text('work broken() -> Int:\n    return "x"\n', encoding='utf-8')
            # Cycles are fine: each file is read once.
            self.assertEqual(self.output('use a\n' + main('say(twice(thrice(1)))\nreturn 0'), base=folder), '6\n')
            with self.assertRaises(Diagnostic) as caught:
                compile_source('use bad\n' + main('return 0'), 'main.vigil', folder)
            self.assertIn('bad.vigil:2:', caught.exception.render('', 'main.vigil'))
            self.assertRaisesRegex(Diagnostic, 'Could not read module', compile_source, 'use nothing\n' + main('return 0'), 'm.vigil', folder)
            self.assertRaisesRegex(Diagnostic, 'already in use', compile_source, 'use a\nwork twice(n: Int) -> Int:\n    return n\n' + main('return 0'), 'm.vigil', folder)

    def test_test_runner(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder, 'checks.vigil')
            path.write_text('work test_bad() -> Unit:\n    witness 1 == 2, "One is not two."\n\nwork test_good() -> Unit:\n    pass\n', encoding='utf-8')
            result = subprocess.run([sys.executable, '-m', 'vigilcode', 'test', str(path)], capture_output=True, encoding='utf-8', cwd=ROOT, timeout=120)
            self.assertEqual(result.returncode, 1)
            self.assertIn('FAIL test_bad', result.stdout)
            self.assertIn('One is not two.', result.stdout)
            self.assertIn('ok   test_good', result.stdout)
            self.assertIn('1 passed, 1 failed.', result.stdout)
        result = subprocess.run([sys.executable, '-m', 'vigilcode', 'test', 'examples/tally/test_words.vigil'], capture_output=True, encoding='utf-8', cwd=ROOT, timeout=120)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertRaisesRegex(Diagnostic, 'No tests found', compile_source, main('return 0'), tests=True)
        self.assertRaisesRegex(Diagnostic, 'takes no parameters', compile_source, 'work test_x(n: Int) -> Unit:\n    pass\n', tests=True)

    # Limits and generated code --------------------------------------------------

    def test_limits(self):
        loop = main('while true:\n    pass\nreturn 0')
        result = self.program(loop, limits={'steps': 1000})
        self.assertIn('Execution limit', result.stderr)
        result = self.program(main('let t = "x"\nwhile true:\n    t = t + t\nreturn 0'), limits={'memory': 1 << 20})
        self.assertIn('Memory limit', result.stderr)
        result = self.program(main('while true:\n    say("x")\nreturn 0'), limits={'output': 100})
        self.assertIn('Output limit', result.stderr)
        self.assertEqual(len(result.stdout), 100)
        deep = 'work down(n: Int) -> Int:\n    discern n == 0:\n        return 0\n    return 1 + down(n - 1)\n\n' + main('say(down(50))\nreturn 0')
        self.assertIn('Call depth', self.program(deep, limits={'depth': 10}).stderr)

    def test_generated_c_has_no_warnings(self):
        compiler = os.environ.get('CC') or shutil.which('clang') or shutil.which('cc')
        sources = [p for p in (ROOT / 'examples').rglob('*.vigil') if p.name != 'words.vigil']
        for path in sources:
            with self.subTest(example=path.name), tempfile.TemporaryDirectory() as folder:
                Path(folder, 'main.c').write_text(compile_source(path.read_text(encoding='utf-8'), str(path), path.parent, tests=path.name.startswith('test_')), encoding='utf-8')
                shutil.copyfile(ROOT / 'vigilcode/runtime.h', Path(folder, 'runtime.h'))
                result = subprocess.run([compiler, '-std=c11', '-Wall', '-Wextra', '-Werror', '-fsyntax-only', str(Path(folder, 'main.c'))], capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
