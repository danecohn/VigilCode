# VigilCode language reference (v0.2)

This describes what the compiler in this repository accepts and does. If this page and the compiler disagree, the compiler is right and this page has a bug.

## Programs and files

A program is one `.vigil` file with `work main() -> Int:` or `work main() -> Unit:`. An `Int` result is the process exit code and must be 0 to 255.

```vigil
work main() -> Int:
    say("Peace be with you.")
    return 0
```

- Indentation is spaces only. Any consistent depth works; four is the convention.
- `#` starts a comment.
- Files are UTF-8. A byte-order mark and CRLF line endings are accepted.
- Identifiers are ASCII letters, digits and `_`, and cannot start with a digit.

### Modules

`use name` at the top level loads `name.vigil` from the same folder as the file that says it. Everything it declares becomes visible: there are no namespaces yet, so names must be unique across a program. Each file is loaded once, so two files may `use` each other.

## Values and bindings

| Type | Meaning |
|---|---|
| `Int` | signed 64-bit integer; overflow stops the program with an error |
| `Real` | IEEE binary64; a non-finite result stops the program |
| `Bool` | `true`, `false` |
| `Text` | immutable UTF-8 text with no NUL characters |
| `List[T]` | immutable list |
| `Option[T]` | a value or `none` |
| `Result[T]` | a value (`ok`) or an error message (`fail`) |
| records, enums | declared by you, below |
| `Unit` | no value; only as a work's result |

```vigil
vow name = "Ana"          # fixed for its whole scope
let count = 0             # can be reassigned with count = ...
vow ids: List[Int] = []   # a type annotation, needed when it cannot be inferred
```

A name cannot be redeclared inside its scope, including in nested blocks (no shadowing). Parameters are fixed like `vow`.

Literals:
- `Int`: `42`. The language has no negative literals: `-42` is negation.
- `Real`: `3.25`. There are no exponent forms.
- `Text`: `"..."` with JSON-style escapes (`\n`, `\"`, `é`).

## Operators

From lowest to highest precedence: `or`, `and`, comparisons (`==` `!=` `<` `>` `<=` `>=`), `+` `-`, `*` `/` `//` `%`, then unary `-` `+` `not`.

- `and` and `or` short-circuit and need `Bool`. There is no implicit truthiness.
- `/` always gives `Real`. `//` and `%` floor, need `Int`, and stop the program on division by zero.
- Comparisons do not chain: write `a < b and b < c`.
- `Text + Text` concatenates. Text compares by bytes.
- Enums support `==` and `!=`. Records and lists have no operators.
- Mixing `Int` and `Real` in arithmetic promotes to `Real`.

## Works (functions)

```vigil
work share(total: Int, people: Int) -> Int:
    covenant total >= 0, "The available amount must not be negative."
    covenant people > 0, "There must be someone to receive a share."
    return total // people
```

- Every path of a non-`Unit` work must `return`.
- Arguments are evaluated left to right.
- A result cannot be silently dropped: a call used as a statement must return `Unit`.
- Works may be declared in any order and may call themselves. Nesting deeper than the depth limit (below) stops the program.
- **`covenant`**: an entry condition. It must come before any other statement. It may use only parameters, literals, operators, records and built-ins without effects, so it cannot read input or files. It is checked on every call, including in optimized builds.
- **`witness`**: an assertion that can appear anywhere. It is checked in every build.

Both forms take an optional message after a comma. When one fails, the program stops with exit code 1 and the source location.

## Control flow

```vigil
discern n > 0:
    say("positive")
otherwise:
    say("not positive")

while n > 0:
    n = n - 1

for i in range(10):        # 0..9; range(start, end) is end-exclusive
    say(i)

for name in names:         # walk a List
    say(name)
```

### match

`match` checks one value against its cases. The compiler makes sure every case is handled.

```vigil
match parse_int(text):
    some n:
        say(n)
    none:
        say("not a number")

match read_file(path):
    ok contents:
        say(contents)
    fail message:
        say(message)

match light:
    Light.Red:
        say("stop")
    otherwise:
        say("go")
```

- Option cases are `some name:` and `none:`.
- Result cases are `ok name:` and `fail name:`, where `name` holds the error message as `Text`.
- Enum cases are written `Type.Variant:`.
- `otherwise:` must be the last case, and only when something is left to handle.
- A match counts as returning when every case returns.

## Records and enums

```vigil
enum Season:
    Planting
    Harvest

record Share:
    owner: Text
    amount: Int
    notes: List[Text]

vow s = Share("Ana", 5, [])
say(s.owner)
vow t = Share(s.owner, s.amount + 1, s.notes)   # fields never change; build a new record
```

- A record field's type must already be declared, so records cannot contain themselves.
- Enums have no payloads. `say` and `to_text` give the variant's name.

## Lists

```vigil
vow xs = [3, 1, 4]
say(xs[0])               # index; out of range stops the program
say(length(xs))
vow ys = push(xs, 1)     # a new list; xs is unchanged
vow zs = set(ys, 0, 9)   # a new list with item 0 replaced
```

Lists are values: nothing changes a list in place. `push` reuses storage when it safely can, so building a list in a loop with `xs = push(xs, item)` is linear overall.

## Built-ins

| Built-in | Result | Notes |
|---|---|---|
| `say(value)` | Unit | prints `Int`, `Real`, `Bool`, `Text` or an enum, then a newline |
| `length(text or list)` | Int | text length is in bytes |
| `arg(i)`, `arg_count()` | Text, Int | command-line arguments, not counting the program |
| `slice(text, start, end)` | Text | byte offsets; must fall on character boundaries |
| `find(text, part)` | Int | byte offset, or -1 |
| `trim(text)` | Text | strips ASCII whitespace at both ends |
| `split(text, separator)`, `join(list, separator)` | List[Text], Text | the separator must be non-empty for `split` |
| `to_text(value)` | Text | `Int`, `Real`, `Bool`, `Text`, enum |
| `parse_int(text)`, `parse_real(text)` | Option[Int], Option[Real] | strict: no spaces or trailing characters |
| `to_real(int)`, `to_int(real)` | Real, Int | `to_int` truncates toward zero; out of range stops the program |
| `push(list, item)`, `set(list, i, item)` | List[T] | see Lists |
| `some(v)`, `none`, `ok(v)`, `fail(message)` | Option / Result | `none` and `fail` need a known type from context |
| `read_line()` | Option[Text] | one line from standard input without its line ending; `none` at end of input |
| `read_file(path)` | Result[Text] | whole file, which must be UTF-8 text with no NUL bytes |
| `write_file(path, text)` | Result[Int] | replaces the file; gives the bytes written |

Text that comes from outside (arguments, input, files) is checked to be valid UTF-8 with no NUL characters.

## Resource limits

Every compiled program enforces limits, set when it is built:

| Limit | `vigil build` default | Workbench | Flag |
|---|---|---|---|
| work calls + loop steps | none | 100,000,000 | `--max-steps N` |
| nested work calls | 2,000 | 2,000 | `--max-depth N` |
| memory for text and lists | 1 GiB | 256 MiB | `--max-memory BYTES` |
| output | none | 1 MiB | `--max-output BYTES` |

A value of 0 means no limit. Reaching a limit stops the program with exit code 1 and a message.

**Memory is not reclaimed while a program runs.** Text and list storage is freed only when the program exits. That is fine for command-line tools and batch jobs. It is not suitable yet for long-running services; reference counting or ownership is planned.

## Tooling

```
vigil check FILE        # type-check only
vigil run FILE -- ARGS  # build and run
vigil build FILE -o OUT [-O]
vigil emit-c FILE       # print the generated C
vigil test FILE         # run every work test_name() -> Unit in its own process
vigil workbench [FOLDER]
```

Building needs a C11 compiler: Clang, GCC, or `--cc PATH`.

## Not in the language yet

These are tracked in `docs/CLAUDE-HANDOFF.md`:
- maps or dictionaries
- generics for user types, and payloads on enums
- module namespaces
- networking, processes, time, and randomness
- a formatter, LSP or debugger
- memory reclamation
- a self-hosted compiler
