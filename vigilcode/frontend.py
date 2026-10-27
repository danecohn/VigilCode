# SPDX-License-Identifier: GPL-3.0-or-later
"""Indentation lexer and recursive-descent parser. Does not parse or execute Python."""
from dataclasses import dataclass, field
import json
import re

@dataclass
class Token:
    kind: str
    value: object
    line: int
    column: int
    file: str = ''

class Diagnostic(Exception):
    def __init__(self, message, token=None):
        self.message, self.token = message, token
        # Set when the error is in a module other than the one being rendered.
        self.file, self.source = None, None
        super().__init__(message)

    def render(self, source, filename="<source>"):
        if self.source is not None:
            source, filename = self.source, self.file
        if not self.token:
            return f"{filename}: {self.message}"
        t = self.token
        lines = source.splitlines()
        line = lines[t.line - 1] if 0 < t.line <= len(lines) else ""
        return f"{filename}:{t.line}:{t.column}: {self.message}\n  {line}\n  {' ' * (t.column - 1)}^"

@dataclass
class Expr:
    kind: str
    token: Token
    value: object = None
    args: list = field(default_factory=list)

@dataclass
class Stmt:
    kind: str
    token: Token
    value: object = None
    args: list = field(default_factory=list)

@dataclass
class Record:
    name: str
    fields: list  # (name, type, token)
    token: Token

@dataclass
class Enum:
    name: str
    variants: list  # (name, token)
    token: Token

@dataclass
class Use:
    name: str
    token: Token

@dataclass
class Work:
    name: str
    params: list
    result: str
    body: list
    token: Token

@dataclass
class Arm:
    pattern: object  # None for otherwise, else (head, qualifier or None)
    binding: object  # name bound to the payload, or None
    body: list
    token: Token

PATTERN = re.compile(r'(?P<SPACE> +)|(?P<REAL>[0-9]+\.[0-9]+)|(?P<INT>[0-9]+)|(?P<TEXT>"(?:[^"\\\n]|\\.)*")|(?P<NAME>[A-Za-z_][A-Za-z_0-9]*)|(?P<OP>->|==|!=|<=|>=|//|[+*/%<>=():,.\[\]\-])|(?P<BAD>.)')
KEYWORDS = set('work record enum use match vow let discern otherwise while for in return witness covenant pass true false and or not'.split())

def lex(source, file=''):
    if source.startswith('﻿'):
        source = source[1:]
    tokens, indents = [], [0]
    lines = source.split('\n')
    for number, line in enumerate(lines, 1):
        line = line[:-1] if line.endswith('\r') else line
        if '\t' in line:
            raise Diagnostic('Use spaces for indentation; tabs are not accepted.', Token('', '', number, line.index('\t') + 1, file))
        if not line.strip(' ') or line.lstrip(' ').startswith('#'):
            continue
        indent = len(line) - len(line.lstrip(' '))
        if indent > indents[-1]:
            indents.append(indent)
            tokens.append(Token('INDENT', '', number, 1, file))
        else:
            while indent < indents[-1]:
                indents.pop()
                tokens.append(Token('DEDENT', '', number, 1, file))
            if indent != indents[-1]:
                raise Diagnostic('Indentation must match an enclosing block.', Token('', '', number, 1, file))
        offset = indent
        while offset < len(line):
            if line[offset] == '#':
                break
            match = PATTERN.match(line, offset)
            kind, text = match.lastgroup, match.group()
            token = Token(kind, text, number, offset + 1, file)
            offset = match.end()
            if kind == 'SPACE':
                continue
            if kind == 'BAD':
                raise Diagnostic(f'Unexpected character {text!r}.', token)
            if kind == 'TEXT':
                try:
                    token.value = json.loads(text)
                    token.value.encode('utf-8')
                except (ValueError, UnicodeError):
                    raise Diagnostic('Text must be a valid UTF-8 JSON-style string.', token)
                if '\0' in token.value:
                    raise Diagnostic('Text cannot contain a NUL character.', token)
            elif kind == 'NAME' and text in KEYWORDS:
                token.kind = text
            elif kind == 'OP':
                token.kind = text
            tokens.append(token)
        tokens.append(Token('NEWLINE', '', number, len(line) + 1, file))
    number = len(lines) + 1
    for _ in indents[1:]:
        tokens.append(Token('DEDENT', '', number, 1, file))
    tokens.append(Token('EOF', '', number, 1, file))
    return tokens

class Parser:
    def __init__(self, source, file=''):
        self.tokens, self.index = lex(source, file), 0

    @property
    def current(self):
        return self.tokens[self.index]

    def take(self, kind=None):
        token = self.current
        if kind and token.kind != kind:
            raise Diagnostic(f'Expected {kind!r}; found {token.value or token.kind!r}.', token)
        self.index += 1
        return token

    def accept(self, kind):
        if self.current.kind == kind:
            return self.take()
        return None

    def type_name(self):
        """A type: Name or Name[Type, ...]. Returned as canonical text such as List[Int]."""
        name = self.take('NAME').value
        if self.accept('['):
            parts = [self.type_name()]
            while self.accept(','):
                parts.append(self.type_name())
            self.take(']')
            name += '[' + ', '.join(parts) + ']'
        return name

    def parse(self):
        items = []
        while self.current.kind != 'EOF':
            if self.current.kind in ('record', 'enum'):
                items.append(self.declaration())
                continue
            if self.current.kind == 'use':
                token = self.take()
                items.append(Use(self.take('NAME').value, token))
                self.take('NEWLINE')
                continue
            start = self.take('work')
            name = self.take('NAME').value
            self.take('(')
            params = []
            if self.current.kind != ')':
                while True:
                    token = self.take('NAME')
                    self.take(':')
                    params.append((token.value, self.type_name(), token))
                    if not self.accept(','):
                        break
            self.take(')')
            self.take('->')
            result = self.type_name()
            items.append(Work(name, params, result, self.block(), start))
        return items

    def declaration(self):
        start = self.take()
        name = self.take('NAME').value
        self.take(':')
        self.take('NEWLINE')
        self.take('INDENT')
        items = []
        while self.current.kind not in ('DEDENT', 'EOF'):
            token = self.take('NAME')
            if start.kind == 'record':
                self.take(':')
                items.append((token.value, self.type_name(), token))
            else:
                items.append((token.value, token))
            self.take('NEWLINE')
        self.take('DEDENT')
        if not items:
            raise Diagnostic(f'A {start.kind} needs at least one {"field" if start.kind == "record" else "variant"}.', start)
        return (Record if start.kind == 'record' else Enum)(name, items, start)

    def block(self):
        self.take(':')
        self.take('NEWLINE')
        self.take('INDENT')
        body = []
        while self.current.kind not in ('DEDENT', 'EOF'):
            body.append(self.statement())
        self.take('DEDENT')
        return body

    def arms(self):
        self.take(':')
        self.take('NEWLINE')
        self.take('INDENT')
        arms = []
        while self.current.kind not in ('DEDENT', 'EOF'):
            token = self.current
            if self.accept('otherwise'):
                arms.append(Arm(None, None, self.block(), token))
                continue
            head = self.take('NAME').value
            qualifier = self.take('NAME').value if self.accept('.') else None
            binding = self.take('NAME').value if self.current.kind == 'NAME' else None
            arms.append(Arm((head, qualifier), binding, self.block(), token))
        self.take('DEDENT')
        if not arms:
            raise Diagnostic('A match needs at least one case.', self.current)
        return arms

    def statement(self):
        token = self.current
        kind = token.kind
        if kind in ('vow', 'let'):
            self.take()
            name = self.take('NAME').value
            annotation = self.type_name() if self.accept(':') else None
            self.take('=')
            statement = Stmt(kind, token, (name, annotation), [self.expression()])
        elif kind == 'discern':
            self.take()
            condition = self.expression()
            yes = self.block()
            no = self.block() if self.accept('otherwise') else []
            return Stmt(kind, token, None, [condition, yes, no])
        elif kind == 'match':
            self.take()
            subject = self.expression()
            return Stmt(kind, token, None, [subject, self.arms()])
        elif kind == 'while':
            self.take()
            condition = self.expression()
            return Stmt(kind, token, None, [condition, self.block()])
        elif kind == 'for':
            self.take()
            name = self.take('NAME').value
            self.take('in')
            iterable = self.expression()
            return Stmt(kind, token, name, [iterable, self.block()])
        elif kind in ('covenant', 'witness'):
            self.take()
            condition = self.expression()
            message = self.expression() if self.accept(',') else Expr('text', token, 'The stated condition did not hold.')
            statement = Stmt(kind, token, None, [condition, message])
        elif kind == 'return':
            self.take()
            statement = Stmt(kind, token, None, [] if self.current.kind == 'NEWLINE' else [self.expression()])
        elif kind == 'pass':
            self.take()
            statement = Stmt(kind, token)
        elif kind == 'NAME' and self.tokens[self.index + 1].kind == '=':
            name = self.take().value
            self.take('=')
            statement = Stmt('assign', token, name, [self.expression()])
        else:
            expression = self.expression()
            if expression.kind in ('field', 'index') and self.current.kind == '=':
                what = 'Record fields' if expression.kind == 'field' else 'List items'
                raise Diagnostic(f'{what} cannot change in place. Build a new value instead.', self.current)
            statement = Stmt('expression', token, None, [expression])
        self.take('NEWLINE')
        return statement

    PRECEDENCE = {'or': 1, 'and': 2, '==': 3, '!=': 3, '<': 3, '>': 3, '<=': 3, '>=': 3, '+': 4, '-': 4, '*': 5, '/': 5, '//': 5, '%': 5}

    def items(self, closing):
        values = []
        if self.current.kind != closing:
            while True:
                values.append(self.expression())
                if not self.accept(','):
                    break
        self.take(closing)
        return values

    def expression(self, minimum=0):
        token = self.take()
        if token.kind in ('INT', 'REAL', 'TEXT', 'true', 'false'):
            left = Expr({'INT': 'int', 'REAL': 'real', 'TEXT': 'text', 'true': 'bool', 'false': 'bool'}[token.kind], token, token.value if token.kind not in ('true', 'false') else token.kind == 'true')
        elif token.kind == 'NAME':
            if self.accept('('):
                left = Expr('call', token, token.value, self.items(')'))
            else:
                left = Expr('name', token, token.value)
        elif token.kind == '[':
            left = Expr('list', token, None, self.items(']'))
        elif token.kind == '(':
            left = self.expression()
            self.take(')')
        elif token.kind in ('-', 'not', '+'):
            left = Expr('unary', token, token.kind, [self.expression(3 if token.kind == 'not' else 6)])
        else:
            raise Diagnostic('Expected a value, a work call, or a parenthesized expression.', token)
        while self.current.kind in ('.', '['):
            if self.accept('.'):
                left = Expr('field', self.current, self.take('NAME').value, [left])
            else:
                bracket = self.take('[')
                index = self.expression()
                self.take(']')
                left = Expr('index', bracket, None, [left, index])
        compared = False
        while self.PRECEDENCE.get(self.current.kind, -1) >= minimum:
            operator = self.take()
            precedence = self.PRECEDENCE[operator.kind]
            if precedence == 3 and compared:
                raise Diagnostic('Write comparisons separately and join them with and.', operator)
            compared = precedence == 3
            right = self.expression(precedence + 1)
            left = Expr('binary', operator, operator.kind, [left, right])
        return left
