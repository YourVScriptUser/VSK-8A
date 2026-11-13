#!/usr/bin/env python3
"""
vsk8a_disasm - disassembler for the VSK-8A

    python vsk8a_disasm.py kernel.bin --base 0x300
    python vsk8a_disasm.py bios.bin --as bios --symbols bios.sym
    python vsk8a_disasm.py kernel.bin --as kernel --asm -o kernel_re.x8

How it works
  * Code is found by FOLLOWING CONTROL FLOW from the entry point (jmp / jz / jnz / call),
    not by decoding every byte in order, so strings, tables and padding do not get
    disassembled as garbage instructions.
  * Addresses loaded with `mov a, <imm16>` that point at something that decodes as clean code
    are treated as function pointers (ISRs, vector tables). Leftover regions that decode as
    clean code are shown as "unreferenced code?". `--strict` turns both heuristics off.
  * Every instruction is only accepted if it is CANONICAL (unused operand fields are zero,
    registers are in range), so `--asm` output reassembles to the same bytes.
  * Anything that is not code is shown as db / dw / times / strings.

Pure standard library, Python 3.8+.
"""

import argparse
import bisect
import os
import sys
from struct import error as struct_error
from collections import defaultdict

# --------------------------------------------------------------------------------------
# Machine description (matches core.py / regs.py / assembler.py)
# --------------------------------------------------------------------------------------
R8 = ["r0", "r1", "r2", "r3", "al", "ah", "bl", "bh", "cl", "ch", "dl", "dh"]
R16 = ["a", "b", "c", "d"]

PORTS = {
    0x00: "video mmio start (low)", 0x01: "video mmio start (high)",
    0x02: "video mmio end (low)",   0x03: "video mmio end (high)",
    0x05: "disk command",
    0x06: "disk dma addr (low)",    0x07: "disk dma addr (high)",
    0x08: "disk sector (low)",      0x09: "disk sector (high)",
    0x0A: "disk status",
    0x0B: "disk sector count (low)", 0x0C: "disk sector count (high)",
    0x0D: "keyboard irq",           0x0E: "keyboard last key",
    0x0F: "keyboard modifier",
    0x10: "cursor x", 0x11: "cursor y", 0x12: "cursor char", 0x13: "cursor bg",
    0x14: "disk irq",
}

INTS = {
    0x10: "bios video", 0x11: "bios disk read / read sector",
    0x12: "wait key", 0x15: "print string (kernel)", 0x16: "clear screen (kernel)",
}

PRESETS = {  # name -> (base address, description)
    "bios":   (0xF000, "BIOS image (reset vector 0xF000)"),
    "boot":   (0x0100, "boot sector, loaded at 0x100 by the BIOS"),
    "kernel": (0x0300, "kernel image at 0x300 (0xBEAF marker + jmp)"),
    "shell":  (0x1900, "shell image at 0x1900"),
}

KERNEL_MAGIC = b"\xAF\xBE"   # dw 0xBEAF
CHAR_NAMES = {10: "\\n", 13: "\\r", 9: "\\t", 8: "\\b", 0: "\\0"}


# --------------------------------------------------------------------------------------
# Operand tokens
# --------------------------------------------------------------------------------------
class Ref:
    """A number inside an instruction. role: code | ptr | mem | imm | num16 | port"""
    __slots__ = ("value", "role", "bits")

    def __init__(self, value, role, bits):
        self.value, self.role, self.bits = value, role, bits


class Mem:
    """[inner] where inner is a register name (str) or a Ref."""
    __slots__ = ("inner",)

    def __init__(self, inner):
        self.inner = inner


class Bad(Exception):
    pass


def r8(i):
    if i >= 12:
        raise Bad
    return R8[i]


def r16(i):
    if i >= 4:
        raise Bad
    return R16[i]


def reg(kind, i):
    if kind == 0:
        return r8(i)
    if kind == 1:
        return r16(i)
    raise Bad


def zero(*vals):
    if any(vals):
        raise Bad


def imm8(v):
    if v > 255:
        raise Bad
    return Ref(v, "imm", 8)


def imm16(v):
    return Ref(v, "imm", 16)


# --------------------------------------------------------------------------------------
# Decoder
# --------------------------------------------------------------------------------------
# flow: seq | jmp | jcc | call | ret | end
def _regular(op, a, w, b):
    """prefix 0: opcode, op8_1=a, op16=w, op8_2=b.  Returns (mnemonic, [operands], flow)."""
    if op == 0:                                   # LOAD_REG
        zero(w); return "mov", [r8(a), imm8(b)], "seq"
    if op == 2:                                   # WRITE_MEM8
        if b == 0:
            return "mov", [Mem(Ref(w, "mem", 16)), imm8(a)], "seq"
        if b == 1:
            return "mov", [Mem(Ref(w, "mem", 16)), r8(a)], "seq"
        raise Bad
    if op == 3:                                   # WRITE_MEM8A
        zero(w); return "mov", [Mem(r16(a)), r8(b)], "seq"
    if op == 4:                                   # WRITE_MEM16
        zero(w); return "mov", [Mem(r16(a)), r16(b)], "seq"
    if op in (5, 7):                              # SUB8 / ADD8   (dest = b, src = a)
        zero(w); return ("sub" if op == 5 else "add"), [r8(b), r8(a)], "seq"
    if op in (6, 8):                              # SUB16 / ADD16
        zero(w); return ("sub" if op == 6 else "add"), [r16(b), r16(a)], "seq"
    if op in (9, 10, 11):                         # JZ / JNZ / JMP
        zero(a, b)
        return {9: "jz", 10: "jnz", 11: "jmp"}[op], [Ref(w, "code", 16)], ("jmp" if op == 11 else "jcc")
    if op == 12:                                  # LOAD_REG16
        zero(b); return "mov", [r16(a), Ref(w, "ptr", 16)], "seq"
    if op in (13, 14):                            # PORT_IN / PORT_OUT
        if w == 0:
            port = r8(b)
        elif w == 1:
            port = Ref(b, "port", 8)
        else:
            raise Bad
        if op == 13:
            return "in", [r8(a), port], "seq"
        return "out", [port, r8(a)], "seq"
    if op == 16:                                  # READ_MEM8A
        zero(w); return "mov", [r8(a), Mem(r16(b))], "seq"
    if op == 17:                                  # READ_MEM8
        zero(b); return "mov", [r8(a), Mem(Ref(w, "mem", 16))], "seq"
    if op == 18:                                  # READ_MEM16
        zero(w); return "mov", [r16(a), Mem(r16(b))], "seq"
    if op in (19, 45):                            # ADD_IMM / SUB_IMM  (a = 0:8-bit 1:16-bit)
        name = "add" if op == 19 else "sub"
        if a == 0:
            return name, [r8(b), imm8(w)], "seq"
        if a == 1:
            return name, [r16(b), imm16(w)], "seq"
        raise Bad
    if op in (20, 21, 22, 23):                    # XOR OR AND TEST  (dest = b, src = a)
        name = {20: "xor", 21: "or", 22: "and", 23: "test"}[op]
        if w not in (0, 1):
            raise Bad
        return name, [reg(w, b), reg(w, a)], "seq"
    if op in (24, 25):                            # PUSH / POP
        zero(w)
        if b not in (0, 1):
            raise Bad
        return ("push" if op == 24 else "pop"), [reg(b, a)], "seq"
    if op == 26:                                  # CALL
        zero(a, b); return "call", [Ref(w, "code", 16)], "call"
    if op == 28:                                  # MOVE_SP
        zero(a, b); return "mov", ["sp", Ref(w, "num16", 16)], "seq"
    if op in (29, 30, 31, 32):                    # ADD/SUB/MUL/DIV with mixed widths
        name = {29: "add", 30: "sub", 31: "mul", 32: "div"}[op]
        if w == 0:
            return name, [r8(b), r16(a)], "seq"   # 8-bit dest, 16-bit source
        if w == 1:
            return name, [r16(a), r8(b)], "seq"   # 16-bit dest, 8-bit source
        raise Bad
    if op in (33, 34):                            # DIV / MUL (8-bit)
        zero(w); return ("div" if op == 33 else "mul"), [r8(b), r8(a)], "seq"
    if op in (35, 36):                            # DIV16 / MUL16
        zero(w); return ("div" if op == 35 else "mul"), [r16(b), r16(a)], "seq"
    if op == 37:                                  # MOVE  (src = a, dest = b)
        if w == 0:
            return "mov", [r8(b), r8(a)], "seq"
        if w == 1:
            return "mov", [r16(b), r16(a)], "seq"
        if w == 2:
            return "mov", [r16(b), r8(a)], "seq"
        if w == 3:
            return "mov", [r8(b), r16(a)], "seq"
        raise Bad
    if op == 38:                                  # COMPARE_Z
        if w == 0:
            return "cmp", [r8(a), r8(b)], "seq"
        if w == 1:
            return "cmp", [r16(a), r16(b)], "seq"
        if w == 2:
            return "cmp", [r16(a), r8(b)], "seq"
        raise Bad
    if op in (39, 40):                            # SHR / SHL
        zero(w)
        if b not in (0, 1):
            raise Bad
        return ("shr" if op == 39 else "shl"), [reg(b, a)], "seq"
    if op == 44:                                  # CMPZ_IMM
        if b == 0:
            return "cmp", [r8(a), imm8(w)], "seq"
        if b == 1:
            return "cmp", [r16(a), imm16(w)], "seq"
        raise Bad
    return None


def _small(op, a):
    """prefix 1: opcode, op8_1=a."""
    if op == 1:
        zero(a); return "hlt", [], "seq"           # an IRQ wakes the CPU, so execution continues
    if op == 15:
        return "jmp", [r16(a)], "end"
    if op == 27:
        zero(a); return "ret", [], "ret"
    if op == 41:
        return "int", [Ref(a, "int", 8)], "seq"
    if op == 42:
        zero(a); return "iret", [], "ret"
    if op == 43:
        if a not in (0, 1):
            raise Bad
        return ("sti" if a else "cli"), [], "seq"
    if op == 46:
        zero(a); return "pusha", [], "seq"
    if op == 47:
        zero(a); return "popa", [], "seq"
    return None


class Insn:
    __slots__ = ("addr", "size", "raw", "mnem", "ops", "flow", "note")

    def __init__(self, addr, size, raw, mnem, ops, flow):
        self.addr, self.size, self.raw = addr, size, raw
        self.mnem, self.ops, self.flow = mnem, ops, flow
        self.note = None

    @property
    def target(self):
        """Address operand of a jmp/jz/jnz/call, or None."""
        if self.flow in ("jmp", "jcc", "call"):
            return self.ops[0].value
        return None


def decode(img, off, base=0):
    """Decode one instruction at img[off]. Returns Insn or None (invalid / non-canonical)."""
    n = len(img)
    if off < 0 or off >= n:
        return None
    p = img[off]
    try:
        if p == 0:
            if off + 6 > n:
                return None
            r = _regular(img[off + 1], img[off + 2], img[off + 3] | (img[off + 4] << 8), img[off + 5])
            size = 6
        elif p == 1:
            if off + 3 > n:
                return None
            r = _small(img[off + 1], img[off + 2])
            size = 3
        else:
            return None
    except Bad:
        return None
    if r is None:
        return None
    return Insn(base + off, size, bytes(img[off:off + size]), r[0], r[1], r[2])


# --------------------------------------------------------------------------------------
# Symbols
# --------------------------------------------------------------------------------------
def parse_int(text):
    t = text.strip().lower()
    if t.startswith("$"):
        return int(t[1:], 16)
    if t.endswith("h") and not t.startswith("0x"):
        return int(t[:-1], 16)
    return int(t, 0)


def _parse_symbol_blob(blob):
    """Parse the binary symbol file written by the assembler's --export-symbols
    (magic 'X8SY', version 1). Returns (labels, consts) or None if it is not that format."""
    import struct
    if blob[:4] != b"X8SY":
        return None
    if len(blob) < 7 or blob[4] != 1:
        raise ValueError("unsupported symbol file version %d" % (blob[4] if len(blob) > 4 else -1))
    pos = 7
    (count,) = struct.unpack_from("<H", blob, 5)

    def cstr():
        nonlocal pos
        end = blob.index(b"\0", pos)
        text, pos = blob[pos:end].decode("utf-8", "replace"), end + 1
        return text

    labels, consts = {}, {}
    for _ in range(count):
        name = cstr()
        kind = blob[pos]; pos += 1
        if kind == 1:                                   # label: u16 address
            (v,) = struct.unpack_from("<H", blob, pos); pos += 2
            labels[name] = v
        elif kind == 2:                                 # constant: i64
            (v,) = struct.unpack_from("<q", blob, pos); pos += 8
            consts[name] = v & 0xFFFF
        elif kind == 3:                                 # macro: skip it
            nparams = blob[pos]; pos += 1
            for _ in range(nparams):
                cstr()
            pos += 2
            cstr()
            (n,) = struct.unpack_from("<I", blob, pos); pos += 4 + n
        else:
            raise ValueError("unknown symbol kind %d" % kind)
    return labels, consts


def load_symbols(path):
    """Returns (labels, consts), each {name: value}.
    Accepts the assembler's --export-symbols file, or a text file with lines like
    `name 0xF573`, `name = 0xF573` or `0xF573 name` (';' / '#' start comments)."""
    with open(path, "rb") as f:
        blob = f.read()
    parsed = _parse_symbol_blob(blob)
    if parsed is not None:
        return parsed
    labels = {}
    for line in blob.decode("utf-8", "replace").splitlines():
        line = line.split(";")[0].split("#")[0].replace("=", " ").replace(":", " ").split()
        if len(line) != 2:
            continue
        for name, val in ((line[0], line[1]), (line[1], line[0])):
            try:
                labels[name] = parse_int(val) & 0xFFFF
                break
            except ValueError:
                continue
    return labels, {}


# --------------------------------------------------------------------------------------
# Disassembler
# --------------------------------------------------------------------------------------
def is_text(b):
    return 0x20 <= b <= 0x7E or b in (9, 10, 13)


class Disassembler:
    def __init__(self, img, base=0, entries=None, labels=None, consts=None, strict=False):
        self.img = bytes(img)
        self.base = base
        self.end = base + len(self.img)
        self.strict = strict
        self.entries = list(entries) if entries else []
        self.insns = {}                       # addr -> Insn
        self.cov = bytearray(len(self.img))   # 1 = start of insn, 2 = inside insn
        self.refs = defaultdict(set)          # addr -> {'call','jump','ptr','mem','entry','sweep'}
        self.xrefs = defaultdict(list)        # addr -> [(from_addr, kind)]
        self.ptrs = {}                        # in-image 16-bit immediates loaded with mov r16, imm
        self.mems = {}                        # in-image absolute addresses
        self.user_labels = defaultdict(list)  # value -> [names]
        self.user_consts = {}                 # value -> name   (first wins)
        for n, v in (labels or {}).items():
            self.user_labels[v].append(n)
        for n, v in (consts or {}).items():
            self.user_consts.setdefault(v, n)
        self.labels = defaultdict(list)       # addr (in image) -> [names]
        self.ext_used = {}                    # name -> value, for the `equ` header
        self._analyse()

    # -- helpers ----------------------------------------------------------------------
    def in_image(self, a):
        return self.base <= a < self.end

    def _is_pad(self, a):
        o = a - self.base
        chunk = self.img[o:o + 12]
        return bool(chunk) and not any(chunk) and (len(chunk) >= 12 or o + len(chunk) == len(self.img))

    def _decode_at(self, a):
        return decode(self.img, a - self.base, self.base)

    # -- control-flow tracing ---------------------------------------------------------
    def _trace(self, starts, speculative):
        """Follow control flow from `starts`. Returns {addr: Insn}, or None if `speculative` and
        anything looks wrong (bad decode, padding, overlap, off the end of the image)."""
        found, local_cov = {}, set()
        stack = list(starts)
        while stack:
            a = stack.pop()
            while True:
                if a in found or a in self.insns:
                    break                                      # already visited
                if not self.in_image(a) or self._is_pad(a):
                    if speculative:
                        return None
                    break
                ins = self._decode_at(a)
                if ins is None:
                    if speculative:
                        return None
                    break
                o = a - self.base
                if any(self.cov[x] or (x in local_cov) for x in range(o, o + ins.size)):
                    if speculative:
                        return None
                    break                                      # overlaps something already decoded
                found[a] = ins
                local_cov.update(range(o, o + ins.size))
                nxt = a + ins.size
                if ins.flow in ("jmp", "jcc", "call"):
                    t = ins.target
                    if self.in_image(t):
                        stack.append(t)
                if ins.flow in ("seq", "jcc", "call"):
                    a = nxt                                    # fall through
                    continue
                break
        return found

    def _commit(self, found):
        for a, ins in found.items():
            self.insns[a] = ins
            o = a - self.base
            self.cov[o] = 1
            for x in range(o + 1, o + ins.size):
                self.cov[x] = 2
        for a, ins in found.items():
            if ins.flow in ("jmp", "jcc", "call") and self.in_image(ins.target):
                kind = "call" if ins.flow == "call" else "jump"
                self.refs[ins.target].add(kind)
                self.xrefs[ins.target].append((a, kind))
            for tok in ins.ops:
                if isinstance(tok, Ref) and tok.role == "ptr" and self.in_image(tok.value):
                    self.ptrs.setdefault(tok.value, []).append(a)
                elif isinstance(tok, Mem) and isinstance(tok.inner, Ref) and self.in_image(tok.inner.value):
                    self.mems.setdefault(tok.inner.value, []).append(a)

    def _analyse(self):
        starts = list(self.entries)
        if not starts:
            starts = [self.base + 2] if self.img[:2] == KERNEL_MAGIC else [self.base]
        for s in starts:
            self.refs[s].add("entry")
        found = self._trace(starts, speculative=False)
        self._commit(found)

        if not self.strict:
            while True:
                progress = False
                # 1) pointers loaded into 16-bit registers that point at clean code
                #    (repeat until no new code turns up, since each ISR can reveal more pointers)
                changed = True
                while changed:
                    changed = False
                    for v in sorted(self.ptrs):
                        if self.cov[v - self.base]:
                            continue
                        f = self._trace([v], speculative=True)
                        if f and (len(f) >= 2 or f[v].flow in ("ret", "end")):
                            self._commit(f)
                            self.refs[v].add("ptr")
                            changed = progress = True
                # 2) unreferenced regions that decode as clean code
                if self._sweep():
                    progress = True
                if not progress:
                    break

        # pointer refs that land exactly on code starts count as 'ptr' references
        for v, srcs in self.ptrs.items():
            if v in self.insns:
                self.refs[v].add("ptr")
                for s in srcs:
                    self.xrefs[v].append((s, "ptr"))
        self._make_labels()

    def _sweep(self):
        """Find regions that were never reached but decode as >= 3 clean instructions."""
        n, o, progress = len(self.img), 0, False
        while o < n:
            if self.cov[o]:
                o += 1
                continue
            a = self.base + o
            if self._is_pad(a):
                while o < n and self.img[o] == 0 and not self.cov[o]:
                    o += 1
                continue
            # linear probe
            count, p = 0, a
            while self.in_image(p) and not self._is_pad(p) and not self.cov[p - self.base]:
                ins = self._decode_at(p)
                if ins is None or any(self.cov[x] for x in range(p - self.base, p - self.base + ins.size)):
                    break
                count += 1
                p += ins.size
            if count >= 3:
                f = self._trace([a], speculative=False)
                if f:
                    self._commit(f)
                    self.refs[a].add("sweep")
                    f[a].note = "unreferenced code?"
                    progress = True
                    o += 1
                    continue
            o += 1
        return progress

    # -- labels -----------------------------------------------------------------------
    def _string_at(self, a):
        o = a - self.base
        j = o
        while j < len(self.img) and is_text(self.img[j]):
            j += 1
        run = j - o
        return run >= 4 or (run >= 3 and j < len(self.img) and self.img[j] == 0)

    def _make_labels(self):
        addrs = set()
        for a, kinds in self.refs.items():
            if a in self.insns:
                addrs.add(a)
        for table in (self.ptrs, self.mems):
            for v in table:
                if v == 0xFFFF and table is self.ptrs:
                    continue                         # almost certainly a timeout / sentinel, not an address
                if v in self.insns:
                    addrs.add(v)
                elif not self.cov[v - self.base] and v not in self.user_consts:
                    addrs.add(v)
        for v in self.user_labels:
            if self.in_image(v) and not (self.cov[v - self.base] == 2):
                addrs.add(v)

        for a in sorted(addrs):
            if a in self.user_labels:
                self.labels[a] = list(self.user_labels[a])
                continue
            k = self.refs.get(a, set())
            if a in self.insns:
                if "call" in k:
                    name = "sub_%04x" % a
                elif "ptr" in k:
                    name = "ptr_%04x" % a
                elif "jump" in k:
                    name = "loc_%04x" % a
                elif "sweep" in k:
                    name = "code_%04x" % a
                else:
                    name = "entry_%04x" % a
            else:
                name = ("str_%04x" if self._string_at(a) else "data_%04x") % a
            self.labels[a] = [name]

    def _name(self, value, role):
        """Label / symbol name for an address operand, or None."""
        if role in ("code", "ptr", "mem"):
            if value in self.labels and (value in self.insns or role != "code"):
                return self.labels[value][0]
            if value in self.user_labels:                 # external label from a symbol file
                name = self.user_labels[value][0]
                if not self.in_image(value):
                    self.ext_used[name] = value
                return name
        if role in ("ptr", "mem", "num16") and value >= 0x100 and value in self.user_consts:
            name = self.user_consts[value]
            self.ext_used[name] = value
            return name
        return None

    # -- formatting -------------------------------------------------------------------
    def _num(self, tok):
        if tok.role == "code" and not self.in_image(tok.value) and tok.value not in self.user_labels:
            return "0x%04x" % tok.value
        name = self._name(tok.value, tok.role)
        if name:
            return name
        if tok.role == "port":
            return "0x%02x" % tok.value
        if tok.role == "int":
            return "0x%02x" % tok.value
        if tok.role in ("code", "ptr", "mem", "num16"):
            return "0x%04x" % tok.value
        if tok.value < 10:
            return str(tok.value)
        return "0x%02x" % tok.value if tok.bits == 8 else "0x%04x" % tok.value

    def fmt_insn(self, ins):
        """-> (text, [comments])"""
        parts, comments = [], []
        for tok in ins.ops:
            if isinstance(tok, str):
                parts.append(tok)
            elif isinstance(tok, Mem):
                inner = tok.inner if isinstance(tok.inner, str) else self._num(tok.inner)
                parts.append("[" + inner + "]")
            else:
                parts.append(self._num(tok))
                if tok.role == "port" and tok.value in PORTS:
                    comments.append(PORTS[tok.value])
                elif tok.role == "int" and tok.value in INTS:
                    comments.append(INTS[tok.value])
                elif tok.role == "imm" and tok.bits == 8:
                    if tok.value in CHAR_NAMES and tok.value not in (0,):
                        comments.append("'%s'" % CHAR_NAMES[tok.value])
                    elif 0x20 <= tok.value <= 0x7E:
                        comments.append("'%s'" % chr(tok.value))
        # `in al, r0` style register ports have no name; nothing to add
        text = ins.mnem if not parts else "%-6s %s" % (ins.mnem, ", ".join(parts))
        if ins.note:
            comments.append(ins.note)
        return text, comments

    # -- data rendering ---------------------------------------------------------------
    @staticmethod
    def _quote(chunk):
        out = []
        for b in chunk:
            c = chr(b)
            if c == "\\":
                out.append("\\\\")
            elif c == '"':
                out.append('\\"')
            elif b == 10:
                out.append("\\n")
            elif b == 13:
                out.append("\\r")
            elif b == 9:
                out.append("\\t")
            else:
                out.append(c)
        return '"' + "".join(out) + '"'

    def _data_chunks(self, s, e):
        """Yield (addr, nbytes, text, comment) for [s, e)."""
        img, base = self.img, self.base
        i = s
        while i < e:
            o = i - base
            if o == 0 and img[:2] == KERNEL_MAGIC and e - i >= 2:
                yield i, 2, "dw 0xBEAF", "kernel marker"
                i += 2
                continue
            if o == 510 and len(img) >= 512 and img[510:512] == b"\x55\xaa" and e - i >= 2:
                yield i, 2, "dw 0xAA55", "boot signature"
                i += 2
                continue
            # zero run
            j = i
            while j < e and img[j - base] == 0:
                j += 1
            if j - i >= 4:
                yield i, j - i, "times %d db 0" % (j - i), ""
                i = j
                continue
            # text run
            j = i
            while j < e and is_text(img[j - base]):
                j += 1
            run = j - i
            if run >= 4 or (run >= 3 and j < e and img[j - base] == 0):
                end = j
                nul = j < e and img[j - base] == 0
                k = i
                while k < end:                                   # split long strings
                    m = min(end, k + 56)
                    last = m == end
                    chunk = img[k - base:m - base]
                    if last and nul:
                        yield k, len(chunk) + 1, "db " + self._quote(chunk) + ", 0", ""
                    else:
                        yield k, len(chunk), "db " + self._quote(chunk), ""
                    k = m
                i = end + (1 if nul else 0)
                continue
            # raw bytes, up to 8, stopping before a zero run / text run
            j = i
            while j < e and j - i < 8:
                if j > i:
                    z = j
                    while z < e and img[z - base] == 0:
                        z += 1
                    t = j
                    while t < e and is_text(img[t - base]):
                        t += 1
                    if z - j >= 4 or t - j >= 4:
                        break
                j += 1
            chunk = img[i - base:j - base]
            yield i, len(chunk), "db " + ", ".join("0x%02x" % b for b in chunk), ""
            i = j

    # -- listing ----------------------------------------------------------------------
    def stats(self):
        code = sum(i.size for i in self.insns.values())
        return len(self.insns), code, len(self.img) - code

    def _xref_comment(self, a):
        refs = sorted(set(self.xrefs.get(a, [])))
        if not refs:
            return None
        shown = ", ".join("%04x %s" % (f, k) for f, k in refs[:6])
        more = " (+%d more)" % (len(refs) - 6) if len(refs) > 6 else ""
        return "xrefs: " + shown + more

    def listing(self, asm=False, show_bytes=True, comments=True, lo=None, hi=None):
        out = []
        bounds = sorted(set(self.insns) | set(self.labels))
        a = self.base
        names_seen = set()

        def emit(addr, raw, text, cmts):
            if lo is not None and addr < lo:
                return
            if hi is not None and addr >= hi:
                return
            if asm:
                line = "    " + text
            else:
                hexcol = " ".join("%02x" % b for b in raw[:8]) if show_bytes else ""
                line = "%04x  %-23s  %s" % (addr, hexcol, text) if show_bytes else "%04x  %s" % (addr, text)
            if comments and cmts:
                line = "%-52s ; %s" % (line, "; ".join(cmts))
            out.append(line.rstrip())

        def in_range(addr):
            return (lo is None or addr >= lo) and (hi is None or addr < hi)

        def emit_labels(addr):
            names = self.labels.get(addr)
            if not names or not in_range(addr):
                return
            if comments:
                x = self._xref_comment(addr)
                kinds = self.refs.get(addr, set())
                if addr in self.insns and ({"call", "ptr", "sweep"} & kinds):
                    out.append("")
                if x:
                    out.append("; " + x)
            for n in names:
                out.append(n + ":")

        while a < self.end:
            emit_labels(a)
            if a in self.insns:
                ins = self.insns[a]
                text, cmts = self.fmt_insn(ins)
                emit(a, ins.raw, text, cmts)
                a += ins.size
                continue
            nxt = bounds[bisect.bisect_right(bounds, a)] if bisect.bisect_right(bounds, a) < len(bounds) else self.end
            # data may also not run into code that starts in the middle of a gap
            for (da, n, text, cmt) in self._data_chunks(a, nxt):
                emit(da, self.img[da - self.base:da - self.base + n], text, [cmt] if cmt else [])
            a = nxt

        header = []
        if asm:
            header.append("; generated by vsk8a_disasm")
            for name, val in sorted(self.ext_used.items(), key=lambda kv: kv[1]):
                header.append("%s equ 0x%04x" % (name, val))
            header.append("org 0x%04x" % self.base)
            header.append("")
        return header + out

    def linear_listing(self, show_bytes=True, asm=False):
        # no labels in linear mode: operands are printed as plain numbers
        saved = (self.labels, self.user_labels, self.user_consts)
        self.labels, self.user_labels, self.user_consts = {}, {}, {}
        try:
            return self._linear(show_bytes, asm)
        finally:
            self.labels, self.user_labels, self.user_consts = saved

    def _linear(self, show_bytes, asm):
        out, a = [], self.base
        while a < self.end:
            ins = self._decode_at(a)
            if ins is None:
                b = self.img[a - self.base]
                text, raw, size, cm = "db 0x%02x" % b, bytes([b]), 1, ""
                if is_text(b):
                    cm = "'%s'" % chr(b) if 0x20 <= b <= 0x7E else ""
            else:
                text, c = self.fmt_insn(ins)
                raw, size, cm = ins.raw, ins.size, "; ".join(c)
            if asm:
                line = "    " + text
            else:
                line = "%04x  %-23s  %s" % (a, " ".join("%02x" % x for x in raw), text) if show_bytes else "%04x  %s" % (a, text)
            if cm:
                line = "%-52s ; %s" % (line, cm)
            out.append(line.rstrip())
            a += size
        if asm:
            out.insert(0, "org 0x%04x" % self.base)
        return out


# --------------------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------------------
def build_parser():
    p = argparse.ArgumentParser(
        prog="vsk8a_disasm",
        description="Disassembler for the VSK-8A (control-flow aware, reassemblable output).",
        epilog="presets (--as): " + "; ".join("%s=0x%04X" % (k, v[0]) for k, v in PRESETS.items()))
    p.add_argument("file", help="binary to disassemble ('-' = stdin)")
    p.add_argument("--base", type=parse_int, help="load address of the first byte (default 0, or from --as)")
    p.add_argument("--as", dest="preset", choices=sorted(PRESETS), help="use a typical load address")
    p.add_argument("--entry", type=parse_int, action="append", default=[],
                   help="extra/explicit entry point (repeatable). Default: base (base+2 after a 0xBEAF marker)")
    p.add_argument("--symbols", action="append", default=[], metavar="FILE",
                   help="assembler --export-symbols file, or text lines like 'name 0xF573' (repeatable)")
    p.add_argument("--offset", type=parse_int, default=0, help="skip this many bytes of the input file")
    p.add_argument("--length", type=parse_int, help="only read this many bytes after --offset")
    p.add_argument("--asm", action="store_true", help="emit reassemblable source (no addresses / bytes)")
    p.add_argument("--linear", action="store_true", help="plain linear sweep (no control-flow analysis)")
    p.add_argument("--strict", action="store_true", help="disable pointer-guessing and unreferenced-code sweep")
    p.add_argument("--no-bytes", action="store_true", help="hide the raw byte column")
    p.add_argument("--no-comments", action="store_true", help="hide comments and xrefs")
    p.add_argument("--from", dest="lo", type=parse_int, help="only print addresses >= this")
    p.add_argument("--to", dest="hi", type=parse_int, help="only print addresses < this")
    p.add_argument("-o", "--output", help="write to a file instead of stdout")
    return p


def disassemble_bytes(data, base=0, entries=None, labels=None, consts=None, strict=False):
    """Library entry point."""
    return Disassembler(data, base=base, entries=entries, labels=labels, consts=consts, strict=strict)


def main(argv=None):
    args = build_parser().parse_args(argv)
    if args.base is None:
        args.base = PRESETS[args.preset][0] if args.preset else 0
    try:
        data = sys.stdin.buffer.read() if args.file == "-" else open(args.file, "rb").read()
    except OSError as e:
        print("vsk8a_disasm: %s: %s" % (args.file, e.strerror), file=sys.stderr)
        return 1
    data = data[args.offset:]
    if args.length is not None:
        data = data[:args.length]
    if not data:
        print("vsk8a_disasm: nothing to disassemble", file=sys.stderr)
        return 1
    if args.base + len(data) > 0x10000:
        print("vsk8a_disasm: warning: image runs past 0xFFFF at base 0x%04x" % args.base, file=sys.stderr)

    labels, consts = {}, {}
    for path in args.symbols:
        try:
            l, c = load_symbols(path)
            labels.update(l)
            consts.update(c)
        except (OSError, ValueError, struct_error) as e:
            print("vsk8a_disasm: %s: %s" % (path, getattr(e, 'strerror', None) or e), file=sys.stderr)
            return 1

    d = Disassembler(data, base=args.base, entries=args.entry, labels=labels, consts=consts, strict=args.strict)
    if args.linear:
        lines = d.linear_listing(show_bytes=not args.no_bytes, asm=args.asm)
    else:
        lines = d.listing(asm=args.asm, show_bytes=not args.no_bytes, comments=not args.no_comments,
                          lo=args.lo, hi=args.hi)
    if not args.asm:
        n, code, other = d.stats()
        name = "stdin" if args.file == "-" else os.path.basename(args.file)
        lines.insert(0, "; %s  base 0x%04x  %d bytes  |  %d instructions (%d bytes code), %d bytes data/unknown"
                     % (name, args.base, len(data), n, code, other))
        lines.insert(1, "")

    text = "\n".join(lines) + "\n"
    if args.output:
        with open(args.output, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
    else:
        try:
            sys.stdout.write(text)
        except BrokenPipeError:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
