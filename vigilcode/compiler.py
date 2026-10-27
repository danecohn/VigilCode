# SPDX-License-Identifier: GPL-3.0-or-later
"""Type checking and deterministic, left-to-right lowering to portable C11."""
from dataclasses import dataclass
import math
from pathlib import Path
import re
from .frontend import Diagnostic, Enum, Parser, Record, Use

TYPES = {'Int': 'int64_t', 'Real': 'double', 'Bool': 'bool', 'Text': 'const char *', 'Unit': 'void'}
GENERIC = {'List', 'Option', 'Result'}
# Built-in works. Each entry: argument count. Their typing is in Compiler.builtin().
BUILTINS = {
    'say': 1, 'length': 1, 'arg': 1, 'arg_count': 0, 'range': None,
    'slice': 3, 'find': 2, 'trim': 1, 'split': 2, 'join': 2,
    'to_text': 1, 'parse_int': 1, 'parse_real': 1, 'to_real': 1, 'to_int': 1,
    'push': 2, 'set': 3, 'some': 1, 'ok': 1, 'fail': 1,
    'read_line': 0, 'read_file': 1, 'write_file': 2,
}
RESERVED = set(BUILTINS) | {'none'}
# Built-ins with no observable effect, allowed inside covenants.
PURE = {'length', 'slice', 'find', 'trim', 'split', 'join', 'to_text', 'parse_int', 'parse_real', 'to_real', 'to_int', 'push', 'set', 'some', 'ok', 'fail'}

def cstr(value):
    return '"' + ''.join('\\%03o' % b for b in value.encode('utf-8')) + '"'

def split_type(type_):
    """'List[Option[Int]]' -> ('List', 'Option[Int]'); 'Int' -> ('Int', None)."""
    if type_.endswith(']') and '[' in type_:
        head, rest = type_.split('[', 1)
        return head, rest[:-1]
    return type_, None

@dataclass
class Binding:
    type: str
    name: str
    mutable: bool

class Compiler:
    def __init__(self, source, filename='<source>', base=None):
        self.source, self.filename = source, filename
        self.sources = {filename: source}
        items = self.load(source, filename, base, set())
        self.works = [i for i in items if not isinstance(i, (Record, Enum))]
        self.declared = [i for i in items if isinstance(i, (Record, Enum))]
        self.user_types, self.signatures = {}, {}
        self.lines, self.typedefs, self.generated = [], [], set()
        self.counter, self.scopes = 0, []
        self.contract = False

    def load(self, source, filename, base, seen):
        """Parse a file and, recursively, every `use name` (name.vigil beside it). Each file is read once."""
        try:
            items = Parser(source, filename).parse()
        except Diagnostic as error:
            self.attach(error)
            raise
        result = []
        for item in items:
            if not isinstance(item, Use):
                result.append(item)
                continue
            if base is None:
                self.error('use needs the program to be a file on disk; build it with vigil.', item.token)
            path = (Path(base) / (item.name + '.vigil')).resolve()
            if path in seen:
                continue
            seen.add(path)
            try:
                text = path.read_text(encoding='utf-8')
            except (OSError, UnicodeError) as problem:
                self.error(f'Could not read module {item.name!r} ({path.name}): {problem.strerror if isinstance(problem, OSError) else "not UTF-8"}.', item.token)
            name = str(path)
            self.sources[name] = text
            result.extend(self.load(text, name, path.parent, seen))
        return result

    def attach(self, error):
        file = error.token.file if error.token else ''
        if file and file != self.filename:
            error.file, error.source = file, self.sources.get(file, '')

    def error(self, message, token):
        error = Diagnostic(message, token)
        self.attach(error)
        raise error

    def line(self, text):
        self.lines.append(text)

    def location(self, token):
        return cstr(f'{token.file or self.filename}:{token.line}:{token.column}')

    # Types --------------------------------------------------------------

    def check_type(self, type_, token, unit=False):
        head, inner = split_type(type_)
        if inner is not None:
            if head not in GENERIC or ',' in inner:
                self.error(f'{type_!r} is not a type. Generic types are List[T], Option[T], and Result[T].', token)
            self.check_type(inner, token)
            return
        if type_ in GENERIC:
            self.error(f'{type_} needs an item type, for example {type_}[Int].', token)
        if type_ == 'Unit' and not unit:
            self.error('Unit cannot be stored in a value, field, or parameter.', token)
        if type_ not in TYPES and type_ not in self.user_types:
            self.error(f'Unknown type {type_!r}.', token)

    def ctype(self, type_):
        if type_ in TYPES:
            return TYPES[type_]
        head, inner = split_type(type_)
        if head == 'List':
            return 'vt_list'
        if head in ('Option', 'Result'):
            name = f'vt_{head.lower()}_' + re.sub(r'[^A-Za-z0-9]', '_', inner)
            if name not in self.generated:
                self.generated.add(name)
                item = self.ctype(inner)
                flag = 'has' if head == 'Option' else 'ok'
                error = ' const char *error;' if head == 'Result' else ''
                self.typedefs.append(f'typedef struct {{ bool {flag}; {item} value;{error} }} {name};')
            return name
        return f'vt_{"rec" if isinstance(self.user_types[type_], Record) else "enum"}_{type_}'

    def is_enum(self, type_):
        return isinstance(self.user_types.get(type_), Enum)

    def temp(self, type_, expression):
        self.counter += 1
        name = f'vt_tmp_{self.counter}'
        self.line(f'{self.ctype(type_)} {name} = {expression};')
        return type_, name

    def cell(self, type_, value):
        """Address and size of a copy of value, for the list runtime."""
        _, name = self.temp(type_, value)
        return f'&{name}, sizeof({name})'

    def lookup(self, name, token):
        for scope in reversed(self.scopes):
            if name in scope:
                return scope[name]
        self.error(f'{name!r} has not been declared in this scope.', token)

    def bind(self, name, type_, mutable, token):
        self.check_type(type_, token)
        if name in RESERVED or name in self.signatures or name in TYPES or name in self.user_types or name in GENERIC:
            self.error(f'{name!r} is reserved for a type, work, or built-in.', token)
        if any(name in scope for scope in self.scopes):
            self.error(f'{name!r} is already declared; shadowing is not allowed.', token)
        self.counter += 1
        result = Binding(type_, f'vt_local_{self.counter}', mutable)
        self.scopes[-1][name] = result
        return result

    def expect(self, actual, expected, token):
        if actual != expected:
            self.error(f'Expected {expected}; found {actual}.', token)

    # Declarations -------------------------------------------------------

    def declare_types(self):
        for item in self.declared:
            if item.name in self.user_types or item.name in TYPES or item.name in RESERVED or item.name in GENERIC:
                self.error(f'The type name {item.name!r} is already in use.', item.token)
            seen = set()
            if isinstance(item, Record):
                for name, type_, token in item.fields:
                    # A field's type must be declared earlier, which also rules out recursive records.
                    if type_ == item.name or (split_type(type_)[0] not in GENERIC and type_ not in TYPES and type_ not in self.user_types):
                        self.error(f'{type_!r} is not a type a field can have; declare it before {item.name}.', token)
                    self.check_type(type_, token)
                    if name in seen:
                        self.error(f'The field {name!r} is declared twice.', token)
                    seen.add(name)
                self.user_types[item.name] = item
                members = ' '.join(f'{self.ctype(t)} f_{n};' for n, t, _ in item.fields)
                self.typedefs.append(f'typedef struct {{ {members} }} {self.ctype(item.name)};')
            else:
                for name, token in item.variants:
                    if name in seen:
                        self.error(f'The variant {name!r} is declared twice.', token)
                    seen.add(name)
                self.user_types[item.name] = item
                variants = ', '.join(f'vt_variant_{item.name}_{n}' for n, _ in item.variants)
                names = ', '.join(cstr(n) for n, _ in item.variants)
                self.typedefs.append(f'typedef enum {{ {variants} }} {self.ctype(item.name)};')
                self.typedefs.append(f'static const char *const vt_names_{item.name}[] = {{ {names} }};')

    def compile(self):
        self.declare_types()
        for work in self.works:
            if work.name in self.signatures or work.name in RESERVED or work.name in TYPES or work.name in self.user_types or work.name in GENERIC:
                self.error(f'The work name {work.name!r} is already in use.', work.token)
            self.check_type(work.result, work.token, unit=True)
            for _, type_, token in work.params:
                self.check_type(type_, token)
            self.signatures[work.name] = work
        main = self.signatures.get('main')
        if not main or main.params or main.result not in ('Int', 'Unit'):
            raise Diagnostic('Declare work main() -> Int: or work main() -> Unit: as the entry point.')
        prototypes = []
        for work in self.works:
            params = ', '.join(self.ctype(t) for _, t, _ in work.params) or 'void'
            prototypes.append(f'{self.ctype(work.result)} vt_work_{work.name}({params});')
        for work in self.works:
            self.scopes = [{}]
            self.work = work
            params = []
            for name, type_, token in work.params:
                value = self.bind(name, type_, False, token)
                params.append(f'{self.ctype(type_)} {value.name}')
            self.line(f'{self.ctype(work.result)} vt_work_{work.name}({", ".join(params) or "void"}) {{')
            self.line(f'vt_step({self.location(work.token)}); vt_enter({self.location(work.token)});')
            returns = self.block(work.body, root=True)
            if work.result != 'Unit' and not returns:
                self.error(f'{work.name!r} must return {work.result} on every path.', work.token)
            if work.result == 'Unit' and not returns:
                self.line('vt_depth--;')
            self.line('}')
        self.line('int main(int argc, char **argv) { vt_init(argc, argv); atexit(vt_cleanup);')
        if main.result == 'Int':
            self.line('int64_t result=vt_work_main(); fflush(stdout); if(result<0 || result>255) vt_fail("main", "main must return an exit code from 0 to 255."); return (int)result; }')
        else:
            self.line('vt_work_main(); fflush(stdout); return 0; }')
        return '\n'.join(['#include "runtime.h"', *self.typedefs, *prototypes, *self.lines]) + '\n'

    # Statements ---------------------------------------------------------

    def block(self, statements, root=False, bindings=()):
        self.scopes.append({})
        for name, type_, code, token in bindings:
            binding = self.bind(name, type_, False, token)
            self.line(f'{self.ctype(type_)} {binding.name} = {code};')
        returned, contracts_open = False, root
        for statement in statements:
            if returned:
                self.error('This statement cannot be reached after return.', statement.token)
            if statement.kind == 'covenant':
                if not contracts_open:
                    self.error('A covenant belongs at the beginning of a work, before its actions.', statement.token)
            else:
                contracts_open = False
            returned = self.statement(statement)
        self.scopes.pop()
        return returned

    def statement(self, s):
        kind, token = s.kind, s.token
        if kind in ('vow', 'let'):
            name, annotation = s.value
            if annotation:
                self.check_type(annotation, token)
            type_, code = self.expression(s.args[0], annotation)
            if annotation:
                self.expect(type_, annotation, token)
            if type_ == 'Unit':
                self.error('This work returns nothing, so there is no value to keep.', token)
            binding = self.bind(name, type_, kind == 'let', token)
            self.line(f'{self.ctype(type_)} {binding.name} = {code};')
        elif kind == 'assign':
            binding = self.lookup(s.value, token)
            if not binding.mutable:
                self.error(f'{s.value!r} is a vow or parameter and cannot change. Use let for a changing value.', token)
            type_, code = self.expression(s.args[0], binding.type)
            self.expect(type_, binding.type, token)
            self.line(f'{binding.name} = {code};')
        elif kind in ('witness', 'covenant'):
            self.contract = kind == 'covenant'
            type_, condition = self.expression(s.args[0])
            self.expect(type_, 'Bool', token)
            self.line(f'if (!({condition})) {{')
            type_, message = self.expression(s.args[1])
            self.expect(type_, 'Text', token)
            self.line(f'vt_obligation({self.location(token)}, {cstr(kind)}, {message}); }}')
            self.contract = False
        elif kind == 'discern':
            type_, condition = self.expression(s.args[0])
            self.expect(type_, 'Bool', token)
            self.line(f'if ({condition}) {{')
            yes = self.block(s.args[1])
            self.line('} else {')
            no = self.block(s.args[2])
            self.line('}')
            return yes and no
        elif kind == 'match':
            return self.match(s)
        elif kind == 'while':
            self.line('for (;;) {')
            self.line(f'vt_step({self.location(token)});')
            type_, condition = self.expression(s.args[0])
            self.expect(type_, 'Bool', token)
            self.line(f'if (!({condition})) break;')
            self.block(s.args[1])
            self.line('}')
        elif kind == 'for':
            self.for_loop(s)
        elif kind == 'return':
            expected = self.work.result
            type_, code = self.expression(s.args[0], expected) if s.args else ('Unit', '')
            self.expect(type_, expected, token)
            self.line('{ vt_depth--; return' + (' ' + code if type_ != 'Unit' else '') + '; }')
            return True
        elif kind == 'expression':
            if s.args[0].kind != 'call':
                self.error('A standalone statement must call a work.', token)
            type_, code = self.expression(s.args[0])
            if type_ != 'Unit':
                self.error('Bind or return the result instead of discarding it.', token)
        elif kind == 'pass':
            self.line(';')
        return False

    def for_loop(self, s):
        token, iterable = s.token, s.args[0]
        if iterable.kind == 'call' and iterable.value == 'range':
            if len(iterable.args) not in (1, 2):
                self.error('Use for name in range(end): or range(start, end):.', token)
            values = [self.expression(e) for e in iterable.args]
            for type_, _ in values:
                self.expect(type_, 'Int', token)
            start, end = ('0', values[0][1]) if len(values) == 1 else (values[0][1], values[1][1])
            self.scopes.append({})
            binding = self.bind(s.value, 'Int', False, token)
            self.line(f'for (int64_t {binding.name}={start}; {binding.name}<{end}; ++{binding.name}) {{')
            self.line(f'vt_step({self.location(token)});')
            self.block(s.args[1])
            self.line('}')
            self.scopes.pop()
            return
        type_, code = self.expression(iterable)
        head, item = split_type(type_)
        if head != 'List':
            self.error(f'for can walk a List or range(...); this value is {type_}.', iterable.token)
        self.counter += 1
        index = f'vt_index_{self.counter}'
        self.line(f'for (int64_t {index}=0; {index}<{code}.len; ++{index}) {{')
        self.line(f'vt_step({self.location(token)});')
        self.block(s.args[1], bindings=[(s.value, item, f'VT_ITEMS({self.ctype(item)}, {code})[{index}]', token)])
        self.line('}')

    def match(self, s):
        token, arms = s.token, s.args[1]
        type_, subject = self.expression(s.args[0])
        head, inner = split_type(type_)
        if self.is_enum(type_):
            cases = {v: (f'{subject} == vt_variant_{type_}_{v}', None) for v, _ in self.user_types[type_].variants}
        elif head == 'Option':
            cases = {'some': (f'{subject}.has', (inner, f'{subject}.value')), 'none': (f'!{subject}.has', None)}
        elif head == 'Result':
            cases = {'ok': (f'{subject}.ok', (inner, f'{subject}.value')), 'fail': (f'!{subject}.ok', ('Text', f'{subject}.error'))}
        else:
            self.error(f'match works on an enum, Option, or Result; this value is {type_}.', token)
        seen, returns, opened = set(), True, False
        for arm in arms:
            if arm.pattern is None:
                if arm is not arms[-1]:
                    self.error('otherwise must be the last case.', arm.token)
                if len(seen) == len(cases):
                    self.error('Every case is already covered, so otherwise would never run.', arm.token)
                self.line('} else {' if opened else '{')
                returns = self.block(arm.body) and returns
                seen = set(cases)
                continue
            first, second = arm.pattern
            if self.is_enum(type_):
                if second is None or first != type_:
                    self.error(f'Write each case as {type_}.Variant.', arm.token)
                key = second
            else:
                if second is not None:
                    self.error(f'Write the case as {" or ".join(cases)}.', arm.token)
                key = first
            if key not in cases:
                self.error(f'{key!r} is not a case of {type_}.', arm.token)
            if key in seen:
                self.error(f'The case {key!r} appears twice.', arm.token)
            seen.add(key)
            condition, payload = cases[key]
            if payload and not arm.binding:
                self.error(f'Name the value carried by {key}, for example: {key} value:', arm.token)
            if arm.binding and not payload:
                self.error(f'{key} carries no value to name.', arm.token)
            # When this arm completes the match, a plain else lets the C compiler see every path.
            if arm is arms[-1] and seen == set(cases):
                self.line('} else {' if opened else '{')
            else:
                self.line(('} else if (' if opened else 'if (') + condition + ') {')
            opened = True
            bindings = [(arm.binding, payload[0], payload[1], arm.token)] if payload else []
            returns = self.block(arm.body, bindings=bindings) and returns
        missing = [k for k in cases if k not in seen]
        if missing:
            self.error(f'This match does not handle: {", ".join(missing)}. Add those cases or an otherwise.', token)
        self.line('}')
        return returns

    # Expressions --------------------------------------------------------

    def expression(self, e, expected=None):
        kind, token = e.kind, e.token
        if kind == 'int':
            value = int(e.value)
            if value > 9223372036854775807:
                self.error('Int is a signed 64-bit integer; this literal is too large.', token)
            return self.temp('Int', f'INT64_C({value})')
        if kind == 'real':
            if not math.isfinite(float(e.value)):
                self.error('Real literals must be finite.', token)
            return self.temp('Real', e.value)
        if kind == 'text':
            return self.temp('Text', cstr(e.value))
        if kind == 'bool':
            return self.temp('Bool', 'true' if e.value else 'false')
        if kind == 'name':
            if e.value == 'none':
                if not expected or split_type(expected)[0] != 'Option':
                    self.error('none needs a known Option type here, for example vow x: Option[Int] = none.', token)
                return self.temp(expected, f'({self.ctype(expected)}){{0}}')
            binding = self.lookup(e.value, token)
            # Snapshot every read: later call arguments may have observable effects.
            return self.temp(binding.type, binding.name)
        if kind == 'list':
            item = None
            if expected and split_type(expected)[0] == 'List':
                item = split_type(expected)[1]
            if not e.args and item is None:
                self.error('An empty list needs a known type here, for example vow names: List[Text] = [].', token)
            values = []
            for arg in e.args:
                actual, value = self.expression(arg, item)
                item = item or actual
                self.expect(actual, item, arg.token)
                values.append(value)
            if item == 'Unit':
                self.error('A list cannot hold Unit.', token)
            _, result = self.temp(f'List[{item}]', '(vt_list){0, NULL}')
            for value in values:
                self.line(f'{result} = vt_list_push({result}, {self.cell(item, value)}, {self.location(token)});')
            return f'List[{item}]', result
        if kind == 'index':
            type_, code = self.expression(e.args[0])
            head, item = split_type(type_)
            if head != 'List':
                self.error(f'Only a List can be indexed; this value is {type_}.', token)
            index_type, index = self.expression(e.args[1])
            self.expect(index_type, 'Int', e.args[1].token)
            self.line(f'vt_list_check({code}, {index}, {self.location(token)});')
            return self.temp(item, f'VT_ITEMS({self.ctype(item)}, {code})[{index}]')
        if kind == 'field':
            base = e.args[0]
            if base.kind == 'name' and self.is_enum(base.value):
                enum = self.user_types[base.value]
                if e.value not in [v for v, _ in enum.variants]:
                    self.error(f'{base.value} has no variant {e.value!r}.', token)
                return self.temp(base.value, f'vt_variant_{base.value}_{e.value}')
            type_, code = self.expression(base)
            record = self.user_types.get(type_)
            if not isinstance(record, Record):
                self.error(f'Only a record has fields; this value is {type_}.', token)
            for name, field_type, _ in record.fields:
                if name == e.value:
                    return self.temp(field_type, f'{code}.f_{name}')
            self.error(f'{type_} has no field {e.value!r}.', token)
        if kind == 'unary':
            if e.value == '-' and e.args[0].kind == 'int' and int(e.args[0].value) == 9223372036854775808:
                return self.temp('Int', 'INT64_MIN')
            type_, code = self.expression(e.args[0])
            if e.value == 'not':
                self.expect(type_, 'Bool', token)
                return self.temp('Bool', f'!({code})')
            if type_ not in ('Int', 'Real'):
                self.error('Unary + and - require a number.', token)
            if e.value == '+':
                return type_, code
            return self.temp(type_, f'vt_neg({code}, {self.location(token)})' if type_ == 'Int' else f'-({code})')
        if kind == 'binary':
            return self.binary(e)
        if kind == 'call':
            return self.call(e, expected)
        raise AssertionError(kind)

    def binary(self, e):
        token, op = e.token, e.value
        left_type, left = self.expression(e.args[0])
        if op in ('and', 'or'):
            self.expect(left_type, 'Bool', token)
            _, result = self.temp('Bool', left)
            self.line(f'if ({"!" if op == "or" else ""}{result}) {{')
            right_type, right = self.expression(e.args[1])
            self.expect(right_type, 'Bool', token)
            self.line(f'{result} = {right}; }}')
            return 'Bool', result
        right_type, right = self.expression(e.args[1])
        if left_type == right_type == 'Text':
            if op == '+':
                return self.temp('Text', f'vt_concat({left}, {right}, {self.location(token)})')
            if op in ('==', '!=', '<', '>', '<=', '>='):
                return self.temp('Bool', f'(strcmp({left}, {right}) {op} 0)')
        if left_type == right_type and self.is_enum(left_type) and op in ('==', '!='):
            return self.temp('Bool', f'({left} {op} {right})')
        if left_type == right_type == 'Bool' and op in ('==', '!='):
            return self.temp('Bool', f'({left} {op} {right})')
        if left_type not in ('Int', 'Real') or right_type not in ('Int', 'Real'):
            self.error(f'Operator {op!r} does not accept {left_type} and {right_type}.', token)
        if op in ('==', '!=', '<', '>', '<=', '>='):
            return self.temp('Bool', f'({left} {op} {right})')
        if op in ('//', '%'):
            self.expect(left_type, 'Int', token)
            self.expect(right_type, 'Int', token)
        if left_type == right_type == 'Int' and op != '/':
            fn = {'+': 'add', '-': 'sub', '*': 'mul', '//': 'div', '%': 'mod'}[op]
            return self.temp('Int', f'vt_{fn}({left}, {right}, {self.location(token)})')
        return self.temp('Real', f'vt_real_{"div" if op == "/" else {"+":"add","-":"sub","*":"mul"}[op]}((double){left}, (double){right}, {self.location(token)})')

    def call(self, e, expected):
        name, token = e.value, e.token
        if name == 'range':
            self.error('range is available only in a for statement.', token)
        record = self.user_types.get(name)
        if self.contract and name not in PURE and not isinstance(record, Record):
            self.error('Covenants must be pure: use parameters, literals, operators, records, and built-ins without effects.', token)
        if isinstance(record, Record):
            if len(e.args) != len(record.fields):
                self.error(f'{name} needs {len(record.fields)} value(s), one for each field.', token)
            values = []
            for arg, (_, type_, _) in zip(e.args, record.fields):
                actual, value = self.expression(arg, type_)
                self.expect(actual, type_, arg.token)
                values.append(value)
            return self.temp(name, f'({self.ctype(name)}){{{", ".join(values)}}}')
        if name in BUILTINS:
            if len(e.args) != BUILTINS[name]:
                self.error(f'{name} expects {BUILTINS[name]} argument(s).', token)
            return self.builtin(e, expected)
        work = self.signatures.get(name)
        if not work:
            self.error(f'Unknown work {name!r}.', token)
        if len(e.args) != len(work.params):
            self.error(f'{name} expects {len(work.params)} argument(s).', token)
        values = []
        for arg, (_, type_, _) in zip(e.args, work.params):
            actual, value = self.expression(arg, type_)
            self.expect(actual, type_, arg.token)
            values.append(value)
        call = f'vt_work_{name}({", ".join(values)})'
        if work.result == 'Unit':
            self.line(call + ';')
            return 'Unit', ''
        return self.temp(work.result, call)

    def builtin(self, e, expected):
        name, token, where = e.value, e.token, self.location(e.token)
        inner = split_type(expected)[1] if expected else None
        if name == 'some':
            type_, value = self.expression(e.args[0], inner if expected and expected.startswith('Option[') else None)
            if type_ == 'Unit':
                self.error('some needs a value.', token)
            return self.temp(f'Option[{type_}]', f'({self.ctype(f"Option[{type_}]")}){{true, {value}}}')
        if name == 'ok':
            type_, value = self.expression(e.args[0], inner if expected and expected.startswith('Result[') else None)
            if type_ == 'Unit':
                self.error('ok needs a value.', token)
            return self.temp(f'Result[{type_}]', f'({self.ctype(f"Result[{type_}]")}){{true, .value = {value}}}')
        if name == 'fail':
            if not expected or not expected.startswith('Result['):
                self.error('fail needs a known Result type here, for example a work that returns Result[Int].', token)
            type_, message = self.expression(e.args[0])
            self.expect(type_, 'Text', e.args[0].token)
            return self.temp(expected, f'({self.ctype(expected)}){{false, .error = {message}}}')
        if name in ('push', 'set'):
            list_type, items = self.expression(e.args[0], expected if expected and expected.startswith('List[') else None)
            head, item = split_type(list_type)
            if head != 'List':
                self.error(f'{name} needs a List first; this value is {list_type}.', e.args[0].token)
            index = None
            if name == 'set':
                index_type, index = self.expression(e.args[1])
                self.expect(index_type, 'Int', e.args[1].token)
            value_arg = e.args[-1]
            type_, value = self.expression(value_arg, item)
            self.expect(type_, item, value_arg.token)
            cell = self.cell(item, value)
            if name == 'push':
                return self.temp(list_type, f'vt_list_push({items}, {cell}, {where})')
            return self.temp(list_type, f'vt_list_set({items}, {index}, {cell}, {where})')
        values = [self.expression(arg) for arg in e.args]
        types = [t for t, _ in values]
        codes = [c for _, c in values]
        def need(*wanted):
            for (actual, _), want, arg in zip(values, wanted, e.args):
                self.expect(actual, want, arg.token)
        if name == 'say':
            type_, value = values[0]
            if self.is_enum(type_):
                self.line(f'vt_say_text(vt_names_{type_}[{value}]);')
            elif type_ not in TYPES or type_ == 'Unit':
                self.error('say prints Int, Real, Bool, Text, or an enum variant. Print a record field instead.', token)
            else:
                self.line(f'vt_say_{type_.lower()}({value});')
            return 'Unit', ''
        if name == 'length':
            if split_type(types[0])[0] == 'List':
                return self.temp('Int', f'{codes[0]}.len')
            need('Text')
            return self.temp('Int', f'vt_length({codes[0]}, {where})')
        if name == 'arg_count':
            return self.temp('Int', '(int64_t)(vt_argc-1)')
        if name == 'arg':
            need('Int')
            return self.temp('Text', f'vt_arg({codes[0]}, {where})')
        if name == 'slice':
            need('Text', 'Int', 'Int')
            return self.temp('Text', f'vt_slice({codes[0]}, {codes[1]}, {codes[2]}, {where})')
        if name == 'find':
            need('Text', 'Text')
            return self.temp('Int', f'vt_find({codes[0]}, {codes[1]}, {where})')
        if name == 'trim':
            need('Text')
            return self.temp('Text', f'vt_trim({codes[0]}, {where})')
        if name == 'split':
            need('Text', 'Text')
            return self.temp('List[Text]', f'vt_split({codes[0]}, {codes[1]}, {where})')
        if name == 'join':
            need('List[Text]', 'Text')
            return self.temp('Text', f'vt_join({codes[0]}, {codes[1]}, {where})')
        if name == 'to_text':
            type_, value = values[0]
            if type_ == 'Text':
                return type_, value
            if self.is_enum(type_):
                return self.temp('Text', f'vt_names_{type_}[{value}]')
            if type_ not in ('Int', 'Real', 'Bool'):
                self.error(f'to_text converts Int, Real, Bool, Text, or an enum; this value is {type_}.', token)
            return self.temp('Text', f'vt_bool_text({value})' if type_ == 'Bool' else f'vt_{type_.lower()}_text({value}, {where})')
        if name in ('parse_int', 'parse_real'):
            need('Text')
            type_ = 'Int' if name == 'parse_int' else 'Real'
            option = f'Option[{type_}]'
            _, result = self.temp(option, f'({self.ctype(option)}){{0}}')
            self.line(f'{result}.has = vt_{name}({codes[0]}, &{result}.value);')
            return option, result
        if name == 'to_real':
            need('Int')
            return self.temp('Real', f'(double){codes[0]}')
        if name == 'to_int':
            need('Real')
            return self.temp('Int', f'vt_to_int({codes[0]}, {where})')
        if name == 'read_line':
            _, result = self.temp('Option[Text]', f'({self.ctype("Option[Text]")}){{0}}')
            self.line(f'{result}.has = vt_read_line(&{result}.value, {where});')
            return 'Option[Text]', result
        if name == 'read_file':
            need('Text')
            _, result = self.temp('Result[Text]', f'({self.ctype("Result[Text]")}){{0}}')
            self.line(f'{result}.value = vt_read_file({codes[0]}, &{result}.error, {where}); {result}.ok = {result}.value != NULL;')
            return 'Result[Text]', result
        if name == 'write_file':
            need('Text', 'Text')
            _, result = self.temp('Result[Int]', f'({self.ctype("Result[Int]")}){{0}}')
            self.line(f'{result}.value = vt_write_file({codes[0]}, {codes[1]}, &{result}.error, {where}); {result}.ok = {result}.value >= 0;')
            return 'Result[Int]', result
        raise AssertionError(name)

def compile_source(source, filename='<source>', base=None):
    return Compiler(source, filename, base).compile()
