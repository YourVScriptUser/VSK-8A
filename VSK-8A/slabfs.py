#!/usr/bin/env python3
"""
slabfs - inspect and extract files from VSK-8A SlabFS disk images (read-only)

    python slabfs.py info    disk.img
    python slabfs.py ls      disk.img
    python slabfs.py map     disk.img
    python slabfs.py check   disk.img            (exit code 1 if it finds errors)
    python slabfs.py cat     disk.img shell.bin  > shell.bin
    python slabfs.py extract disk.img --all -d out/
    python slabfs.py hexdump disk.img shell.bin
    python slabfs.py hexdump disk.img --sector 0
    python slabfs.py dis     disk.img shell.bin --base 0x1900

On-disk layout (what kernel.x8 reads)
    sector 0        boot sector (loaded to 0x100 by the BIOS, signature 0x55 0xAA at bytes 510-511)
    sectors 1-8     metadata: 4096 bytes of 29-byte file descriptors, ended by a descriptor
                    whose first byte is 0
    sectors 9..     file data, 512-byte sectors, each file stored contiguously

    descriptor (29 bytes)
        0-24   name, NUL terminated (max 24 characters)
        25     unused (0)
        26-27  start sector, little endian
        28     length in sectors MINUS ONE   (0 = 1 sector ... 255 = 256 sectors)

SlabFS does not store exact byte sizes, only whole sectors. `--trim` strips trailing zero bytes,
which is usually what you want for text but can eat the end of a binary that really ends in 0x00.

Pure standard library, Python 3.8+. Also importable:  fs = SlabFS.open("disk.img"); fs.files
"""

import argparse
import json
import os
import sys

SECTOR = 512
DEFAULT_DSIZE = 29
DEFAULT_META_START = 1
DEFAULT_META_SECTORS = 8
BOOT_SIG = b"\x55\xaa"
KERNEL_MAGIC = b"\xaf\xbe"      # dw 0xBEAF at the start of the kernel image


# --------------------------------------------------------------------------------------
# Model
# --------------------------------------------------------------------------------------
class Entry:
    def __init__(self, index, name, start, sectors, raw):
        self.index = index          # position in the metadata table
        self.name = name            # str (latin-1 decoded, may contain odd characters)
        self.start = start          # first sector
        self.sectors = sectors      # number of sectors (descriptor byte + 1)
        self.raw = raw              # the descriptor bytes
        self.problems = []          # list of (severity, text)

    @property
    def end(self):
        """Last sector (inclusive)."""
        return self.start + self.sectors - 1

    def problem(self, severity, text):
        self.problems.append((severity, text))


class SlabFS:
    def __init__(self, data, dsize=DEFAULT_DSIZE, meta_start=DEFAULT_META_START,
                 meta_sectors=DEFAULT_META_SECTORS, path=None):
        self.data = data
        self.path = path
        self.dsize = dsize
        self.meta_start = meta_start
        self.meta_sectors = meta_sectors
        self.total_sectors = len(data) // SECTOR
        self.issues = []                    # disk-level (severity, text)
        self.files = []                     # [Entry]
        self._parse()

    @classmethod
    def open(cls, path, **kw):
        with open(path, "rb") as f:
            return cls(f.read(), path=path, **kw)

    # -- raw access -------------------------------------------------------------------
    def sector(self, n):
        """Bytes of sector n (shorter or empty if it is past the end of the image)."""
        return self.data[n * SECTOR:(n + 1) * SECTOR]

    def read(self, entry, trim=False):
        out = self.data[entry.start * SECTOR:(entry.end + 1) * SECTOR]
        return out.rstrip(b"\x00") if trim else out

    def find(self, name):
        """First entry with exactly this name (the kernel's strcmp also finds the first match)."""
        for e in self.files:
            if e.name == name:
                return e
        return None

    # -- parsing ----------------------------------------------------------------------
    def _parse(self):
        d = self.dsize
        if d < 5:
            raise ValueError("descriptor size must be at least 5")
        meta_end = self.meta_start + self.meta_sectors          # first data sector
        blk = self.data[self.meta_start * SECTOR:meta_end * SECTOR]

        if len(self.data) % SECTOR:
            self.issues.append(("error", "image size %d is not a multiple of 512: the emulator's Disk "
                                "reports an error (status 2) and the disk is unusable" % len(self.data)))
        if len(blk) < self.meta_sectors * SECTOR:
            self.issues.append(("error", "image is too small to hold the %d metadata sectors" % self.meta_sectors))
        if self.total_sectors > 0xFFFF:
            self.issues.append(("warn", "%d sectors do not fit the 16-bit sector ports (0x08/0x09, 0x0B/0x0C)"
                                % self.total_sectors))
        if self.sector(0)[510:512] != BOOT_SIG:
            self.issues.append(("warn", "boot sector has no 0x55 0xAA signature: the BIOS will not boot this disk"))

        name_len = d - 4
        terminated = False
        for i in range(len(blk) // d):
            raw = blk[i * d:(i + 1) * d]
            if raw[0] == 0:
                terminated = True
                break
            field = raw[:name_len]
            nul = field.find(b"\x00")
            e_name = field[:nul if nul >= 0 else name_len].decode("latin-1")
            start = raw[d - 3] | (raw[d - 2] << 8)
            e = Entry(i, e_name, start, raw[d - 1] + 1, raw)
            if nul < 0:
                e.problem("error", "name has no NUL terminator (the kernel's strcmp would run on)")
            if raw[d - 4] != 0:
                e.problem("warn", "unused byte %d is 0x%02x, expected 0" % (d - 4, raw[d - 4]))
            if any(not (0x20 <= ord(c) <= 0x7E) for c in e_name):
                e.problem("warn", "name contains non-printable characters")
            self.files.append(e)
        if not terminated and self.files:
            self.issues.append(("info", "metadata table is completely full (%d entries, no terminator)"
                                % len(self.files)))

        # per-entry placement checks
        seen = {}
        for e in self.files:
            if e.start < meta_end:
                e.problem("error", "starts at sector %d, inside the boot/metadata area (sectors 0-%d)"
                          % (e.start, meta_end - 1))
            if e.end >= self.total_sectors:
                e.problem("error", "runs to sector %d but the disk only has %d sectors"
                          % (e.end, self.total_sectors))
            if e.name in seen:
                e.problem("warn", "same name as entry #%d, so this one can never be loaded by name"
                          % seen[e.name].index)
            else:
                seen[e.name] = e
        for i, a in enumerate(self.files):
            for b in self.files[i + 1:]:
                if a.start <= b.end and b.start <= a.end:
                    a.problem("warn", "shares sectors with #%d '%s'" % (b.index, b.name))
                    b.problem("warn", "shares sectors with #%d '%s'" % (a.index, a.name))

    # -- analysis ---------------------------------------------------------------------
    def classify(self):
        """One character per sector (see `map`)."""
        n = self.total_sectors
        cls = ["."] * n
        meta_end = self.meta_start + self.meta_sectors
        for s in range(n):
            if self.sector(s).strip(b"\x00"):
                cls[s] = "?"                                    # data, but nobody claims it
        letters = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
        claimed = {}
        for e in self.files:
            ch = letters[e.index % len(letters)]
            for s in range(max(e.start, 0), min(e.end, n - 1) + 1):
                if s in claimed or s < meta_end:
                    cls[s] = "!"
                else:
                    cls[s] = ch
                claimed[s] = e
        for s in range(n):
            if s == 0:
                cls[s] = "B"
            elif s < meta_end:
                cls[s] = "M"
            elif cls[s] == "?" and self.sector(s)[:2] == KERNEL_MAGIC:
                cls[s] = "K"
                t = s + 1                                       # the rest of the kernel image
                while t < n and cls[t] == "?" and self.sector(t)[:2] != KERNEL_MAGIC:
                    cls[t] = "k"
                    t += 1
        return cls

    def kernel_candidates(self):
        meta_end = self.meta_start + self.meta_sectors
        return [s for s in range(meta_end, self.total_sectors)
                if self.sector(s)[:2] == KERNEL_MAGIC and not any(e.start <= s <= e.end for e in self.files)]

    def free_runs(self):
        """[(start, length)] of all-zero sectors after the metadata that no file claims."""
        cls, runs, cur = self.classify(), [], None
        for s in range(self.meta_start + self.meta_sectors, len(cls)):
            if cls[s] == ".":
                cur = (cur[0], cur[1] + 1) if cur else (s, 1)
            elif cur:
                runs.append(cur)
                cur = None
        if cur:
            runs.append(cur)
        return runs

    def all_issues(self):
        out = [("disk", sev, txt) for sev, txt in self.issues]
        for e in self.files:
            for sev, txt in e.problems:
                out.append(("#%d '%s'" % (e.index, e.name), sev, txt))
        return out


# --------------------------------------------------------------------------------------
# Output helpers
# --------------------------------------------------------------------------------------
def _enable_colour():
    if os.environ.get("NO_COLOR") or not sys.stdout.isatty():
        return False
    if os.name == "nt":
        os.system("")          # turns on ANSI escape handling in recent Windows consoles
    return True


COLOUR = False
CODES = {"error": "31", "warn": "33", "info": "36", "dim": "2", "ok": "32", "bold": "1"}


def paint(text, kind):
    return "\033[%sm%s\033[0m" % (CODES[kind], text) if COLOUR and kind in CODES else text


def hexdump(data, start=0):
    lines = []
    for i in range(0, len(data), 16):
        row = data[i:i + 16]
        hx = " ".join("%02x" % b for b in row[:8])
        if len(row) > 8:
            hx += "  " + " ".join("%02x" % b for b in row[8:])
        asc = "".join(chr(b) if 0x20 <= b <= 0x7E else "." for b in row)
        lines.append("%06x  %-48s |%s|" % (start + i, hx, asc))
    return lines


def human(n):
    return "%d B" % n if n < 1024 else ("%.1f KiB" % (n / 1024) if n < 1048576 else "%.1f MiB" % (n / 1048576))


def parse_int(text):
    t = text.strip().lower()
    if t.startswith("$"):
        return int(t[1:], 16)
    if t.endswith("h") and not t.startswith("0x"):
        return int(t[:-1], 16)
    return int(t, 0)


def severity_rank(s):
    return {"error": 0, "warn": 1, "info": 2}.get(s, 3)


# --------------------------------------------------------------------------------------
# Commands
# --------------------------------------------------------------------------------------
def load(args):
    try:
        return SlabFS.open(args.image, dsize=args.dsize, meta_start=args.meta_start,
                           meta_sectors=args.meta_sectors)
    except OSError as e:
        sys.exit("slabfs: %s: %s" % (args.image, e.strerror))
    except ValueError as e:
        sys.exit("slabfs: %s" % e)


def need_entry(fs, name):
    e = fs.find(name)
    if e is None:
        near = [x.name for x in fs.files if x.name.lower() == name.lower()]
        hint = "  (did you mean '%s'? names are case-sensitive)" % near[0] if near else ""
        sys.exit("slabfs: no file named '%s' on this disk%s" % (name, hint))
    return e


def print_issues(fs, prefix="  "):
    issues = sorted(fs.all_issues(), key=lambda t: severity_rank(t[1]))
    for who, sev, txt in issues:
        print("%s%s %s: %s" % (prefix, paint("%-5s" % sev, sev), who, txt))
    return issues


def cmd_info(args):
    fs = load(args)
    name = os.path.basename(args.image)
    print(paint(name, "bold"))
    print("  size            %s (%d bytes, %d sectors)" % (human(len(fs.data)), len(fs.data), fs.total_sectors))
    sig = fs.sector(0)[510:512] == BOOT_SIG
    print("  boot sector     %s" % (paint("present (0x55 0xAA)", "ok") if sig else paint("no 0x55 0xAA signature", "warn")))
    print("  metadata        sectors %d-%d, %d-byte descriptors, max %d files"
          % (fs.meta_start, fs.meta_start + fs.meta_sectors - 1, fs.dsize,
             fs.meta_sectors * SECTOR // fs.dsize))
    used = sum(e.sectors for e in fs.files)
    print("  files           %d (%d sectors, %s)" % (len(fs.files), used, human(used * SECTOR)))
    free = fs.free_runs()
    free_total = sum(n for _, n in free)
    if free:
        big = max(free, key=lambda r: r[1])
        print("  free            %d sectors (%s), largest run %d at sector %d"
              % (free_total, human(free_total * SECTOR), big[1], big[0]))
    kc = fs.kernel_candidates()
    if kc:
        print("  kernel image    0xBEAF marker at sector %s" % ", ".join(map(str, kc[:6])))
    if fs.files:
        print()
        print_table(fs)
    problems = fs.all_issues()
    print()
    if problems:
        print(paint("%d issue(s):" % len(problems), "warn"))
        print_issues(fs)
    else:
        print(paint("no problems found", "ok"))


def print_table(fs):
    rows = [("#", "name", "start", "sectors", "range", "size", "")]
    for e in fs.files:
        trimmed = len(fs.read(e, trim=True))
        flag = "!" if any(s == "error" for s, _ in e.problems) else ("?" if e.problems else "")
        rows.append((str(e.index), e.name, str(e.start), str(e.sectors),
                     "%d-%d" % (e.start, e.end), "~%d B" % trimmed, flag))
    widths = [max(len(r[c]) for r in rows) for c in range(7)]
    for n, r in enumerate(rows):
        line = "  ".join(r[c].ljust(widths[c]) if c in (1, 4) else r[c].rjust(widths[c]) for c in range(6))
        if n == 0:
            print(paint(line, "dim"))
        else:
            flag = r[6]
            print(line + ("  " + paint(flag, "error" if flag == "!" else "warn") if flag else ""))
    print(paint("  size = bytes up to the last non-zero byte (SlabFS only stores whole sectors)", "dim"))


def cmd_ls(args):
    fs = load(args)
    if args.json:
        print(json.dumps([{"index": e.index, "name": e.name, "start": e.start, "sectors": e.sectors,
                           "end": e.end, "trimmed_size": len(fs.read(e, trim=True)),
                           "problems": [t for _, t in e.problems]} for e in fs.files], indent=2))
        return
    if not fs.files:
        print("(no files)")
        return
    print_table(fs)


def cmd_map(args):
    fs = load(args)
    cls = fs.classify()
    per_row = args.width
    for i in range(0, len(cls), per_row):
        row = cls[i:i + per_row]
        coloured = "".join(paint(c, {"!": "error", "?": "warn", ".": "dim", "B": "info",
                                     "M": "info", "K": "ok", "k": "ok"}.get(c, "bold")) for c in row)
        print("%5d  %s" % (i, coloured))
    print()
    print("B boot   M metadata   K kernel start (0xBEAF)  k kernel body   . empty   ? data nobody claims   ! overlap/bad")
    for e in fs.files:
        letters = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
        print("%s %s (sectors %d-%d)" % (letters[e.index % len(letters)], e.name, e.start, e.end))


def cmd_check(args):
    fs = load(args)
    problems = fs.all_issues()
    if not problems:
        print(paint("%s: OK (%d files)" % (os.path.basename(args.image), len(fs.files)), "ok"))
        return 0
    print_issues(fs, prefix="")
    return 1 if any(sev == "error" for _, sev, _ in problems) else 0


def cmd_cat(args):
    fs = load(args)
    e = need_entry(fs, args.name)
    data = fs.read(e, trim=args.trim)
    if len(data) < e.sectors * SECTOR and not args.trim:
        print("slabfs: warning: file runs past the end of the image (got %d of %d bytes)"
              % (len(data), e.sectors * SECTOR), file=sys.stderr)
    sys.stdout.buffer.write(data)


def safe_filename(name):
    base = os.path.basename(name.replace("\\", "/"))
    return None if base in ("", ".", "..") else base


def cmd_extract(args):
    fs = load(args)
    if args.all:
        targets = list(fs.files)
    elif args.names:
        targets = [need_entry(fs, n) for n in args.names]
    else:
        sys.exit("slabfs: give file names to extract, or --all")
    if args.output and len(targets) != 1:
        sys.exit("slabfs: -o takes exactly one file; use -d DIR for several")
    if args.dir:
        os.makedirs(args.dir, exist_ok=True)
    status = 0
    for e in targets:
        fname = safe_filename(e.name)
        if args.output:
            dest = args.output
        elif fname is None:
            print("slabfs: skipping entry #%d: unusable file name %r" % (e.index, e.name), file=sys.stderr)
            status = 1
            continue
        else:
            dest = os.path.join(args.dir or ".", fname)
        if os.path.exists(dest) and not args.force:
            print("slabfs: %s exists (use --force to overwrite)" % dest, file=sys.stderr)
            status = 1
            continue
        data = fs.read(e, trim=args.trim)
        with open(dest, "wb") as f:
            f.write(data)
        print("%s -> %s (%d bytes)" % (e.name, dest, len(data)))
    return status


def cmd_hexdump(args):
    fs = load(args)
    if args.sector is not None:
        if not 0 <= args.sector < fs.total_sectors:
            sys.exit("slabfs: sector %d is outside the disk (0-%d)" % (args.sector, fs.total_sectors - 1))
        data = fs.data[args.sector * SECTOR:(args.sector + args.count) * SECTOR]
        base = args.sector * SECTOR
        print(paint("; sectors %d-%d (disk offset 0x%x)" % (args.sector, args.sector + args.count - 1, base), "dim"))
    elif args.name:
        e = need_entry(fs, args.name)
        data, base = fs.read(e, trim=args.trim), 0
        print(paint("; %s: sectors %d-%d" % (e.name, e.start, e.end), "dim"))
    else:
        sys.exit("slabfs: give a file name or --sector N")
    lines = hexdump(data, base)
    # squeeze long runs of identical lines like hexdump -C does
    prev, squeezing = None, False
    for ln in lines:
        body = ln[8:]
        if body == prev:
            if not squeezing:
                print("*")
                squeezing = True
            continue
        squeezing, prev = False, body
        print(ln)


def cmd_dis(args):
    here = os.path.dirname(os.path.abspath(__file__))
    if here not in sys.path:
        sys.path.insert(0, here)
    try:
        import vsk8a_disasm
    except ImportError:
        sys.exit("slabfs: dis needs vsk8a_disasm.py next to slabfs.py")
    fs = load(args)
    e = need_entry(fs, args.name)
    full = fs.read(e)
    data = full.rstrip(b"\x00")
    if not data:
        sys.exit("slabfs: '%s' is empty" % e.name)
    if len(data) < len(full):
        data += b"\x00"            # keep one terminator so a final string still ends in 0
    labels, consts = {}, {}
    for path in args.symbols:
        try:
            l, c = vsk8a_disasm.load_symbols(path)
        except (OSError, ValueError) as ex:
            sys.exit("slabfs: %s: %s" % (path, getattr(ex, "strerror", None) or ex))
        labels.update(l)
        consts.update(c)
    d = vsk8a_disasm.Disassembler(data, base=args.base, entries=args.entry, labels=labels,
                                  consts=consts, strict=args.strict)
    lines = d.listing(asm=args.asm, show_bytes=not args.no_bytes)
    if not args.asm:
        n, code, other = d.stats()
        lines.insert(0, "; %s from %s  base 0x%04x  %d bytes  |  %d instructions, %d bytes data"
                     % (e.name, os.path.basename(args.image), args.base, len(data), n, other))
        lines.insert(1, "")
    print("\n".join(lines))


# --------------------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------------------
def build_parser():
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("image", help="disk image (the file you pass to vsk8a.py --disk)")
    common.add_argument("--dsize", type=int, default=DEFAULT_DSIZE, help="descriptor size (default 29)")
    common.add_argument("--meta-start", type=int, default=DEFAULT_META_START, help="first metadata sector (default 1)")
    common.add_argument("--meta-sectors", type=int, default=DEFAULT_META_SECTORS, help="metadata sectors (default 8)")

    p = argparse.ArgumentParser(prog="slabfs", description="Inspect and extract files from SlabFS disk images.")
    sub = p.add_subparsers(dest="cmd", required=True, metavar="command")

    sub.add_parser("info", parents=[common], help="overview: layout, files, free space, problems").set_defaults(fn=cmd_info)

    s = sub.add_parser("ls", parents=[common], help="list files")
    s.add_argument("--json", action="store_true", help="machine-readable output")
    s.set_defaults(fn=cmd_ls)

    s = sub.add_parser("map", parents=[common], help="sector usage map")
    s.add_argument("--width", type=int, default=64, help="sectors per row (default 64)")
    s.set_defaults(fn=cmd_map)

    sub.add_parser("check", parents=[common], help="report problems; exit code 1 on errors").set_defaults(fn=cmd_check)

    s = sub.add_parser("cat", parents=[common], help="write a file's sectors to stdout")
    s.add_argument("name")
    s.add_argument("--trim", action="store_true", help="strip trailing zero bytes")
    s.set_defaults(fn=cmd_cat)

    s = sub.add_parser("extract", parents=[common], help="extract files to the host")
    s.add_argument("names", nargs="*")
    s.add_argument("--all", action="store_true", help="extract every file")
    s.add_argument("-d", "--dir", help="destination directory (default: current)")
    s.add_argument("-o", "--output", help="destination file (single file only)")
    s.add_argument("--trim", action="store_true", help="strip trailing zero bytes")
    s.add_argument("--force", action="store_true", help="overwrite existing files")
    s.set_defaults(fn=cmd_extract)

    s = sub.add_parser("hexdump", parents=[common], help="hex dump a file or raw sectors")
    s.add_argument("name", nargs="?")
    s.add_argument("--sector", type=int, help="dump raw sectors instead of a file")
    s.add_argument("--count", type=int, default=1, help="number of sectors with --sector (default 1)")
    s.add_argument("--trim", action="store_true", help="strip trailing zero bytes")
    s.set_defaults(fn=cmd_hexdump)

    s = sub.add_parser("dis", parents=[common], help="disassemble a file (needs vsk8a_disasm.py)")
    s.add_argument("name")
    s.add_argument("--base", type=parse_int, default=0x1900, help="load address (default 0x1900, the shell's)")
    s.add_argument("--entry", type=parse_int, action="append", default=[])
    s.add_argument("--symbols", action="append", default=[], metavar="FILE")
    s.add_argument("--asm", action="store_true")
    s.add_argument("--strict", action="store_true")
    s.add_argument("--no-bytes", action="store_true")
    s.set_defaults(fn=cmd_dis)
    return p


def main(argv=None):
    global COLOUR
    args = build_parser().parse_args(argv)
    COLOUR = _enable_colour()
    try:
        return args.fn(args) or 0
    except BrokenPipeError:
        return 0


if __name__ == "__main__":
    sys.exit(main())
