import core # local import
import sys 
import os
import ctypes
import time
import threading

import random # i eat shit

# DEVICES
import Hardware.Disk     as Disk
import Hardware.Keyboard as Keyboard

# this file is a bit of a mess

DEFAULT_BIOS = os.path.abspath(__file__).strip("vsk8a.py") + "/bios/bios.bin" # People can place their BIOS images here if they dont want to specify a path every time

def step_pressed():
    return bool(ctypes.windll.user32.GetAsyncKeyState(0x12) & 0x8000)

if len(sys.argv) == 1:
    print("Usage: vsk8a.py <path-to-bios-bin>")
    sys.exit(1)

print("[vsk8a]: setting up objects ...")
CPUCore = core.vsk8a_enviroment()

bios_path = sys.argv[1]
if bios_path == "default_bios":            
    bios_path = DEFAULT_BIOS
    
if not os.path.exists(bios_path):
    print(f"'{bios_path}': File not found.")
    sys.exit(1)
    
# Load the binary and start the CPU
print("[vsk8a]: spinning up ... (press ctrl+c to stop CPU)")

# Load the binary
with open(bios_path, "rb") as f:
    bios_bytes = f.read()
    
        
print("[vsk8a]: loaded provided bios!")  
print("[vsk8a]: starting screen")     

STEP_ACTIVE, CPUCore.STEP = '--step' in sys.argv, '--step' in sys.argv

STEPTIME = 0.1
if "--steptime" in sys.argv:
    try:
        STEPTIME = sys.argv[sys.argv.index("--steptime") + 1]
        STEPTIME = float(STEPTIME)

    except:
        STEPTIME = 0.1

DISKPATH = "PATHDOESNOTEXIST"
if "--disk" in sys.argv:
    try:
        DISKPATH = sys.argv[sys.argv.index("--disk")+1]

    except:
        DISKPATH = "PATHDOESNOTEXIST"
        
DUMPPATH = None 
if "--dump" in sys.argv:
    try:
        DUMPPATH = sys.argv[sys.argv.index("--dump")+1]

    except:
        DUMPPATH = None 
        
BREAKPOINT = None      
if "--break" in sys.argv:
    try:
        BREAKPOINT = int(sys.argv[sys.argv.index("--break")+1], 0)

    except:
        BREAKPOINT = None  
        
VERBOSE = "--verbose-run" in sys.argv    
CORRUPTOR = None
BREAKPOINT = None
INTENSITY  = None      
if "--corrupt-run" in sys.argv:
    try:
        INTENSITY = sys.argv[sys.argv.index("--corrupt-run")+1]
        CORRUPTOR = True 

    except:
        INTENSITY, CORRUPTOR = None, None  

Screen = core.video.Screen(ports=CPUCore.PMIO, memory=CPUCore.Memory, core=CPUCore) if "--gui" not in sys.argv else core.guivideo.Screen(ports=CPUCore.PMIO, memory=CPUCore.Memory, core=CPUCore)
Screen.start().start() # this is a crime against humanity
Screen.can_refresh = True

def end():
    print("[vsk8a]: end() called, debug info after run:\n")
    print(f"rA / rB / rC / rD: {CPUCore.Registers.read_16bitgpr('A'):04x} / {CPUCore.Registers.read_16bitgpr('B'):04x} / {CPUCore.Registers.read_16bitgpr('C'):04x} / {CPUCore.Registers.read_16bitgpr('D'):04x}")
    print(f"8-bit GPRs (r0-r{len(CPUCore.Registers.registers)-1}): {' '.join([f'{b:02x}' for b in CPUCore.Registers.registers])}")
    print(f"PC={CPUCore.PC:04x} zero_bit={CPUCore.ALU.zero}")
    print("\nMemory around PC (256 bytes):\n===============================================", end="")
    if disk.handle is not None: # FIX: i think you know why this is here.
        disk.handle.close()
    
    start = max(0, CPUCore.PC - 256)
    end = CPUCore.PC + 256
    
    dump = CPUCore.Memory.memory[start:end]
    
    for char, b in enumerate(dump):
        if char % 16 == 0:
            print(f'\n{start + char:04x}: ', end="")
    
        print(
            f'({b:02x})' if start + char == CPUCore.PC else f' {b:02x} ',
            end=""
        )
    
    print("\n===============================================\n\nHardware ports:\n===============================================")
    c = 0
    for b in CPUCore.PMIO.pmio:
        print(f'{b:02x} ', end='')
        c += 1
        if c > 15:
            print()
            c = 0
        
    print("===============================================")
    if DUMPPATH and os.path.exists(DUMPPATH):
        print(f"Dumping memory... '{DUMPPATH + '/memory.bin'}'")
        with open(DUMPPATH + "/memory.bin", "wb") as f:
            f.write(CPUCore.Memory.memory)
            
        print(f"Dumping vram... '{DUMPPATH + '/vram.bin'}'")    
        with open(DUMPPATH + "/vram.bin", "wb") as f:
            f.write(CPUCore.Memory.memory[CPUCore.PMIO.read_port(0x00) | (CPUCore.PMIO.read_port(0x01) << 8):CPUCore.PMIO.read_port(0x02) | (CPUCore.PMIO.read_port(0x03) << 8)])
    
    else:
        print("No '--dump' specified")    
    
    sys.exit(0)
   
def exit_pressed():
    return bool(ctypes.windll.user32.GetAsyncKeyState(0xA2) & 0x8000)  

def reset_pressed():
    return bool(ctypes.windll.user32.GetAsyncKeyState(0xA3) & 0x8000) 
   
UPDATE_DIE = False    
UPDATE_PAUSE = False
def update_step():
    global STEP_ACTIVE, UPDATE_DIE
    """Meant to be ran in a thread"""
    while True:   
        if UPDATE_PAUSE:
            time.sleep(0.5)
            continue
        if UPDATE_DIE: sys.exit(0)
        time.sleep(0.1)
        if STEP_ACTIVE:
            if step_pressed():
                CPUCore.STEP = not CPUCore.STEP
                time.sleep(0.5)
  
if STEP_ACTIVE:
    threading.Thread(target=update_step, daemon=True).start()        
   
def reset():
    CPUCore.Memory.memory = bytearray(len(CPUCore.Memory.memory))
    CPUCore.Registers.registers = bytearray(len(CPUCore.Registers.registers))
    
    CPUCore.faults_before_reset = 0
    CPUCore.PC = 0xf000 # reset vector 
    CPUCore.SP = 0  
    CPUCore.faults_before_reset = 0
    CPUCore.ALU.zero = 0
    
    CPUCore.halted = False
    
    CPUCore.PMIO.pmio = bytearray(len(CPUCore.PMIO.pmio))
    
    time.sleep(0.5) # The GUI GUI cant keep up with fast restarts, this fixes it.
    
    # load given BIOS
    with open(bios_path, "rb") as f:
        bios_bytes = f.read()
    
    for a, v in enumerate(bios_bytes):
        try:
          CPUCore.Memory.write_byte(address=a+0xf000, value=v)
        
        except core.memory.InvalidMemoryAccess:
            print(f"'{bios_path}': File too big to fit into emulator RAM")
            sys.exit(1)
        
TF_IGNORE = "--quiet-triple-fault" in sys.argv        
            
def clean(bp_status = False):
    global UPDATE_DIE
    UPDATE_DIE = True   
    Screen.can_refresh = False
    Screen.DIE_NOW = True
    time.sleep(0.055)
    if not bp_status:
        print("\n[vsk8a]: interrupted by user!")
        
    else:
        print("\n[vsk8a]: breakpoint address reached!")
    end()    

if "--gui" in sys.argv:
    print("<== output in seperate window ==>")

disk     = Disk.Disk(computer=CPUCore, path=DISKPATH)
keyboard = Keyboard.Keyboard(computer=CPUCore)

hardware = core.Hardware(devices=[disk, keyboard])
hardware.hwclock()

check_ticks = 0
MessageBoxW = ctypes.windll.user32.MessageBoxW

CPUCore.halted = False
do_check = "--gui" in sys.argv

if not do_check and VERBOSE:
    print("Verbose logging cannot be done without the GUI window.")
    sys.exit(1)

def floppyflipper(v, pos):
    return v ^ (1 << pos)

reset()
while True:
    # Don't remove these key-press and step checks thinking it will imrpove emulator speed, it does not.
    # It makes it 10000000000x slower
    # Python's stupid GIL is to blame.
    # (the check_ticks thingy worked though)
    
    check_ticks += 1
    
    if CORRUPTOR:
        if random.randint(0, 100000) < 1 if INTENSITY == "mild" else 3 if INTENSITY == "bad" else 7 if INTENSITY == "hell" else 10:
            address = random.randint(0, CPUCore.Memory.max_address)
            p       = random.randint(0, 7)
            flipped = floppyflipper(CPUCore.Memory.read_byte(address), p) 
            CPUCore.Memory.write_byte(address=address, value=flipped)
    
    if check_ticks % 100 == 0:
        check_ticks = 0
        
        if CPUCore.STEP:
            time.sleep(STEPTIME)     
    
        if exit_pressed():
            clean() 
            
        if reset_pressed():
            reset()
            
        # Also check the status flags for the GUI if we are using the GUI GUI (ah yes, the GUI GUI)
        if do_check:
            flag = Screen.flag
            if not flag:
                continue
            
            if flag == Screen.FLAG_RESET:
                Screen.flag = 0
                reset()
                
            elif flag == Screen.FLAG_SHUTDOWN:
                Screen.flag = 0
                clean()
                
            elif flag == Screen.FLAG_STEP:
                Screen.flag = 0
                if STEP_ACTIVE:
                    CPUCore.STEP = not CPUCore.STEP

    # force-reset upon triple fault
    if CPUCore.faults_before_reset > 3:
        if not TF_IGNORE:
            MessageBoxW(0, f"The guest has triple faulted at IP {CPUCore.PC:04x} (SP {CPUCore.SP:04x}) and will be forced to reset.", "VSK-8A: Triple Fault", 0x10)
        reset()
        
    if BREAKPOINT:
        if CPUCore.PC == BREAKPOINT:
            clean(True) 
            
    if VERBOSE:
        if CPUCore.last_irq:
            print(f"IRQ {CPUCore.last_irq} raised at PC {CPUCore.PC:04x} SP {CPUCore.SP:04x}")
            CPUCore.last_irq = 0
            
        if CPUCore.faults_before_reset:
            print(f"Fault count is above 0 ({CPUCore.faults_before_reset})")   
        
    CPUCore.step()
    

    
