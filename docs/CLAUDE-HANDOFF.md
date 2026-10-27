# Handoff for the next session

Continue **VigilCode** in https://github.com/danecohn/VigilCode. Read this file first, then `docs/LANGUAGE.md` (the language reference) and `docs/DESIGN.md` (the design direction).

## What the owner wants

- An original, Python-inspired programming language with its own compiler that produces native executables.
- Its own IDE, in the VigilTech look and feel, installed on the owner's Mac. The look and feel source is https://github.com/danecohn/vigilicons.
- Both should run on macOS, Windows and Linux, on x64 and ARM64.
- The owner plans to build VigilTech apps in it, so robustness matters more than features.
- They have asked for it to be feature-complete and development-ready. That is the direction, not the current state: see "Not done".
- Design direction: **balanced** Christian/Catholic. Meaningful concepts (vow, covenant, witness, discern, work) sit alongside readable everyday syntax, and the theming stays understated. Do not add theological vocabulary for its own sake, claim church endorsement, or equate bugs with sin.
- Keep this separate from the VigilTech suite rebrand: do not change the VigilTech repos, Railway services, or brand assets. The workbench reads the vigilicons palette and bundles its Vigil Sans font (OFL), unmodified.
- The owner pushes with GitHub Desktop. Sessions usually have no push credentials: commit locally, and say which folder and branch to push.

## State (v0.2.0, branch `compiler/v0.2-language`)

v0.1 work (call-depth guard, records and enums, first workbench, macOS installer) was merged to `main` as `31ed041`.

### Compiler (`vigilcode/`)
- `frontend.py`: an original lexer (indentation, UTF-8 text, BOM, CRLF) and a recursive-descent parser. Tokens carry their file name for module diagnostics.
- `compiler.py`: type checking and lowering to C11 in one pass. It covers:
  - records and enums
  - `List[T]`, `Option[T]`, `Result[T]`
  - exhaustive `match`
  - expected-type inference for `[]`, `none` and `fail`
  - modules (`use name`)
  - test mode (`test_` works)
  - pure covenants, return-path analysis, left-to-right evaluation
- `runtime.h`:
  - checked integer arithmetic
  - UTF-8 validation of all outside text
  - lists as immutable values over shared append-only buffers (amortized O(1) `push`)
  - text, file and console built-ins
  - build-time limits (steps, depth, memory, output)
  - binary stdout on Windows
- `cli.py`: `check`, `emit-c`, `build`, `run`, `test`, `workbench`, plus the `--max-*` limit flags.

### IDE (`vigil workbench [FOLDER]`)
- A local web app on 127.0.0.1 with a project file list, open/save/new, syntax highlighting, auto-indent, run with arguments, and click-to-jump problems, including problems in other modules.
- VigilTech night palette and Vigil Sans.
- Security:
  - every API call needs the per-session token and a loopback Host header
  - files are confined to the project folder and to `.vigil`
  - saves are atomic, runs are serialized
  - limits of 10 s, 100M steps, 256 MiB memory and 1 MiB output per run
  - a strict CSP
- macOS app: `~/Applications/VigilCode Workbench.app` opens `~/VigilCode Projects`. It has a generic icon, because vigilicons has no VigilCode product.

### Installers (`scripts/`)
- Per-user, no admin rights: `install-macos.sh`, `install-linux.sh`, `install-windows.ps1`, each with a matching uninstall script.
- All three create `~/VigilCode Projects` once and never overwrite it.

## Verified, and how

| Claim | Evidence |
|---|---|
| 50 tests pass | `python3 -m unittest discover -s tests` on macOS arm64, Python 3.9.6, Apple clang; full suite repeated 6× with no flake |
| Generated C is warning-free | test compiles every example with `-Wall -Wextra -Werror` |
| Parser/checker never crash | 20,000-mutation fuzz (3,000 in the suite): only diagnostics |
| Checker and codegen agree | 6,000 mutations; all 676 that type-checked produced C that compiles |
| Installed app works on this Mac | `install-macos.sh` run; app launched with `open`; installed `vigil test` passes; in a browser the app opened `~/VigilCode Projects`, ran `ledger.vigil`, and loaded Vigil Sans |
| v0.1 on 4 of 6 CI targets | run on `31ed041`: ubuntu x64, ubuntu arm64, macOS arm64 and macOS Intel passed |

## Not verified or not done

- **CI for this branch has not run.** Push `compiler/v0.2-language` and check it.
- **Windows** failed tests on `31ed041`. The logs need a GitHub sign-in, so the cause was not seen. This branch fixes the likely causes: test output decoded as cp1252, and text-mode `\r\n`. CI now turns failing tests into annotations, readable at `api.github.com/repos/danecohn/VigilCode/check-runs/<id>/annotations` without signing in. `install-windows.ps1` has never been run; CI will run it. Windows jobs are `continue-on-error` until they pass once.
- **The Linux installer** has never been run outside CI.
- **Memory is not reclaimed while a program runs.** It is freed at exit. This blocks long-running services. Plan reference counting for Text and List buffers.
- **Language gaps:**
  - maps or dictionaries
  - user generics, and enum payloads (only `Option` and `Result` carry values)
  - module namespaces
  - networking, processes, time, randomness
  - `break` and `continue`
  - character iteration (`length` and `slice` work in bytes)
- **Tooling gaps:** no formatter, LSP or debugger. The workbench has no Test button.
- **A self-hosted compiler** (VigilCode written in VigilCode): not started. Prerequisites in order:
  1. maps
  2. character access
  3. memory reclamation, or the bootstrap compiler will exhaust memory
  4. a typed IR separate from C emission

  Port the lexer first as a test of the language.
- **Release packaging:** wheels and sdist build. There are no signed installers, notarization, standalone binaries without Python, or downloads page. These need signing identities and a decision from the owner.
- **Icon:** the owner must supply a VigilCode product icon (add it to vigilicons). Do not draw one.
- Runtime licensing exception for proprietary user programs: still undecided. Do not add one silently.

## Suggested order for the next session

1. Push and read CI. Fix Windows using the annotations.
2. Memory reclamation, since the owner wants apps.
3. Maps, then `break`/`continue`, then enum payloads.
4. A Test button and a formatter in the workbench.
5. Begin the self-host lexer port.

## How to verify

```
python3 -m unittest discover -s tests -v
python3 -m vigilcode run examples/tally/main.vigil -- examples/tally/words.vigil
python3 -m vigilcode test examples/tally/test_words.vigil
python3 -m vigilcode workbench examples        # open the URL it prints
sh scripts/install-macos.sh                    # then open ~/Applications/VigilCode Workbench.app
```
