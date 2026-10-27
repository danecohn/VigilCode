# VigilCode

An original, Python-inspired programming language by VigilTech, with a Christian and Catholic design vocabulary. Version 0.2 is a working compiler and editor for small native programs. It is not yet a finished general-purpose language.

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

Use Python 3.9+ and a C11 compiler (Clang or GCC). From the repository root:

```sh
python3 -m vigilcode run examples/stewardship.vigil
python3 -m vigilcode run examples/tally/main.vigil -- examples/tally/words.vigil
python3 -m vigilcode test examples/tally/test_words.vigil
python3 -m vigilcode build examples/stewardship.vigil -O -o build/stewardship
python3 -m vigilcode workbench examples
python3 -m unittest discover -s tests -v
```

`python3 -m pip install .` installs the `vigil` command. On macOS, `sh scripts/install-macos.sh` installs it under your home folder together with the VigilCode Workbench app; `sh scripts/uninstall-macos.sh` removes both.

## The language

[docs/LANGUAGE.md](docs/LANGUAGE.md) is the reference. In short:
- `work` declares functions; `vow` and `let` declare fixed and changeable values.
- `covenant` (entry conditions) and `witness` (assertions) stay on in optimized builds.
- Records, enums, `List[T]`, `Option[T]` and `Result[T]`, with an exhaustive `match`.
- Text, file and console built-ins; modules with `use`; `vigil test` for tests.

The compiled program checks integer overflow, list bounds, UTF-8 validity of outside text, recursion depth and memory use. It reports the source location when one of those checks fails.

## Christian and Catholic design

The balanced vocabulary is deliberate: ordinary code stays readable, while fidelity to commitments, work in service of others, truthful assertions and stewardship influence actual behavior. The distinction between immutable vows and changing local state is enforced, and covenants are checked before actions. Diagnostics explain what failed without moral judgment.

These are engineering interpretations inspired by Christian and Catholic thought, not doctrinal definitions. See [design notes](docs/DESIGN.md). The compiler does not decide whether a program is morally good.

## Current limits

The compiler generates native programs on the six combinations of macOS, Linux and Windows on x64 and ARM64 wherever Python and a C compiler exist. CI runs on all six. Windows results are listed in the handoff. Memory is freed when a program exits, not while it runs, so this version suits tools and batch programs rather than long-running services. There are no maps, user generics, networking, language server, debugger or self-hosted compiler yet; see [the reference](docs/LANGUAGE.md#not-in-the-language-yet).

## Continuing development

[Claude handoff](docs/CLAUDE-HANDOFF.md) contains the accepted direction, implementation inventory, verification commands and unfinished work. Preserve the existing VigilTech brand artwork; no VigilCode-specific icon has been supplied or invented.

Compiler and runtime: GPL v3 or later; see [LICENSE](LICENSE). Existing upstream license text is preserved. No third-party compiler source has been vendored.
