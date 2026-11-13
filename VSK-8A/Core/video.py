# A 80x25 text mode display implementation for the VSK-8A   

# 6KB needed, MMIO region selection in ports 0x00/0x01 0x02/0x03 (words low/high)
# Ports 0x10, 0x11, 0x12 belong to the blinking cursor control ports
# 0x10: x coord
# 0x11: y coord
# 0x12: The char (cursor is not shown if this is 0)
# 0x13: The chars background (fg is white by default)

# 3 bytes for each char:

#  offset   byte
#  ------   ----
#  0        background (0 = black, 1 = white, 2 = red, 3 = green, 4 = blue, 5 = light blue)
#  1        foreground  (0 = black, 1 = white, 2 = red, 3 = green, 4 = blue, 5 = light blue)
#  2        ascii char

import sys
import time
import threading
import os

FG_COLORS = {
    0: "\033[38;2;0;0;0m",
    1: "\033[38;2;255;255;255m",
    2: "\033[38;2;255;0;0m",
    3: "\033[38;2;0;255;0m",
    4: "\033[38;2;0;0;255m",
    5: "\033[38;2;0;170;255m"
}

BG_COLORS = {
    0: "\033[48;2;0;0;0m",
    1: "\033[48;2;255;255;255m",
    2: "\033[48;2;255;0;0m",
    3: "\033[48;2;0;255;0m",
    4: "\033[48;2;0;0;255m",
    5: "\033[48;2;0;170;255m"
}

RESET        = "\033[0m"
CURSOR_HOME  = "\033[H"
SCREEN_CLEAR = "\033[2J\033[3J\033[H"

class Screen:
    def __init__(self, ports, memory, core):
        self.ports  = ports 
        self.memory = memory
        self.can_refresh = False
        
        self.core = core # for debugging
        self.instrs_per_second = 0 # also for debugging
        
        self.b80x25 = 80 * 25 * 3 # the total correct size of the MMIO region
        
        self.no_signal_vram = bytearray(80 * 25 * 3) # a hardcoded framebuffer for when there is no proper MMIO initialized, just renders a black screen
        
        self.DIE_NOW = False
        
        self.header                = "Left Ctrl to exit | Left Alt to step | Right Ctrl to reset"
        
        self.cursor_showing = False # used to signal if the cursor is visible on screen
        self.cursor_interval = 0.5
        self.cursor_last_toggle = time.monotonic()
        
        # the screen has a lil debugging thing at the bottom left     
    
        
    def count_instrs_per_second(self):
        """Meant to run in a seperate thread"""
        while True:
            start_time = time.time()
            start_instr = self.core.instructions_executed
            time.sleep(0.5)
            end_time = time.time()  
            end_instr = self.core.instructions_executed
            
            change = end_instr - start_instr
            passed_time = end_time - start_time
            
            self.instrs_per_second = round(change / passed_time, 2)
        
    def refresh(self):
        """Meant to run in a seperate thread"""
        BOTTOM = os.get_terminal_size().lines
        
        while True:
          if self.DIE_NOW:
              exit()
          if self.can_refresh:
            time.sleep(0.033)
            LAST_BOTTOM = BOTTOM
            BOTTOM = os.get_terminal_size().lines
            
            # no need for and masking, read_port always returns a byte
            mmio_start = self.ports.read_port(0x00) | (self.ports.read_port(0x01) << 8) 
            mmio_end   = self.ports.read_port(0x02) | (self.ports.read_port(0x03) << 8) 
            
            # Only render from MMIO if the MMIO regions are correct
            if mmio_end >= mmio_start and ((mmio_end - mmio_start) + 1) == self.b80x25:
                VRAM = self.memory.memory[mmio_start:mmio_end+1]
                curs = 0
                
                # Blinky boi timing
                now = time.monotonic()
                
                if now - self.cursor_last_toggle >= self.cursor_interval:
                    self.cursor_showing = not self.cursor_showing
                    self.cursor_last_toggle = now
                
                text_heap = [] # fill this up with text then dump it all at once
                
                # Blinky boi cursor infastructure
                x_cursor = self.ports.read_port(0x10)
                y_cursor = self.ports.read_port(0x11)
                curs_chr = self.ports.read_port(0x12)
                curs_bg  = self.ports.read_port(0x13)
                
                charsX = 0
                charsY = 0
                
                while curs + 2 < len(VRAM):
                    # Read background
                    bg   = VRAM[curs]
                    
                    # Read foreground 
                    fg   = VRAM[curs+1]
                    
                    # Read ascii char
                    char = VRAM[curs+2]
                    curs += 3
        
                    if charsX == x_cursor and charsY == y_cursor:
                        if curs_chr and self.cursor_showing and charsX < 80:
                            text_heap.append(BG_COLORS.get(curs_bg, BG_COLORS[0]) + chr(curs_chr))
                            charsX += 1
                            continue
        
                    if charsX >= 80:
                       text_heap.append("\n")
                       charsX = 0
                       charsY += 1
                       
                    # Append this char
                    if charsY >= 25:
                        break
                    
                    text_heap.append(BG_COLORS.get(bg, BG_COLORS[0]) + FG_COLORS.get(fg, FG_COLORS[0]) + (chr(char) if 32 <= char <= 126 else " ") + RESET)
                    charsX += 1
            
            # otherwise, build it from a hardcoded blank framebuffer
            else:
                VRAM = self.no_signal_vram
                curs = 0
                
                text_heap = [] # fill this up with text then dump it all at once
                
                charsX = 0
                charsY = 0
                
                while curs + 2 < len(VRAM):
                    # Read background
                    bg   = VRAM[curs]
                    
                    # Read foreground 
                    fg   = VRAM[curs+1]
                    
                    # Read ascii char
                    char = VRAM[curs+2]
                    curs += 3
        
                    if charsX >= 80:
                       text_heap.append("\n")
                       charsX = 0
                       charsY += 1
                       
                    # Append this char
                    if charsY >= 25:
                        break
                    
                    text_heap.append(BG_COLORS.get(bg, BG_COLORS[0]) + FG_COLORS.get(fg, FG_COLORS[0]) + (chr(char) if 32 <= char <= 126 else " ") + RESET)
                    charsX += 1
                      
                          
                          
            sys.stdout.write(CURSOR_HOME)
            if LAST_BOTTOM != BOTTOM:
                sys.stdout.write(SCREEN_CLEAR)
            
            # Dump it all at once (+ debug info)
            
            debug_str = (f"[vsk8a]: instr/s: {round(self.instrs_per_second / 1000000, 2)} MIPS | PC: {self.core.PC:04x} | SP: {self.core.SP:04x} | zero bit: {self.core.ALU.zero} | if bit: {self.core.IF} | carry bit: {self.core.ALU.carry} | {'halted' if self.core.halted else 'not halted'} | step: {str(self.core.STEP).lower()}" + " " * 10) 
            # put 10 spaces infront of the debug string so if the debug string grows large then small, there wont be leftover chars from the last refresh.

            sys.stdout.write(self.header + "\n" + ''.join(text_heap) + ("\n" * (BOTTOM - 26)) + debug_str)
            sys.stdout.flush()
            continue
            
           
            
    
        
    def start(self):
        print("\033[2J\033[H\x1b[?25l") # clear the screen + cursor hide
        
        threading.Thread(target=self.count_instrs_per_second, daemon=True).start()
        return threading.Thread(target=self.refresh, daemon=True)
        

            
            
            
            
        
        
        
        
    