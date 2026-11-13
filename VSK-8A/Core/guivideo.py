# A dedicated GUI window for output for people who might like that
# made by claude because i hate making gui

import ctypes
import os
import threading
import time
from ctypes import wintypes

import dearpygui.dearpygui as dpg
import numpy as np

COLS, ROWS = 80, 25

# VGA text mode: 9x16 cells -> 720x400, exactly what QEMU shows
CELL_W, CELL_H = 9, 16
FB_W, FB_H = COLS * CELL_W, ROWS * CELL_H

# Same palette as the old ANSI tables (index -> RGB). Anything else renders black.
PALETTE = {
    0: (0, 0, 0),
    1: (255, 255, 255),
    2: (255, 0, 0),
    3: (0, 255, 0),
    4: (0, 0, 255),
    5: (0, 170, 255),
}

# The old terminal version only drew bytes 32..126 and showed everything else as a space.
# Set this to True to draw the full CP437 set (smileys, box drawing, ...) like a real VGA card.
RENDER_FULL_CP437 = False


# IBM VGA 8x16 ROM font: 256 glyphs x 16 bytes (the vgafont16 table from SeaBIOS' VGA BIOS,
# which is the font QEMU's VGA shows; public domain).
_VGA_FONT_16_HEX = (
    "0000000000000000000000000000000000007e81a58181bd9981817e00000000"
    "00007effdbffffc3e7ffff7e00000000000000006cfefefefe7c381000000000"
    "0000000010387cfe7c38100000000000000000183c3ce7e7e718183c00000000"
    "000000183c7effff7e18183c00000000000000000000183c3c18000000000000"
    "ffffffffffffe7c3c3e7ffffffffffff00000000003c664242663c0000000000"
    "ffffffffffc399bdbd99c3ffffffffff00001e0e1a3278cccccccc7800000000"
    "00003c666666663c187e18180000000000003f333f3030303070f0e000000000"
    "00007f637f6363636367e7e6c00000000000001818db3ce73cdb181800000000"
    "0080c0e0f0f8fef8f0e0c080000000000002060e1e3efe3e1e0e060200000000"
    "0000183c7e1818187e3c18000000000000006666666666666600666600000000"
    "00007fdbdbdb7b1b1b1b1b1b00000000007cc660386cc6c66c380cc67c000000"
    "0000000000000000fefefefe000000000000183c7e1818187e3c187e00000000"
    "0000183c7e18181818181818000000000000181818181818187e3c1800000000"
    "0000000000180cfe0c1800000000000000000000003060fe6030000000000000"
    "000000000000c0c0c0fe00000000000000000000002466ff6624000000000000"
    "000000001038387c7cfefe000000000000000000fefe7c7c3838100000000000"
    "000000000000000000000000000000000000183c3c3c18181800181800000000"
    "006666662400000000000000000000000000006c6cfe6c6c6cfe6c6c00000000"
    "18187cc6c2c07c060686c67c1818000000000000c2c60c183060c68600000000"
    "0000386c6c3876dccccccc760000000000303030600000000000000000000000"
    "00000c18303030303030180c00000000000030180c0c0c0c0c0c183000000000"
    "0000000000663cff3c66000000000000000000000018187e1818000000000000"
    "0000000000000000001818183000000000000000000000fe0000000000000000"
    "000000000000000000001818000000000000000002060c183060c08000000000"
    "00003c66c3c3dbdbc3c3663c0000000000001838781818181818187e00000000"
    "00007cc6060c183060c0c6fe0000000000007cc606063c060606c67c00000000"
    "00000c1c3c6cccfe0c0c0c1e000000000000fec0c0c0fc060606c67c00000000"
    "00003860c0c0fcc6c6c6c67c000000000000fec606060c183030303000000000"
    "00007cc6c6c67cc6c6c6c67c0000000000007cc6c6c67e0606060c7800000000"
    "0000000018180000001818000000000000000000181800000018183000000000"
    "000000060c18306030180c060000000000000000007e00007e00000000000000"
    "0000006030180c060c1830600000000000007cc6c60c18181800181800000000"
    "0000007cc6c6dedededcc07c00000000000010386cc6c6fec6c6c6c600000000"
    "0000fc6666667c66666666fc0000000000003c66c2c0c0c0c0c2663c00000000"
    "0000f86c6666666666666cf8000000000000fe6662687868606266fe00000000"
    "0000fe6662687868606060f00000000000003c66c2c0c0dec6c6663a00000000"
    "0000c6c6c6c6fec6c6c6c6c60000000000003c18181818181818183c00000000"
    "00001e0c0c0c0c0ccccccc78000000000000e666666c78786c6666e600000000"
    "0000f06060606060606266fe000000000000c3e7ffffdbc3c3c3c3c300000000"
    "0000c6e6f6fedecec6c6c6c60000000000007cc6c6c6c6c6c6c6c67c00000000"
    "0000fc6666667c60606060f00000000000007cc6c6c6c6c6c6d6de7c0c0e0000"
    "0000fc6666667c6c666666e60000000000007cc6c660380c06c6c67c00000000"
    "0000ffdb991818181818183c000000000000c6c6c6c6c6c6c6c6c67c00000000"
    "0000c3c3c3c3c3c3c3663c18000000000000c3c3c3c3c3dbdbff666600000000"
    "0000c3c3663c18183c66c3c3000000000000c3c3c3663c181818183c00000000"
    "0000ffc3860c183060c1c3ff0000000000003c30303030303030303c00000000"
    "00000080c0e070381c0e06020000000000003c0c0c0c0c0c0c0c0c3c00000000"
    "10386cc600000000000000000000000000000000000000000000000000ff0000"
    "303018000000000000000000000000000000000000780c7ccccccc7600000000"
    "0000e06060786c666666667c0000000000000000007cc6c0c0c0c67c00000000"
    "00001c0c0c3c6ccccccccc760000000000000000007cc6fec0c0c67c00000000"
    "0000386c6460f060606060f000000000000000000076cccccccccc7c0ccc7800"
    "0000e060606c7666666666e60000000000001818003818181818183c00000000"
    "00000606000e06060606060666663c000000e06060666c78786c66e600000000"
    "00003818181818181818183c000000000000000000e6ffdbdbdbdbdb00000000"
    "0000000000dc6666666666660000000000000000007cc6c6c6c6c67c00000000"
    "0000000000dc66666666667c6060f000000000000076cccccccccc7c0c0c1e00"
    "0000000000dc7666606060f00000000000000000007cc660380cc67c00000000"
    "0000103030fc30303030361c000000000000000000cccccccccccc7600000000"
    "0000000000c3c3c3c3663c18000000000000000000c3c3c3dbdbff6600000000"
    "0000000000c3663c183c66c3000000000000000000c6c6c6c6c6c67e060cf800"
    "0000000000fecc183060c6fe0000000000000e18181870181818180e00000000"
    "000018181818001818181818000000000000701818180e181818187000000000"
    "000076dc0000000000000000000000000000000010386cc6c6c6fe0000000000"
    "00003c66c2c0c0c0c2663c0c067c00000000cc0000cccccccccccc7600000000"
    "000c1830007cc6fec0c0c67c000000000010386c00780c7ccccccc7600000000"
    "0000cc0000780c7ccccccc76000000000060301800780c7ccccccc7600000000"
    "00386c3800780c7ccccccc7600000000000000003c666060663c0c063c000000"
    "0010386c007cc6fec0c0c67c000000000000c600007cc6fec0c0c67c00000000"
    "00603018007cc6fec0c0c67c0000000000006600003818181818183c00000000"
    "00183c66003818181818183c0000000000603018003818181818183c00000000"
    "00c60010386cc6c6fec6c6c600000000386c3800386cc6c6fec6c6c600000000"
    "18306000fe66607c606066fe0000000000000000006e3b1b7ed8dc7700000000"
    "00003e6cccccfeccccccccce000000000010386c007cc6c6c6c6c67c00000000"
    "0000c600007cc6c6c6c6c67c0000000000603018007cc6c6c6c6c67c00000000"
    "003078cc00cccccccccccc76000000000060301800cccccccccccc7600000000"
    "0000c60000c6c6c6c6c6c67e060c780000c6007cc6c6c6c6c6c6c67c00000000"
    "00c600c6c6c6c6c6c6c6c67c000000000018187ec3c0c0c0c37e181800000000"
    "00386c6460f060606060e6fc000000000000c3663c18ff18ff18181800000000"
    "00fc66667c62666f666666f300000000000e1b1818187e1818181818d8700000"
    "0018306000780c7ccccccc7600000000000c1830003818181818183c00000000"
    "00183060007cc6c6c6c6c67c000000000018306000cccccccccccc7600000000"
    "000076dc00dc6666666666660000000076dc00c6e6f6fedecec6c6c600000000"
    "003c6c6c3e007e00000000000000000000386c6c38007c000000000000000000"
    "0000303000303060c0c6c67c00000000000000000000fec0c0c0c00000000000"
    "000000000000fe06060606000000000000c0c0c2c6cc183060ce9b060c1f0000"
    "00c0c0c2c6cc183066ce963e0606000000001818001818183c3c3c1800000000"
    "0000000000366cd86c360000000000000000000000d86c366cd8000000000000"
    "1144114411441144114411441144114455aa55aa55aa55aa55aa55aa55aa55aa"
    "dd77dd77dd77dd77dd77dd77dd77dd7718181818181818181818181818181818"
    "18181818181818f818181818181818181818181818f818f81818181818181818"
    "36363636363636f6363636363636363600000000000000fe3636363636363636"
    "0000000000f818f818181818181818183636363636f606f63636363636363636"
    "363636363636363636363636363636360000000000fe06f63636363636363636"
    "3636363636f606fe000000000000000036363636363636fe0000000000000000"
    "1818181818f818f8000000000000000000000000000000f81818181818181818"
    "181818181818181f000000000000000018181818181818ff0000000000000000"
    "00000000000000ff1818181818181818181818181818181f1818181818181818"
    "00000000000000ff000000000000000018181818181818ff1818181818181818"
    "18181818181f181f181818181818181836363636363636373636363636363636"
    "363636363637303f000000000000000000000000003f30373636363636363636"
    "3636363636f700ff00000000000000000000000000ff00f73636363636363636"
    "363636363637303736363636363636360000000000ff00ff0000000000000000"
    "3636363636f700f736363636363636361818181818ff00ff0000000000000000"
    "36363636363636ff00000000000000000000000000ff00ff1818181818181818"
    "00000000000000ff3636363636363636363636363636363f0000000000000000"
    "18181818181f181f000000000000000000000000001f181f1818181818181818"
    "000000000000003f363636363636363636363636363636ff3636363636363636"
    "1818181818ff18ff181818181818181818181818181818f80000000000000000"
    "000000000000001f1818181818181818ffffffffffffffffffffffffffffffff"
    "00000000000000fffffffffffffffffff0f0f0f0f0f0f0f0f0f0f0f0f0f0f0f0"
    "0f0f0f0f0f0f0f0f0f0f0f0f0f0f0f0fffffffffffffff000000000000000000"
    "000000000076dcd8d8d8dc7600000000000078ccccccd8ccc6c6c6cc00000000"
    "0000fec6c6c0c0c0c0c0c0c00000000000000000fe6c6c6c6c6c6c6c00000000"
    "000000fec66030183060c6fe0000000000000000007ed8d8d8d8d87000000000"
    "0000000066666666667c6060c00000000000000076dc18181818181800000000"
    "0000007e183c6666663c187e00000000000000386cc6c6fec6c66c3800000000"
    "0000386cc6c6c66c6c6c6cee0000000000001e30180c3e666666663c00000000"
    "00000000007edbdbdb7e00000000000000000003067edbdbf37e60c000000000"
    "00001c3060607c606060301c000000000000007cc6c6c6c6c6c6c6c600000000"
    "00000000fe0000fe0000fe00000000000000000018187e18180000ff00000000"
    "00000030180c060c1830007e000000000000000c18306030180c007e00000000"
    "00000e1b1b18181818181818181818181818181818181818d8d8d87000000000"
    "000000001818007e0018180000000000000000000076dc0076dc000000000000"
    "00386c6c38000000000000000000000000000000000000181800000000000000"
    "00000000000000001800000000000000000f0c0c0c0c0cec6c6c3c1c00000000"
    "00d86c6c6c6c6c0000000000000000000070d83060c8f8000000000000000000"
    "000000007c7c7c7c7c7c7c000000000000000000000000000000000000000000"
)


# --------------------------------------------------------------------------- #
# Glyph / colour lookup tables
# --------------------------------------------------------------------------- #

def _build_glyphs():
    raw = np.frombuffer(bytes.fromhex(_VGA_FONT_16_HEX), dtype=np.uint8).reshape(256, 16)
    bits = np.unpackbits(raw, axis=1).reshape(256, 16, 8).astype(bool)   # MSB = leftmost pixel
    # VGA 9-dot mode: the 9th column is blank, except chars 0xC0-0xDF where it repeats the 8th
    # column (so box-drawing lines connect).
    col9 = np.zeros((256, 16, 1), dtype=bool)
    col9[0xC0:0xE0] = bits[0xC0:0xE0, :, 7:8]
    return np.concatenate([bits, col9], axis=2)                           # (256, 16, 9)


GLYPHS = _build_glyphs()

PAL_LUT = np.zeros((256, 3), dtype=np.float32)
for _i, _rgb in PALETTE.items():
    PAL_LUT[_i] = np.array(_rgb, dtype=np.float32) / 255.0

CHAR_MAP = np.arange(256, dtype=np.uint8)
if not RENDER_FULL_CP437:
    CHAR_MAP[(CHAR_MAP < 32) | (CHAR_MAP > 126)] = 32


# --------------------------------------------------------------------------- #
# Win32 plumbing: forward keys from the GUI window into the console input buffer
# --------------------------------------------------------------------------- #

WM_KEYDOWN = 0x0100
WM_CHAR = 0x0102
WM_SYSKEYDOWN = 0x0104
WM_SYSKEYUP = 0x0105
WM_SYSCOMMAND = 0x0112
SC_KEYMENU = 0xF100
GWLP_WNDPROC = -4

VK_MENU = 0x12
VK_F10 = 0x79
VK_F11 = 0x7A

KEY_EVENT = 0x0001
ENHANCED_KEY = 0x0100
SHIFT_PRESSED = 0x0010
LEFT_CTRL_PRESSED = 0x0008
LEFT_ALT_PRESSED = 0x0002

# keys that don't produce a WM_CHAR but that getch() reports as 0x00/0xE0 + scan code
_SPECIAL_VKS = set(range(0x21, 0x29)) | {0x2D, 0x2E} | (set(range(0x70, 0x7C)) - {VK_F11})
# keys whose WM_CHAR is a control code but still have a virtual key of their own
_CHAR_VKS = {8: 0x08, 9: 0x09, 13: 0x0D, 27: 0x1B}


class _KEY_EVENT_RECORD(ctypes.Structure):
    _fields_ = [
        ("bKeyDown", wintypes.BOOL),
        ("wRepeatCount", wintypes.WORD),
        ("wVirtualKeyCode", wintypes.WORD),
        ("wVirtualScanCode", wintypes.WORD),
        ("UnicodeChar", wintypes.WCHAR),
        ("dwControlKeyState", wintypes.DWORD),
    ]


class _INPUT_EVENT(ctypes.Union):
    _fields_ = [("KeyEvent", _KEY_EVENT_RECORD)]


class _INPUT_RECORD(ctypes.Structure):
    _fields_ = [("EventType", wintypes.WORD), ("Event", _INPUT_EVENT)]


if os.name == "nt":
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    _WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, wintypes.HWND, wintypes.UINT,
                                  wintypes.WPARAM, wintypes.LPARAM)
    _ENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    _set_wndproc = getattr(user32, "SetWindowLongPtrW", None) or user32.SetWindowLongW
    _set_wndproc.restype = ctypes.c_void_p
    _set_wndproc.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_void_p]

    user32.CallWindowProcW.restype = ctypes.c_ssize_t
    user32.CallWindowProcW.argtypes = [ctypes.c_void_p, wintypes.HWND, wintypes.UINT,
                                       wintypes.WPARAM, wintypes.LPARAM]
    user32.EnumWindows.argtypes = [_ENUMPROC, wintypes.LPARAM]
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.VkKeyScanW.argtypes = [wintypes.WCHAR]
    user32.VkKeyScanW.restype = ctypes.c_short
    user32.MapVirtualKeyW.argtypes = [wintypes.UINT, wintypes.UINT]
    user32.MapVirtualKeyW.restype = wintypes.UINT
    user32.GetKeyState.argtypes = [ctypes.c_int]
    user32.GetKeyState.restype = ctypes.c_short

    kernel32.GetCurrentThreadId.restype = wintypes.DWORD
    kernel32.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                     ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD,
                                     ctypes.c_void_p]
    kernel32.CreateFileW.restype = ctypes.c_void_p
    kernel32.WriteConsoleInputW.argtypes = [ctypes.c_void_p, ctypes.POINTER(_INPUT_RECORD),
                                            wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
    kernel32.WriteConsoleInputW.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]


def _find_own_window():
    """The visible top-level window created by the calling thread (the Dear PyGui viewport)."""
    tid = kernel32.GetCurrentThreadId()
    found = []

    def cb(hwnd, _lparam):
        if user32.IsWindowVisible(hwnd) and user32.GetWindowThreadProcessId(hwnd, None) == tid:
            found.append(hwnd)
            return False
        return True

    user32.EnumWindows(_ENUMPROC(cb), 0)
    return found[0] if found else None


class _KeyBridge:
    """Sub-classes the viewport window and forwards typed keys into the console input buffer.

    msvcrt.kbhit()/getch() read the console's input buffer, which only fills when the console
    window itself has focus. Now that the emulator has its own window, we write the key events
    into that buffer ourselves, so the keyboard thread needs no changes.
    """

    def __init__(self, on_fullscreen):
        self.hwnd = None
        self._on_fullscreen = on_fullscreen
        self._old_proc = None
        self._proc_ref = None
        self._conin = None

    def install(self, hwnd):
        self.hwnd = hwnd
        handle = kernel32.CreateFileW("CONIN$", 0xC0000000, 3, None, 3, 0, None)
        if handle not in (None, ctypes.c_void_p(-1).value):
            self._conin = handle
        # else: no console attached, nothing to forward to

        self._proc_ref = _WNDPROC(self._wndproc)   # keep a reference or it gets collected
        self._old_proc = _set_wndproc(hwnd, GWLP_WNDPROC,
                                      ctypes.cast(self._proc_ref, ctypes.c_void_p))

    def remove(self):
        if self.hwnd and self._old_proc:
            _set_wndproc(self.hwnd, GWLP_WNDPROC, self._old_proc)
            self._old_proc = None
        if self._conin:
            kernel32.CloseHandle(self._conin)
            self._conin = None

    def has_focus(self):
        return bool(self.hwnd) and user32.GetForegroundWindow() == self.hwnd

    # -- window procedure ------------------------------------------------ #

    def _wndproc(self, hwnd, msg, wparam, lparam):
        try:
            if msg == WM_CHAR:
                self._send_char(wparam)
            elif msg in (WM_KEYDOWN, WM_SYSKEYDOWN):
                if wparam == VK_F11:
                    if msg == WM_KEYDOWN and not (lparam & (1 << 30)):
                        self._on_fullscreen()
                    return 0
                if wparam == VK_MENU:
                    return 0          # a bare Alt press must not open the window menu (step key!)
                if wparam in _SPECIAL_VKS:
                    self._send_special(wparam, lparam)
            elif msg == WM_SYSKEYUP and wparam in (VK_MENU, VK_F10):
                return 0
            elif msg == WM_SYSCOMMAND and (wparam & 0xFFF0) == SC_KEYMENU:
                return 0              # swallow "Alt opens the menu" (and Alt+Space)
        except Exception:
            pass
        return user32.CallWindowProcW(self._old_proc, hwnd, msg, wparam, lparam)

    # -- injection ------------------------------------------------------- #

    @staticmethod
    def _control_state():
        state = 0
        if user32.GetKeyState(0x10) & 0x8000:
            state |= SHIFT_PRESSED
        if user32.GetKeyState(0x11) & 0x8000:
            state |= LEFT_CTRL_PRESSED
        if user32.GetKeyState(0x12) & 0x8000:
            state |= LEFT_ALT_PRESSED
        return state

    def _write(self, vk, scan, char, state):
        if not self._conin:
            return
        records = (_INPUT_RECORD * 2)()
        for n, down in enumerate((True, False)):
            records[n].EventType = KEY_EVENT
            ev = records[n].Event.KeyEvent
            ev.bKeyDown = down
            ev.wRepeatCount = 1
            ev.wVirtualKeyCode = vk
            ev.wVirtualScanCode = scan
            ev.UnicodeChar = char
            ev.dwControlKeyState = state
        written = wintypes.DWORD(0)
        kernel32.WriteConsoleInputW(self._conin, records, 2, ctypes.byref(written))

    def _send_char(self, code):
        # 3 is Ctrl+C: injecting it would raise a real KeyboardInterrupt in the emulator
        if code == 3 or code > 0xFF:
            return
        vk = _CHAR_VKS.get(code)
        if vk is None:
            vk = user32.VkKeyScanW(chr(code)) & 0xFF
            if vk == 0xFF:
                vk = 0
        scan = user32.MapVirtualKeyW(vk, 0) if vk else 0
        self._write(vk, scan, chr(code), self._control_state())

    def _send_special(self, vk, lparam):
        scan = (lparam >> 16) & 0xFF
        state = self._control_state()
        if lparam & (1 << 24):
            state |= ENHANCED_KEY
        self._write(vk, scan, "\0", state)


# --------------------------------------------------------------------------- #
# The screen
# --------------------------------------------------------------------------- #

class Screen:
    STATUS_H = 24             # height of the optional debug strip
    DEFAULT_ZOOM = 1          # QEMU opens text mode at its native 720x400
    UI_FONT_PX = 15
    FALLBACK_MENU_H = 21

    # values of `flag`, set by the menu buttons
    FLAG_NONE = 0
    FLAG_RESET = 1
    FLAG_SHUTDOWN = 2
    FLAG_STEP = 3

    def __init__(self, ports, memory, core, on_close=None):
        self.ports = ports
        self.memory = memory
        self.core = core                     # for debugging
        self.on_close = on_close

        # Set by the Machine menu; read (and reset to 0) by your main loop. See FLAG_* above.
        self.flag = self.FLAG_NONE

        self.can_refresh = False
        self.instrs_per_second = 0           # also for debugging
        self.b80x25 = COLS * ROWS * 3        # the total correct size of the MMIO region

        self.DIE_NOW = False
        self.window_closed = False

        self.header = "Left Ctrl to exit | Left Alt to step | Right Ctrl to reset"

        self.cursor_showing = False          # used to signal if the cursor is visible on screen
        self.cursor_interval = 0.5
        self.cursor_last_toggle = time.monotonic()

        self.hwnd = None
        self._keys = None

        # framebuffer: float RGBA, uploaded to a texture whenever the picture changes
        self._rgba = np.ones((FB_H, FB_W, 4), dtype=np.float32)
        self._flat = self._rgba.reshape(-1)  # same memory, 1-D view for the texture upload
        self._tex = None
        self._last_state = None

        self._dl = None
        self._img = None
        self._strip_rect = None
        self._strip_text = None
        self._menubar = None

        self._debug_visible = False          # MIPS readout etc. is off by default
        self._fullscreen = False
        self._want_fullscreen = False
        self._title = None
        self._layout_key = None
        self._frame = 0
        self._last_status_update = 0.0
        self._counter_started = False

    # ------------------------------------------------------------------ #
    # Background helpers
    # ------------------------------------------------------------------ #

    def count_instrs_per_second(self):
        """Meant to run in a seperate thread"""
        while not (self.DIE_NOW or self.window_closed):
            start_time = time.time()
            start_instr = self.core.instructions_executed
            time.sleep(0.5)
            end_time = time.time()
            end_instr = self.core.instructions_executed

            change = end_instr - start_instr
            passed_time = end_time - start_time

            if passed_time > 0:
                self.instrs_per_second = round(change / passed_time, 2)

    def start(self):
        """Returns the (un-started) GUI thread, same contract as the old terminal version."""
        return threading.Thread(target=self.run, daemon=True)

    def has_focus(self):
        """True while the emulator window is the foreground window."""
        return bool(self._keys and self._keys.has_focus())

    # ------------------------------------------------------------------ #
    # Menu callbacks
    # ------------------------------------------------------------------ #

    def _cb_reset(self):
        self.flag = self.FLAG_RESET

    def _cb_step(self):
        self.flag = self.FLAG_STEP

    def _cb_quit(self):
        self.flag = self.FLAG_SHUTDOWN

    def _request_fullscreen(self):
        # called from inside the window procedure; do the real work from the main loop
        self._want_fullscreen = True

    def _cb_fullscreen(self):
        self._request_fullscreen()

    def _cb_zoom(self, sender, app_data, user_data):
        self._set_zoom(user_data)

    def _cb_debug(self, sender, app_data):
        self._debug_visible = bool(app_data)
        dpg.configure_item(self._strip_rect, show=self._debug_visible)
        dpg.configure_item(self._strip_text, show=self._debug_visible)
        self._last_status_update = 0.0

    # ------------------------------------------------------------------ #
    # Window metrics / layout
    # ------------------------------------------------------------------ #

    def _metrics(self):
        """(top of the drawlist, extra inset needed to clear the menu bar)."""
        dl_top = int(dpg.get_item_rect_min(self._dl)[1])
        try:
            menu_h = int(dpg.get_item_rect_size(self._menubar)[1])
        except Exception:
            menu_h = 0
        if menu_h <= 0:
            menu_h = self.FALLBACK_MENU_H
        return dl_top, max(0, menu_h - dl_top)

    def _status_h(self):
        return self.STATUS_H if self._debug_visible else 0

    def _set_zoom(self, zoom):
        """Resize the window so the display is shown at `zoom`x of 720x400."""
        if self._fullscreen:
            return
        dl_top, inset = self._metrics()
        client_w = int(FB_W * zoom)
        client_h = int(FB_H * zoom) + dl_top + inset + self._status_h()
        frame_w = dpg.get_viewport_width() - dpg.get_viewport_client_width()
        frame_h = dpg.get_viewport_height() - dpg.get_viewport_client_height()
        dpg.set_viewport_width(client_w + frame_w)
        dpg.set_viewport_height(client_h + frame_h)

    def _check_layout(self):
        dl_top, inset = self._metrics()
        key = (int(dpg.get_viewport_client_width()), int(dpg.get_viewport_client_height()),
               dl_top, inset, self._status_h())
        if key == self._layout_key:
            return
        self._layout_key = key
        cw, ch, dl_top, inset, status_h = key

        area_w = cw
        area_h = ch - dl_top - inset - status_h
        if area_w < 8 or area_h < 8:
            return

        # scale to fit, keep the 720x400 aspect ratio, letterbox on black (like QEMU)
        scale = min(area_w / FB_W, area_h / FB_H)
        w, h = round(FB_W * scale), round(FB_H * scale)
        ox = (area_w - w) // 2
        oy = inset + (area_h - h) // 2

        dpg.configure_item(self._dl, width=cw, height=ch - dl_top)
        dpg.configure_item(self._img, pmin=(ox, oy), pmax=(ox + w, oy + h))

        sy = ch - dl_top - status_h
        dpg.configure_item(self._strip_rect, pmin=(0, sy), pmax=(cw, sy + self.STATUS_H))
        dpg.configure_item(self._strip_text, pos=(10, sy + 4))

    # ------------------------------------------------------------------ #
    # GUI construction
    # ------------------------------------------------------------------ #

    def _load_ui_font(self):
        path = "C:/Windows/Fonts/segoeui.ttf"
        if os.path.exists(path):
            with dpg.font_registry():
                dpg.bind_font(dpg.add_font(path, self.UI_FONT_PX))

    def _build_ui(self):
        with dpg.texture_registry():
            self._tex = dpg.add_dynamic_texture(FB_W, FB_H, self._flat.tolist())

        # Black, edge-to-edge primary window (this theme only affects this window; the menu
        # bar below is a separate viewport menu bar and keeps normal spacing)
        with dpg.theme() as main_theme:
            with dpg.theme_component(dpg.mvAll):
                dpg.add_theme_color(dpg.mvThemeCol_WindowBg, (0, 0, 0, 255))
                dpg.add_theme_style(dpg.mvStyleVar_WindowPadding, 0, 0)
                dpg.add_theme_style(dpg.mvStyleVar_WindowBorderSize, 0)

        with dpg.viewport_menu_bar() as self._menubar:
            with dpg.menu(label="Machine"):
                dpg.add_menu_item(label="Reset", shortcut="Right Ctrl", callback=self._cb_reset)
                dpg.add_menu_item(label="Step", shortcut="Left Alt", callback=self._cb_step)
                dpg.add_separator()
                dpg.add_menu_item(label="Quit", shortcut="Left Ctrl", callback=self._cb_quit)
            with dpg.menu(label="View"):
                dpg.add_menu_item(label="Fullscreen", shortcut="F11",
                                  callback=self._cb_fullscreen)
                dpg.add_separator()
                for z in (1, 2, 3):
                    dpg.add_menu_item(label=f"Zoom {z}x", callback=self._cb_zoom, user_data=z)
                dpg.add_separator()
                dpg.add_menu_item(label="Show debug info", check=True, default_value=False,
                                  callback=self._cb_debug)

        with dpg.window(tag="main", no_title_bar=True, no_move=True, no_resize=True,
                        no_scrollbar=True, no_scroll_with_mouse=True):
            self._dl = dpg.add_drawlist(FB_W, FB_H)
            self._img = dpg.draw_image(self._tex, (0, 0), (FB_W, FB_H), parent=self._dl)
            self._strip_rect = dpg.draw_rectangle((0, 0), (1, 1), color=(0, 0, 0, 0),
                                                  fill=(24, 24, 28, 255), parent=self._dl,
                                                  show=False)
            self._strip_text = dpg.draw_text((0, 0), "", color=(170, 174, 186, 255),
                                             size=self.UI_FONT_PX, parent=self._dl,
                                             show=False)
        dpg.bind_item_theme("main", main_theme)

    # ------------------------------------------------------------------ #
    # Rendering
    # ------------------------------------------------------------------ #

    def _compose(self, chars, bg_idx, fg_idx):
        """chars/bg_idx/fg_idx are (25, 80) uint8 arrays; fills the RGB part of the framebuffer."""
        mask = GLYPHS[chars]                                          # (25, 80, 16, 9) bool
        fg = PAL_LUT[fg_idx][:, :, None, None, :]
        bg = PAL_LUT[bg_idx][:, :, None, None, :]
        out = np.where(mask[..., None], fg, bg)                       # (25, 80, 16, 9, 3)
        self._rgba[:, :, :3] = out.transpose(0, 2, 1, 3, 4).reshape(FB_H, FB_W, 3)
        dpg.set_value(self._tex, self._flat)

    def _show_no_signal(self):
        if self._last_state == "blank":
            return
        self._last_state = "blank"
        # no signal: plain black screen
        self._rgba[:, :, :3] = 0.0
        dpg.set_value(self._tex, self._flat)

    def _update_screen(self):
        """Redraws if anything changed. Returns True if the MMIO region is valid."""
        mmio_start = self.ports.read_port(0x00) | (self.ports.read_port(0x01) << 8)
        mmio_end = self.ports.read_port(0x02) | (self.ports.read_port(0x03) << 8)

        # Blinky boi timing
        now = time.monotonic()
        if now - self.cursor_last_toggle >= self.cursor_interval:
            self.cursor_showing = not self.cursor_showing
            self.cursor_last_toggle = now

        # Only render from MMIO if the MMIO regions are correct
        if not (mmio_end >= mmio_start and ((mmio_end - mmio_start) + 1) == self.b80x25):
            self._show_no_signal()
            return False

        vram = bytes(self.memory.memory[mmio_start:mmio_end + 1])

        x_cursor = self.ports.read_port(0x10)
        y_cursor = self.ports.read_port(0x11)
        curs_chr = self.ports.read_port(0x12)
        curs_bg = self.ports.read_port(0x13)

        cursor = None
        if curs_chr and self.cursor_showing and x_cursor < COLS and y_cursor < ROWS:
            cursor = (x_cursor, y_cursor, curs_chr, curs_bg)

        state = (vram, cursor)
        if state == self._last_state:
            return True
        self._last_state = state

        cells = np.frombuffer(vram, dtype=np.uint8).reshape(ROWS, COLS, 3)
        bg = cells[:, :, 0].copy()
        fg = cells[:, :, 1].copy()
        chars = CHAR_MAP[cells[:, :, 2]]

        if cursor:
            cx, cy, c, cbg = cursor
            chars[cy, cx] = CHAR_MAP[c & 0xFF]
            bg[cy, cx] = cbg if cbg in PALETTE else 0
            fg[cy, cx] = 1                  # cursor fg is white by default

        self._compose(chars, bg, fg)
        return True

    # ------------------------------------------------------------------ #
    # Title / debug line
    # ------------------------------------------------------------------ #

    def _update_status(self):
        now = time.monotonic()
        if now - self._last_status_update < 0.1:
            return
        self._last_status_update = now

        core = self.core
        halted = bool(core.halted)
        stepping = bool(core.STEP)

        # QEMU puts machine state in the window title
        title = "VSK-8A"
        if halted:
            title += " [Halted]"
        elif stepping:
            title += " [Step]"
        if title != self._title:
            self._title = title
            dpg.set_viewport_title(title)

        if self._debug_visible:
            dpg.configure_item(
                self._strip_text,
                text=(f"{self.instrs_per_second / 1_000_000:.2f} MIPS    "
                      f"PC {core.PC:04x}    SP {core.SP:04x}    "
                      f"zero {int(bool(core.ALU.zero))}  carry {int(bool(core.ALU.carry))}  if {int(bool(core.IF))}    "
                      f"{'halted' if halted else 'running'}    "
                      f"step {'on' if stepping else 'off'}"))

    # ------------------------------------------------------------------ #
    # Main loop
    # ------------------------------------------------------------------ #

    def run(self):
        """Creates the window and blocks until it is closed (or DIE_NOW is set)."""
        if not self._counter_started:
            self._counter_started = True
            threading.Thread(target=self.count_instrs_per_second, daemon=True).start()

        dpg.create_context()
        try:
            self._load_ui_font()
            self._build_ui()

            dpg.create_viewport(title="VSK-8A", width=FB_W + 16, height=FB_H + 70,
                                min_width=320, min_height=200, clear_color=(0, 0, 0, 255))
            dpg.setup_dearpygui()
            dpg.show_viewport()
            dpg.set_primary_window("main", True)

            if os.name == "nt":
                self.hwnd = _find_own_window()
                if self.hwnd:
                    self._keys = _KeyBridge(self._request_fullscreen)
                    self._keys.install(self.hwnd)

            while dpg.is_dearpygui_running() and not self.DIE_NOW:
                self._frame += 1
                if self._frame == 3:
                    # the menu bar has been measured by now: size the window exactly
                    self._set_zoom(self.DEFAULT_ZOOM)

                if self._want_fullscreen:
                    self._want_fullscreen = False
                    self._fullscreen = not self._fullscreen
                    dpg.toggle_viewport_fullscreen()

                self._check_layout()

                if self.can_refresh:
                    self._update_screen()
                else:
                    self._show_no_signal()

                self._update_status()
                dpg.render_dearpygui_frame()
        finally:
            self.window_closed = True
            if self._keys:
                self._keys.remove()
            dpg.destroy_context()
            if self.on_close:
                self.on_close()