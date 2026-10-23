#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
UNG-Script 1.0 - a simple, plain-English language for building websites,
together with its own web server.

Everything lives in this one file. It needs only Python 3.8 or newer.
Nothing else to install.

    python ung.py new mysite        make a starter website in the folder "mysite"
    python ung.py serve mysite      start the web server -> http://localhost:8000
    python ung.py run page.ung      run one file and print what it shows
    python ung.py check page.ung    look for mistakes without running
"""

import sys, os, re, json, html as _html, math, time, datetime, sqlite3
import threading, difflib, mimetypes, socket, urllib.parse, traceback
import random as _random
from decimal import Decimal, ROUND_HALF_UP
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

VERSION = "1.0"
MAX_STEPS = 3_000_000          # stops pages that loop forever
MAX_SECONDS = 10               # longest a page may run
MAX_DEPTH = 150                # how deep functions may call each other
MAX_TEXT = 10_000_000          # biggest text a page may build
MAX_BODY = 10 * 1024 * 1024    # biggest form a visitor may send

sys.setrecursionlimit(30000)


# ════════════════════════════════════════════════════════════════════
#  Errors and signals
# ════════════════════════════════════════════════════════════════════

class UngError(Exception):
    """A mistake in a UNG-Script program, explained in plain words."""
    def __init__(self, message, line=None, file=None):
        super().__init__(message)
        self.message, self.line, self.file = message, line, file

    def where(self):
        bits = []
        if self.file:
            bits.append(os.path.basename(self.file))
        if self.line:
            bits.append("line %d" % self.line)
        return ", ".join(bits)

    def __str__(self):
        w = self.where()
        return "%s: %s" % (w, self.message) if w else self.message


class ReturnSignal(Exception):
    def __init__(self, value):
        self.value = value

class StopSignal(Exception): pass
class SkipSignal(Exception): pass
class FinishSignal(Exception): pass

class RedirectSignal(Exception):
    def __init__(self, url):
        self.url = url


# ════════════════════════════════════════════════════════════════════
#  1. Tokenizer - cuts the code into words and symbols
# ════════════════════════════════════════════════════════════════════

KEYWORDS = {
    "set", "show", "show_html", "if", "then", "else", "end", "while",
    "repeat", "times", "for", "each", "in", "from", "to", "step",
    "function", "return", "stop", "skip", "finish", "and", "or", "not",
    "is", "true", "false", "nothing", "add", "remove", "include",
}
TWO_CHAR_OPS = ("==", "!=", "<=", ">=")
ONE_CHAR_OPS = "+-*/%=<>()[]{},.:"
# Phones often turn " into curly quotes, so accept those too.
QUOTES = {'"': '"“”', '“': '"“”', '”': '"“”',
          "'": "'‘’", '‘': "'‘’", '’': "'‘’"}
ESCAPES = {"n": "\n", "t": "\t", "\\": "\\", '"': '"', "'": "'", "{": "{", "}": "}"}


class Tok:
    __slots__ = ("kind", "value", "line")

    def __init__(self, kind, value, line):
        self.kind, self.value, self.line = kind, value, line

    def describe(self):
        return {"NL": "the end of the line", "EOF": "the end of the file",
                "STR": "some text in quotes", "HTML": "HTML",
                "ECHO": "'{{'", "ECHO_END": "'}}'"}.get(self.kind, "'%s'" % (self.value,))


def read_string(src, i, line):
    closers = QUOTES[src[i]]
    i += 1
    n = len(src)
    parts, buf = [], []
    while True:
        if i >= n or src[i] == "\n":
            raise UngError("This text is missing its closing quote mark.", line)
        ch = src[i]
        if ch == "\\" and i + 1 < n and src[i + 1] in ESCAPES:
            buf.append(ESCAPES[src[i + 1]])
            i += 2
            continue
        if ch in closers:
            i += 1
            break
        if ch == "{":
            j = src.find("}", i)
            nl = src.find("\n", i)
            if j == -1 or (nl != -1 and nl < j):
                raise UngError("A '{' inside text needs a matching '}'. "
                               "To show a plain { write \\{ instead.", line)
            code = src[i + 1:j]
            if not code.strip():
                raise UngError("There's an empty {} inside this text. "
                               "Put a name inside, like {name}.", line)
            if buf:
                parts.append("".join(buf))
                buf = []
            parts.append(("code", code, line))
            i = j + 1
            continue
        buf.append(ch)
        i += 1
    if buf or not parts:
        parts.append("".join(buf))
    return i, Tok("STR", parts, line)


def tokenize_code(src, line, out):
    """Turn code into tokens, appending to `out`. Returns the last line number."""
    i, n = 0, len(src)
    while i < n:
        c = src[i]
        if c == "\n":
            out.append(Tok("NL", None, line))
            line += 1
            i += 1
        elif c in " \t\r﻿ ":
            i += 1
        elif c == "#":
            while i < n and src[i] != "\n":
                i += 1
        elif c.isdigit():
            j = i
            while j < n and src[j].isdigit():
                j += 1
            if j + 1 < n and src[j] == "." and src[j + 1].isdigit():
                j += 1
                while j < n and src[j].isdigit():
                    j += 1
                out.append(Tok("NUM", float(src[i:j]), line))
            else:
                out.append(Tok("NUM", int(src[i:j]), line))
            i = j
        elif c.isalpha() or c == "_":
            j = i
            while j < n and (src[j].isalnum() or src[j] == "_"):
                j += 1
            word = src[i:j]
            if word.lower() in KEYWORDS:
                out.append(Tok("KW", word.lower(), line))
            else:
                out.append(Tok("NAME", word, line))
            i = j
        elif c in QUOTES:
            i, tok = read_string(src, i, line)
            out.append(tok)
        elif src[i:i + 2] in TWO_CHAR_OPS:
            out.append(Tok("OP", src[i:i + 2], line))
            i += 2
        elif c in ONE_CHAR_OPS:
            out.append(Tok("OP", c, line))
            i += 1
        else:
            raise UngError("I don't understand the symbol '%s' here." % c, line)
    return line


OPEN_RE = re.compile(r"<ung>|\{\{", re.I)


def tokenize_template(src):
    """A page: plain HTML, with code inside <ung> ... </ung> and values inside {{ }}."""
    src = src.replace("\r\n", "\n")
    low = src.lower()
    out, line, pos = [], 1, 0
    while True:
        m = OPEN_RE.search(src, pos)
        text = src[pos:m.start()] if m else src[pos:]
        if text:
            stray = text.lower().find("</ung>")
            if stray != -1:
                raise UngError("There's a </ung> here without a <ung> before it.",
                               line + text.count("\n", 0, stray))
            out.append(Tok("HTML", text, line))
            line += text.count("\n")
        if not m:
            break
        if m.group(0) == "{{":
            end = src.find("}}", m.end())
            if end == -1:
                raise UngError("A '{{' is never closed with '}}'.", line)
            code = src[m.end():end]
            if not code.strip():
                raise UngError("There's an empty {{ }}. Put a value inside, like {{ name }}.", line)
            out.append(Tok("ECHO", None, line))
            tmp = []
            tokenize_code(code, line, tmp)
            out.extend(t for t in tmp if t.kind != "NL")
            out.append(Tok("ECHO_END", None, line))
            line += code.count("\n")
            pos = end + 2
        else:
            end = low.find("</ung>", m.end())
            if end == -1:
                raise UngError("This <ung> block is never closed with </ung>.", line)
            code = src[m.end():end]
            line = tokenize_code(code, line, out)
            out.append(Tok("NL", None, line))
            pos = end + 6
    out.append(Tok("EOF", None, line))
    return out


def tokenize_script(src):
    """Plain code with no HTML around it (used by the Playground)."""
    out = []
    line = tokenize_code(src.replace("\r\n", "\n"), 1, out)
    out.append(Tok("EOF", None, line))
    return out


# ════════════════════════════════════════════════════════════════════
#  2. Parser - works out the meaning of each line
# ════════════════════════════════════════════════════════════════════

ASSIGNABLE = ("var", "index", "attr")


class Parser:
    def __init__(self, toks):
        self.toks = toks
        self.i = 0
        self.loops = 0          # are we inside a loop? (for stop / skip)
        self.in_function = 0

    # --- small helpers ---
    def peek(self, k=0):
        return self.toks[min(self.i + k, len(self.toks) - 1)]

    def next(self):
        t = self.toks[self.i]
        if t.kind != "EOF":
            self.i += 1
        return t

    def is_kw(self, word, k=0):
        t = self.peek(k)
        return t.kind == "KW" and t.value == word

    def is_op(self, op, k=0):
        t = self.peek(k)
        return t.kind == "OP" and t.value == op

    def accept_kw(self, word):
        if self.is_kw(word):
            self.next()
            return True
        return False

    def accept_op(self, op):
        if self.is_op(op):
            self.next()
            return True
        return False

    def expect_kw(self, word, hint=None):
        if not self.accept_kw(word):
            t = self.peek()
            msg = "I expected '%s' here, but found %s." % (word, t.describe())
            raise UngError(msg + (" " + hint if hint else ""), t.line)

    def expect_op(self, op, hint=None):
        if not self.accept_op(op):
            t = self.peek()
            msg = "I expected '%s' here, but found %s." % (op, t.describe())
            raise UngError(msg + (" " + hint if hint else ""), t.line)

    def expect_name(self, what):
        t = self.peek()
        if t.kind == "NAME":
            self.next()
            return t.value
        if t.kind == "KW":
            raise UngError("'%s' is a special word in UNG-Script, so it can't be used as %s. "
                           "Pick a different name." % (t.value, what), t.line)
        raise UngError("I expected %s here, but found %s." % (what, t.describe()), t.line)

    def skip_nl(self):
        while self.peek().kind == "NL":
            self.next()

    def at_stmt_end(self):
        t = self.peek()
        return (t.kind in ("NL", "EOF", "HTML", "ECHO")
                or (t.kind == "KW" and t.value in ("end", "else")))

    def end_stmt(self):
        t = self.peek()
        if t.kind == "NL":
            self.next()
        elif not self.at_stmt_end():
            raise UngError("I didn't expect %s here. Put each instruction on its own line."
                           % t.describe(), t.line)

    # --- program structure ---
    def parse_program(self):
        body = self.block((), None)
        return body

    def block(self, stops, opener):
        stmts = []
        while True:
            t = self.peek()
            if t.kind == "NL":
                self.next()
                continue
            if t.kind == "EOF":
                if opener is not None:
                    raise UngError("The '%s' on line %d is never closed. Add 'end' after its last line."
                                   % (opener.value, opener.line), opener.line)
                return stmts
            if t.kind == "KW" and t.value in stops:
                return stmts
            stmts.append(self.statement())

    def loop_body(self, opener):
        self.loops += 1
        try:
            body = self.block(("end",), opener)
        finally:
            self.loops -= 1
        self.expect_kw("end")
        self.end_stmt()
        return body

    def cond_expr(self):
        e = self.expr()
        if self.is_op("="):
            raise UngError("To compare two things use 'is' (or '=='). A single '=' is only for "
                           "giving a name a value.", self.peek().line)
        return e

    # --- statements ---
    def statement(self):
        t = self.peek()
        L = t.line
        if t.kind == "HTML":
            self.next()
            return ("html", L, t.value)
        if t.kind == "ECHO":
            self.next()
            e = self.expr()
            if self.peek().kind != "ECHO_END":
                raise UngError("Inside {{ }} put just one value, like {{ name }}.", L)
            self.next()
            return ("echo", L, e)
        if t.kind == "KW":
            w = t.value
            if w == "set":
                self.next()
                target = self.postfix()
                if target[0] not in ASSIGNABLE:
                    raise UngError("After 'set' put a name, like: set score = 10", L)
                if not (self.accept_op("=") or self.accept_kw("to")):
                    raise UngError("After the name put '=' (or 'to') and then the value, "
                                   "like: set score = 10", L)
                val = self.expr()
                self.end_stmt()
                return ("assign", L, target, val)
            if w in ("show", "show_html"):
                self.next()
                if self.at_stmt_end():
                    raise UngError("'%s' needs something to show, like: show \"Hello\"" % w, L)
                e = self.expr()
                self.end_stmt()
                return ("show", L, e, w == "show_html")
            if w == "if":
                return self.if_stmt()
            if w == "while":
                self.next()
                cond = self.cond_expr()
                return ("while", L, cond, self.loop_body(t))
            if w == "repeat":
                self.next()
                count = self.expr()
                self.expect_kw("times", "Write it like: repeat 5 times")
                return ("repeat", L, count, self.loop_body(t))
            if w == "for":
                self.next()
                if self.accept_kw("each"):
                    var = self.expect_name("a name for each item")
                    self.expect_kw("in", "Write it like: for each fruit in fruits")
                    it = self.expr()
                    return ("foreach", L, var, it, self.loop_body(t))
                var = self.expect_name("a counter name")
                self.expect_kw("from", "Write it like: for i from 1 to 10   "
                                       "(or: for each item in my_list)")
                a = self.expr()
                self.expect_kw("to", "Write it like: for i from 1 to 10")
                b = self.expr()
                step = self.expr() if self.accept_kw("step") else None
                return ("forrange", L, var, a, b, step, self.loop_body(t))
            if w == "function":
                self.next()
                name = self.expect_name("a function name")
                self.expect_op("(", "A function needs brackets after its name, like: function greet(name)")
                params = []
                if not self.is_op(")"):
                    while True:
                        p = self.expect_name("a name for the input")
                        if p in params:
                            raise UngError("The input '%s' is listed twice." % p, L)
                        params.append(p)
                        if not self.accept_op(","):
                            break
                self.expect_op(")")
                saved = self.loops
                self.loops = 0
                self.in_function += 1
                try:
                    body = self.block(("end",), t)
                finally:
                    self.loops = saved
                    self.in_function -= 1
                self.expect_kw("end")
                self.end_stmt()
                return ("func", L, name, params, body)
            if w == "return":
                self.next()
                e = None if self.at_stmt_end() else self.expr()
                self.end_stmt()
                return ("return", L, e)
            if w in ("stop", "skip"):
                if not self.loops:
                    raise UngError("'%s' only works inside a loop (repeat, for, while)." % w, L)
                self.next()
                self.end_stmt()
                return (w, L)
            if w == "finish":
                self.next()
                self.end_stmt()
                return ("finish", L)
            if w in ("add", "remove"):
                self.next()
                val = self.expr()
                joiner = "to" if w == "add" else "from"
                self.expect_kw(joiner, "Write it like: %s item %s my_list" % (w, joiner))
                target = self.postfix()
                if target[0] not in ASSIGNABLE:
                    raise UngError("After '%s' put the name of a list, like: %s item %s my_list"
                                   % (joiner, w, joiner), L)
                self.end_stmt()
                return (w, L, val, target)
            if w == "include":
                self.next()
                e = self.expr()
                self.end_stmt()
                return ("include", L, e)
            if w == "end":
                raise UngError("There's an 'end' here, but nothing open for it to close.", L)
            if w == "else":
                raise UngError("There's an 'else' here without a matching 'if' before it.", L)
        e = self.expr()
        if self.is_op("="):
            if e[0] not in ASSIGNABLE:
                raise UngError("The left side of '=' must be a name, like: score = 10", L)
            self.next()
            val = self.expr()
            self.end_stmt()
            return ("assign", L, e, val)
        if e[0] != "call":
            raise UngError("This line has a value but doesn't do anything with it. "
                           "Did you forget 'show' at the start?", L)
        self.end_stmt()
        return ("exprstmt", L, e)

    def if_stmt(self):
        t = self.next()
        branches = []
        cond = self.cond_expr()
        self.accept_kw("then")
        branches.append((cond, self.block(("else", "end"), t)))
        else_body = None
        while self.accept_kw("else"):
            if self.accept_kw("if"):
                cond = self.cond_expr()
                self.accept_kw("then")
                branches.append((cond, self.block(("else", "end"), t)))
            else:
                else_body = self.block(("end",), t)
                break
        self.expect_kw("end", "Every 'if' needs an 'end' after its last line.")
        self.end_stmt()
        return ("if", t.line, branches, else_body)

    # --- expressions, lowest priority first ---
    def expr(self):
        return self.or_expr()

    def or_expr(self):
        a = self.and_expr()
        while self.is_kw("or"):
            L = self.next().line
            a = ("or", L, a, self.and_expr())
        return a

    def and_expr(self):
        a = self.not_expr()
        while self.is_kw("and"):
            L = self.next().line
            a = ("and", L, a, self.not_expr())
        return a

    def not_expr(self):
        if self.is_kw("not"):
            L = self.next().line
            return ("not", L, self.not_expr())
        return self.compare()

    def compare(self):
        a = self.add_expr()
        t = self.peek()
        if t.kind == "OP" and t.value in ("==", "!=", "<", ">", "<=", ">="):
            self.next()
            op = t.value
        elif self.is_kw("is"):
            self.next()
            op = "!=" if self.accept_kw("not") else "=="
        else:
            return a
        return ("bin", t.line, op, a, self.add_expr())

    def add_expr(self):
        a = self.mul_expr()
        while self.peek().kind == "OP" and self.peek().value in ("+", "-"):
            t = self.next()
            a = ("bin", t.line, t.value, a, self.mul_expr())
        return a

    def mul_expr(self):
        a = self.unary()
        while self.peek().kind == "OP" and self.peek().value in ("*", "/", "%"):
            t = self.next()
            a = ("bin", t.line, t.value, a, self.unary())
        return a

    def unary(self):
        if self.is_op("-"):
            L = self.next().line
            return ("neg", L, self.unary())
        return self.postfix()

    def postfix(self):
        e = self.atom()
        while True:
            t = self.peek()
            if t.kind != "OP":
                return e
            if t.value == "(":
                self.next()
                e = ("call", t.line, e, self.items(")"))
            elif t.value == "[":
                self.next()
                self.skip_nl()
                idx = self.expr()
                self.skip_nl()
                self.expect_op("]")
                e = ("index", t.line, e, idx)
            elif t.value == ".":
                self.next()
                nt = self.peek()
                if nt.kind not in ("NAME", "KW"):
                    raise UngError("After '.' put the name of a part, like person.name", t.line)
                self.next()
                e = ("attr", t.line, e, nt.value)
            else:
                return e

    def items(self, close):
        out = []
        self.skip_nl()
        if self.accept_op(close):
            return out
        while True:
            self.skip_nl()
            out.append(self.expr())
            self.skip_nl()
            if self.accept_op(close):
                return out
            if not self.accept_op(","):
                t = self.peek()
                raise UngError("I expected ',' or '%s' here, but found %s." % (close, t.describe()), t.line)
            self.skip_nl()
            if self.accept_op(close):
                return out

    def map_items(self):
        pairs = []
        self.skip_nl()
        if self.accept_op("}"):
            return pairs
        while True:
            self.skip_nl()
            t = self.peek()
            if t.kind in ("NAME", "KW") and self.is_op(":", 1):
                self.next()
                key = ("lit", t.line, t.value)
            else:
                key = self.expr()
            self.skip_nl()
            self.expect_op(":", 'In a map, write each entry like:  name: "Sam"')
            self.skip_nl()
            pairs.append((key, self.expr()))
            self.skip_nl()
            if self.accept_op("}"):
                return pairs
            if not self.accept_op(","):
                t = self.peek()
                raise UngError("I expected ',' or '}' here, but found %s." % t.describe(), t.line)
            self.skip_nl()
            if self.accept_op("}"):
                return pairs

    def atom(self):
        t = self.peek()
        L = t.line
        if t.kind == "NUM":
            self.next()
            return ("lit", L, t.value)
        if t.kind == "STR":
            self.next()
            return self.string_node(t)
        if t.kind == "NAME":
            self.next()
            return ("var", L, t.value)
        if t.kind == "KW":
            if t.value in ("true", "false", "nothing"):
                self.next()
                return ("lit", L, {"true": True, "false": False, "nothing": None}[t.value])
            raise UngError("'%s' is a special word and can't be used here." % t.value, L)
        if t.kind == "OP":
            if t.value == "(":
                self.next()
                self.skip_nl()
                e = self.expr()
                self.skip_nl()
                self.expect_op(")", "Every '(' needs a closing ')'.")
                return e
            if t.value == "[":
                self.next()
                return ("list", L, self.items("]"))
            if t.value == "{":
                self.next()
                return ("map", L, self.map_items())
        if t.kind in ("NL", "EOF", "ECHO_END", "HTML", "ECHO"):
            raise UngError("A value is missing here.", L)
        raise UngError("I didn't expect %s here." % t.describe(), L)

    def string_node(self, t):
        parts = []
        for p in t.value:
            if isinstance(p, str):
                parts.append(p)
                continue
            toks = []
            tokenize_code(p[1], p[2], toks)
            toks = [x for x in toks if x.kind != "NL"]
            toks.append(Tok("EOF", None, p[2]))
            sub = Parser(toks)
            e = sub.expr()
            if sub.peek().kind != "EOF":
                raise UngError("Inside { } in text put just one value, like {name}.", p[2])
            parts.append(e)
        if all(isinstance(p, str) for p in parts):
            return ("lit", t.line, "".join(parts))
        return ("str", t.line, parts)


def parse_page(src):
    return Parser(tokenize_template(src)).parse_program()


def parse_script(src):
    return Parser(tokenize_script(src)).parse_program()


# ════════════════════════════════════════════════════════════════════
#  3. Values - how numbers, text, lists and maps behave
# ════════════════════════════════════════════════════════════════════

class Function:
    def __init__(self, name, params, body, file):
        self.name, self.params, self.body, self.file = name, params, body, file


class Builtin:
    def __init__(self, name, fn, lo, hi, usage, doc):
        self.name, self.fn, self.lo, self.hi, self.usage, self.doc = name, fn, lo, hi, usage, doc


NUM_RE = re.compile(r"^-?\d+(\.\d+)?$")


def numeric(v):
    """The number inside v, or None. Text like "42" counts as a number."""
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return v
    if isinstance(v, str) and len(v) < 40 and NUM_RE.match(v):
        return float(v) if "." in v else int(v)
    return None


def tidy(n):
    if isinstance(n, float) and n.is_integer() and abs(n) < 1e15:
        return int(n)
    return n


def to_text(v, nested=False):
    if v is None:
        return "nothing" if nested else ""
    if v is True:
        return "true"
    if v is False:
        return "false"
    if isinstance(v, float):
        if v != v or v in (float("inf"), float("-inf")):
            return str(v)
        if v.is_integer() and abs(v) < 1e15:
            return str(int(v))
        s = ("%.10f" % v).rstrip("0").rstrip(".")
        return s if s not in ("", "-0") else "0"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, str):
        return '"%s"' % v if nested else v
    if isinstance(v, list):
        return "[" + ", ".join(to_text(x, True) for x in v) + "]"
    if isinstance(v, dict):
        return "{" + ", ".join("%s: %s" % (k, to_text(x, True)) for k, x in v.items()) + "}"
    if isinstance(v, (Function, Builtin)):
        return "function %s" % v.name
    return str(v)


def type_name(v):
    if v is None:
        return "nothing"
    if isinstance(v, bool):
        return "true/false"
    if isinstance(v, (int, float)):
        return "number"
    if isinstance(v, str):
        return "text"
    if isinstance(v, list):
        return "list"
    if isinstance(v, dict):
        return "map"
    return "function"


def describe(v):
    if v is None:
        return "nothing"
    if isinstance(v, bool):
        return to_text(v)
    if isinstance(v, (int, float)):
        return "the number %s" % to_text(v)
    if isinstance(v, str):
        s = v if len(v) <= 30 else v[:27] + "..."
        return 'the text "%s"' % s
    if isinstance(v, list):
        return "a list"
    if isinstance(v, dict):
        return "a map"
    return "a function"


def truthy(v):
    if v is None or v is False:
        return False
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return v != 0
    if isinstance(v, (str, list, dict)):
        return len(v) > 0
    return True


def ung_equal(a, b):
    if isinstance(a, bool) or isinstance(b, bool):
        return isinstance(a, bool) and isinstance(b, bool) and a == b
    if isinstance(a, (int, float)) or isinstance(b, (int, float)):
        na, nb = numeric(a), numeric(b)
        return na is not None and nb is not None and na == nb
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(ung_equal(x, y) for x, y in zip(a, b))
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(ung_equal(a[k], b[k]) for k in a)
    return type(a) is type(b) and a == b


def key_of(v):
    if isinstance(v, str):
        return v
    if isinstance(v, (int, float, bool)) or v is None:
        return to_text(v)
    raise UngError("A map key must be text or a number, not %s." % describe(v))


def binary(op, a, b):
    if op == "+":
        if isinstance(a, list) and isinstance(b, list):
            return a + b
        if isinstance(a, str) or isinstance(b, str):
            # If either side is text, + joins them: "Age: " + 5 gives "Age: 5"
            r = to_text(a) + to_text(b)
        else:
            na, nb = numeric(a), numeric(b)
            if na is not None and nb is not None:
                return tidy(na + nb)
            raise UngError("I can't add %s and %s together." % (describe(a), describe(b)))
        if len(r) > MAX_TEXT:
            raise UngError("This text has grown too big.")
        return r
    if op in ("-", "*", "/", "%"):
        na, nb = numeric(a), numeric(b)
        if op == "*" and isinstance(a, str) and na is None and isinstance(nb, int):
            if len(a) * max(nb, 0) > MAX_TEXT:
                raise UngError("This text would be too big.")
            return a * nb
        if na is None or nb is None:
            raise UngError("'%s' only works with numbers, but here it got %s and %s."
                           % (op, describe(a), describe(b)))
        if op == "-":
            return tidy(na - nb)
        if op == "*":
            return tidy(na * nb)
        if nb == 0:
            raise UngError("You can't divide by zero.")
        return tidy(na / nb if op == "/" else na % nb)
    if op == "==":
        return ung_equal(a, b)
    if op == "!=":
        return not ung_equal(a, b)
    na, nb = numeric(a), numeric(b)
    if na is not None and nb is not None:
        x, y = na, nb
    elif isinstance(a, str) and isinstance(b, str):
        x, y = a, b
    else:
        raise UngError("I can't tell if %s is bigger or smaller than %s." % (describe(a), describe(b)))
    return {"<": x < y, ">": x > y, "<=": x <= y, ">=": x >= y}[op]


# ════════════════════════════════════════════════════════════════════
#  4. Storage - save(), load(), add_record() ...
# ════════════════════════════════════════════════════════════════════

def check_saveable(v):
    if v is None or isinstance(v, (bool, int, float, str)):
        return
    if isinstance(v, list):
        for x in v:
            check_saveable(x)
    elif isinstance(v, dict):
        for x in v.values():
            check_saveable(x)
    else:
        raise UngError("Only text, numbers, true/false, lists and maps can be saved, not a function.")


def stamp():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M")


class Storage:
    """Keeps saved data in one small database file (_data.sqlite) in the site folder."""
    def __init__(self, path):
        self.path = path
        self.lock = threading.Lock()
        self.db = None

    def conn(self):
        if self.db is None:
            self.db = sqlite3.connect(self.path, check_same_thread=False)
            self.db.execute("CREATE TABLE IF NOT EXISTS saved (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            self.db.execute("CREATE TABLE IF NOT EXISTS records (id INTEGER PRIMARY KEY AUTOINCREMENT, "
                            "tbl TEXT NOT NULL, data TEXT NOT NULL, created TEXT NOT NULL)")
            self.db.commit()
        return self.db

    def save(self, key, value):
        with self.lock:
            c = self.conn()
            c.execute("INSERT OR REPLACE INTO saved(key, value) VALUES (?, ?)", (key, json.dumps(value)))
            c.commit()

    def load(self, key):
        with self.lock:
            row = self.conn().execute("SELECT value FROM saved WHERE key = ?", (key,)).fetchone()
        return (True, json.loads(row[0])) if row else (False, None)

    def add_record(self, tbl, data):
        with self.lock:
            c = self.conn()
            cur = c.execute("INSERT INTO records(tbl, data, created) VALUES (?, ?, ?)",
                            (tbl, json.dumps(data), stamp()))
            c.commit()
            return cur.lastrowid

    def get_records(self, tbl):
        with self.lock:
            rows = self.conn().execute("SELECT id, data, created FROM records WHERE tbl = ? ORDER BY id",
                                       (tbl,)).fetchall()
        out = []
        for rid, data, created in rows:
            rec = {"id": rid}
            rec.update(json.loads(data))
            rec["id"] = rid
            rec["created"] = created
            out.append(rec)
        return out

    def delete_record(self, tbl, rid):
        with self.lock:
            c = self.conn()
            cur = c.execute("DELETE FROM records WHERE tbl = ? AND id = ?", (tbl, rid))
            c.commit()
            return cur.rowcount > 0

    def clear_records(self, tbl):
        with self.lock:
            c = self.conn()
            cur = c.execute("DELETE FROM records WHERE tbl = ?", (tbl,))
            c.commit()
            return cur.rowcount


class MemoryStorage:
    """Same as Storage, but forgets everything afterwards (used by the Playground)."""
    def __init__(self):
        self.saved, self.records, self.next_id = {}, [], 1

    def save(self, key, value):
        self.saved[key] = json.loads(json.dumps(value))

    def load(self, key):
        return (key in self.saved, json.loads(json.dumps(self.saved.get(key))))

    def add_record(self, tbl, data):
        rid = self.next_id
        self.next_id += 1
        self.records.append((rid, tbl, json.loads(json.dumps(data)), stamp()))
        return rid

    def get_records(self, tbl):
        out = []
        for rid, t, data, created in self.records:
            if t == tbl:
                rec = {"id": rid}
                rec.update(json.loads(json.dumps(data)))
                rec["id"], rec["created"] = rid, created
                out.append(rec)
        return out

    def delete_record(self, tbl, rid):
        before = len(self.records)
        self.records = [r for r in self.records if not (r[1] == tbl and r[0] == rid)]
        return len(self.records) < before

    def clear_records(self, tbl):
        before = len(self.records)
        self.records = [r for r in self.records if r[1] != tbl]
        return before - len(self.records)


# ════════════════════════════════════════════════════════════════════
#  5. Built-in functions
# ════════════════════════════════════════════════════════════════════

BUILTINS = {}


def builtin(usage, doc, lo=None, hi=None):
    """Register a built-in. `usage` looks like 'length(x)' or 'round(x, digits?)'."""
    name = usage.split("(")[0]
    inside = usage[len(name) + 1:-1].strip()
    params = [p.strip() for p in inside.split(",")] if inside else []
    need = len([p for p in params if not p.endswith("?") and p != "..."])
    most = 99 if "..." in params else len(params)

    def deco(f):
        BUILTINS[name] = Builtin(name, f, need if lo is None else lo, most if hi is None else hi, usage, doc)
        return f
    return deco


def need_number(v, fname):
    n = numeric(v)
    if n is None:
        raise UngError("%s() needs a number, but got %s." % (fname, describe(v)))
    return n


def need_whole(v, fname):
    n = need_number(v, fname)
    if isinstance(n, float) and not n.is_integer():
        raise UngError("%s() needs a whole number, but got %s." % (fname, to_text(n)))
    return int(n)


def need_list(v, fname):
    if not isinstance(v, list):
        raise UngError("%s() needs a list, but got %s." % (fname, describe(v)))
    return v


def need_map(v, fname):
    if not isinstance(v, dict):
        raise UngError("%s() needs a map, but got %s." % (fname, describe(v)))
    return v


@builtin("length(x)", "How many items are in a list or map, or how many letters are in text.")
def b_length(rt, x):
    if isinstance(x, (str, list, dict)):
        return len(x)
    if x is None:
        return 0
    if isinstance(x, (int, float)) and not isinstance(x, bool):
        return len(to_text(x))
    raise UngError("length() needs text, a list or a map, but got %s." % describe(x))


@builtin("upper(text)", "Text in CAPITAL letters.")
def b_upper(rt, x):
    return to_text(x).upper()


@builtin("lower(text)", "Text in small letters.")
def b_lower(rt, x):
    return to_text(x).lower()


@builtin("trim(text)", "Text without spaces at the start and end.")
def b_trim(rt, x):
    return to_text(x).strip()


@builtin("text(x)", "Turns anything into text.")
def b_text(rt, x):
    return to_text(x)


@builtin("number(x)", 'Turns text like "42" into the number 42.')
def b_number(rt, x):
    n = numeric(x.strip() if isinstance(x, str) else x)
    if n is None:
        raise UngError("%s isn't a number. Use is_number() first to check." % describe(x))
    return n


@builtin("is_number(x)", 'true if x is a number or text like "42".')
def b_is_number(rt, x):
    return numeric(x.strip() if isinstance(x, str) else x) is not None


@builtin("round(x, digits?)", "Rounds a number. round(3.456, 2) gives 3.46.")
def b_round(rt, x, digits=0):
    n = need_number(x, "round")
    d = need_whole(digits, "round")
    q = Decimal(1).scaleb(-d)
    return tidy(float(Decimal(str(n)).quantize(q, rounding=ROUND_HALF_UP)))


@builtin("random(low, high)", "A random whole number from low to high (both included).")
def b_random(rt, lo, hi):
    a, b = need_whole(lo, "random"), need_whole(hi, "random")
    if a > b:
        a, b = b, a
    return _random.randint(a, b)


@builtin("pick(list)", "One random item from a list.")
def b_pick(rt, lst):
    need_list(lst, "pick")
    return _random.choice(lst) if lst else None


@builtin("now()", 'The date and time now, like "2026-10-22 18:40".')
def b_now(rt):
    return stamp()


@builtin("today()", 'Today\'s date, like "2026-10-22".')
def b_today(rt):
    return datetime.date.today().isoformat()


@builtin("hour()", "The hour now, from 0 to 23.")
def b_hour(rt):
    return datetime.datetime.now().hour


@builtin("contains(where, what)", "true if text contains a piece, a list contains an item, or a map has a key.")
def b_contains(rt, where, what):
    if isinstance(where, str):
        return to_text(what) in where
    if isinstance(where, list):
        return any(ung_equal(x, what) for x in where)
    if isinstance(where, dict):
        return key_of(what) in where
    if where is None:
        return False
    raise UngError("contains() needs text, a list or a map first, but got %s." % describe(where))


@builtin("starts_with(text, piece)", "true if text starts with piece.")
def b_starts(rt, t, p):
    return to_text(t).startswith(to_text(p))


@builtin("ends_with(text, piece)", "true if text ends with piece.")
def b_ends(rt, t, p):
    return to_text(t).endswith(to_text(p))


@builtin("find(text, piece)", "Position of piece inside text (1 = first letter), or 0 if not found.")
def b_find(rt, t, p):
    return to_text(t).find(to_text(p)) + 1


@builtin("replace(text, old, new)", "Text with every old piece swapped for new.")
def b_replace(rt, t, old, new):
    return to_text(t).replace(to_text(old), to_text(new))


@builtin("split(text, separator?)", 'Cuts text into a list. split("a,b", ",") gives ["a", "b"].')
def b_split(rt, t, sep=None):
    t = to_text(t)
    if sep is None or to_text(sep) == "":
        return t.split()
    return t.split(to_text(sep))


@builtin("join(list, separator?)", 'Glues a list into text. join(["a","b"], ", ") gives "a, b".')
def b_join(rt, lst, sep=""):
    need_list(lst, "join")
    return to_text(sep).join(to_text(x) for x in lst)


@builtin("part(x, start, end?)", "A piece of text or a list, from position start to end (both included).")
def b_part(rt, x, start, end=None):
    if not isinstance(x, (str, list)):
        raise UngError("part() needs text or a list, but got %s." % describe(x))
    s = need_whole(start, "part")
    e = len(x) if end is None else need_whole(end, "part")
    if s < 1:
        s = 1
    return x[s - 1:max(e, 0)]


@builtin("keys(map)", "A list of the names in a map.")
def b_keys(rt, m):
    return list(need_map(m, "keys").keys())


@builtin("values(map)", "A list of the values in a map.")
def b_values(rt, m):
    return list(need_map(m, "values").values())


def sort_key(x):
    n = numeric(x)
    return (0, n, "") if n is not None else (1, 0, to_text(x).lower())


@builtin("sort(list)", "A sorted copy of a list (numbers small to big, text A to Z).")
def b_sort(rt, lst):
    return sorted(need_list(lst, "sort"), key=sort_key)


@builtin("reverse(x)", "A list or text turned back to front.")
def b_reverse(rt, x):
    if isinstance(x, (list, str)):
        return x[::-1]
    raise UngError("reverse() needs a list or text, but got %s." % describe(x))


@builtin("first(list)", "The first item of a list (nothing if empty).")
def b_first(rt, lst):
    need_list(lst, "first")
    return lst[0] if lst else None


@builtin("last(list)", "The last item of a list (nothing if empty).")
def b_last(rt, lst):
    need_list(lst, "last")
    return lst[-1] if lst else None


def numbers_from(args, fname):
    vals = args[0] if len(args) == 1 and isinstance(args[0], list) else list(args)
    return [need_number(v, fname) for v in vals]


@builtin("sum(list)", "All the numbers in a list added up.")
def b_sum(rt, lst):
    return tidy(sum(numbers_from([need_list(lst, "sum")], "sum")))


@builtin("min(list or numbers...)", "The smallest number. min(4, 9) or min(my_list).", lo=1, hi=99)
def b_min(rt, *args):
    nums = numbers_from(args, "min")
    return min(nums) if nums else None


@builtin("max(list or numbers...)", "The biggest number. max(4, 9) or max(my_list).", lo=1, hi=99)
def b_max(rt, *args):
    nums = numbers_from(args, "max")
    return max(nums) if nums else None


@builtin("type_of(x)", 'What kind of value x is: "number", "text", "list", "map", "true/false" or "nothing".')
def b_type_of(rt, x):
    return type_name(x)


@builtin("escape(text)", "Makes text safe to put inside show_html.")
def b_escape(rt, x):
    return _html.escape(to_text(x))


@builtin("form(name?, default?)", "What a visitor typed in a form box (or in the web address). "
                                  "form() alone gives all of it as a map.", lo=0, hi=2)
def b_form(rt, name=None, default=""):
    req = rt.request or {}
    if name is None:
        d = dict(req.get("query") or {})
        d.update(req.get("form") or {})
        return d
    key = to_text(name)
    for src in (req.get("form") or {}, req.get("query") or {}):
        if key in src:
            return src[key]
    return default


@builtin("is_post()", "true when a visitor has just sent a form (method=\"post\").")
def b_is_post(rt):
    return (rt.request or {}).get("method") == "POST"


@builtin("page()", 'The address of this page, like "/guestbook".')
def b_page(rt):
    return (rt.request or {}).get("path", "/")


@builtin("redirect(address)", "Sends the visitor to another page, and stops this one.")
def b_redirect(rt, url):
    raise RedirectSignal(re.sub(r"[\r\n]", "", to_text(url)))


@builtin("save(name, value)", "Saves a value so it is still there next time (even after a restart).")
def b_save(rt, key, value):
    check_saveable(value)
    rt.storage.save(to_text(key), value)
    return None


@builtin("load(name, default?)", "Gets a saved value back. Gives default (or nothing) if it was never saved.")
def b_load(rt, key, default=None):
    found, value = rt.storage.load(to_text(key))
    return value if found else default


@builtin("add_record(table, map)", "Adds a record (a map) to a table and gives back its id number.")
def b_add_record(rt, tbl, data):
    need_map(data, "add_record")
    check_saveable(data)
    return rt.storage.add_record(to_text(tbl), data)


@builtin("get_records(table)", "All records in a table, as a list of maps. Each has .id and .created too.")
def b_get_records(rt, tbl):
    return rt.storage.get_records(to_text(tbl))


@builtin("delete_record(table, id)", "Deletes one record. Gives true if it was found.")
def b_delete_record(rt, tbl, rid):
    return rt.storage.delete_record(to_text(tbl), need_whole(rid, "delete_record"))


@builtin("clear_records(table)", "Deletes every record in a table. Gives how many were deleted.")
def b_clear_records(rt, tbl):
    return rt.storage.clear_records(to_text(tbl))


# ════════════════════════════════════════════════════════════════════
#  6. Interpreter - runs the program
# ════════════════════════════════════════════════════════════════════

_cache = {}
_cache_lock = threading.Lock()


def read_source(path):
    try:
        with open(path, encoding="utf-8-sig") as f:
            return f.read()
    except UnicodeDecodeError:
        raise UngError("This file isn't saved as plain UTF-8 text.", None, path)


def load_program(path):
    """Read and understand a page file (remembered until the file changes)."""
    st = os.stat(path)
    stamp_key = (st.st_mtime_ns, st.st_size)
    with _cache_lock:
        hit = _cache.get(path)
        if hit and hit[0] == stamp_key:
            return hit[1]
    try:
        nodes = parse_page(read_source(path))
    except UngError as e:
        e.file = e.file or path
        raise
    with _cache_lock:
        _cache[path] = (stamp_key, nodes)
    return nodes


class Runtime:
    def __init__(self, site_root, storage, html_mode=True, max_seconds=MAX_SECONDS):
        self.site_root = os.path.abspath(site_root)
        self.storage = storage
        self.html_mode = html_mode
        self.request = {}
        self.out = []
        self.globals = {}
        self.scopes = [self.globals]
        self.steps = 0
        self.deadline = time.time() + max_seconds
        self.depth = 0
        self.include_depth = 0
        self.file = None
        self.status = 200

    # --- running whole programs ---
    def run_file(self, path):
        path = os.path.abspath(path)
        nodes = load_program(path)
        self.file = path
        self.run_top(nodes)

    def run_top(self, nodes):
        self.hoist(nodes)
        try:
            self.run_block(nodes)
        except (FinishSignal, ReturnSignal):
            pass

    def hoist(self, nodes):
        """Functions can be used before the line that defines them."""
        for s in nodes:
            if s[0] == "func":
                self.globals[s[2]] = Function(s[2], s[3], s[4], self.file)

    def output(self):
        return "".join(self.out)

    def esc(self, text):
        return _html.escape(text, quote=True) if self.html_mode else text

    # --- names ---
    def lookup(self, name, line):
        local = self.scopes[-1]
        if name in local:
            return local[name]
        if name in self.globals:
            return self.globals[name]
        b = BUILTINS.get(name)
        if b is not None:
            return b
        raise UngError(self.unknown(name), line)

    def unknown(self, name, as_function=False):
        pool = set(self.globals) | set(self.scopes[-1]) | set(BUILTINS)
        close = difflib.get_close_matches(name, pool, n=1, cutoff=0.7)
        if not close:
            close = [p for p in pool if p.lower() == name.lower()]
        if close:
            return "I don't know what '%s' is. Did you mean '%s'?" % (name, close[0])
        if as_function:
            return "There's no function called '%s'. Make one with: function %s() ... end" % (name, name)
        return "I don't know what '%s' is. Give it a value first, like: %s = ..." % (name, name)

    def set_var(self, name, value):
        local = self.scopes[-1]
        if local is not self.globals and name not in local and name in self.globals:
            self.globals[name] = value
        else:
            local[name] = value

    def has_var(self, name):
        return name in self.scopes[-1] or name in self.globals

    # --- statements ---
    def tick(self, line):
        self.steps += 1
        if self.steps > MAX_STEPS or ((self.steps & 1023) == 0 and time.time() > self.deadline):
            raise UngError("This is taking too long. Is there a loop that never stops?", line)

    def run_block(self, body):
        for s in body:
            self.exec(s)

    def exec(self, s):
        self.tick(s[1])
        try:
            k = s[0]
            if k == "html":
                self.out.append(s[2])
            elif k == "echo":
                self.out.append(self.esc(to_text(self.ev(s[2]))))
            elif k == "assign":
                self.assign(s[2], self.ev(s[3]))
            elif k == "show":
                text = to_text(self.ev(s[2]))
                self.out.append((text if s[3] else self.esc(text)) + "\n")
            elif k == "exprstmt":
                self.ev(s[2])
            elif k == "if":
                for cond, body in s[2]:
                    if truthy(self.ev(cond)):
                        self.run_block(body)
                        return
                if s[3] is not None:
                    self.run_block(s[3])
            elif k == "foreach":
                self.do_foreach(s)
            elif k == "forrange":
                self.do_forrange(s)
            elif k == "repeat":
                n = numeric(self.ev(s[2]))
                if n is None:
                    raise UngError("'repeat' needs a number, like: repeat 5 times", s[1])
                for _ in range(int(n)):
                    self.tick(s[1])
                    try:
                        self.run_block(s[3])
                    except SkipSignal:
                        continue
                    except StopSignal:
                        break
            elif k == "while":
                while truthy(self.ev(s[2])):
                    self.tick(s[1])
                    try:
                        self.run_block(s[3])
                    except SkipSignal:
                        continue
                    except StopSignal:
                        break
            elif k == "func":
                self.scopes[-1][s[2]] = Function(s[2], s[3], s[4], self.file)
            elif k == "return":
                raise ReturnSignal(None if s[2] is None else self.ev(s[2]))
            elif k == "stop":
                raise StopSignal()
            elif k == "skip":
                raise SkipSignal()
            elif k == "finish":
                raise FinishSignal()
            elif k == "add":
                self.do_add(s)
            elif k == "remove":
                self.do_remove(s)
            elif k == "include":
                self.do_include(to_text(self.ev(s[2])), s[1])
            else:
                raise UngError("Unknown instruction (this is a bug in UNG-Script).", s[1])
        except UngError as e:
            if e.line is None:
                e.line = s[1]
            if e.file is None:
                e.file = self.file
            raise

    def do_foreach(self, s):
        v = self.ev(s[3])
        if isinstance(v, list):
            items = list(v)
        elif isinstance(v, dict):
            items = list(v.keys())
        elif isinstance(v, str):
            items = list(v)
        elif v is None:
            items = []
        else:
            raise UngError("'for each' can go through a list, a map or text, not %s. "
                           "To count, use: repeat 5 times" % describe(v), s[1])
        for item in items:
            self.tick(s[1])
            self.set_var(s[2], item)
            try:
                self.run_block(s[4])
            except SkipSignal:
                continue
            except StopSignal:
                break

    def do_forrange(self, s):
        a = numeric(self.ev(s[3]))
        b = numeric(self.ev(s[4]))
        if a is None or b is None:
            raise UngError("'for ... from ... to ...' needs numbers, like: for i from 1 to 10", s[1])
        if s[5] is None:
            step = 1 if b >= a else -1
        else:
            step = numeric(self.ev(s[5]))
            if step is None or step == 0:
                raise UngError("'step' must be a number that isn't zero.", s[1])
        i = a
        while (step > 0 and i <= b) or (step < 0 and i >= b):
            self.tick(s[1])
            self.set_var(s[2], tidy(i))
            try:
                self.run_block(s[6])
            except SkipSignal:
                pass
            except StopSignal:
                break
            i = i + step

    def do_add(self, s):
        val = self.ev(s[2])
        target = s[3]
        if target[0] == "var" and not self.has_var(target[2]):
            self.set_var(target[2], [val])
            return
        container = self.ev(target)
        if isinstance(container, list):
            container.append(val)
        elif container is None and target[0] == "var":
            self.set_var(target[2], [val])
        else:
            raise UngError("You can only add things to a list, but this is %s." % describe(container), s[1])

    def do_remove(self, s):
        val = self.ev(s[2])
        container = self.ev(s[3])
        if isinstance(container, list):
            for i, x in enumerate(container):
                if ung_equal(x, val):
                    del container[i]
                    return
        elif isinstance(container, dict):
            container.pop(key_of(val), None)
        else:
            raise UngError("You can only remove things from a list or a map, not from %s."
                           % describe(container), s[1])

    def do_include(self, name, line):
        if self.include_depth > 20:
            raise UngError("Too many includes inside includes. Does a file include itself?", line)
        base = os.path.dirname(self.file) if self.file else self.site_root
        path = os.path.abspath(os.path.join(base, name))
        if path != self.site_root and not path.startswith(self.site_root + os.sep):
            raise UngError("You can only include files that are inside your website folder.", line)
        if not os.path.isfile(path):
            raise UngError("I can't find the file '%s' to include." % name, line)
        nodes = load_program(path)
        saved = self.file
        self.file = path
        self.include_depth += 1
        try:
            self.hoist(nodes)
            self.run_block(nodes)
        finally:
            self.file = saved
            self.include_depth -= 1

    def assign(self, target, value):
        k = target[0]
        if k == "var":
            self.set_var(target[2], value)
            return
        obj = self.ev(target[2])
        if k == "attr":
            if not isinstance(obj, dict):
                raise UngError("Only maps have named parts like .%s, but this is %s."
                               % (target[3], describe(obj)), target[1])
            obj[target[3]] = value
            return
        idx = self.ev(target[3])
        if isinstance(obj, dict):
            obj[key_of(idx)] = value
        elif isinstance(obj, list):
            n = self.position(idx, target[1])
            if 1 <= n <= len(obj):
                obj[n - 1] = value
            elif n == len(obj) + 1:
                obj.append(value)
            elif -len(obj) <= n < 0:
                obj[n] = value
            else:
                raise UngError("There's no item number %d. This list has %d item(s)." % (n, len(obj)), target[1])
        elif isinstance(obj, str):
            raise UngError("Text can't be changed letter by letter. Use replace() or build new text.", target[1])
        else:
            raise UngError("You can only use [ ] on a list or a map, not on %s." % describe(obj), target[1])

    def position(self, idx, line):
        n = numeric(idx)
        if n is None or (isinstance(n, float) and not n.is_integer()):
            raise UngError("A position must be a whole number, like my_list[1].", line)
        n = int(n)
        if n == 0:
            raise UngError("Positions start at 1 in UNG-Script, so the first item is [1], not [0].", line)
        return n

    # --- expressions ---
    def ev(self, n):
        k = n[0]
        if k == "lit":
            return n[2]
        if k == "var":
            return self.lookup(n[2], n[1])
        try:
            if k == "bin":
                return binary(n[2], self.ev(n[3]), self.ev(n[4]))
            if k == "str":
                r = "".join(p if isinstance(p, str) else to_text(self.ev(p)) for p in n[2])
                if len(r) > MAX_TEXT:
                    raise UngError("This text has grown too big.")
                return r
            if k == "call":
                return self.call(n)
            if k == "attr":
                obj = self.ev(n[2])
                if isinstance(obj, dict):
                    return obj.get(n[3])
                if obj is None:
                    raise UngError("Can't get .%s from nothing. Was this value set?" % n[3])
                raise UngError("Only maps have named parts like .%s, but this is %s." % (n[3], describe(obj)))
            if k == "index":
                return self.get_index(self.ev(n[2]), self.ev(n[3]), n[1])
            if k == "and":
                a = self.ev(n[2])
                return self.ev(n[3]) if truthy(a) else a
            if k == "or":
                a = self.ev(n[2])
                return a if truthy(a) else self.ev(n[3])
            if k == "not":
                return not truthy(self.ev(n[2]))
            if k == "neg":
                v = numeric(self.ev(n[2]))
                if v is None:
                    raise UngError("'-' in front only works with numbers.")
                return -v
            if k == "list":
                return [self.ev(x) for x in n[2]]
            if k == "map":
                return {key_of(self.ev(a)): self.ev(b) for a, b in n[2]}
        except UngError as e:
            if e.line is None:
                e.line = n[1]
            raise
        raise UngError("Unknown value (this is a bug in UNG-Script).", n[1])

    def get_index(self, obj, idx, line):
        if isinstance(obj, dict):
            return obj.get(key_of(idx))
        if isinstance(obj, (list, str)):
            n = self.position(idx, line)
            size = len(obj)
            if n > size or n < -size:
                what = "list" if isinstance(obj, list) else "text"
                unit = "item(s)" if isinstance(obj, list) else "letter(s)"
                raise UngError("There's no item number %d. This %s has %d %s." % (n, what, size, unit), line)
            return obj[n - 1] if n > 0 else obj[n]
        if obj is None:
            raise UngError("Can't look inside nothing. Was this value set?", line)
        raise UngError("You can only use [ ] on a list, a map or text, not on %s." % describe(obj), line)

    def call(self, n):
        fn_node, line = n[2], n[1]
        name = "this"
        if fn_node[0] == "var":
            name = fn_node[2]
            if name in self.scopes[-1]:
                fn = self.scopes[-1][name]
            elif name in self.globals:
                fn = self.globals[name]
            elif name in BUILTINS:
                fn = BUILTINS[name]
            else:
                raise UngError(self.unknown(name, True), line)
        else:
            fn = self.ev(fn_node)
        args = [self.ev(a) for a in n[3]]
        return self.call_value(fn, args, line, name)

    def call_value(self, fn, args, line, name):
        if isinstance(fn, Builtin):
            if not fn.lo <= len(args) <= fn.hi:
                raise UngError("%s() was given %d input(s). Use it like: %s"
                               % (fn.name, len(args), fn.usage), line)
            return fn.fn(self, *args)
        if isinstance(fn, Function):
            if len(args) != len(fn.params):
                raise UngError("%s() needs %d input(s) (%s) but was given %d."
                               % (fn.name, len(fn.params), ", ".join(fn.params) or "none", len(args)), line)
            if self.depth >= MAX_DEPTH:
                raise UngError("Functions are calling each other too deeply (more than %d). "
                               "Does a function call itself forever?" % MAX_DEPTH, line)
            self.scopes.append(dict(zip(fn.params, args)))
            self.depth += 1
            saved = self.file
            self.file = fn.file
            try:
                self.run_block(fn.body)
            except ReturnSignal as r:
                return r.value
            finally:
                self.scopes.pop()
                self.depth -= 1
                self.file = saved
            return None
        raise UngError("'%s' is %s, not a function, so it can't be used with ( )." % (name, describe(fn)), line)


# ════════════════════════════════════════════════════════════════════
#  7. Friendly error pages
# ════════════════════════════════════════════════════════════════════

def source_lines(e):
    if not (e.file and e.line and os.path.isfile(e.file)):
        return []
    try:
        lines = read_source(e.file).replace("\r\n", "\n").split("\n")
    except Exception:
        return []
    lo, hi = max(1, e.line - 3), min(len(lines), e.line + 3)
    return [(i, lines[i - 1]) for i in range(lo, hi + 1)]


def error_text(e):
    out = ["", "  Problem: " + e.message]
    if e.where():
        out.append("  Where:   " + e.where())
    for num, text in source_lines(e):
        mark = ">>" if num == e.line else "  "
        out.append("  %s %4d | %s" % (mark, num, text))
    out.append("")
    return "\n".join(out)


def error_page(e, root):
    esc = _html.escape
    rows = "".join('<div class="ln%s"><span>%d</span>%s</div>'
                   % (" hit" if num == e.line else "", num, esc(text) or "&nbsp;")
                   for num, text in source_lines(e))
    where = ""
    if e.file:
        rel = os.path.relpath(e.file, root) if root else os.path.basename(e.file)
        where = esc(rel) + (", line %d" % e.line if e.line else "")
    return """<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Problem on this page</title>
<style>
body{font:16px/1.5 system-ui,sans-serif;margin:0;background:#fbf7f2;color:#2a2018}
.box{max-width:760px;margin:32px auto;padding:0 16px}
h1{font-size:20px;color:#a0331c;margin:0 0 6px}
.msg{font-size:18px;background:#fff;border-left:4px solid #d4553a;padding:12px 14px;border-radius:6px}
.where{color:#7a6a5c;margin:10px 0}
.code{background:#2b2420;color:#efe6dc;border-radius:8px;padding:10px 0;overflow-x:auto;font:14px/1.6 ui-monospace,Menlo,monospace}
.ln{white-space:pre;padding:0 14px}.ln span{display:inline-block;width:3em;color:#8d7b6c}
.hit{background:#5b2a1f}.hit span{color:#ffb39e}
small{color:#7a6a5c}
</style></head><body><div class="box">
<h1>UNG-Script found a problem</h1>
<div class="msg">%s</div>
<div class="where">%s</div>
%s
<p><small>Fix the file, save it, and refresh this page.</small></p>
</div></body></html>""" % (esc(e.message), where, ('<div class="code">%s</div>' % rows) if rows else "")


# ════════════════════════════════════════════════════════════════════
#  8. Built-in Guide and Playground pages
# ════════════════════════════════════════════════════════════════════

GUIDE = [
    ("What is UNG-Script?",
     "A simple language for making web pages. A page is a normal HTML file ending in .ung. "
     "Wherever you want the page to think, put code between <ung> and </ung>. "
     "To drop a value into the HTML, wrap it in {{ }}.",
     '<h1>Hello!</h1>\n<ung>\nname = "Sam"\n</ung>\n<p>Welcome, {{ name }}.</p>'),
    ("Showing things",
     "show writes something onto the page. Text inside quotes can include values in { }. "
     "show keeps text safe; show_html lets you write real HTML tags.",
     'show "Hello world"\nshow "2 + 2 = {2 + 2}"\nshow_html "<b>Bold!</b>"'),
    ("Names (variables)",
     "Give a value a name with =  (or the longer: set score to 10). Names can hold numbers, "
     "text, true/false, lists and maps. Use # to write a note the computer ignores.",
     'score = 10\nset player to "Amina"\nscore = score + 5   # now 15\nshow player + " has " + score + " points"'),
    ("Making choices",
     "Use if ... then ... end. Compare with is, is not, <, >, <=, >=. Combine with and, or, not.",
     'age = 20\nif age >= 18 then\n  show "Adult"\nelse if age >= 13 then\n  show "Teenager"\nelse\n  show "Child"\nend'),
    ("Repeating",
     "Three kinds of loop. 'stop' leaves a loop early; 'skip' jumps to the next round.",
     'repeat 3 times\n  show "Hip hip hooray!"\nend\n\nfor i from 1 to 5\n  show i\nend\n\n'
     'count = 3\nwhile count > 0\n  show count\n  count = count - 1\nend'),
    ("Lists",
     "A list keeps things in order. The first item is number 1.",
     'fruits = ["mango", "banana"]\nadd "pineapple" to fruits\nshow fruits[1]          # mango\n'
     'show length(fruits)     # 3\nfor each fruit in fruits\n  show upper(fruit)\nend\nremove "banana" from fruits'),
    ("Maps",
     "A map stores values under names, like a card with labelled boxes.",
     'person = {name: "Sam", city: "Kampala"}\nshow person.name\nperson.age = 30\nshow person["city"]'),
    ("Functions",
     "A function is a set of steps with a name, so you can use it again. 'return' gives an answer back.",
     'function greet(name)\n  return "Hello, " + name + "!"\nend\n\nshow greet("Amina")'),
    ("Forms (getting what visitors type)",
     "form(\"box name\") gives what a visitor typed. is_post() tells you a form was just sent.",
     '<form method="post">\n  <input name="city">\n  <button>Send</button>\n</form>\n'
     '<ung>\nif is_post() then\n  show "You live in " + form("city")\nend\n</ung>'),
    ("Saving data",
     "save and load keep single values. add_record and get_records keep lists of entries, "
     "like a guestbook. Everything is stored in the file _data.sqlite in your site folder.",
     'visits = load("visits", 0) + 1\nsave("visits", visits)\n\nadd_record("orders", {item: "Rice", bags: 2})\n'
     'for each order in get_records("orders")\n  show order.id + ": " + order.item\nend'),
    ("Sharing parts between pages",
     "Put a header or menu in its own file and include it. Files whose names start with _ "
     "can be included but visitors can't open them directly.",
     'include "_header.ung"'),
    ("Other useful words",
     "finish ends the page early. redirect(\"/page\") sends the visitor somewhere else. "
     "If either side of + is text, + joins them: \"Age: \" + 5 gives \"Age: 5\". "
     "What visitors type in forms is text, so use number(form(\"age\")) before doing sums.",
     'if form("password") is not "open" then\n  show "Not allowed."\n  finish\nend'),
]

PAGE_CSS = """
:root{--bg:#fbf7f2;--card:#fff;--ink:#2a2018;--soft:#7a6a5c;--line:#e8dccf;--accent:#1f6f5c;--code:#2b2420;--codeink:#efe6dc}
@media (prefers-color-scheme:dark){:root{--bg:#1c1815;--card:#26211d;--ink:#efe6dc;--soft:#a8998b;--line:#3a322b;--accent:#5fc3a6;--code:#120f0d}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.55 system-ui,-apple-system,sans-serif}
.wrap{max-width:820px;margin:0 auto;padding:20px 16px 60px}
header{display:flex;gap:14px;align-items:baseline;flex-wrap:wrap;margin-bottom:8px}
header b{font-size:20px}header a{color:var(--accent)}
h2{font-size:18px;margin:28px 0 6px}
pre{background:var(--code);color:var(--codeink);padding:12px 14px;border-radius:8px;overflow-x:auto;font:14px/1.6 ui-monospace,Menlo,monospace;margin:8px 0}
table{border-collapse:collapse;width:100%;font-size:14px}td{border-top:1px solid var(--line);padding:7px 6px;vertical-align:top}
td code{white-space:nowrap;color:var(--accent);font-weight:600}
"""


def guide_html():
    esc = _html.escape
    parts = []
    for title, text, code in GUIDE:
        parts.append("<h2>%s</h2><p>%s</p><pre>%s</pre>" % (esc(title), esc(text), esc(code)))
    rows = "".join("<tr><td><code>%s</code></td><td>%s</td></tr>" % (esc(b.usage), esc(b.doc))
                   for b in BUILTINS.values())
    return """<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>UNG-Script Guide</title>
<style>%s</style></head><body><div class="wrap">
<header><b>UNG-Script Guide</b><a href="/">Home</a><a href="/_playground">Playground</a></header>
<p>Everything you need, in plain words. Try any example in the <a href="/_playground">Playground</a>
(type the code without the &lt;ung&gt; tags there).</p>
%s
<h2>All built-in functions</h2><table>%s</table>
</div></body></html>""" % (PAGE_CSS, "".join(parts), rows)


PLAYGROUND_EXAMPLES = {
    "Hello": 'name = "Sam"\nshow "Hello, {name}!"\nshow "Today is " + today()',
    "Choices": 'temperature = 31\nif temperature > 30 then\n  show "Hot day - drink water!"\nelse\n  show "Nice weather."\nend',
    "Loops": 'for i from 1 to 10\n  show "7 x {i} = {7 * i}"\nend',
    "Lists": 'fruits = ["mango", "banana", "jackfruit"]\nadd "pineapple" to fruits\nfor each fruit in sort(fruits)\n  show upper(fruit)\nend\nshow "I have {length(fruits)} fruits."',
    "Functions": 'function price_with_tax(price)\n  return round(price * 1.18)\nend\n\nshow price_with_tax(10000)',
    "HTML": 'show_html "<h2 style=\'color:teal\'>Shopping list</h2>"\nfor each item in ["Rice", "Beans", "Sugar"]\n  show_html "<li>" + escape(item) + "</li>"\nend',
}


def playground_html():
    return """<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>UNG-Script Playground</title>
<style>%s
textarea{width:100%%;min-height:240px;font:15px/1.55 ui-monospace,Menlo,monospace;padding:12px;border-radius:8px;
 border:1px solid var(--line);background:var(--card);color:var(--ink);resize:vertical;tab-size:2}
.bar{display:flex;gap:8px;flex-wrap:wrap;margin:10px 0}
button,select{font:inherit;padding:8px 14px;border-radius:8px;border:1px solid var(--line);background:var(--card);color:var(--ink)}
button.run{background:var(--accent);color:#fff;border-color:var(--accent);font-weight:600}
iframe{width:100%%;min-height:200px;border:1px solid var(--line);border-radius:8px;background:#fff}
.err{display:none;background:#fde8e3;color:#7a1f0e;border-left:4px solid #d4553a;padding:10px 12px;border-radius:6px;margin:10px 0}
small{color:var(--soft)}
</style></head><body><div class="wrap">
<header><b>UNG-Script Playground</b><a href="/">Home</a><a href="/_guide">Guide</a></header>
<p><small>Type code and press Run (or Ctrl+Enter). No &lt;ung&gt; tags needed here.
Things you save here are forgotten afterwards.</small></p>
<textarea id="code" spellcheck="false" autocapitalize="off" autocorrect="off"></textarea>
<div class="bar"><button class="run" id="run">Run &#9654;</button>
<select id="ex"><option value="">Examples...</option></select></div>
<div class="err" id="err"></div>
<iframe id="out" sandbox title="Output"></iframe>
<script>
const EX = %s;
const code = document.getElementById("code"), out = document.getElementById("out"),
      err = document.getElementById("err"), ex = document.getElementById("ex");
for (const k of Object.keys(EX)) { const o = document.createElement("option"); o.value = k; o.textContent = k; ex.appendChild(o); }
ex.onchange = () => { if (ex.value) { code.value = EX[ex.value]; ex.value = ""; run(); } };
code.value = EX["Hello"];
code.addEventListener("keydown", e => {
  if ((e.ctrlKey || e.metaKey) && e.key === "Enter") { e.preventDefault(); run(); }
  if (e.key === "Tab") { e.preventDefault(); const s = code.selectionStart;
    code.value = code.value.slice(0, s) + "  " + code.value.slice(code.selectionEnd); code.selectionStart = code.selectionEnd = s + 2; }
});
async function run() {
  err.style.display = "none";
  try {
    const r = await fetch("/_playground/run", {method: "POST", headers: {"Content-Type": "application/json"},
                          body: JSON.stringify({code: code.value})});
    const d = await r.json();
    out.srcdoc = '<style>body{font:15px/1.5 system-ui,sans-serif;white-space:pre-wrap;margin:12px;color:#222}</style>' + (d.output || "");
    if (!d.ok) { err.textContent = (d.line ? "Line " + d.line + ": " : "") + d.error; err.style.display = "block"; }
  } catch (e) { err.textContent = "Couldn't reach the server. Is it still running?"; err.style.display = "block"; }
}
document.getElementById("run").onclick = run;
run();
</script></div></body></html>""" % (PAGE_CSS, json.dumps(PLAYGROUND_EXAMPLES).replace("</", "<\\/"))


def run_playground(code):
    rt = Runtime(".", MemoryStorage(), html_mode=True, max_seconds=5)
    try:
        nodes = parse_script(code)
        rt.run_top(nodes)
        return {"ok": True, "output": rt.output()}
    except RedirectSignal as r:
        return {"ok": True, "output": rt.output() + _html.escape("(would go to %s)" % r.url)}
    except UngError as e:
        return {"ok": False, "output": rt.output(), "error": e.message, "line": e.line}
    except RecursionError:
        return {"ok": False, "output": rt.output(), "error": "Too many things nested inside each other."}


# ════════════════════════════════════════════════════════════════════
#  9. The web server
# ════════════════════════════════════════════════════════════════════

BLOCKED_EXTS = {".py", ".pyc", ".sqlite", ".db", ".env", ".log", ".ini", ".cfg"}


def parse_form(text):
    out = {}
    for k, vals in urllib.parse.parse_qs(text, keep_blank_values=True).items():
        out[k] = vals[-1] if len(vals) == 1 else vals
    return out


class SiteServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, addr, root, playground):
        super().__init__(addr, Handler)
        self.root = os.path.abspath(root)
        # On a cloud host, UNG_DATA_DIR can point at a lasting disk (a "volume")
        data_dir = os.environ.get("UNG_DATA_DIR") or self.root
        os.makedirs(data_dir, exist_ok=True)
        self.storage = Storage(os.path.join(data_dir, "_data.sqlite"))
        self.playground = playground


class Handler(BaseHTTPRequestHandler):
    server_version = "UNG-Server/" + VERSION
    sys_version = ""

    def log_message(self, fmt, *args):
        sys.stderr.write("  [%s] %s\n" % (time.strftime("%H:%M:%S"), fmt % args))

    def do_GET(self):
        self.route("GET")

    def do_POST(self):
        self.route("POST")

    def do_HEAD(self):
        self.route("GET")

    def route(self, method):
        try:
            parts = urllib.parse.urlsplit(self.path)
            path = urllib.parse.unquote(parts.path) or "/"
            query = parse_form(parts.query)
            body = b""
            if method == "POST":
                length = int(self.headers.get("Content-Length") or 0)
                if length > MAX_BODY:
                    return self.send(413, "text/plain; charset=utf-8", b"Too much data was sent.")
                body = self.rfile.read(length) if length > 0 else b""

            if path == "/_guide":
                return self.send_html(200, guide_html())
            if path in ("/_playground", "/_playground/run"):
                if not self.server.playground:
                    return self.not_found()
                if path == "/_playground":
                    return self.send_html(200, playground_html())
                if method != "POST":
                    return self.send(405, "text/plain; charset=utf-8", b"Use POST.")
                try:
                    code = json.loads(body.decode("utf-8") or "{}").get("code", "")
                except ValueError:
                    code = ""
                result = run_playground(str(code)[:100_000])
                return self.send(200, "application/json", json.dumps(result).encode("utf-8"))

            form = {}
            if method == "POST":
                ctype = (self.headers.get("Content-Type") or "").split(";")[0].strip().lower()
                if ctype in ("", "application/x-www-form-urlencoded"):
                    form = parse_form(body.decode("utf-8", "replace"))

            target = self.resolve(path)
            if target is None:
                return self.not_found()
            if isinstance(target, tuple):              # folder without a trailing /
                return self.redirect(target[1])
            if target.endswith(".ung"):
                return self.run_page(target, method, path, query, form)
            return self.send_static(target)
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception:
            traceback.print_exc()
            try:
                self.send(500, "text/plain; charset=utf-8", b"The server had a problem. See the server window for details.")
            except Exception:
                pass

    def resolve(self, path):
        root = self.server.root
        bits = [b for b in path.split("/") if b]
        for b in bits:
            if b.startswith(".") or b.startswith("_") or "\\" in b or "\0" in b:
                return None
        full = os.path.abspath(os.path.join(root, *bits))
        if full != root and not full.startswith(root + os.sep):
            return None
        if os.path.isdir(full):
            if bits and not path.endswith("/"):
                return ("redirect", path + "/")
            for name in ("index.ung", "index.html", "index.htm"):
                if os.path.isfile(os.path.join(full, name)):
                    return os.path.join(full, name)
            return None
        if os.path.isfile(full):
            if os.path.splitext(full)[1].lower() in BLOCKED_EXTS:
                return None
            return full
        if not os.path.splitext(full)[1]:
            for ext in (".ung", ".html"):
                if os.path.isfile(full + ext):
                    return full + ext
        return None

    def run_page(self, file, method, path, query, form):
        rt = Runtime(self.server.root, self.server.storage, html_mode=True)
        rt.request = {"method": method, "path": path, "query": query, "form": form}
        try:
            rt.run_file(file)
        except RedirectSignal as r:
            return self.redirect(r.url)
        except UngError as e:
            sys.stderr.write("  Problem: %s\n" % e)
            return self.send_html(500, error_page(e, self.server.root))
        except RecursionError:
            e = UngError("Too many things nested inside each other.", None, file)
            return self.send_html(500, error_page(e, self.server.root))
        self.send_html(rt.status, rt.output())

    def send_static(self, file):
        ctype = mimetypes.guess_type(file)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript", "application/json"):
            ctype += "; charset=utf-8"
        with open(file, "rb") as f:
            data = f.read()
        self.send(200, ctype, data)

    def redirect(self, url):
        self.send_response(303)
        self.send_header("Location", url)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def not_found(self):
        self.send_html(404, """<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>Page not found</title><body style="font:16px system-ui;text-align:center;padding:60px 16px">
<h1>Page not found</h1><p>There's no page at this address.</p><p><a href="/">Go to the home page</a></p>""")

    def send_html(self, status, text):
        self.send(status, "text/html; charset=utf-8", text.encode("utf-8"), no_cache=True)

    def send(self, status, ctype, data, no_cache=False):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("X-Content-Type-Options", "nosniff")
        if no_cache:
            self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)


def lan_address():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return None


# ════════════════════════════════════════════════════════════════════
#  10. Starter website (python ung.py new mysite)
# ════════════════════════════════════════════════════════════════════

STARTER = {
    "_header.ung": """<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{{ title }}</title>
  <link rel="stylesheet" href="/style.css">
</head>
<body>
<nav>
  <a href="/">Home</a>
  <a href="/guestbook">Guestbook</a>
  <a href="/_guide">Guide</a>
  <a href="/_playground">Playground</a>
</nav>
<main>
""",
    "_footer.ung": """</main>
<footer>Made with UNG-Script &middot; {{ today() }}</footer>
</body>
</html>
""",
    "index.ung": """<ung>
# This is the home page. Lines starting with # are notes for people.
title = "My UNG website"
include "_header.ung"

# Count visitors, and remember the count even after a restart
visits = load("visits", 0) + 1
save("visits", visits)

if hour() < 12 then
  greeting = "Good morning"
else if hour() < 17 then
  greeting = "Good afternoon"
else
  greeting = "Good evening"
end

fruits = ["mango", "banana", "pineapple", "jackfruit"]
</ung>

<h1>{{ greeting }}!</h1>
<p>This page was made with <b>UNG-Script</b>. It has been visited <b>{{ visits }}</b> times.</p>

<h2>Fruits I like</h2>
<ul>
<ung> for each fruit in fruits </ung>
  <li>{{ upper(fruit) }}</li>
<ung> end </ung>
</ul>

<h2>Times table for 7</h2>
<ung>
for i from 1 to 10
  show_html "<div>7 &times; {i} = <b>{7 * i}</b></div>"
end
</ung>

<ung> include "_footer.ung" </ung>
""",
    "guestbook.ung": """<ung>
title = "Guestbook"
include "_header.ung"

problem = ""
if is_post() then
  name = trim(form("name"))
  message = trim(form("message"))
  if name is "" or message is "" then
    problem = "Please fill in both your name and a message."
  else if length(message) > 500 then
    problem = "Your message is too long (500 letters at most)."
  else
    add_record("guestbook", {name: name, message: message})
    redirect("/guestbook")
  end
end

entries = reverse(get_records("guestbook"))
</ung>

<h1>Guestbook</h1>

<ung> if problem is not "" then </ung>
  <p class="problem">{{ problem }}</p>
<ung> end </ung>

<form method="post">
  <label>Your name <input name="name" value="{{ form("name") }}"></label>
  <label>Message <textarea name="message" rows="3">{{ form("message") }}</textarea></label>
  <button>Sign the guestbook</button>
</form>

<h2>{{ length(entries) }} messages</h2>
<ung> for each entry in entries </ung>
  <div class="entry">
    <b>{{ entry.name }}</b> <small>{{ entry.created }}</small>
    <p>{{ entry.message }}</p>
  </div>
<ung> end </ung>

<ung> include "_footer.ung" </ung>
""",
    "style.css": """* { box-sizing: border-box; }
body { margin: 0; font: 17px/1.6 system-ui, -apple-system, sans-serif; background: #fbf7f2; color: #2a2018; }
nav { display: flex; gap: 18px; flex-wrap: wrap; padding: 14px 16px; background: #1f6f5c; }
nav a { color: #fff; text-decoration: none; font-weight: 600; }
main { max-width: 720px; margin: 0 auto; padding: 16px; }
h1 { margin-top: 8px; }
form { display: grid; gap: 10px; background: #fff; padding: 16px; border-radius: 10px; border: 1px solid #e8dccf; }
label { display: grid; gap: 4px; font-weight: 600; }
input, textarea { font: inherit; padding: 8px 10px; border: 1px solid #cdbfb1; border-radius: 8px; }
button { font: inherit; font-weight: 600; padding: 10px; border: 0; border-radius: 8px; background: #1f6f5c; color: #fff; }
.entry { border-bottom: 1px solid #e8dccf; padding: 10px 0; }
.entry p { margin: 4px 0 0; }
.problem { background: #fde8e3; color: #7a1f0e; padding: 10px 12px; border-radius: 8px; }
footer { text-align: center; color: #7a6a5c; padding: 30px 16px; font-size: 14px; }
""",
}


# ════════════════════════════════════════════════════════════════════
#  11. Command line
# ════════════════════════════════════════════════════════════════════

HELP = """UNG-Script %s - a simple language for building websites

  python ung.py new mysite            make a starter website in folder "mysite"
  python ung.py serve mysite          start the web server (http://localhost:8000)
        --port 8080                   use a different port
        --share                       let phones on the same WiFi open it too
        --no-playground               turn off the /_playground page
  python ung.py run page.ung          run a file and print what it shows
  python ung.py run page.ung name=Sam    ...pretending a visitor typed name=Sam
  python ung.py check page.ung        look for mistakes without running
""" % VERSION


def cmd_new(args):
    if not args:
        print("Tell me a folder name, like:  python ung.py new mysite")
        return 1
    folder = args[0]
    os.makedirs(folder, exist_ok=True)
    made = []
    for name, content in STARTER.items():
        p = os.path.join(folder, name)
        if os.path.exists(p):
            print("  kept your existing", name)
            continue
        with open(p, "w", encoding="utf-8") as f:
            f.write(content)
        made.append(name)
    print("Made a starter website in '%s' (%s)." % (folder, ", ".join(made) or "nothing new"))
    print("Start it with:  python ung.py serve %s" % folder)
    return 0


def cmd_serve(args):
    folder, port, share, playground = ".", None, False, True
    rest = list(args)
    while rest:
        a = rest.pop(0)
        if a == "--port" and rest:
            port = int(rest.pop(0))
        elif a == "--share":
            share = True
        elif a == "--no-playground":
            playground = False
        elif a.startswith("--"):
            print("I don't know the option", a)
            return 1
        else:
            folder = a
    if not os.path.isdir(folder):
        print("There's no folder called '%s'. Make one with: python ung.py new %s" % (folder, folder))
        return 1
    env_port = os.environ.get("PORT")
    if port is None:
        port = int(env_port) if env_port else 8000
    host = "0.0.0.0" if (share or env_port) else "127.0.0.1"
    threading.stack_size(64 * 1024 * 1024)
    try:
        server = SiteServer((host, port), folder, playground)
    except OSError:
        print("Port %d is already in use. Try:  python ung.py serve %s --port %d" % (port, folder, port + 1))
        return 1
    print("\n  UNG-Script %s web server is running" % VERSION)
    print("  Website:     http://localhost:%d" % port)
    if share and lan_address():
        print("  On a phone:  http://%s:%d   (same WiFi)" % (lan_address(), port))
    print("  Guide:       http://localhost:%d/_guide" % port)
    if playground:
        print("  Playground:  http://localhost:%d/_playground" % port)
    print("  Folder:      %s" % os.path.abspath(folder))
    print("  Press Ctrl+C to stop.\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Stopped. Bye!")
    finally:
        server.server_close()
    return 0


def cmd_run(args):
    if not args:
        print("Tell me which file to run, like:  python ung.py run page.ung")
        return 1
    path = os.path.abspath(args[0])
    if not os.path.isfile(path):
        print("I can't find the file", args[0])
        return 1
    form = {}
    for a in args[1:]:
        if "=" in a:
            k, v = a.split("=", 1)
            form[k] = v
    folder = os.path.dirname(path)
    rt = Runtime(folder, Storage(os.path.join(folder, "_data.sqlite")), html_mode=False, max_seconds=60)
    rt.request = {"method": "POST" if form else "GET", "path": "/", "query": {}, "form": form}
    code = 0
    try:
        rt.run_file(path)
    except RedirectSignal as r:
        rt.out.append("\n(the page would now go to %s)\n" % r.url)
    except UngError as e:
        sys.stdout.write(rt.output())
        print(error_text(e))
        return 1
    except RecursionError:
        print("\n  Problem: too many things nested inside each other.")
        code = 1
    sys.stdout.write(rt.output())
    if rt.out and not rt.output().endswith("\n"):
        print()
    return code


def cmd_check(args):
    if not args:
        print("Tell me which file to check, like:  python ung.py check page.ung")
        return 1
    bad = 0
    for name in args:
        try:
            load_program(os.path.abspath(name))
            print("  %s: no mistakes found" % name)
        except UngError as e:
            print(error_text(e))
            bad += 1
        except OSError:
            print("  I can't find the file", name)
            bad += 1
    return 1 if bad else 0


def main(argv):
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(HELP)
        return 0
    cmd, rest = argv[0], argv[1:]
    if cmd in ("--version", "version"):
        print("UNG-Script", VERSION)
        return 0
    commands = {"new": cmd_new, "serve": cmd_serve, "run": cmd_run, "check": cmd_check}
    if cmd not in commands:
        if cmd.endswith(".ung"):
            return cmd_run(argv)
        print("I don't know the command '%s'.\n" % cmd)
        print(HELP)
        return 1
    return commands[cmd](rest)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
