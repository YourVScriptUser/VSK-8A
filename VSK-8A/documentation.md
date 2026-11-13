**VSK-8A Technical Documentation** 

# Contents
1. [Opcodes](#opcodes)

2. [Exception IRQs](#exception-irqs)

3. [Virtual Hardware](#virtual-hardware)

4. [VRAM](#vram)

5. [CLI Control](#cli-control)

6. [eBIOS](#ebios)

7. [ISA](#isa)

# Opcodes

The emulator has 50 opcodes at the time that this was written (I will do my best to update this amount and add documentation for any new opcodes being added)

Opcodes have 2 types, 'big' opcodes and 'small' opcodes

Instruction encoding is little-endian (just like everything else with the emulator)

Byte encoding:
```
'Big' Opcode - 6 bytes:
  OFFSET | PURPOSE
  0      | Prefix, defines if this opcode is a big or small opcode
  1      | The opcode
  2      | op8_1: 8-bit operand 1
  3      | Low byte of op16 (16 bit operand)
  4      | High byte of op16 (16 bit operand)
  5      | op8_2: 8-bit operand 2

  
'Small' Opcode - 3 bytes:
  OFFSET | PURPOSE
  0      | Prefix, defines if this opcode is a big or a small opcode
  1      | The opcode
  2      | op8: Single 8-bit operand
```
The prefix tells the CPU which opcode type it is actively decoding, a invalid prefix raises a unknown opcode fault 
A prefix of 0 means it is a big opcode, whereas a prefix of 1 means it is a small opcode.

The op8 operands are mostly for source/destination registers whilst op16 is normally used for a immediate or memory address, however when the opcode does not need a immediate or memory address it can use it as a flag.
For example, XOR which needs op16 to know the width of the registers, say if op8_1 was 1, how does the CPU know if it targets 16-bit register 1 (corresponds to rB) or 8-bit register r1, it does not need a immediate or address in op16, so it uses it as a flag to know what registers to target. If a opcode receives a flag that is not valid, it raises an unknown opcode fault.

Unlike previous CPUs in the VSK family where a null byte (0) is an invalid opcode, the VSK-8A treats 0 as the big opcode LOAD_REG, which loads the value in op8_2 into a 8-bit register specified in op8_1, which means the 6-byte opcode `00 00 00 00 00 00` is a perfectly valid opcode and corresponds to the x8 assembly instruction `mov r0, 0`  

Most opcodes are 6-byte opcodes because they need the extra args, however there are still a fair few small opcodes (`hlt, jmp (register only - immediate jmp is a 6-byte opcode), ret, iret, int, cli, sti, pusha, popa`)

If a instructions prefix is valid, but its opcode is unknown, it will always raise a unknown opcode fault

Some other opcode examples:
```
mov a, 0x1234
00 0C 00 34 12 00

jmp 0x1234
00 0B 00 34 12 00

INT 5h
01 29 05
```
There is also a known nuance with the CMP opcode, and the x8 assembler warns about it.
WARNING: In a opcode like this "`CMP A, r0`": the zero flag is right but the carry flag is reversed because the emulator has no instruction to do that but does have an instruction for things like "`CMP r0, A`", so the assembler swaps them. This is fine and is a known nuance, since you will never really need to compare registers of different widths anyway.


# Exception IRQs

Exception IRQs are placed high in the IVT to avoid colliding with SWIs.
There are not many exception IRQs.

```
Unknown opcode - IRQ 0x7c
Invalid register     - IRQ 0x7e
ALU Unmatching Widths - IRQ 0x7d
Invalid memory address - IRQ 0x7f
Unknown - 0x7b
```
# Virtual Hardware

At the current time of this doc write, the VSK-8A has 2 implemented devices, a disk and a keyboard. And one special device (the screen)

Hardware is updated every 0.01 seconds if the device has been behaving (the device will not be updated if it has faulted)

IRQ 0 **CANNOT** be used as a device IRQ.

The screen is a special hardware type and does not use the same hardware bus as updating every 0.01 and having to share duty time with other devices would make the screen slow, so it gets its own hardware bus.

You communicate to devices via PMIO, and the devices are made to be as bare-metal as possible.
Overview on how to talk to devices:
``` 
1. Disk
The disk uses 512B sectors and has two modes, polling mode and interrupt mode. If the IRQ port is nonzero, it is in IRQ mode it will interrupt the processor when done.
PORT | PURPOSE
0x5  | Command, 1=read, 2=write, set to 0 when the command is complete
0x6  | DMA Memory Address (low) (used for read/write, writing writes the block to a sector, reading writes the sector to this address)
0x7  | DMA Memory Address (high)
0x8  | Linear Sector (low) (the sector to read/write)
0x9  | Linear Sector (high)
0xa  | Error Status (0=no errors, 1=no disk, 2=disk error) 
0xb  | Amount of sectors (low)
0xc  | Amount of sectors (high)

2. Keyboard
The keyboard is a very dumb keyboard with only one modifier key (shift) and a scancode system
PORT | PURPOSE      
0xd  | The IRQ to raise upon a keypress - set this to 0 to disable the keyboard completley
0xe  | The latest key pressed (scancode)
0xf  | Modifier

Scancodes:
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

3. Screen
PORT | PURPOSE
0x0  | Start address low  (the start address for the video buffer in RAM)
0x1  | Start address high 
0x2  | End address low    (the end address for the video buffer in RAM - not inclusive)
0x3  | End address high
0x10 | x coord for blinking char (the screen supports 1 blinking char)
0x11 | y coord for blinking char
0x12 | The blinking char (in ascii)
0x13 | The chars background
```

# VRAM

The screen is a 80x25 text-mode implementation a 6000B buffer, with 3 bytes per character. (see above for ports)
``` 
offset |  byte
0      |  background (0 = black, 1 = white, 2 = red, 3 = green, 4 = blue, 5 = light blue)
1      |  foreground (0 = black, 1 = white, 2 = red, 3 = green, 4 = blue, 5 = light blue)
2      |  ascii char
``` 
I know i could have shortened it by making ids for fg/bg combinations but i found this to be nicer to use, and so I'm not ripping off Intel.

# CLI Control
Put the install dir into your path enviroment vars, and the command vsk8a will control the emulator.
CLI Control is implemented inside `{install_dir}/vsk8a.py`

Command Overview:
``` 
The first arg is always the BIOS path, but eBIOS is included with the emulator. Type 'default_bios' to use it.

Extra args:
--disk: Put a path to a disk path here if you want a disk (warning: the disk image size (in bytes) must be divisible by 512)
--gui:  Put video output into a dedicated GUI window, using QEMU's text mode font
--quiet-triple-fault: Disable the error message when a triple fault occurs and silentley reset instead
--step: Put the CPU into step mode
--steptime: Sleep for this amount of time (in seconds) inbetween instructions when in step mode
--dump: Excpects a dir, puts memory.bin and vram.bin dumps in that dir
--break: Breakpoint address (when ip hits this address the emulator auto-dies)
--verbose-run: Print interrupts as they come (warning: requires --gui and deprecated)

For fun:
--corrupt-run: activate the memory random bit flopper, takes an intensity. Intensities are mild, bad and hell.
``` 

# Specifications

IVT region: 0x00-0xFF, 128 total IRQs, 2 bytes per entry

Register list:
``` 
16-bits: A, B, C, D
8-bits:
r0, r1, r2, r3, al, ah, bl, bh, cl, ch, dl, dh
``` 

# eBIOS 
Since the VSK-8A is a LLE, it needs a BIOS, and it's BIOS is written entirely in x8 assembly.
Upon boot, the BIOS gets loaded to 0xf000, the BIOS then clears IF, sets up the registers then sets up a stack to the BIOS stack region at 0xeddf, it then clears the hardware ports and initialises VRAM to 0xb000

The BIOS has 3 main services, INT 10h, 11h and 12h.
Service overview:
``` 
INT 12h (wait key)
Waits for a single key
Pushes ascii key to stack

INT 11h (read disk) 
Read a single sector
Sector in A, DMA address in B 
pushed onto stack: status (0 = success, 1 = no disk, 2 = disk error, 3 = timeout)

INT 10h (video services)
function in r3

function 1:
simple tty (using bios inbuilt coords, supports auto-wrapping and '\n')
r0: ASCII char
r1: BG
r2: FG

function 2:
coord tty (warning: no '\n' support or auto-wrapping)
r0: ASCII char
r1: BG
r2: FG
rA: coord x
rB: coord y

function 3:
reset BIOS x, y (does not clear the screen)

function 4:
wind back to the last char (x - 1 (also does y handling for if x is 0, it just goes back to the last line))

function 5:
read bios internal x,y
pushes them to stack in this form: [x, y] (do pop a to get x in al and y in ah)

function 6
write bios internal x,y
r0: new x
r1: new y
``` 

# ISA

Where r8 is any 8-bit GPR and r16 is any 16-bit GPR (0=A, 1=B, 2=C, 3=D), opcodes with `(S)` use small encoding, ones without `(S)` use big encoding.


| Op | Mnemonic              | Operands                                                                                                 | Behavior                                                       |
| -- | --------------------- | -------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------- |
| 0  | `LOAD_REG`            | op8_1 = dest r8, op8_2 = imm8                                                                            | `r8[op8_1] = op8_2`                                            |
| 1  | `HALT` **(S)**        | none                                                                                                     | Halts the CPU until an enabled interrupt arrives                       |
| 2  | `WRITE_MEM8`          | op16 = address, op8_1 = value or r8, op8_2 = source type (0 = imm, 1 = reg)                              | `mem8[op16] = op8_1` (imm) or `r8[op8_1]` (reg)                |
| 3  | `WRITE_MEM8A`         | op8_1 = address r16, op8_2 = value r8                                                                    | `mem8[r16[op8_1]] = r8[op8_2]`                                 |
| 4  | `WRITE_MEM16`         | op8_1 = address r16, op8_2 = value r16                                                                   | `mem16[r16[op8_1]] = r16[op8_2]`                               |
| 5  | `SUB8`                | op8_1 = src r8, op8_2 = dest r8                                                                          | `dest -= src`                                                  |
| 6  | `SUB16`               | op8_1 = src r16, op8_2 = dest r16                                                                        | `dest -= src`                                                  |
| 7  | `ADD8`                | op8_1 = src r8, op8_2 = dest r8                                                                          | `dest += src`                                                  |
| 8  | `ADD16`               | op8_1 = src r16, op8_2 = dest r16                                                                        | `dest += src`                                                  |
| 9  | `JZ`                  | op16 = address                                                                                           | Jump if ZF = 1                                                 |
| 10 | `JNZ`                 | op16 = address                                                                                           | Jump if ZF = 0                                                 |
| 11 | `JMP`                 | op16 = address                                                                                           | `PC = op16`                                                    |
| 12 | `LOAD_REG16`          | op8_1 = dest r16, op16 = imm16                                                                           | `r16[op8_1] = op16`                                            |
| 13 | `PORT_IN`             | op8_1 = dest r8, op8_2 = port or port reg, op16 = mode (0 = op8_2 is a reg, 1 = op8_2 is the port)       | `r8[op8_1] = read_port(port)`                                  |
| 14 | `PORT_OUT`            | op8_1 = value r8, op8_2 = port or port reg, op16 = mode (0 = reg, 1 = port)                              | `write_port(port, r8[op8_1])`                                  |
| 15 | `JMP_REG` **(S)**     | op8_1 = r16                                                                                              | `PC = r16[op8_1]`                                              |
| 16 | `READ_MEM8A`          | op8_1 = dest r8, op8_2 = address r16                                                                     | `r8[op8_1] = mem8[r16[op8_2]]`                                 |
| 17 | `READ_MEM8`           | op16 = address, op8_1 = dest r8                                                                          | `r8[op8_1] = mem8[op16]`                                       |
| 18 | `READ_MEM16`          | op8_1 = dest r16, op8_2 = address r16                                                                    | `r16[op8_1] = mem16[r16[op8_2]]`                               |
| 19 | `ADD_IMM`             | op8_1 = dest type (0 = r8, 1 = r16), op8_2 = dest reg, op16 = imm                                        | `dest += op16`, sets CF and ZF                                 |
| 20 | `XOR`                 | op8_1 = src, op8_2 = dest, op16 = reg type (0 = 8-bit, 1 = 16-bit)                                       | `dest ^= src`, sets ZF                                         |
| 21 | `OR`                  | same as XOR                                                                                              | `dest \|= src`, sets ZF                                        |
| 22 | `AND`                 | same as XOR                                                                                              | `dest &= src`, sets ZF                                         |
| 23 | `AND_TEST`            | same as XOR                                                                                              | Computes `dest & src`, sets ZF, discards the result            |
| 24 | `PUSH`                | op8_1 = reg, op8_2 = reg type (0 = r8, 1 = r16)                                                          | Pushes the register onto the stack                             |
| 25 | `POP`                 | op8_1 = reg, op8_2 = reg type (0 = r8, 1 = r16)                                                          | Pops the stack into the register                               |
| 26 | `CALL`                | op16 = address                                                                                           | `push16(PC)`, then `PC = op16`                                 |
| 27 | `RET` **(S)**         | none                                                                                                     | `PC = pop16()`                                                 |
| 28 | `MOVE_SP`             | op16 = value                                                                                             | `SP = op16`                                                    |
| 29 | `ADD_UNM`             | op8_1 = r16, op8_2 = r8, op16 = direction (0 = r16 is src and r8 is dest, 1 = r8 is src and r16 is dest) | `dest += src`                                                  |
| 30 | `SUB_UNM`             | same as ADD_UNM                                                                                          | `dest -= src`                                                  |
| 31 | `MUL_UNM`             | same as ADD_UNM                                                                                          | `dest *= src`                                                  |
| 32 | `DIV_UNM`             | same as ADD_UNM                                                                                          | `dest /= src`                                                  |
| 33 | `DIV`                 | op8_1 = src r8, op8_2 = dest r8                                                                          | `dest /= src`                                                  |
| 34 | `MUL`                 | op8_1 = src r8, op8_2 = dest r8                                                                          | `dest *= src`                                                  |
| 35 | `DIV16`               | op8_1 = src r16, op8_2 = dest r16                                                                        | `dest /= src`                                                  |
| 36 | `MUL16`               | op8_1 = src r16, op8_2 = dest r16                                                                        | `dest *= src`                                                  |
| 37 | `MOVE`                | op8_1 = src, op8_2 = dest, op16 = type (0 = r8→r8, 1 = r16→r16, 2 = r8→r16, 3 = r16→r8)                  | Copies src to dest                                             |
| 38 | `COMPARE_Z`           | op8_1 = reg 1, op8_2 = reg 2, op16 = type (0 = r8/r8, 1 = r16/r16, 2 = r16/r8)                           | Computes reg 1 − reg 2, sets ZF and CF, discards the result    |
| 39 | `SHR`                 | op8_1 = reg, op8_2 = reg type (0 = r8, 1 = r16)                                                          | `reg >>= 1`                                                    |
| 40 | `SHL`                 | op8_1 = reg, op8_2 = reg type (0 = r8, 1 = r16)                                                          | `reg <<= 1`                                                    |
| 41 | `INT` **(S)**         | op8_1 = vector                                                                                           | Software interrupt, taken even if IF = 0                       |
| 42 | `IRET` **(S)**        | none                                                                                                     | Returns from an interrupt and restores PC, GPRs, ZF, CF and IF |
| 43 | `INTERRUPT_C` **(S)** | op8_1 = 0 or 1                                                                                           | `IF = op8_1`, any other value is an invalid opcode             |
| 44 | `CMPZ_IMM`            | op8_1 = reg, op16 = imm, op8_2 = reg type (0 = r8, 1 = r16)                                              | Computes reg − op16, sets ZF and CF, discards the result       |
| 45 | `SUB_IMM`             | op8_1 = dest type (0 = r8, 1 = r16), op8_2 = dest reg, op16 = imm                                        | `dest -= op16`, sets CF and ZF                                 |
| 46 | `PUSH_ALL` **(S)**    | none                                                                                                     | Pushes r0-r3, then A, B, C, D                                  |
| 47 | `POP_ALL` **(S)**     | none                                                                                                     | Pops D, C, B, A, then r3, r2, r1, r0                           |
| 48 | `JUMP_CARRY`          | op16 = address                                                                                           | Jump if CF = 1                                                 |
| 49 | `JUMP_NOT_CARRY`      | op16 = address                                                                                           | Jump if CF = 0                                                 |

Arithmetic flag behaviour:
| Op    | Mnemonic             | ZF                 | CF                                             |
| ----- | -------------------- | ------------------ | ---------------------------------------------- |
| 5     | `SUB8`               | result == 0        | set on borrow (`dest < src`)                   |
| 6     | `SUB16`              | result == 0        | set on borrow                                  |
| 7     | `ADD8`               | result == 0        | set if the sum exceeds 0xFF                    |
| 8     | `ADD16`              | result == 0        | set if the sum exceeds 0xFFFF                  |
| 19    | `ADD_IMM`            | result == 0        | set on overflow past 0xFF (r8) or 0xFFFF (r16) |
| 20-22 | `XOR` / `OR` / `AND` | result == 0        | unchanged                                      |
| 23    | `AND_TEST`           | result == 0        | unchanged                                      |
| 29    | `ADD_UNM`            | result == 0        | set on overflow past the dest width            |
| 30    | `SUB_UNM`            | result == 0        | set on borrow                                  |
| 31    | `MUL_UNM`            | result == 0        | set on overflow past the dest width            |
| 32    | `DIV_UNM`            | result == 0        | unchanged                                      |
| 33    | `DIV`                | result == 0        | unchanged                                      |
| 34    | `MUL`                | result == 0        | set if the product exceeds 0xFF                |
| 35    | `DIV16`              | result == 0        | unchanged                                      |
| 36    | `MUL16`              | result == 0        | set if the product exceeds 0xFFFF              |
| 38    | `COMPARE_Z`          | reg 1 − reg 2 == 0 | set if reg 1 < reg 2                           |
| 44    | `CMPZ_IMM`           | reg − imm == 0     | set if reg < imm                               |
| 45    | `SUB_IMM`            | result == 0        | set on borrow                                  |

`SHR`, `SHL`, `MOVE`, the loads and stores, the stack ops, port I/O, and the jumps leave both flags unchanged.