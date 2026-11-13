import core 
import ctypes 
import msvcrt

# I HATE KEYBOARDS

# Sweep from left for every keyboard row
scancodes = {
    # Number row
    "`": 1,
    "1": 2,
    "2": 3,
    "3": 4,
    "4": 5,
    "5": 6,
    "6": 7,
    "7": 8,
    "8": 9,
    "9": 10,
    "0": 11,
    "-": 12,
    "=": 13,
    "\b": 14,

    # QWERTY row
    "\t": 15,
    "q": 16,
    "w": 17,
    "e": 18,
    "r": 19,
    "t": 20,
    "y": 21,
    "u": 22,
    "i": 23,
    "o": 24,
    "p": 25,
    "[": 26,
    "]": 27,
    "\\": 28,

    # Home row
    "a": 29,
    "s": 30,
    "d": 31,
    "f": 32,
    "g": 33,
    "h": 34,
    "j": 35,
    "k": 36,
    "l": 37,
    ";": 38,
    "'": 39,
    "\r": 40,

    # Bottom row
    "z": 41,
    "x": 42,
    "c": 43,
    "v": 44,
    "b": 45,
    "n": 46,
    "m": 47,
    ",": 48,
    ".": 49,
    "/": 50,

    # Spacebar
    " ": 51,
    
    # Caps lock
    "CAPS_LOCK": 52,
    
    # Modifiers
    "MOD_SHIFT": 100,
}

SHIFTED_KEYS = {
    "!": "1",
    "@": "2",
    "#": "3",
    "$": "4",
    "%": "5",
    "^": "6",
    "&": "7",
    "*": "8",
    "(": "9",
    ")": "0",
    "_": "-",
    "+": "=",
    "~": "`",
    "{": "[",
    "}": "]",
    "|": "\\",
    ":": ";",
    '"': "'",
    "<": ",",
    ">": ".",
    "?": "/",
}

# Put this in code or whatever:
"""
` = 1
1 = 2
2 = 3
3 = 4
4 = 5
5 = 6
6 = 7
7 = 8
8 = 9
9 = 10
0 = 11
- = 12
= = 13
Backspace (\b) = 14
Tab = 15
q = 16
w = 17
e = 18
r = 19
t = 20
y = 21
u = 22
i = 23
o = 24
p = 25
[ = 26
] = 27
\\ = 28
a = 29
s = 30
d = 31
f = 32
g = 33
h = 34
j = 35
k = 36
l = 37
; = 38
' = 39
Enter = 40
z = 41
x = 42
c = 43
v = 44
b = 45
n = 46
m = 47
, = 48
. = 49
/ = 50
Space = 51
Caps lock = 52

Mods:
  Shift = 100
  
Ports:
 0xd = Keyboard IRQ
 0xe = Latest key
 0xf = Modifier 
"""


VK_SHIFT   = 0x10
VK_CAPITAL = 0x14

GetAsyncKeyState = ctypes.windll.user32.GetAsyncKeyState

class Keyboard:
    def __init__(self, computer: core.vsk8a):
        self.computer = computer
        self.caps_pressed = False
        
    def kb_interrupt(self, key):
        # Interrupt only if IRQ port is not 0
        if self.computer.PMIO.read_port(0xd):
            self.computer.PMIO.write_port(port=0xe, value=key)
            self.computer.pending_irq = self.computer.PMIO.read_port(0xd)
        
    def set_mod_port(self, mod_key):
        self.computer.PMIO.write_port(port=0xf, value=mod_key)

    def check_caps(self):
        pressed = bool(GetAsyncKeyState(VK_CAPITAL) & 0x8000)
    
        if pressed and not self.caps_pressed:
            self.kb_interrupt(scancodes["CAPS_LOCK"])

        self.caps_pressed = pressed
            
    def check_mods(self):
        self.check_caps()
    
        if (GetAsyncKeyState(VK_SHIFT) & 0x8000):
            self.set_mod_port(scancodes["MOD_SHIFT"])
            
        else:
            self.set_mod_port(0) # This is fine as we currently only have 1 modifier key AND ITS STAYING THAT WAY
        
    def tick(self):
        # SPEED FIX: dont do shit by default if IRQ is 0
        # Since the keyboard is a fucking hunk of slow make it so it returns immediately if the irq port is null
        # This was already implemented (setting pord 0xd to 0 is the main way to turn the keyboard into a brick)
        # So now intensive tasks that use other devices alot and need speed can disable the keyboard during that time
        # This didnt do shit
        # Fuck you microsoft and your slow ass keyboard driver bullshit
        if not self.computer.PMIO.read_port(0xd):
            return
        
        # Check mods even if no key was pressed
        self.check_mods() 
        
        # Now detect a keypress
        # Ignore prefix keys, use msvcrt for non-modifier keys.
        if msvcrt.kbhit():
            key = msvcrt.getch().decode('latin-1').lower()
            
            if key in ('\x00', '\xe0'):
                msvcrt.getch()
                return # ignore prefix keys
            
            key = SHIFTED_KEYS.get(key, key).lower()
            
            # only interrupt if this key has a valid scancode
            if key in scancodes:
                self.kb_interrupt(scancodes[key])
   