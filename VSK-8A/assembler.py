#!/usr/bin/env python3
"""
vsk8asm - assembler for the VSK-8A emulator.

    python3 vsk8asm.py program.asm                 -> program.bin
    python3 vsk8asm.py program.asm -o out.bin -l   -> also prints a listing
    python3 vsk8asm.py program.asm --big-endian    -> if your RAM.read_word is big-endian

The output is a flat image. ORG only sets the address labels are computed from
(nothing is padded); a leading ORG is printed as the "load address".
"""

# --------------------------------------------------------------------------
# Version.  Bump this (and add a line below) with EVERY change to the assembler.
#   MAJOR: source-level breaking change (code that assembled before no longer does,
#          or assembles to something different)
#   MINOR: new instruction / directive / feature     PATCH: bug fix, no new syntax
# 1.0 - 1.11 are reconstructed from the build history; 2.0 onwards were recorded as they happened.
# --------------------------------------------------------------------------
VERSION = (5, 1, 0)
CHANGELOG = """\
5.1.0  JC, JNC (jump if carry / no carry); warning when CMP r8, r16 is swapped (carry would be reversed)
5.0.0  EXPORT directive (only exported names reach the symbol file); symbol files are now a binary table of
       labels, constants and macros; macros can be exported and imported; --show-symbols; old text .sym files rejected
4.1.0  --export-symbols FILE / --import-symbols FILE: share labels and constants between separately assembled files
4.0.0  __DATE__ no longer pads the day: "May 4 2021" (10 bytes) instead of "May  4 2021"
3.3.0  __ASM_VER__ and friends, --version, this changelog
3.2.0  __TIME__, __ISO_DATE__, __FILE__, __YEAR__..__SECOND__, __POSIX_TIME__, __LINE__
3.1.0  __DATE__
3.0.0  HALT renamed HLT (HALT no longer accepted)
2.4.0  TIMES count statement, $$, ALIGN (PAD/BOOTSIG tried and removed); PUSHA/POPA fixed core
2.3.0  PUSHA, POPA
2.2.0  SUB reg, imm emits SUB_IMM
2.1.0  IN/OUT with immediate ports, CMP reg, imm (CMPZ_IMM)
2.0.0  ORG no longer pads; load address reported
1.11.0 INT, IRET, CLI, STI
1.10.0 CMP, SHR, SHL
1.9.0  MOV between any registers (MOVE)
1.8.0  MUL, DIV, mixed-width ADD/SUB/MUL/DIV
1.7.0  PUSH, POP, CALL, RET, MOV SP, imm
1.6.0  TEST
1.5.0  C/D registers, AL/AH.. aliases, ADD/SUB immediates, XOR/OR/AND
1.4.0  hex literals (0x, h suffix, $), memory reads and pointer writes
1.3.0  JMP reg
1.2.0  IN, OUT
1.1.0  ORG, little-endian output, --big-endian
1.0.0  MOV/ADD/SUB, JMP/JZ/JNZ, HALT, macros, DB/DW with strings, labels, .bin output
"""
VERSION_STR = ".".join(map(str, VERSION))

import argparse
import itertools
import re
import sys

# --------------------------------------------------------------------------
# Machine description - edit these if your regs.py differs
# --------------------------------------------------------------------------
NUM_REG8 = 12                                   # R0..R11
REG8  = {f"R{i}": i for i in range(NUM_REG8)}  # 8-bit register name -> index
REG16 = {"A": 0, "B": 1, "C": 2, "D": 3}                       # 16-bit register name -> index

# The 16-bit registers are pairs of 8-bit ones (little-endian, low byte first):
#   A = R5:R4   B = R7:R6   C = R9:R8   D = R11:R10
# These aliases name the halves, so MOV AL, 5 is the same as MOV R4, 5.
REG8.update({"AL": 4, "AH": 5, "BL": 6, "BH": 7,
             "CL": 8, "CH": 9, "DL": 10, "DH": 11})

OPC = dict(LOAD_REG=0, HALT=1, WRITE_MEM8=2, WRITE_MEM8A=3, WRITE_MEM16=4,
           SUB8=5, SUB16=6, ADD8=7, ADD16=8, JZ=9, JNZ=10, JMP=11,
           LOAD_REG16=12, PORT_IN=13, PORT_OUT=14, JMP_REG=15,
           READ_MEM8A=16, READ_MEM8=17, READ_MEM16=18,
           ADD_IMM=19, XOR=20, OR=21, AND=22, AND_TEST=23,
           PUSH=24, POP=25, CALL=26, RET=27, MOVE_SP=28,
           ADD_UNM=29, SUB_UNM=30, MUL_UNM=31, DIV_UNM=32,
           DIV=33, MUL=34, DIV16=35, MUL16=36, MOVE=37,
           COMPARE_Z=38, SHR=39, SHL=40,
           INT=41, IRET=42, INTERRUPT_C=43, CMPZ_IMM=44, SUB_IMM=45, PUSH_ALL=46, POP_ALL=47,
           JUMP_CARRY=48, JUMP_NOT_CARRY=49)

# Built-in constants.  Text ones are only valid in DB; numeric ones work in any expression.
BUILTIN_STR = {"__DATE__", "__TIME__", "__ISO_DATE__", "__FILE__", "__ASM_VER__"}
BUILTIN_NUM = {"__YEAR__", "__MONTH__", "__DAY__", "__HOUR__", "__MINUTE__", "__SECOND__",
               "__POSIX_TIME__", "__LINE__", "__ASM_VER_MAJOR__", "__ASM_VER_MINOR__", "__ASM_VER_PATCH__"}

MNEMONICS  = {"MOV", "ADD", "SUB", "MUL", "DIV", "CMP", "SHR", "SHL", "INT", "IRET", "CLI", "STI", "PUSHA", "POPA", "XOR", "OR", "AND", "TEST", "PUSH", "POP", "CALL", "RET",
               "JMP", "JZ", "JNZ", "JC", "JNC", "HLT", "IN", "OUT"}
DIRECTIVES = {"DB", "DW", "ORG", "EQU", "MACRO", "ENDMACRO", "ALIGN", "TIMES", "EXPORT"}
RESERVED   = set(REG8) | set(REG16) | MNEMONICS | DIRECTIVES | {"SP"} | BUILTIN_STR | BUILTIN_NUM

IDENT = r"[A-Za-z_.@][\w.@]*"
LABEL_RE = re.compile(rf"^({IDENT})\s*:\s*(.*)$")
EQU_RE   = re.compile(rf"^({IDENT})\s+equ\s+(.+)$", re.I)
EQ_RE    = re.compile(rf"^({IDENT})\s*=\s*(.+)$")
MACRO_RE = re.compile(r"^macro\s+([A-Za-z_]\w*)\s*(.*)$", re.I)
ENDM_RE  = re.compile(r"^endmacro$", re.I)

ESCAPES = {"n": 10, "r": 13, "t": 9, "0": 0, "\\": 92, '"': 34, "'": 39}


class AsmError(Exception):
    pass


MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def build_clock():
    """The moment of assembly. SOURCE_DATE_EPOCH (UTC) makes builds reproducible; otherwise local time."""
    import datetime, os
    epoch = os.environ.get("SOURCE_DATE_EPOCH")
    if epoch and epoch.isdigit():
        return datetime.datetime.fromtimestamp(int(epoch), datetime.timezone.utc)
    return datetime.datetime.now()


# --------------------------------------------------------------------------
# Text helpers
# --------------------------------------------------------------------------
def strip_comment(line):
    """Remove a ';' comment (ignoring ';' inside quotes) and trim."""
    out, q, i = [], None, 0
    while i < len(line):
        c = line[i]
        if q:
            out.append(c)
            if c == "\\" and i + 1 < len(line):
                out.append(line[i + 1])
                i += 1
            elif c == q:
                q = None
        else:
            if c == ";":
                break
            if c in "\"'":
                q = c
            out.append(c)
        i += 1
    return "".join(out).strip()


def split_args(s):
    """Split on top-level commas (not inside quotes/brackets/parens)."""
    s = s.strip()
    if not s:
        return []
    args, cur, depth, q, i = [], [], 0, None, 0
    while i < len(s):
        c = s[i]
        if q:
            cur.append(c)
            if c == "\\" and i + 1 < len(s):
                cur.append(s[i + 1])
                i += 1
            elif c == q:
                q = None
        elif c in "\"'":
            q = c
            cur.append(c)
        elif c in "([":
            depth += 1
            cur.append(c)
        elif c in ")]":
            depth -= 1
            cur.append(c)
        elif c == "," and depth == 0:
            args.append("".join(cur).strip())
            cur = []
        else:
            cur.append(c)
        i += 1
    args.append("".join(cur).strip())
    return args


def quoted_end(s):
    """Index of the closing quote of a string starting at s[0], or -1."""
    q, i = s[0], 1
    while i < len(s):
        if s[i] == "\\":
            i += 2
            continue
        if s[i] == q:
            return i
        i += 1
    return -1


def parse_quoted(s):
    """'text' or "text" (with quotes) -> list of byte values."""
    body, out, i = s[1:-1], [], 0
    while i < len(body):
        c = body[i]
        if c == "\\":
            i += 1
            if i >= len(body) or body[i] not in ESCAPES:
                raise AsmError(f"bad escape sequence in {s}")
            out.append(ESCAPES[body[i]])
        else:
            out.extend(c.encode("utf-8"))
        i += 1
    return out


# --------------------------------------------------------------------------
# Expressions:  numbers, 'c', labels, $, + - * / % & | ^ ~ << >> ( )
# --------------------------------------------------------------------------
TOKEN_RE = re.compile(r"""\s*(?:
    (?P<hexd>\$[0-9a-fA-F][0-9a-fA-F_]*(?![\w.@])) |
    (?P<hexh>[0-9a-fA-F][0-9a-fA-F_]*[hH](?![\w.@])) |
    (?P<num>0[xX][0-9a-fA-F_]+|0[bB][01_]+|\d[\d_]*) |
    (?P<chr>'(?:\\.|[^'\\])') |
    (?P<id>[A-Za-z_.@][\w.@]*) |
    (?P<sec>\$\$) |
    (?P<op><<|>>|[-+*/%&|^~()$])
)""", re.X)

# A name like DFh or Ch is read as a hex number, so it cannot also be a symbol.
HEXH_RE = re.compile(r"[0-9a-fA-F][0-9a-fA-F_]*[hH]")

BINOPS = {"|": 1, "^": 2, "&": 3, "<<": 4, ">>": 4,
          "+": 5, "-": 5, "*": 6, "/": 6, "%": 6}


def eval_expr(text, syms, pc, lenient, origin=0):
    text = text.strip()
    if not text:
        raise AsmError("missing value")
    toks, pos = [], 0
    while pos < len(text):
        m = TOKEN_RE.match(text, pos)
        if not m:
            if text[pos:].strip() == "":
                break
            raise AsmError(f"cannot parse expression '{text}'")
        pos = m.end()
        kind = m.lastgroup
        toks.append((kind, m.group(kind)))

    i = 0

    def atom():
        nonlocal i
        if i >= len(toks):
            raise AsmError(f"incomplete expression '{text}'")
        kind, v = toks[i]
        i += 1
        if kind == "hexd":                       # $DF
            return int(v[1:].replace("_", ""), 16)
        if kind == "hexh":                       # DFh / 0DFh
            if v.upper() in REG8:                # AH / BH are registers, not 0Ah / 0Bh
                raise AsmError(f"register {v.upper()} cannot be used as a value "
                               f"(write hex 0xA as 0Ah, not Ah)")
            return int(v[:-1].replace("_", ""), 16)
        if kind == "num":
            v = v.replace("_", "")
            return int(v, 0) if v[:2].lower() in ("0x", "0b") else int(v, 10)
        if kind == "chr":
            b = parse_quoted(v)
            if len(b) != 1:
                raise AsmError(f"bad character literal {v}")
            return b[0]
        if kind == "sec":                        # $$ = address of the first byte of the output
            return origin
        if kind == "id":
            if v in syms:
                return syms[v]
            if v.startswith("__") and v.upper() in syms:      # __year__ == __YEAR__
                return syms[v.upper()]
            if v.upper() in BUILTIN_STR:
                raise AsmError(f"{v} is text; it can only be used in DB")
            if lenient:
                return 0
            raise AsmError(f"undefined symbol '{v}'")
        if v == "$":
            return pc
        if v == "(":
            r = expr(1)
            if i >= len(toks) or toks[i][1] != ")":
                raise AsmError(f"missing ')' in '{text}'")
            i += 1
            return r
        if v == "-":
            return -atom()
        if v == "+":
            return atom()
        if v == "~":
            return ~atom()
        raise AsmError(f"unexpected '{v}' in '{text}'")

    def expr(minp):
        nonlocal i
        left = atom()
        while (i < len(toks) and toks[i][0] == "op"
               and toks[i][1] in BINOPS and BINOPS[toks[i][1]] >= minp):
            op = toks[i][1]
            i += 1
            right = expr(BINOPS[op] + 1)
            if op == "|":   left |= right
            elif op == "^": left ^= right
            elif op == "&": left &= right
            elif op == "<<": left <<= right
            elif op == ">>": left >>= right
            elif op == "+": left += right
            elif op == "-": left -= right
            elif op == "*": left *= right
            else:
                if right == 0:
                    if lenient:
                        left = 0
                        continue
                    raise AsmError("division by zero")
                left = left // right if op == "/" else left % right
        return left

    result = expr(1)
    if i != len(toks):
        raise AsmError(f"unexpected '{toks[i][1]}' in '{text}'")
    return result


# --------------------------------------------------------------------------
# Macro preprocessor
# --------------------------------------------------------------------------
def preprocess(src_lines, imported=None):
    """Collect MACRO definitions and expand invocations.
    `imported` is a {NAME: macro} table read from symbol files.
    Returns ([(text, line_no, context), ...], {NAME: macro}) - the macro table includes imported ones."""
    macros, main, cur = dict(imported or {}), [], None

    for no, raw in enumerate(src_lines, 1):
        line = strip_comment(raw)
        if cur is not None:
            if ENDM_RE.match(line):
                macros[cur["name"]] = cur
                cur = None
            elif MACRO_RE.match(line):
                raise AsmError(f"line {no}: macros cannot be defined inside macros")
            else:
                cur["body"].append((line, no))
            continue
        m = MACRO_RE.match(line)
        if m:
            name = m.group(1).upper()
            if name in RESERVED:
                raise AsmError(f"line {no}: '{name}' is a reserved word")
            if name in macros:
                if macros[name].get("sym"):
                    raise AsmError(f"line {no}: macro '{name}' is already imported from "
                                   f"{macros[name]['sym']}; it can't be defined again here")
                raise AsmError(f"line {no}: macro '{name}' already defined")
            params = split_args(m.group(2))
            for p in params:
                if not re.fullmatch(r"[A-Za-z_]\w*", p):
                    raise AsmError(f"line {no}: bad macro parameter name '{p}'")
            cur = {"name": name, "params": params, "body": [], "line": no, "file": None, "sym": None}
        else:
            if ENDM_RE.match(line):
                raise AsmError(f"line {no}: ENDMACRO without MACRO")
            main.append((line, no, ""))
    if cur is not None:
        raise AsmError(f"macro '{cur['name']}' (line {cur['line']}) has no ENDMACRO")

    uid_counter = itertools.count(1)

    def expand(items, stack):
        out = []
        for line, no, ctx in items:
            body, labels = line, []
            while True:
                m = LABEL_RE.match(body)
                if not m:
                    break
                labels.append(m.group(1))
                body = m.group(2)
            parts = body.split(None, 1)
            if not parts or parts[0].upper() not in macros:
                out.append((line, no, ctx))
                continue
            name = parts[0].upper()
            mac = macros[name]
            if name in stack:
                raise AsmError(f"line {no}: macro '{name}' calls itself")
            args = split_args(parts[1]) if len(parts) > 1 else []
            if len(args) != len(mac["params"]):
                raise AsmError(f"line {no}: macro {name} takes {len(mac['params'])} "
                               f"argument(s), got {len(args)}")
            mapping = dict(zip(mac["params"], args))
            uid = next(uid_counter)
            for lab in labels:
                out.append((lab + ":", no, ctx))
            sub = []
            for bline, bno in mac["body"]:
                t = re.sub(r"\{(\w+)\}",
                           lambda mm: mapping.get(mm.group(1), mm.group(0)), bline)
                t = re.sub(r"@([A-Za-z_]\w*)",
                           lambda mm: f"__{mm.group(1)}_{uid}", t)
                where = f" from {mac['file']}" if mac.get("file") else ""
                sub.append((t, no, f"{ctx} [in macro {name}{where}, its line {bno}]"))
            out.extend(expand(sub, stack + [name]))
        return out

    return expand(main, []), macros


# --------------------------------------------------------------------------
# The assembler proper
# --------------------------------------------------------------------------
class Assembler:
    def __init__(self, big_endian=False, filename="<input>", imports=None, import_macros=None):
        self.be = big_endian
        self.syms = {}
        self.kinds = {}                            # name -> "label" | "constant"
        self.exports = []                          # (name, line) from EXPORT directives
        self.warnings = []                         # (line, text), filled during the final pass
        self.macros = {}                           # NAME -> macro (filled by the preprocessor)
        self.import_macros = dict(import_macros or {})
        self.imported = dict(imports or {})        # name -> (value, symbol file, kind)
        for name, (val, _src, kind) in self.imported.items():
            self.syms[name] = val
            self.kinds[name] = kind
        self.out = bytearray()
        self.listing = []
        self.final = False   # False = pass 1 (forward refs read as 0)
        self.filename = filename
        now = build_clock()        # fixed once, so both passes agree even across midnight
        self.strings = {           # text constants (DB only)
            "__DATE__":     f"{MONTHS[now.month - 1]} {now.day} {now.year}".encode("ascii"),   # May 14 2021 / May 4 2021 (length varies)
            "__TIME__":     now.strftime("%H:%M:%S").encode("ascii"),                              # 13:05:09
            "__ISO_DATE__": now.strftime("%Y-%m-%d").encode("ascii"),                              # 2021-05-14
            "__FILE__":     filename.encode("utf-8"),
            "__ASM_VER__":  VERSION_STR.encode("ascii"),                                           # 3.3.0
        }
        import calendar
        posix = calendar.timegm(now.utctimetuple()) if now.tzinfo else int(now.timestamp())
        self.syms.update({         # numeric constants (any expression)
            "__YEAR__": now.year, "__MONTH__": now.month, "__DAY__": now.day,
            "__HOUR__": now.hour, "__MINUTE__": now.minute, "__SECOND__": now.second,
            "__POSIX_TIME__": posix, "__LINE__": 0,
            "__ASM_VER_MAJOR__": VERSION[0], "__ASM_VER_MINOR__": VERSION[1], "__ASM_VER_PATCH__": VERSION[2],
        })
        self.base = 0        # set by ORG: address of the first output byte
        self.origin = 0      # load address of the .bin (first ORG at the very start)

    def addr(self):
        """Current assembly address = ORG base + bytes emitted so far."""
        return self.base + len(self.out)

    # -- helpers ----------------------------------------------------------
    def pack16(self, v):
        return (v & 0xFFFF).to_bytes(2, "big" if self.be else "little")

    def value(self, text):
        return eval_expr(text, self.syms, self.addr(), not self.final, self.origin)

    def imm8(self, v):
        if self.final and not -128 <= v <= 255:
            raise AsmError(f"value {v} does not fit in 8 bits")
        return v & 0xFF

    def imm16(self, v):
        if self.final and not -32768 <= v <= 65535:
            raise AsmError(f"value {v} does not fit in 16 bits")
        return v & 0xFFFF

    def define(self, name, val, kind="constant"):
        if HEXH_RE.fullmatch(name):
            raise AsmError(f"'{name}' would be read as a hex number (h suffix); "
                           "pick another name")
        if name.upper() in RESERVED:
            raise AsmError(f"'{name}' is a reserved word")
        if name in self.imported:
            raise AsmError(f"'{name}' is already imported from {self.imported[name][1]}; "
                           "it can't be defined again here")
        if not self.final and name in self.syms:
            raise AsmError(f"symbol '{name}' defined twice")
        self.syms[name] = val
        self.kinds[name] = kind

    def regular(self, op, a=0, w=0, b=0):
        self.out += bytes([0, OPC[op], a & 0xFF]) + self.pack16(w) + bytes([b & 0xFF])

    # -- operands -----------------------------------------------------------
    def operand(self, text):
        t = text.strip()
        if not t:
            raise AsmError("empty operand")
        if t.startswith("[") and t.endswith("]"):
            inner = t[1:-1].strip()
            u = inner.upper()
            if u in REG16:
                return ("ind16", REG16[u])
            if u in REG8:
                raise AsmError("an 8-bit register cannot be used as an address; use A-D")
            if u == "SP":
                raise AsmError("[SP] is not supported; use PUSH / POP")
            return ("mem", self.imm16(self.value(inner)))
        u = t.upper()
        if u in REG8:
            return ("r8", REG8[u])
        if u in REG16:
            return ("r16", REG16[u])
        if u == "SP":
            return ("sp", 0)
        return ("imm", self.value(t))

    # -- instructions ---------------------------------------------------------
    def mov(self, d, s):
        (dk, dv), (sk, sv) = d, s
        if dk == "sp" and sk == "imm":
            self.regular("MOVE_SP", w=self.imm16(sv))
        elif dk == "sp" or sk == "sp":
            raise AsmError("SP can only be loaded with a number or label (MOV SP, 0xFFFF); "
                           "it cannot be read or copied")
        elif dk == "r8" and sk == "imm":
            self.regular("LOAD_REG", a=dv, b=self.imm8(sv))
        elif dk in ("r8", "r16") and sk in ("r8", "r16"):
            # MOVE: op8_1 = source, op8_2 = dest, op16 = 0 (8->8), 1 (16->16), 2 (8->16), 3 (16->8)
            kind = {("r8", "r8"): 0, ("r16", "r16"): 1, ("r16", "r8"): 2, ("r8", "r16"): 3}[(dk, sk)]
            self.regular("MOVE", a=sv, w=kind, b=dv)
        elif dk == "r16" and sk == "imm":
            self.regular("LOAD_REG16", a=dv, w=self.imm16(sv))
        elif dk == "mem" and sk == "imm":
            self.regular("WRITE_MEM8", a=self.imm8(sv), w=dv, b=0)
        elif dk == "mem" and sk == "r8":
            self.regular("WRITE_MEM8", a=sv, w=dv, b=1)
        elif dk == "mem" and sk == "r16":
            raise AsmError("no instruction writes a 16-bit register to a fixed address; "
                           "use MOV [A], B (pointer in A or B) instead")
        elif dk == "ind16" and sk == "r8":
            self.regular("WRITE_MEM8A", a=dv, b=sv)
        elif dk == "ind16" and sk == "r16":
            self.regular("WRITE_MEM16", a=dv, b=sv)
        elif dk == "ind16" and sk == "imm":
            raise AsmError("no instruction stores an immediate through a pointer; "
                           "load it into an 8-bit register first")
        elif dk == "r8" and sk == "ind16":       # MOV R0, [A]
            self.regular("READ_MEM8A", a=dv, b=sv)
        elif dk == "r8" and sk == "mem":         # MOV R0, [0x2000]
            self.regular("READ_MEM8", a=dv, w=sv)
        elif dk == "r16" and sk == "ind16":      # MOV A, [B]  (reads a word)
            self.regular("READ_MEM16", a=dv, b=sv)
        elif dk == "r16" and sk == "mem":
            raise AsmError("no instruction reads a 16-bit register from a fixed address; "
                           "put the address in A or B first: MOV B, addr  then  MOV A, [B]")
        else:
            raise AsmError("unsupported MOV operand combination "
                           f"({dk} <- {sk}); see the MOV forms in the docs")

    def arith(self, mnem, d, s):
        """ADD / SUB / MUL / DIV dest, source. The opcode follows the operand widths."""
        (dk, dv), (sk, sv) = d, s
        simple = mnem in ("ADD", "SUB")          # only these two have an immediate form
        if dk == "r8" and sk == "r8":
            self.regular(mnem + "8" if simple else mnem, a=sv, b=dv)   # op8_1 = source, op8_2 = dest
        elif dk == "r16" and sk == "r16":
            self.regular(mnem + "16", a=sv, b=dv)
        elif dk == "r8" and sk == "r16":         # mixed widths: op16 says which side is which
            self.regular(mnem + "_UNM", a=sv, w=0, b=dv)   # 8-bit dest, 16-bit source
        elif dk == "r16" and sk == "r8":
            self.regular(mnem + "_UNM", a=dv, w=1, b=sv)   # 16-bit dest, 8-bit source
        elif dk in ("r8", "r16") and sk == "imm":
            if not simple:
                raise AsmError(f"{mnem} has no immediate form; load the value into a register first")
            wide = dk == "r16"
            val = self.imm16(sv) if wide else self.imm8(sv)    # range-checked, masked to the width
            self.regular("ADD_IMM" if mnem == "ADD" else "SUB_IMM", a=int(wide), w=val, b=dv)
        else:
            raise AsmError(f"{mnem} needs two registers (R0-R{NUM_REG8 - 1} or A-D)"
                           + (", or a register and a number" if simple else ""))

    def compare(self, d, s):
        """CMP a, b: sets the zero flag (a == b) and the carry flag (a < b, unsigned) from a - b."""
        (dk, dv), (sk, sv) = d, s
        if dk == "r8" and sk == "r8":
            self.regular("COMPARE_Z", a=dv, w=0, b=sv)
        elif dk == "r16" and sk == "r16":
            self.regular("COMPARE_Z", a=dv, w=1, b=sv)
        elif dk == "r16" and sk == "r8":
            self.regular("COMPARE_Z", a=dv, w=2, b=sv)
        elif dk == "r8" and sk == "r16":
            # the CPU only has "16-bit vs 8-bit", so swap the operands.  Equality (zero flag) is
            # symmetric, but the carry flag (a < b) comes out reversed.
            if self.final:
                self.warnings.append((self.syms.get("__LINE__", 0),
                                      "CMP r8, r16 is assembled as CMP r16, r8: the zero flag is right but the "
                                      "carry flag is reversed (JC/JNC would test r16 < r8)"))
            self.regular("COMPARE_Z", a=sv, w=2, b=dv)
        elif dk in ("r8", "r16") and sk == "imm":
            self.regular("CMPZ_IMM", a=dv, w=self.imm8(sv) if dk == "r8" else self.imm16(sv),
                         b=int(dk == "r16"))
        else:
            raise AsmError(f"CMP needs two registers (R0-R{NUM_REG8 - 1} or A-D)")

    def logic(self, mnem, d, s):
        """XOR / OR / AND / TEST: op8_1 = source, op8_2 = dest, op16 = 0 (8-bit) or 1 (16-bit).
        TEST is AND without the write-back: it only sets the zero flag."""
        (dk, dv), (sk, sv) = d, s
        if dk == sk and dk in ("r8", "r16"):
            self.regular("AND_TEST" if mnem == "TEST" else mnem, a=sv, w=int(dk == "r16"), b=dv)
        elif dk in ("r8", "r16") and sk == "imm":
            raise AsmError(f"{mnem} has no immediate form; load the value into a register first")
        else:
            raise AsmError(f"{mnem} needs two registers of the same size "
                           f"(R0-R{NUM_REG8 - 1} or A-D)")

    def instruction(self, mnem, rest):
        ops = split_args(rest)
        if mnem in ("HLT", "RET", "IRET", "PUSHA", "POPA"):
            if ops:
                raise AsmError(f"{mnem} takes no operands")
            opc = {"HLT": "HALT", "PUSHA": "PUSH_ALL", "POPA": "POP_ALL"}.get(mnem, mnem)   # HALT is the core's opcode name
            self.out += bytes([1, OPC[opc], 0])
        elif mnem in ("IN", "OUT"):
            usage = "IN dest, port" if mnem == "IN" else "OUT port, value"
            if len(ops) != 2:
                raise AsmError(f"{mnem} takes two operands: {usage}")
            (k1, v1), (k2, v2) = self.operand(ops[0]), self.operand(ops[1])
            if mnem == "IN":
                reg, (pk, pv) = (k1, v1), (k2, v2)      # IN dest, port
            else:
                reg, (pk, pv) = (k2, v2), (k1, v1)      # OUT port, value
            if reg[0] != "r8":
                raise AsmError(f"{mnem}: the {'destination' if mnem == 'IN' else 'value'} "
                               f"must be an 8-bit register (R0-R{NUM_REG8 - 1})")
            if pk == "r8":                 # port number held in a register -> mode 0
                port, mode = pv, 0
            elif pk == "imm":              # port number written directly   -> mode 1
                if self.final and not 0 <= pv <= 255:
                    raise AsmError(f"port {pv} is out of range (0-255)")
                port, mode = pv & 0xFF, 1
            else:
                raise AsmError(f"{mnem}: the port must be an 8-bit register or a number 0-255")
            self.regular("PORT_IN" if mnem == "IN" else "PORT_OUT", a=reg[1], w=mode, b=port)
        elif mnem in ("CLI", "STI"):
            if ops:
                raise AsmError(f"{mnem} takes no operands")
            self.out += bytes([1, OPC["INTERRUPT_C"], int(mnem == "STI")])   # operand = new value of IF
        elif mnem == "INT":
            if len(ops) != 1:
                raise AsmError("INT takes one operand: the vector number (0-255)")
            kind, val = self.operand(ops[0])
            if kind != "imm":
                raise AsmError("INT needs a vector number (0-255), not a register")
            if self.final and not 0 <= val <= 255:
                raise AsmError(f"INT vector {val} is out of range (0-255)")
            self.out += bytes([1, OPC["INT"], val & 0xFF])
        elif mnem in ("SHR", "SHL"):
            if len(ops) != 1:
                raise AsmError(f"{mnem} takes one operand (a register); it shifts by one bit")
            kind, val = self.operand(ops[0])
            if kind not in ("r8", "r16"):
                raise AsmError(f"{mnem} needs a register (R0-R{NUM_REG8 - 1} or A-D)")
            self.regular(mnem, a=val, b=int(kind == "r16"))   # op8_1 = reg, op8_2 = 0 (8-bit) / 1 (16-bit)
        elif mnem in ("PUSH", "POP"):
            if len(ops) != 1:
                raise AsmError(f"{mnem} takes one operand: an 8-bit register or A-D")
            kind, val = self.operand(ops[0])
            if kind not in ("r8", "r16"):
                raise AsmError(f"{mnem} needs a register (R0-R{NUM_REG8 - 1} or A-D)"
                               + ("; push a number via a register first" if mnem == "PUSH" else ""))
            self.regular(mnem, a=val, b=int(kind == "r16"))   # op8_1 = reg, op8_2 = 0/1
        elif mnem in ("JMP", "JZ", "JNZ", "JC", "JNC", "CALL"):
            if len(ops) != 1:
                raise AsmError(f"{mnem} takes one operand (an address or label)")
            kind, val = self.operand(ops[0])
            if kind == "r16" and mnem == "JMP":      # JMP A / JMP B -> JMP_REG (small opcode)
                self.out += bytes([1, OPC["JMP_REG"], val])
            elif kind != "imm":
                raise AsmError(f"{mnem} needs an address or label"
                               + (" (or A-D for JMP)" if mnem == "JMP" else ""))
            else:
                opc = {"JC": "JUMP_CARRY", "JNC": "JUMP_NOT_CARRY"}.get(mnem, mnem)
                self.regular(opc, w=self.imm16(val))
        else:
            if len(ops) != 2:
                raise AsmError(f"{mnem} takes two operands: {mnem} dest, source")
            d, s = self.operand(ops[0]), self.operand(ops[1])
            if mnem == "MOV":
                self.mov(d, s)
            elif mnem in ("ADD", "SUB", "MUL", "DIV"):
                self.arith(mnem, d, s)
            elif mnem == "CMP":
                self.compare(d, s)
            else:
                self.logic(mnem, d, s)

    def data(self, mnem, rest):
        args = split_args(rest)
        if not args or "" in args:
            raise AsmError(f"{mnem} needs a comma-separated list of values")
        for a in args:
            if mnem == "DB":
                if a.upper() in self.strings:
                    self.out += self.strings[a.upper()]
                elif a[0] in "\"'" and quoted_end(a) == len(a) - 1:
                    self.out += bytes(parse_quoted(a))
                else:
                    self.out.append(self.imm8(self.value(a)))
            else:
                self.out += self.pack16(self.imm16(self.value(a)))

    def const(self, text):
        """Evaluate an expression that must be known right now (it decides how many bytes are emitted)."""
        saved, self.final = self.final, True
        try:
            return self.value(text)
        finally:
            self.final = saved

    def align(self, rest):
        """ALIGN n[, fill]: pad until the current address is a multiple of n."""
        args = split_args(rest)
        if not 1 <= len(args) <= 2 or "" in args:
            raise AsmError("ALIGN takes a multiple and an optional fill byte: ALIGN n[, fill]")
        n = self.const(args[0])
        fill = self.imm8(self.const(args[1])) if len(args) == 2 else 0
        if n <= 0:
            raise AsmError("ALIGN needs a positive multiple")
        pad = -self.addr() % n
        self.check_size(len(self.out) + pad)
        self.out += bytes([fill]) * pad

    def check_size(self, size):
        if size > 0x10000:
            raise AsmError("the output would be larger than 64 KiB")

    def split_times(self, rest):
        """Split 'COUNT-EXPR  statement' at the first name that cannot continue the expression."""
        pos, want_operand = 0, True
        while pos < len(rest):
            m = TOKEN_RE.match(rest, pos)
            if not m:
                break
            kind, text, start = m.lastgroup, m.group(m.lastgroup), m.start(m.lastgroup)
            if kind == "id" and not want_operand:
                return rest[:start], rest[start:]
            if kind in ("hexd", "hexh", "num", "chr", "sec", "id") or text == "$":
                want_operand = False
            elif text == ")":
                want_operand = False
            else:                                  # binary / unary operator or '('
                want_operand = True
            pos = m.end()
        raise AsmError("TIMES needs a count and something to repeat: TIMES count instruction-or-DB/DW")

    def times(self, rest):
        count_text, stmt = self.split_times(rest)
        count = self.const(count_text)
        if count < 0:
            raise AsmError(f"TIMES count is negative ({count})")
        for _ in range(count):
            self.emit(stmt.strip())
            self.check_size(len(self.out))

    # -- lines ----------------------------------------------------------------
    def assemble_line(self, text):
        start = len(self.out)
        start_addr = self.addr()
        body = text
        while True:
            m = LABEL_RE.match(body)
            if not m:
                break
            self.define(m.group(1), self.addr(), "label")
            body = m.group(2)
        if body:
            self.emit(body)
        if self.final:
            self.listing.append((start_addr, bytes(self.out[start:]), text))

    def emit(self, body):
        """Assemble one statement (no label)."""
        if body:
            m = EQU_RE.match(body) or EQ_RE.match(body)
            parts = body.split(None, 1)
            mnem = parts[0].upper()
            rest = parts[1] if len(parts) > 1 else ""
            if m:
                self.define(m.group(1), self.value(m.group(2)))
            elif mnem == "ORG":
                saved, self.final = self.final, True      # ORG must be known now
                try:
                    target = self.value(rest)
                finally:
                    self.final = saved
                if not 0 <= target <= 0xFFFF:
                    raise AsmError(f"ORG 0x{target:X} is outside the 16-bit address space")
                # ORG only changes the address that labels / $ are computed from.
                # Nothing is padded: following bytes are emitted right after the previous ones.
                self.base = target - len(self.out)
                if not self.out:
                    self.origin = target
            elif mnem in ("DB", "DW"):
                self.data(mnem, rest)
            elif mnem == "ALIGN":
                self.align(rest)
            elif mnem == "TIMES":
                self.times(rest)
            elif mnem == "EXPORT":
                names = split_args(rest)
                if not names or any(not re.fullmatch(IDENT, n) for n in names):
                    raise AsmError("EXPORT takes a comma-separated list of label, constant or macro names")
                self.exports += [(n, self.syms.get("__LINE__", 0)) for n in names]
            elif mnem in MNEMONICS:
                self.instruction(mnem, rest)
            else:
                raise AsmError(f"unknown instruction or directive '{parts[0]}'")

    def run_pass(self, items):
        self.out = bytearray()
        self.listing = []
        self.base = 0
        self.origin = 0
        self.exports = []
        self.warnings = []
        for text, no, ctx in items:
            if not text:
                continue
            self.syms["__LINE__"] = no
            try:
                self.assemble_line(text)
            except AsmError as e:
                raise AsmError(f"line {no}{ctx}: {e}") from None

    def assemble(self, src_lines):
        items, self.macros = preprocess(src_lines, self.import_macros)
        self.final = False
        self.run_pass(items)       # pass 1: find label addresses
        self.final = True
        self.run_pass(items)       # pass 2: real values
        if len(self.out) > 0x10000:
            raise AsmError("program is larger than 64 KiB")
        return bytes(self.out)


def assemble(source_text, big_endian=False, filename="<input>", imports=None, import_macros=None):
    asm = Assembler(big_endian, filename, imports, import_macros)
    return asm.assemble(source_text.splitlines()), asm


# --------------------------------------------------------------------------
# Symbol files (binary).  Only names listed in an EXPORT directive are written.
#
#   header : "X8SY" | u8 format version (1) | u16 entry count                  (all little-endian)
#   entry  : name (ASCII, NUL-terminated) | u8 kind | data
#   kind 1 label    data = u16 address
#   kind 2 constant data = i64 value
#   kind 3 macro    data = u8 parameter count | each parameter name (ASCII, NUL-terminated)
#                          | u16 line the macro was defined on | source file name (UTF-8, NUL-terminated)
#                          | u32 body length | body (UTF-8, lines separated by \n)
# --------------------------------------------------------------------------
import struct

SYM_MAGIC, SYM_VERSION = b"X8SY", 1
KIND_LABEL, KIND_CONST, KIND_MACRO = 1, 2, 3
KIND_NAMES = {KIND_LABEL: "label", KIND_CONST: "constant", KIND_MACRO: "macro"}
KIND_IDS = {"label": KIND_LABEL, "constant": KIND_CONST}


def collect_exports(asm):
    """Resolve the EXPORT directives -> ordered list of (name, kind_id, payload). Raises AsmError."""
    out, seen = [], set()
    for name, line in asm.exports:
        found = False
        if name in asm.syms and name not in BUILTIN_NUM:
            found = True
            if (name, "sym") not in seen:
                seen.add((name, "sym"))
                val, kind = asm.syms[name], asm.kinds.get(name, "constant")
                if kind == "label" and not 0 <= val <= 0xFFFF:
                    raise AsmError(f"line {line}: EXPORT: label '{name}' (0x{val:X}) is outside the 16-bit address space")
                out.append((name, KIND_IDS[kind], val))
        mac = asm.macros.get(name.upper())
        if mac:
            found = True
            if (name.upper(), "macro") not in seen:
                seen.add((name.upper(), "macro"))
                out.append((name.upper(), KIND_MACRO, mac))
        if not found:
            if name.upper() in BUILTIN_NUM | BUILTIN_STR:
                raise AsmError(f"line {line}: EXPORT: '{name}' is a built-in constant")
            raise AsmError(f"line {line}: EXPORT: '{name}' is not a label, constant or macro defined or imported here")
        if len(name) > 255:
            raise AsmError(f"line {line}: EXPORT: name '{name[:20]}...' is too long")
    return out


def macro_warnings(asm, entries):
    """Exported macros expand in the importing file, so names they use must exist there too."""
    exported = {n for n, _, _ in entries}
    exported_macros = {n for n, k, _ in entries if k == KIND_MACRO}
    warns = []
    for name, kind, mac in entries:
        if kind != KIND_MACRO:
            continue
        text = "\n".join(line for line, _ in mac["body"])
        text = re.sub(r"\{\w+\}|@\w+", " ", text)
        for w in dict.fromkeys(re.findall(IDENT, text)):
            if w.upper() in RESERVED or w in mac["params"]:
                continue
            uses_sym = w in asm.syms and w not in BUILTIN_NUM and w not in exported
            uses_mac = w.upper() in asm.macros and w.upper() not in exported_macros
            if uses_sym or uses_mac:
                warns.append(f"warning: exported macro '{name}' uses '{w}', which is not exported; "
                             f"files that import {name} must define or import '{w}' themselves")
    return warns


def pack_symbols(entries, filename):
    body = bytearray()
    for name, kind, data in entries:
        body += name.encode("ascii") + b"\0" + bytes([kind])
        if kind == KIND_LABEL:
            body += struct.pack("<H", data)
        elif kind == KIND_CONST:
            body += struct.pack("<q", data)
        else:
            params = data["params"]
            text = "\n".join(line for line, _ in data["body"]).encode("utf-8")
            body += bytes([len(params)])
            for p in params:
                body += p.encode("ascii") + b"\0"
            src = (data.get("file") or filename).encode("utf-8")
            body += struct.pack("<H", data["line"]) + src + b"\0" + struct.pack("<I", len(text)) + text
    return SYM_MAGIC + bytes([SYM_VERSION]) + struct.pack("<H", len(entries)) + bytes(body)


def unpack_symbols(blob):
    """Parse a symbol file -> list of (name, kind_id, data).  Raises AsmError with the byte offset."""
    pos = 0

    def need(n, what):
        if pos + n > len(blob):
            raise AsmError(f"offset 0x{pos:X}: truncated symbol file (expected {what})")

    def cstr(what):
        nonlocal pos
        end = blob.find(b"\0", pos)
        if end < 0:
            raise AsmError(f"offset 0x{pos:X}: truncated symbol file (unterminated {what})")
        text, pos = blob[pos:end], end + 1
        return text

    if blob[:4] != SYM_MAGIC:
        raise AsmError("not a vsk8asm symbol file (bad magic); symbol files from before 5.0.0 "
                       "must be re-exported using EXPORT directives")
    if len(blob) < 7:
        raise AsmError("truncated symbol file (header)")
    if blob[4] != SYM_VERSION:
        raise AsmError(f"unsupported symbol file version {blob[4]} (this assembler reads version {SYM_VERSION})")
    (count,), pos = struct.unpack_from("<H", blob, 5), 7
    entries = []
    for _ in range(count):
        name = cstr("name").decode("ascii", "replace")
        need(1, "kind"); kind = blob[pos]; pos += 1
        if kind == KIND_LABEL:
            need(2, "label address"); (data,) = struct.unpack_from("<H", blob, pos); pos += 2
        elif kind == KIND_CONST:
            need(8, "constant value"); (data,) = struct.unpack_from("<q", blob, pos); pos += 8
        elif kind == KIND_MACRO:
            need(1, "parameter count"); nparams = blob[pos]; pos += 1
            params = [cstr("parameter").decode("ascii", "replace") for _ in range(nparams)]
            need(2, "macro line"); (line,) = struct.unpack_from("<H", blob, pos); pos += 2
            src = cstr("source name").decode("utf-8", "replace")
            need(4, "macro body length"); (n,) = struct.unpack_from("<I", blob, pos); pos += 4
            need(n, "macro body"); text = blob[pos:pos + n].decode("utf-8", "replace"); pos += n
            lines = text.split("\n")
            data = {"name": name, "params": params, "line": line, "file": src,
                    "body": [(t, line + 1 + i) for i, t in enumerate(lines)]}
        else:
            raise AsmError(f"offset 0x{pos - 1:X}: unknown symbol kind {kind} for '{name}'")
        entries.append((name, kind, data))
    return entries


def read_symbols(path):
    """Load a symbol file -> ({name: (value, path, kind)}, {NAME: macro}).  Raises AsmError / OSError."""
    with open(path, "rb") as f:
        entries = unpack_symbols(f.read())
    syms, macros = {}, {}
    for name, kind, data in entries:
        if kind == KIND_MACRO:
            macros[name.upper()] = dict(data, sym=path)
        else:
            if HEXH_RE.fullmatch(name) or name.upper() in RESERVED:
                raise AsmError(f"'{name}' is not a usable symbol name")
            syms[name] = (data, path, KIND_NAMES[kind])
    return syms, macros


def describe_symbols(entries):
    lines = [f"{'NAME':<24} {'KIND':<9} DATA"]
    for name, kind, data in entries:
        if kind == KIND_LABEL:
            shown = f"0x{data:04X}"
        elif kind == KIND_CONST:
            shown = f"0x{data:04X}" if 0 <= data <= 0xFFFF else str(data)
        else:
            shown = f"({', '.join(data['params'])})  {len(data['body'])} line(s), from {data['file']}:{data['line']}"
        lines.append(f"{name:<24} {KIND_NAMES[kind]:<9} {shown}")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description="Assembler for the VSK-8A emulator")
    ap.add_argument("--version", action="version", version=f"vsk8asm {VERSION_STR}")
    ap.add_argument("source", nargs="?")
    ap.add_argument("-o", "--output", help="output .bin (default: <source>.bin)")
    ap.add_argument("--big-endian", action="store_true",
                    help="emit 16-bit values big-endian (default little-endian)")
    ap.add_argument("--export-symbols", metavar="FILE",
                    help="write the names listed in EXPORT directives (labels, constants, macros) to FILE")
    ap.add_argument("--import-symbols", metavar="FILE", action="append", default=[],
                    help="read labels, constants and macros from a symbol file (repeatable)")
    ap.add_argument("--show-symbols", metavar="FILE",
                    help="print the contents of a symbol file and exit")
    ap.add_argument("-l", "--listing", action="store_true",
                    help="print address/bytes/source listing and symbol table")
    args = ap.parse_args()

    if args.show_symbols:
        try:
            with open(args.show_symbols, "rb") as f:
                print(describe_symbols(unpack_symbols(f.read())))
        except OSError as e:
            print(f"{args.show_symbols}: error: cannot read symbol file ({e.strerror})", file=sys.stderr)
            sys.exit(1)
        except AsmError as e:
            print(f"{args.show_symbols}: error: {e}", file=sys.stderr)
            sys.exit(1)
        return
    if not args.source:
        ap.error("the following arguments are required: source")

    with open(args.source, encoding="utf-8") as f:
        text = f.read()
    imports, import_macros = {}, {}
    for path in args.import_symbols:
        try:
            syms, macros = read_symbols(path)
            for name, (val, src, kind) in syms.items():
                if name in imports and imports[name][:1] + imports[name][2:] != (val, kind):
                    raise AsmError(f"'{name}' is also defined in {imports[name][1]} with a different value")
                imports[name] = (val, src, kind)
            for name, mac in macros.items():
                old = import_macros.get(name)
                if old and (old["params"], old["body"]) != (mac["params"], mac["body"]):
                    raise AsmError(f"macro '{name}' is also defined in {old['sym']} with a different body")
                import_macros[name] = mac
        except OSError as e:
            print(f"{path}: error: cannot read symbol file ({e.strerror})", file=sys.stderr)
            sys.exit(1)
        except AsmError as e:
            print(f"{path}: error: {e}", file=sys.stderr)
            sys.exit(1)
    try:
        data, asm = assemble(text, args.big_endian, args.source, imports, import_macros)
        entries = collect_exports(asm)
    except AsmError as e:
        print(f"{args.source}: error: {e}", file=sys.stderr)
        sys.exit(1)

    out = args.output or re.sub(r"\.[^.\\/]*$", "", args.source) + ".bin"
    with open(out, "wb") as f:
        f.write(data)

    for line, msg in asm.warnings:
        print(f"{args.source}: warning: line {line}: {msg}", file=sys.stderr)
    if args.export_symbols:
        for w in macro_warnings(asm, entries):
            print(f"{args.source}: {w}", file=sys.stderr)
        with open(args.export_symbols, "wb") as f:
            f.write(pack_symbols(entries, args.source))
    elif entries:
        print(f"{args.source}: warning: EXPORT directives found but --export-symbols was not given", file=sys.stderr)

    if args.listing:
        for addr, bs, src in asm.listing:
            shown = " ".join(f"{b:02X}" for b in bs[:6])
            if len(bs) > 6:
                shown += " ..."
            print(f"{addr:04X}  {shown:<21} {src}")
        print("\nSymbols:")
        own = {k: v for k, v in asm.syms.items() if k not in asm.imported and k not in BUILTIN_NUM}
        for k, v in sorted(own.items(), key=lambda kv: kv[1]):
            print(f"  {k:<16} 0x{v & 0xFFFF:04X}  {asm.kinds.get(k, 'constant')}")
        if asm.imported or asm.import_macros:
            print("\nImported:")
            for k, (v, src, kind) in sorted(asm.imported.items(), key=lambda kv: kv[1][0]):
                print(f"  {k:<16} 0x{v & 0xFFFF:04X}  {kind}  ({src})")
            for k, mac in sorted(asm.import_macros.items()):
                print(f"  {k:<16} macro({', '.join(mac['params'])})  ({mac['sym']})")
    where = f" (load address 0x{asm.origin:04X})" if asm.origin else ""
    extra = f", exported {len(entries)} symbol(s) -> {args.export_symbols}" if args.export_symbols else ""
    print(f"Assembled {len(data)} bytes{where} -> {out}{extra}")


if __name__ == "__main__":
    main()