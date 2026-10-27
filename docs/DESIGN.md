# Design direction

VigilCode is an original language with Python-inspired indentation and a native compilation target. The user chose **balanced** Christian and Catholic vocabulary. Keep normal programming clear; do not mechanically rename every ordinary keyword or use sacred names for arbitrary machine failures.

The Catechism's account of work emphasizes service to people and the dignity of the person doing the work (§§2426–2429). This informs the language's name for a function, `work`, and examples that account for resources and serve others. Source: [Vatican, Economic Activity and Social Justice](https://www.vatican.va/content/catechism/en/part_three/section_two/chapter_two/article_7/iv_economic_activity_and_social_justice.index.html). This is design inspiration rather than an assertion that the Catechism prescribes programming constructs.

The other choices are engineering analogies:

| Concept | Current engineering behavior | Further work |
|---|---|---|
| Fidelity / vow | Immutable bindings and parameters | Immutable structured data |
| Covenant | Pure entry conditions checked before actions | Postconditions and typed obligations |
| Truthful witness | Assertions remain enabled under optimization | Property tests and optional verification |
| Discernment | Explicit Bool conditions, no implicit truthiness | Exhaustive matching over sum types |
| Stewardship | Checked integer arithmetic, bounded prototype allocation | Resource ownership and deterministic cleanup |
| Dignity | Specific diagnostics without shaming the programmer | Accessible editor and documentation |

Do not equate software errors with sin or claim that code is morally approved by compiling. Do not add church endorsement claims. The project can have an explicitly Christian identity and still be usable by anyone.

## Architecture

`frontend.py`: independent lexer → indentation tokens → recursive-descent parser → AST.

`compiler.py`: signatures → static types/scope/obligation validation → C11 with named temporaries for defined evaluation order.

`runtime.h`: checked arithmetic, immutable text support, diagnostics, arguments, output and prototype execution budgets.

`cli.py`: check, emit-c, build and run; subprocess invocation uses argument arrays, not a shell.

C is the initial backend. Reusing a native code generator does not make VigilCode a Python dialect: its syntax and semantics are handled by its own frontend. Do not claim a machine-code backend or self-hosting implementation exists. LLVM or a direct backend is a later option, not required for the initial native language.

## UI direction, not yet built

A dedicated editor/workbench can weave in a restrained Christian/Catholic visual language and terminology. Use the supplied VigilTech typography, tokens and exact corporate artwork; request a product icon instead of inventing one. Prioritize readable code, accessible contrast, keyboard controls, diagnostics and a visible build/run state. The earlier suite-wide ban on religious copy is superseded specifically for this user-requested Christian language. Keep Claude's unrelated rebrand work isolated.
