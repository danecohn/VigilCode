# SPDX-License-Identifier: GPL-3.0-or-later
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from . import __version__
from .compiler import compile_source
from .frontend import Diagnostic


LIMITS = {'steps': 'VT_MAX_STEPS', 'depth': 'VT_MAX_DEPTH', 'memory': 'VT_MAX_MEMORY', 'output': 'VT_MAX_OUTPUT'}


def build(source, output, *, filename='<source>', cc=None, optimize=False, base=None, limits=None):
    generated = compile_source(source, filename, base)
    compiler = cc or os.environ.get('CC') or shutil.which('clang') or shutil.which('cc')
    if not compiler:
        raise RuntimeError('No native C compiler found. Install Clang or a C11 compiler, or pass --cc PATH.')
    output = Path(output)
    if os.name == 'nt' and not output.suffix:
        output = output.with_suffix('.exe')
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='vigil-build-') as folder:
        root = Path(folder)
        (root / 'main.c').write_text(generated, encoding='utf-8')
        shutil.copyfile(Path(__file__).with_name('runtime.h'), root / 'runtime.h')
        binary = root / ('program.exe' if os.name == 'nt' else 'program')
        defines = [f'-D{LIMITS[k]}={int(v)}' for k, v in (limits or {}).items()]
        command = [compiler, '-std=c11', '-O2' if optimize else '-O0', *defines, str(root / 'main.c'), '-o', str(binary)]
        result = subprocess.run(command, capture_output=True, text=True, timeout=60)
        if result.returncode:
            raise RuntimeError('Native compiler failed:\n' + result.stderr)
        # Never overwrite source files, and keep old executables intact on build failure.
        shutil.copy2(binary, output)
    return output


def main(argv=None):
    parser = argparse.ArgumentParser(prog='vigil', description='VigilCode native compiler')
    parser.add_argument('--version', action='version', version='VigilCode ' + __version__)
    commands = parser.add_subparsers(dest='command', required=True)
    workbench = commands.add_parser('workbench', help='Open the local editor in your browser')
    workbench.add_argument('folder', nargs='?', type=Path, help='Project folder (default: the current folder)')
    workbench.add_argument('--port', type=int, default=8765)
    workbench.add_argument('--no-open', action='store_true', help='Do not open a browser window')
    for name in ['check', 'emit-c', 'build', 'run']:
        command = commands.add_parser(name)
        command.add_argument('source', type=Path)
        if name in ('build', 'emit-c'):
            command.add_argument('-o', '--output', type=Path)
        if name in ('build', 'run'):
            command.add_argument('--cc', help='Path to a C11 compiler (one executable, no shell expansion)')
            command.add_argument('-O', '--optimize', action='store_true')
            command.add_argument('--max-steps', type=int, metavar='N', help='Stop after N work calls and loop steps (default: no limit)')
            command.add_argument('--max-depth', type=int, metavar='N', help='Nested work call limit (default: 2000)')
            command.add_argument('--max-memory', type=int, metavar='BYTES', help='Memory limit (default: 1 GiB)')
            command.add_argument('--max-output', type=int, metavar='BYTES', help='Output limit (default: no limit)')
        if name == 'run':
            command.add_argument('args', nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    if args.command == 'workbench':
        from .workbench import serve
        try:
            serve(args.port, open_browser=not args.no_open, root=args.folder)
        except (OSError, RuntimeError) as error:
            print(f'VigilCode: {error}', file=sys.stderr)
            return 1
        return 0
    source = ''
    try:
        source = args.source.read_text(encoding='utf-8')
        base = args.source.resolve().parent
        generated = compile_source(source, str(args.source), base)
        options = {}
        if args.command in ('build', 'run'):
            limits = {k: getattr(args, 'max_' + k) for k in LIMITS if getattr(args, 'max_' + k) is not None}
            if any(v < 0 for v in limits.values()):
                raise RuntimeError('Limits must be zero or more.')
            options = dict(filename=str(args.source), cc=args.cc, optimize=args.optimize, base=base, limits=limits)
        if args.command == 'check':
            print('VigilCode: checks passed.')
            return 0
        if args.command == 'emit-c':
            if args.output:
                if args.output.resolve() == args.source.resolve():
                    raise RuntimeError('Choose an output different from the source file.')
                args.output.write_text(generated, encoding='utf-8')
            else:
                sys.stdout.write(generated)
            return 0
        if args.command == 'build':
            output = args.output or Path('build') / args.source.stem
            if output.resolve() == args.source.resolve():
                raise RuntimeError('Choose an output different from the source file.')
            built = build(source, output, **options)
            print(f'Built {built}')
            return 0
        with tempfile.TemporaryDirectory(prefix='vigil-run-') as folder:
            binary = build(source, Path(folder) / 'program', **options)
            values = args.args[1:] if args.args[:1] == ['--'] else args.args
            return subprocess.run([str(binary), *values], timeout=30).returncode
    except Diagnostic as error:
        print(error.render(source, str(args.source)), file=sys.stderr)
    except (OSError, RuntimeError, subprocess.TimeoutExpired, UnicodeError, RecursionError) as error:
        print(f'VigilCode: {error}', file=sys.stderr)
    return 1
