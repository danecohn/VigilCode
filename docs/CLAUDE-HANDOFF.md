# Handoff prompt for Claude

Continue building **VigilCode** for VigilTech in https://github.com/danecohn/VigilCode.

## User's request and accepted choices

The user wants an original, Python-inspired, Christian/Catholic programming language with a compiler that produces native binary executables. They prefer an original implementation over a Python dialect. They selected **balanced: meaningful concepts with readable everyday syntax**, rather than theological vocabulary everywhere. They asked Codex to push its current work and hand it off because credits are nearly exhausted. This handoff is for continuation; do not mistake the foundation for a completed language.

The repository and local folder are separate from the software-suite rebrand you are already doing. Do not touch the deployed suite or Railway for this project unless the user requests that later. Local path: `/Users/ant/Documents/ChatGPT/AltStack/VigilCode`.

## Current implementation

- `vigilcode/frontend.py`: original indentation lexer, AST, recursive-descent/precedence parser. Does not use Python's AST, eval or exec.
- `vigilcode/compiler.py`: typed functions, lexical scopes, immutable vows/parameters, mutable lets, pure entry covenants, runtime witnesses, branch/loop lowering, all-path return checks, left-to-right evaluation, short-circuit Booleans. Emits C11.
- `vigilcode/runtime.h`: checked Int64 arithmetic, floor division/modulo, finite binary64 arithmetic, immutable text concatenation, byte length, process arguments, printing, source-located failures and prototype resource budgets.
- `vigilcode/cli.py`: `check`, `emit-c`, `build`, `run`; Clang/cc builds real host-native binaries without a Python dependency in the resulting program. The compiler is implemented in Python, not self-hosting.
- `examples`: hello, stewardship with covenants/witnesses, recursive Fibonacci.
- `tests/test_language.py`, `tests/test_workbench.py`: 27 test methods in total (see the continuation section below); they compile and execute real binaries.
- `.github/workflows/ci.yml`: Linux/macOS tests and native sample build. Inspect remote CI; do not claim it passed based solely on its configuration.
- README and DESIGN document implemented behavior and limitations. Existing GPL license retained. No product icon fabricated.

## Validation already performed locally

`python3 -m unittest discover -s tests -v` passed all 12 tests. Tests cover the examples, immutable values, strict types, precondition placement/purity/effect ordering, optimized witnesses, short-circuiting, integer boundaries/division by zero, floor arithmetic, call evaluation order, strings/arguments/bounds, return/scope checks and malformed source.

`python3 -m vigilcode build examples/stewardship.vigil -O -o build/stewardship` produced a **Mach-O arm64 native executable** on this Mac. The executable is ignored under build/. Re-run it to confirm output `All shares accounted for.`. The compiler and generated runtime are an early prototype, not audited production infrastructure.

## Immediate next steps

1. Review the pushed branch/PR and run the full tests plus CLI smoke tests. Review CI results. Preserve GPL and third-party notices. Continue via branches/PRs; don't force-push over work.
2. Audit and fuzz lexer/parser/type errors. Add regression tests for discovered issues. In particular check Unicode/text escaping, extreme integers and multiplication sign combinations, numeric promotion, scope/return analysis, invalid annotations, compiler failure handling and command-line argument behavior.
3. Add a recursion depth guard: current C-stack recursion can exhaust the stack before the execution-step limit. Resource budgets are prototype policy, not a sandbox or ownership model.
4. Design a coherent next language layer: immutable records, enums/Option/Result, collections, exhaustive matching, modules, postconditions, explicit effects and resource ownership. Implement small specified steps, not decorative vocabulary aliases.
5. Develop an actual language specification and stability/versioning policy. The type checker currently performs checks while lowering into C; an independently typed IR will help additional backends/tooling.
6. Build the requested Christian/Catholic-centric editor/workbench UI. It has **not been started**. Use the exact VigilTech assets from the established read-only asset repos and a carefully scoped project visual direction. A VigilCode-specific icon needs to be supplied/mapped; do not redraw or improvise the suite artwork.
7. Verify Windows separately and plan actual compiler distribution. Current native validation is on this Apple Silicon Mac, with Linux/macOS CI configured. There are no signed installers, six-platform releases, downloads page, web app, LSP or package registry yet. Do not present those as done.
8. Decide/document whether to introduce a runtime linking exception before inviting proprietary user programs; runtime currently shares the repo's GPL licensing. Do not silently add an exception.

## Working language example

```vigil
work share(total: Int, people: Int) -> Int:
    covenant total >= 0, "The available amount must not be negative."
    covenant people > 0, "There must be someone to receive a share."
    return total // people

work main() -> Int:
    vow each = share(35, 7)
    witness each == 5, "Each person should receive five."
    say(each)
    return 0
```

The balanced influence should shape actual semantics: fidelity through immutability, covenants through obligations, witnesses through checked assertions, stewardship through explicit resource handling, and humane diagnostics. These are design analogies, not doctrinal definitions. `witness` currently means a runtime assertion, not a mathematical proof. Do not claim the language establishes moral correctness or church endorsement.

## Known limits and details

No records/enums/collections/modules/file/network I/O, ownership checker, LSP, debugger, editor or self-hosting. ASCII identifiers, double-quoted JSON-style text, no NUL text, no shadowing, lexical block scope, forward work declarations. `length` counts bytes. `range` is ascending and end-exclusive with one or two integer arguments. `/` yields Real; `//` floors. Real operations use IEEE binary64 and mixed numeric comparisons can round large integers. `main` returns Unit or Int 0..255. Statements cannot discard non-Unit results.

Prototype runtime: 1,000,000 calls/loop steps; 1 MiB output; 16 MiB cumulative concatenation; text allocations freed at exit. No automatic sound, religious error judgment or third-party art. Use README and source as the exact behavior reference.

## Continuation (second session)

### Verified by running
- Original CI on commit `0ee9a36` (run 2, pull_request, and run 1, push): both jobs, ubuntu-latest and macos-latest, succeeded, including the native sample build (read from the GitHub API). Nothing after that commit has run in CI because it could not be pushed from this session (no credentials). **CI for the commits below is unknown until they are pushed.**
- Locally (macOS arm64, Python 3.9.6, Apple clang): `python3 -m unittest discover -s tests` passes 27 tests. The workbench tests were repeated 25 times without a failure. A flaky test found along the way (oversized-body check racing a connection reset) was fixed in the test.
- Packaging: `python -m build` produces an sdist and wheel; the wheel installed into a clean venv ran `vigil run examples/ledger.vigil` correctly.
- A mutation fuzz (20,000 mutated examples, plus a 3,000-case version in the test suite) found no crash other than ordinary diagnostics.

### Done
1. **Robustness.** A recursion depth limit of 2,000 nested work calls (infinite recursion used to segfault silently; confirmed, then fixed). UTF-8 BOM accepted. Tests for Unicode escapes, lone surrogates, huge literals, empty files, CRLF.
2. **Richer types.** Immutable `record` (fixed fields, nested allowed, declared before use, no field assignment, no `==`) and payload-free `enum` (`Season.Harvest`, `==`/`!=`, `say` prints the variant name). Constructors and field reads are allowed in covenants. See `examples/ledger.vigil`.
3. **Editor.** `vigil workbench` serves a local editor on 127.0.0.1 (check, run, jump to problem, open/save, keyboard run). Because it compiles and runs code, every API call needs a per-session token and a loopback Host header; runs are serialized, limited to 10 seconds and 64 KiB of output. Checked visually in a browser: a diagnostic shows on line 2, and a fix runs and prints.
   - Styling is a neutral placeholder palette (CSS variables in `vigilcode/workbench.html`). The VigilTech tokens/artwork were not available and no icon was made. The religious theming is only the language's own keywords.
4. **macOS install (this Mac, per user, no sudo).** `scripts/install-macos.sh` installs a venv in `~/Library/Application Support/VigilCode`, the `vigil` command in `~/.local/bin`, and `~/Applications/VigilCode Workbench.app` (generic icon, unsigned). Run and checked here. `scripts/uninstall-macos.sh` removes it.
5. **Packaging.** `requires-python` lowered to >=3.9 (the suite passes on 3.9.6 locally; CI uses 3.12). The wheel includes `runtime.h` and the workbench page.

### Not done, and what blocks it
- **Windows.** Never run. This Mac cannot run it, and no cross-compiler is installed. Prepared but unverified: `.exe` output suffix, and CI jobs `windows-latest` and `windows-11-arm` with `CC=clang` (set `continue-on-error`, so they show red/green without blocking). Known risks: the runtime's C is untested on MSVC/MinGW; `\n` text-mode translation on stdout; the 2,000-call limit was chosen for a 1 MiB stack but not measured there; no Windows install script (the macOS one is shell-only).
- **Six-target support (Windows/macOS/Linux, x64 and ARM64).** The compiler and workbench are pure Python plus generated C11, so they should run wherever Python 3.9+ and a C compiler exist. The CI matrix now lists all six (ubuntu x64/arm64, macos arm64/Intel, windows x64/arm64), but only macOS arm64 has been run. Runner labels such as `macos-15-intel` and `windows-11-arm` may need adjusting. Native single-file installers, signing/notarization and a Linux/Windows launcher are not built.
- **Release packaging.** Source and wheel only. No signed installers, downloads page or publishing workflow. Needs signing identities and a distribution decision from the owner.
- **A compiler written in VigilCode (self-hosting).** Not started, deliberately. It needs, in order: lists/collections, Text slicing and character access, file I/O, a way to report errors as values (`Result`/`Option`), modules, and a typed IR separated from C emission (item 5 above). Records and enums are the first of these. A realistic plan is to port the lexer first as a test of the language.
- **Building real apps in VigilCode.** Not yet possible: no collections, I/O, networking, modules, JSON or HTTP. Treat the language as a prototype, not a base for VigilTech apps yet. Next steps in order: collections, `Result`/`Option` with exhaustive `match`, file I/O, modules, then a spec and compatibility policy.
- Unchanged from before: exhaustive matching, postconditions, ownership, LSP, runtime licensing exception decision (not made).

### How to verify
```
python3 -m unittest discover -s tests -v
python3 -m vigilcode run examples/ledger.vigil
python3 -m vigilcode workbench        # then use Check/Run in the browser
sh scripts/install-macos.sh           # macOS only
```
