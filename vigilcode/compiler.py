# SPDX-License-Identifier: GPL-3.0-or-later
"""Type checking and deterministic, left-to-right lowering to portable C11."""
from dataclasses import dataclass
import math
from .frontend import Diagnostic, Enum, Parser, Record

TYPES = {'Int': 'int64_t', 'Real': 'double', 'Bool': 'bool', 'Text': 'const char *', 'Unit': 'void'}
BUILTINS = {'say', 'length', 'arg', 'arg_count', 'range'}

def cstr(value):
    return '"' + ''.join('\\%03o' % b for b in value.encode('utf-8')) + '"'

@dataclass
class Binding:
    type: str
    name: str
    mutable: bool

class Compiler:
    def __init__(self, source, filename='<source>'):
        self.source, self.filename = source, filename
        items = Parser(source).parse()
        self.works = [i for i in items if not isinstance(i, (Record, Enum))]
        self.declared = [i for i in items if isinstance(i, (Record, Enum))]
        self.user_types = {}
        self.signatures = {}
        self.lines, self.counter, self.scopes = [], 0, []
        self.contract = False

    def error(self, message, token):
        raise Diagnostic(message, token)

    def line(self, text):
        self.lines.append(text)

    def location(self, token):
        return cstr(f'{self.filename}:{token.line}:{token.column}')

    def ctype(self, type_):
        if type_ in TYPES:
            return TYPES[type_]
        return f'vt_{"rec" if isinstance(self.user_types[type_], Record) else "enum"}_{type_}'

    def known(self, type_):
        return type_ in TYPES or type_ in self.user_types

    def temp(self, type_, expression):
        self.counter += 1
        name = f'vt_tmp_{self.counter}'
        self.line(f'{self.ctype(type_)} {name} = {expression};')
        return type_, name

    def lookup(self, name, token):
        for scope in reversed(self.scopes):
            if name in scope:
                return scope[name]
        self.error(f'{name!r} has not been declared in this scope.', token)

    def bind(self, name, type_, mutable, token):
        if not self.known(type_) or type_ == 'Unit':
            self.error(f'{type_!r} is not a type that a value can have.', token)
        if name in BUILTINS or name in self.signatures or name in TYPES or name in self.user_types:
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

    def declare_types(self):
        names = set()
        for item in self.declared:
            if item.name in self.user_types or item.name in TYPES or item.name in BUILTINS:
                self.error(f'The type name {item.name!r} is already in use.', item.token)
            seen = set()
            if isinstance(item, Record):
                for name, type_, token in item.fields:
                    # A field's type must be declared earlier, which also rules out recursive records.
                    if not self.known(type_) or type_ == 'Unit':
                        self.error(f'{type_!r} is not a type a field can have; declare it before {item.name}.', token)
                    if name in seen:
                        self.error(f'The field {name!r} is declared twice.', token)
                    seen.add(name)
            else:
                for name, token in item.variants:
                    if name in seen:
                        self.error(f'The variant {name!r} is declared twice.', token)
                    seen.add(name)
            self.user_types[item.name] = item
            self.line_types = getattr(self, 'line_types', [])
            if isinstance(item, Record):
                members = ' '.join(f'{self.ctype(t)} f_{n};' for n, t, _ in item.fields)
                self.line_types.append(f'typedef struct {{ {members} }} {self.ctype(item.name)};')
            else:
                variants = ', '.join(f'vt_variant_{item.name}_{n}' for n, _ in item.variants)
                names_c = ', '.join(cstr(n) for n, _ in item.variants)
                self.line_types.append(f'typedef enum {{ {variants} }} {self.ctype(item.name)};')
                self.line_types.append(f'static const char *const vt_names_{item.name}[] = {{ {names_c} }};')

    def compile(self):
        self.declare_types()
        for work in self.works:
            if work.name in self.signatures or work.name in BUILTINS or work.name in TYPES or work.name in self.user_types:
                self.error(f'The work name {work.name!r} is already in use.', work.token)
            if not self.known(work.result):
                self.error(f'Unknown result type {work.result!r}.', work.token)
            for _, type_, token in work.params:
                if not self.known(type_) or type_ == 'Unit':
                    self.error(f'{type_!r} is not a type that a parameter can have.', token)
            self.signatures[work.name] = work
        main = self.signatures.get('main')
        if not main or main.params or main.result not in ('Int', 'Unit'):
            raise Diagnostic('Declare work main() -> Int: or work main() -> Unit: as the entry point.')
        self.line('#include "runtime.h"')
        self.lines.extend(getattr(self, 'line_types', []))
        for work in self.works:
            params = ', '.join(self.ctype(t) for _, t, _ in work.params) or 'void'
            self.line(f'{self.ctype(work.result)} vt_work_{work.name}({params});')
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
        self.line('int main(int argc, char **argv) { vt_argc=argc; vt_argv=argv; atexit(vt_cleanup);')
        if main.result == 'Int':
            self.line('int64_t result=vt_work_main(); if(result<0 || result>255) vt_fail("main", "main must return an exit code from 0 to 255."); return (int)result; }')
        else:
            self.line('vt_work_main(); return 0; }')
        return '\n'.join(self.lines) + '\n'

    def block(self, statements, root=False):
        self.scopes.append({})
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
            type_, code = self.expression(s.args[0])
            name, annotation = s.value
            if annotation:
                self.expect(type_, annotation, token)
            binding = self.bind(name, type_, kind == 'let', token)
            self.line(f'{self.ctype(type_)} {binding.name} = {code};')
        elif kind == 'assign':
            binding = self.lookup(s.value, token)
            if not binding.mutable:
                self.error(f'{s.value!r} is a vow or parameter and cannot change. Use let for a changing value.', token)
            type_, code = self.expression(s.args[0])
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
        elif kind == 'while':
            self.line('for (;;) {')
            self.line(f'vt_step({self.location(token)});')
            type_, condition = self.expression(s.args[0])
            self.expect(type_, 'Bool', token)
            self.line(f'if (!({condition})) break;')
            self.block(s.args[1])
            self.line('}')
        elif kind == 'for':
            call = s.args[0]
            if call.kind != 'call' or call.value != 'range' or len(call.args) not in (1, 2):
                self.error('Use for name in range(end): or range(start, end):.', token)
            values = [self.expression(e) for e in call.args]
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
        elif kind == 'return':
            type_, code = self.expression(s.args[0]) if s.args else ('Unit', '')
            self.expect(type_, self.work.result, token)
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

    def expression(self, e):
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
            binding = self.lookup(e.value, token)
            # Snapshot every read: later call arguments may have observable effects.
            return self.temp(binding.type, binding.name)
        if kind == 'field':
            base = e.args[0]
            if base.kind == 'name' and isinstance(self.user_types.get(base.value), Enum):
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
            left_type, left = self.expression(e.args[0])
            op = e.value
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
            if left_type == right_type and isinstance(self.user_types.get(left_type), Enum) and op in ('==', '!='):
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
        if kind == 'call':
            name = e.value
            if name == 'range':
                self.error('range is available only in a for statement.', token)
            if self.contract and name != 'length' and not isinstance(self.user_types.get(name), Record):
                self.error('Covenants must be pure: use parameters, literals, operators, and length.', token)
            if name in ('say', 'length', 'arg', 'arg_count'):
                expected = 0 if name == 'arg_count' else 1
                if len(e.args) != expected:
                    self.error(f'{name} expects {expected} argument(s).', token)
                values = [self.expression(arg) for arg in e.args]
                if name == 'say':
                    type_, value = values[0]
                    if type_ in self.user_types and isinstance(self.user_types[type_], Enum):
                        self.line(f'vt_say_text(vt_names_{type_}[{value}]);')
                    elif type_ not in TYPES or type_ == 'Unit':
                        self.error('say prints Int, Real, Bool, Text, or an enum variant. Print a record field instead.', token)
                    else:
                        self.line(f'vt_say_{type_.lower()}({value});')
                    return 'Unit', ''
                if name == 'arg_count':
                    return self.temp('Int', '(int64_t)(vt_argc-1)')
                type_, value = values[0]
                self.expect(type_, 'Text' if name == 'length' else 'Int', token)
                return self.temp('Int' if name == 'length' else 'Text', f'vt_{name}({value}, {self.location(token)})')
            record = self.user_types.get(name)
            if isinstance(record, Record):
                if len(e.args) != len(record.fields):
                    self.error(f'{name} needs {len(record.fields)} value(s), one for each field.', token)
                values = []
                for arg, (field_name, type_, _) in zip(e.args, record.fields):
                    actual, value = self.expression(arg)
                    self.expect(actual, type_, arg.token)
                    values.append(value)
                return self.temp(name, f'({self.ctype(name)}){{{", ".join(values)}}}')
            work = self.signatures.get(name)
            if not work:
                self.error(f'Unknown work {name!r}.', token)
            if len(e.args) != len(work.params):
                self.error(f'{name} expects {len(work.params)} argument(s).', token)
            values = []
            for arg, (_, type_, _) in zip(e.args, work.params):
                actual, value = self.expression(arg)
                self.expect(actual, type_, arg.token)
                values.append(value)
            call = f'vt_work_{name}({", ".join(values)})'
            if work.result == 'Unit':
                self.line(call + ';')
                return 'Unit', ''
            return self.temp(work.result, call)
        raise AssertionError(kind)

def compile_source(source, filename='<source>'):
    return Compiler(source, filename).compile()
