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


def build(source, output, *, filename='<source>', cc=None, optimize=False):
    generated = compile_source(source, filename)
    compiler = cc or os.environ.get('CC') or shutil.which('clang') or shutil.which('cc')
    if not compiler:
        raise RuntimeError('No native C compiler found. Install Clang or a C11 compiler, or pass --cc PATH.')
    output = Path(output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='vigil-build-') as folder:
        root = Path(folder)
        (root / 'main.c').write_text(generated, encoding='utf-8')
        shutil.copyfile(Path(__file__).with_name('runtime.h'), root / 'runtime.h')
        binary = root / ('program.exe' if os.name == 'nt' else 'program')
        command = [compiler, '-std=c11', '-O2' if optimize else '-O0', str(root / 'main.c'), '-o', str(binary)]
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
        if name == 'run':
            command.add_argument('args', nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    if args.command == 'workbench':
        from .workbench import serve
        serve(args.port, open_browser=not args.no_open)
        return 0
    source = ''
    try:
        source = args.source.read_text(encoding='utf-8')
        generated = compile_source(source, str(args.source))
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
            build(source, output, filename=str(args.source), cc=args.cc, optimize=args.optimize)
            print(f'Built {output}')
            return 0
        with tempfile.TemporaryDirectory(prefix='vigil-run-') as folder:
            binary = build(source, Path(folder) / 'program', filename=str(args.source), cc=args.cc, optimize=args.optimize)
            values = args.args[1:] if args.args[:1] == ['--'] else args.args
            return subprocess.run([str(binary), *values], timeout=30).returncode
    except Diagnostic as error:
        print(error.render(source, str(args.source)), file=sys.stderr)
    except (OSError, RuntimeError, subprocess.TimeoutExpired, UnicodeError, RecursionError) as error:
        print(f'VigilCode: {error}', file=sys.stderr)
    return 1
