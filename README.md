# VigilCode

An original, Python-inspired programming language by VigilTech, with a Christian and Catholic design vocabulary. Version 0.1 is a working compiler foundation, not a finished general-purpose language or IDE.

VigilCode has its own lexer, parser, syntax tree and type checker. It generates C11; Clang or another C11 compiler produces a native executable. Generated programs do not need Python. The compiler itself currently does.

```vigil
work share(total: Int, people: Int) -> Int:
    covenant total >= 0, "The available amount must not be negative."
    covenant people > 0, "There must be someone to receive a share."
    return total // people

work main() -> Int:
    vow each = share(35, 7)
    witness each == 5, "Each person should receive five."
    say("All shares accounted for.")
    return 0
```

## Try it

Use Python 3.10+ and a C11 compiler. From the repository root:

```sh
python3 -m vigilcode check examples/stewardship.vigil
python3 -m vigilcode run examples/stewardship.vigil
python3 -m vigilcode build examples/stewardship.vigil -O -o build/stewardship
./build/stewardship
python3 -m unittest discover -s tests -v
```

The last executable is a normal native binary for the build host. Local validation produced a working Apple Silicon Mach-O executable. Linux and macOS CI is configured; Windows compatibility and cross-compilation are not yet verified. `--cc` selects a compiler executable; `CC` must likewise be one executable path, not shell flags. Flags for `run` go before the source filename; program arguments follow it, optionally after `--`.

For installed commands, `python3 -m pip install .` exposes `vigil` and `vigilcode`. `emit-c` prints C; compilation of that C also needs `vigilcode/runtime.h` on the include path.

## Language core

- `work`: a typed function, including recursive functions and forward calls.
- `vow`: an immutable local binding. Parameters are immutable too.
- `let`: an explicitly mutable local binding.
- `covenant`: a checked entry condition, before a work performs actions. Conditions must be pure; they may use parameters, literals, operators and `length`.
- `witness`: an assertion checked in every build, including optimized builds. This is a runtime assertion, not a formal proof.
- `discern` / `otherwise`: Boolean branching. `for ... in range(...)` and `while` provide loops.
- `Int`, `Real`, `Bool`, `Text`, `Unit`: static types; no general truthiness or implicit assignment coercion.
- `say(value)`, `length(text)`, `arg(index)`, `arg_count()`: initial built-ins. `length` counts UTF-8 bytes, not characters or graphemes.

Indent with spaces. Text uses double-quoted, JSON-style escapes. Comments start with `#`. Names use ASCII letters, digits and underscores. Expressions evaluate left to right; `and` and `or` short-circuit. Integer division floors as in Python; `/` returns Real. Integer overflow and division by zero fail with a source location. Non-finite Real arithmetic fails. Real is binary64 and mixed numeric arithmetic/comparison may round large integers.

Blocks have lexical scope; no shadowing. Non-Unit works must return on every statically provable path. `main` takes no parameters and returns Unit or an Int exit code from 0 to 255. Unused non-Unit results must be bound or returned.

## Christian and Catholic design

The balanced vocabulary is deliberate: ordinary code stays readable, while fidelity to commitments, work in service of others, truthful assertions and stewardship influence actual behavior. The distinction between immutable vows and changing local state is enforced, and covenants are checked before actions. Diagnostics explain what failed without moral judgment.

These are engineering interpretations inspired by Christian and Catholic thought, not doctrinal definitions. See [design notes](docs/DESIGN.md). The compiler does not decide whether a program is morally good.

## Current limits

There are no collections, records, enums, modules, packages, file/network I/O, ownership checker, debugger, language server, editor UI or self-hosting compiler yet. Recursion uses the C stack and does not have a stack-depth guard. This compiler has initial end-to-end tests; it has not been fuzzed or audited.

The v0.1 runtime limits a program to 1,000,000 work calls/loop steps, 1 MiB output, and 16 MiB cumulative concatenated text. Allocated text is immutable and reclaimed at process exit, not by a production garbage collector. These limits and memory policy need future design work. Do not describe this version as a sandbox.

## Continuing development

[Claude handoff](docs/CLAUDE-HANDOFF.md) contains the accepted direction, implementation inventory, verification commands and unfinished work. Preserve the existing VigilTech brand artwork; no VigilCode-specific icon has been supplied or invented.

Compiler and runtime: GPL v3 or later; see [LICENSE](LICENSE). Existing upstream license text is preserved. No third-party compiler source has been vendored.
