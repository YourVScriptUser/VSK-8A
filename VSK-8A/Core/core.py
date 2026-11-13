# VSK-8A Core
# Contains instruction decoding and the core system

import memory 
import alu
import regs 
import virtio

import video     # video subsystem
import guivideo  # different video subsystem (yuh uh)

def vsk8a_enviroment():
    # Return a CPU object
    
    Memory    = memory.RAM(size=64 * 1024) # 64KiB
    Registers = regs.Registers()
    ALU       = alu.ALU(regs=Registers)
    PMIO      = virtio.PMIO()
    
    CPUCore   = vsk8a(Memory=Memory, Registers=Registers, ALU=ALU, PMIO=PMIO)
    return CPUCore

class Hardware:
    def __init__(self, devices: list):
        self.devices = devices 
        self.faulty  = [] # a list of faulty devices
                          # upon a py exception they get put on this list and do not get ticked if they are in this list
        
    def hwclock(self):
        def tickall():
            """Meant to run in a thread"""    
            while True:
                # NOTE: IF KEYBOARD RESPONDS SLOWLY, DECREASE THIS CALL BELOW.
                video.time.sleep(0.01) 
                for device in self.devices:
                    try:
                        if device not in self.faulty:
                            device.tick()
                    except Exception:
                        self.faulty.append(device)
                    
        video.threading.Thread(target=tickall, daemon=True).start()
    
class vsk8a:
    class InvalidOpcode(Exception): pass
    STEP = False
    
    class Opcodes:
        LOAD_REG    = 0
        # op8[1] = the register, op8[2] = the value 
        
        HALT        = 1
        # No ops.
        
        WRITE_MEM8  = 2
        # op16 = the address, op8[1] = the value / register, op8[2] = source type (0 = imm, 1 = reg)    
        
        WRITE_MEM8A = 3
        # op8_1 = source address 16-bit gpr, op8_2 = 8-bit gpr value  
        
        WRITE_MEM16 = 4
        # op8_1 = source address 16-bit gpr, op8_2 = source value 16-bit gpr
        
        SUB8        = 5
        # op8_1 = source 8 bit reg, op8_2 = dest 8 bit reg
        
        SUB16       = 6
        # op8_1 = source 16 bit reg, op8_2 = dest 16-bit reg
        
        ADD8        = 7
        # op8_1 = source 8 bit reg, op8_2 = dest 8 bit reg
        
        ADD16       = 8
        # op8_1 = source 16 bit reg, op8_2 = dest 16-bit reg
        
        JZ          = 9
        # op16 = address
        
        JNZ         = 10
        # op16 = address
        
        JMP         = 11
        # op16 = address
        
        LOAD_REG16  = 12
        # op8_1 = the 16-bit gpr, op16 = the value
        
        PORT_IN     = 13
        # op8_1 = the 8 bit register dest, op8_2 = the 8 bit register port, op16 = mode (0 = op8_2 is a register, 1 = op8_2 is a port)
        
        PORT_OUT    = 14
        # op8_1 = the 8 bit register value, op8_2 = the 8 bit register port, op16 = mode (0 = op8_2 is a register, 1 = op8_2 is a port)
        
        JMP_REG     = 15
        # op8_1 = the 16-bit gpr to jump to
        
        READ_MEM8A   = 16
        # op8_1 = dest 8 bit reg, op8_2 address 16 bit gpr
        
        READ_MEM8    = 17
        # op16 = address, op8_1 = dest 8 bit reg  
        
        READ_MEM16   = 18
        # op8_1 = dest 16-bit gpr, op8_2 = address 16-bit gpr
        
        ADD_IMM      = 19 
        # op8_1 = dest type (0 = 8 bit gpr, 1 = 16 bit gpr), op16 = src (to add to dest), op8_2 = dest reg
        
        XOR          = 20
        # op8_1 = src, op8_2 = dest, op16 = regtype (0 = 8 bit gpr, 1 = 16 bit gpr)
        
        OR           = 21
        # op8_1 = src, op8_2 = dest, op16 = regtype (0 = 8 bit gpr, 1 = 16 bit gpr)
        
        AND          = 22
        # op8_1 = src, op8_2 = dest, op16 = regtype (0 = 8 bit gpr, 1 = 16 bit gpr)
        
        AND_TEST     = 23
        # op8_1 = src, op8_2 = dest, op16 = regtype (0 = 8 bit gpr, 1 = 16 bit gpr)
        
        PUSH         = 24
        # op8_1 = reg, op8_2 = regtype (0 = 8 bit gpr, 1 = 16 bit gpr)
        
        POP          = 25
        # op8_1 = reg, op8_2 = regtype (0 = 8 bit gpr, 1 = 16 bit gpr)
        
        CALL         = 26
        # op16 = address
        
        RET          = 27
        # No ops.
        
        MOVE_SP      = 28
        # op16 = address
        
        ADD_UNM      = 29
        # op8_1 = 16 bit reg, op8_2 = 8 bit reg, op16 = dest/src switch (0 = 16 bit gpr src, 8 bit gpr dest, 1 = 8 bit gpr src, 16 bit gpr dest)
        
        SUB_UNM      = 30
        # op8_1 = 16 bit reg, op8_2 = 8 bit reg, op16 = dest/src switch (0 = 16 bit gpr src, 8 bit gpr dest, 1 = 8 bit gpr src, 16 bit gpr dest)
        
        MUL_UNM      = 31
        # op8_1 = 16 bit reg, op8_2 = 8 bit reg, op16 = dest/src switch (0 = 16 bit gpr src, 8 bit gpr dest, 1 = 8 bit gpr src, 16 bit gpr dest)
        
        DIV_UNM      = 32
        # op8_1 = 16 bit reg, op8_2 = 8 bit reg, op16 = dest/src switch (0 = 16 bit gpr src, 8 bit gpr dest, 1 = 8 bit gpr src, 16 bit gpr dest)
        
        DIV          = 33
        # op8_1 = source 8 bit reg, op8_2 = dest 8 bit reg
        
        MUL          = 34
        # op8_1 = source 8 bit reg, op8_2 = dest 8 bit reg
        
        DIV16        = 35
        # op8_1 = source 16 bit reg, op8_2 = dest 16 bit reg
        
        MUL16        = 36
        # op8_1 = source 16 bit reg, op8_2 = dest 16 bit reg
        
        MOVE         = 37
        # op8_1 = source reg, op8_2 = dest reg, op16 = type (0 = 8 bit gpr to 8 bit gpr, 1 = 16 bit gpr to 16 bit gpr, 2 = 8 bit gpr to 16 bit gpr, 3 = 16 bit gpr to 8 bit gpr)
        
        COMPARE_Z    = 38
        # op8_1 = reg 1, op8_2 = reg 2, op16 = type (0 = 8 bit gpr to 8 bit gpr, 1 = 16 bit gpr to 16 bit gpr, 2 = 8 bit gpr to 16 bit gpr)
        
        SHR          = 39
        # op8_1 = reg, op8_2 = regtype (0 = 8 bit, 1 = 16 bit)
        
        SHL          = 40
        # op8_1 = reg, op8_2 = regtype (0 = 8 bit, 1 = 16 bit)
        
        INT          = 41
        # op8_1 = vector
        
        IRET         = 42
        # No ops.
        
        INTERRUPT_C  = 43
        # op8_1 = mode (sets IF to op8_1 if op8_1 is a single bit large)
        
        CMPZ_IMM     = 44
        # op8_1 = reg, op16 = compare, op8_2 = regtype (0 = 8 bit, 1 = 16 bit)
        
        SUB_IMM      = 45
        # op8_1 = dest type (0 = 8 bit gpr, 1 = 16 bit gpr), op16 = src (to add to dest), op8_2 = dest reg
        
        PUSH_ALL     = 46
        # No ops.
        
        POP_ALL      = 47
        # No ops.
        
        JUMP_CARRY   = 48
        # op16 = the address
        
        JUMP_NOT_CARRY = 49
        # op16 = the address
    
    def __init__(self, Memory: memory.RAM, Registers: regs.Registers, ALU: alu.ALU, PMIO: virtio.PMIO):
        self.Memory      = Memory
        self.Registers   = Registers
        self.ALU         = ALU  
        self.PMIO        = PMIO
        self.PC          = 0
        self.SP          = 0
        self.halted      = True
        self.zf_save     = self.ALU.zero
        self.if_save     = 0
        self.cf_save     = 0
        self.pending_irq = 0
        self.last_irq    = 0 # for '--verbose-run'
        
        self.faults_before_reset = 0 
        
        self.IF          = 0 # interrupt flag
        
        self.edt         = {
            memory.InvalidMemoryAccess: 127,
            regs.InvalidRegister: 126,
            alu.UnmatchingWidths: 125,
            self.InvalidOpcode:   124,
            "unknown":            123
            } # exception dispatch table
            # place exception IRQs high in the IVT
            
        self.reg_save_stack = [] # used by interrupts 
        
        self.instructions_executed = 0
        
    def fetch8(self):
        self.PC &= 0xFFFF
        value = self.Memory.read_byte(self.PC)
        self.PC += 1
        return value
    
    def fetch16(self):
        self.PC &= 0xFFFF
        value = self.Memory.read_word(self.PC)
        self.PC += 2
        return value
        
    def interrupt(self, irq, software=False):
        """Interrupts the processor"""
        if not self.IF and not software:
            return
        
        self.last_irq = irq
        
        vector = irq * 2
        isr = self.Memory.read_word(vector)

        self.context_switch("in")
        self.halted = False # FIX: a interrupt should wake up the processor
        self.PC = isr
        
    def out_interrupt(self):
        """Takes the CPU out of a interrupt (eg. IRET)"""
        # Reset fault count here, so incase it was a exception IRQ, then the fault count will be reset (fault handler returned successfully)
        # HACK: Could maybe perhaps cause weird behaviour in non-exception IRQs? Rarely, prolly not.
        self.faults_before_reset = 0

        # Only actually do a out context switch if the preservation stack is not empty to avoid errors with list.pop()
        if self.reg_save_stack:
            self.context_switch("out")
        
    def context_switch(self, mode):
        if mode == "in": # into an interrupt (INT / HWI)
            self.zf_save = self.ALU.zero
            self.if_save = self.IF # save original IF
            # Nested interrupts are supported, but they will not save IF and ZF properly. Which is fine, they are not that important and software can handle it.
            
            self.IF = 0 # prevent nested interrupts (they are not supported) 
                        # erm actually they are but keep IF like that because i have autism
            
            self.cf_save = self.ALU.carry
            
            # Push PC normally
            self.push16(self.PC)
            
            # Now push the rest of the regs to a special CPU-managed stack
            self.reg_save_stack.append(self.Registers.registers.copy())
            
        elif mode == "out": # out of a interrupt (IRET)
            self.ALU.zero = self.zf_save
            self.IF = self.if_save
            
            self.ALU.carry = self.cf_save
            
            # Pop PC
            self.PC = self.pop16()
            
            # Pop from special stack
            self.Registers.registers = self.reg_save_stack.pop().copy()
        
        
    def resolve_16gpr(self, n):
        """Returns a string to pass to add_regs or write_16regs from a integer"""
        match n:
            case 0:
                return "A"
            
            case 1:
                return "B"  
            
            case 2:
                return "C"
            
            case 3:
                return "D"  
            
            case _:
                raise regs.InvalidRegister
        
    def push8(self, value):
        self.SP -= 1
        self.SP &= 0xFFFF
        self.Memory.write_byte(value=value, address=self.SP)
            
    def push16(self, value):
        self.SP -= 2
        self.SP &= 0xFFFF
        self.Memory.write_word(value=value, address=self.SP)      
        
    def pop8(self):
        value = self.Memory.read_byte(self.SP)
        self.SP += 1
        self.SP &= 0xFFFF
        return value 
    
    def pop16(self):
        value = self.Memory.read_word(self.SP)
        self.SP += 2
        self.SP &= 0xFFFF
        return value 
        
    def step(self):
        try:
            self.ex()  
            
        except Exception as e:
            self.faults_before_reset += 1
            irq = self.edt.get(type(e), self.edt["unknown"])
            self.interrupt(irq, True) 
        
    def ex(self):
        """
        prefix 00: regular opcode, has 6 bytes:
         offset byte
         0        prefix
         1        opcode
         2        8-bit operand
         3        16-bit operand
         5        second 8-bit operand
         
        prefix 01: small opcode, has 3 bytes:
         offset byte
         0        prefix
         1        opcode
         2        8-bit immediate
        """
        
        if self.pending_irq:
            self.interrupt(self.pending_irq)
            self.pending_irq = 0
        
        # FIX: Check for a active interrupt 50 times with a 100ms sleep inbetween to free up the GIL but still detect interrupts.
        if self.halted:
            for i in range(50):
              if self.pending_irq:
                  self.interrupt(self.pending_irq)
                  self.pending_irq = 0
                  video.time.sleep(0.1)
            return
        
        # Decode the instruction
        prefix = self.Memory.memory[self.PC]
        opcode = 0
        op8_1  = 0
        op16   = 0
        op8_2  = 0
    
        match prefix:
            case 0: # Regular opcode
                opcode = self.Memory.memory[self.PC+1]
                op8_1  = self.Memory.memory[self.PC+2]
                op16   = self.Memory.memory[self.PC+3] | (self.Memory.memory[self.PC+4] << 8) & 0xFFFF
                op8_2  = self.Memory.memory[self.PC+5]
                
                self.PC += 6
                
            case 1: # Small opcode
                opcode = self.Memory.memory[self.PC+1]
                op8_1  = self.Memory.memory[self.PC+2]
                
                self.PC += 3
                
            case _:
                raise self.InvalidOpcode
            
        # Execute the instruction
        # Branch instruction opcodes based on the prefix
        
        self.instructions_executed += 1
        
        if prefix == 0: # Regular opcode
            if opcode == self.Opcodes.LOAD_REG:
                self.Registers.write_8bitgpr(reg=op8_1, value=op8_2)
                
            elif opcode == self.Opcodes.WRITE_MEM8:
                if op8_2 == 0: # immediate
                    self.Memory.write_byte(address=op16, value=op8_1)
                    
                elif op8_2 == 1: # register
                    self.Memory.write_byte(address=op16, value=self.Registers.read_8bitgpr(op8_1))
                    
                else:
                    raise self.InvalidOpcode
                    
                
                    
            elif opcode == self.Opcodes.WRITE_MEM8A:
                self.Memory.write_byte(address=self.Registers.read_16bitgpr(self.resolve_16gpr(op8_1)), value=self.Registers.read_8bitgpr(op8_2))
                
            elif opcode == self.Opcodes.WRITE_MEM16:
                self.Memory.write_word(address=self.Registers.read_16bitgpr(self.resolve_16gpr(op8_1)), value=self.Registers.read_16bitgpr(self.resolve_16gpr(op8_2)))
                

                
            elif opcode == self.Opcodes.SUB8:
                self.ALU.sub_regs(regA=op8_2, regB=op8_1) # op8_2 is dest
                
            elif opcode == self.Opcodes.SUB16:
                self.ALU.sub_regs(regA=self.resolve_16gpr(op8_2), regB=self.resolve_16gpr(op8_1))
      
            elif opcode == self.Opcodes.ADD8:
                self.ALU.add_regs(regA=op8_2, regB=op8_1) # op8_2 is dest
                
            elif opcode == self.Opcodes.ADD16:
                self.ALU.add_regs(regA=self.resolve_16gpr(op8_2), regB=self.resolve_16gpr(op8_1)) 
                
            elif opcode == self.Opcodes.JZ:
                self.PC = op16 if self.ALU.zero else self.PC
                
            elif opcode == self.Opcodes.JNZ:
                self.PC = op16 if not self.ALU.zero else self.PC   
            
            elif opcode == self.Opcodes.JMP:
                self.PC = op16 
                
            elif opcode == self.Opcodes.LOAD_REG16:
                self.Registers.write_16bitgpr(reg=self.resolve_16gpr(op8_1), value=op16)
                
            elif opcode == self.Opcodes.PORT_IN:   
                # op16 = mode (0 = op8_2 is a register, 1 = op8_2 is a port)
                if op16 == 0:
                    self.Registers.write_8bitgpr(reg=op8_1, value=self.PMIO.read_port(self.Registers.read_8bitgpr(op8_2)))
                    
                elif op16 == 1:
                    self.Registers.write_8bitgpr(reg=op8_1, value=self.PMIO.read_port(op8_2))
                    
                else:
                    raise self.InvalidOpcode
                
            elif opcode == self.Opcodes.PORT_OUT:
                if op16 == 0:
                    self.PMIO.write_port(value=self.Registers.read_8bitgpr(op8_1), port=self.Registers.read_8bitgpr(op8_2))
                    
                elif op16 == 1:
                    self.PMIO.write_port(value=self.Registers.read_8bitgpr(op8_1), port=op8_2)
                    
                else:
                    raise self.InvalidOpcode
                
            elif opcode == self.Opcodes.READ_MEM8A:
                self.Registers.write_8bitgpr(reg=op8_1, value=self.Memory.read_byte(self.Registers.read_16bitgpr(self.resolve_16gpr(op8_2))))
                
            elif opcode == self.Opcodes.READ_MEM8:
                self.Registers.write_8bitgpr(reg=op8_1, value=self.Memory.read_byte(op16))
                
            elif opcode == self.Opcodes.READ_MEM16:
                self.Registers.write_16bitgpr(reg=self.resolve_16gpr(op8_1), value=self.Memory.read_word(self.Registers.read_16bitgpr(self.resolve_16gpr(op8_2))))
                
            elif opcode == self.Opcodes.ADD_IMM:
                if op8_1 == 0:
                    raw = ((self.Registers.read_8bitgpr(op8_2) + op16))
                    self.ALU.cf_positive(raw, 0xFF)
                    result = raw & 0xFF
                    self.ALU.z(result)
                    self.Registers.write_8bitgpr(reg=op8_2, value=result)
                    
                elif op8_1 == 1:
                    raw = ((self.Registers.read_16bitgpr(self.resolve_16gpr(op8_2)) + op16))
                    self.ALU.cf_positive(raw, 0xFFFF)
                    result = raw & 0xFFFF
                    self.ALU.z(result)
                    
                    self.Registers.write_16bitgpr(reg=self.resolve_16gpr(op8_2), value=result)
                    
                else:
                    raise self.InvalidOpcode
                          
            elif opcode == self.Opcodes.XOR:
                if op16 == 0:
                    result = (self.Registers.read_8bitgpr(op8_2) ^ self.Registers.read_8bitgpr(op8_1))
                    self.ALU.z(result)
                    self.Registers.write_8bitgpr(reg=op8_2, value=result)
                    
                elif op16 == 1:
                    result = (self.Registers.read_16bitgpr(self.resolve_16gpr(op8_2)) ^ self.Registers.read_16bitgpr(self.resolve_16gpr(op8_1)))
                    self.ALU.z(result)
                    self.Registers.write_16bitgpr(reg=self.resolve_16gpr(op8_2), value=result)
                    
                else:
                    raise self.InvalidOpcode    
                    
            elif opcode == self.Opcodes.OR:
                if op16 == 0:
                    result = (self.Registers.read_8bitgpr(op8_2) | self.Registers.read_8bitgpr(op8_1))
                    self.ALU.z(result)
                    self.Registers.write_8bitgpr(reg=op8_2, value=result)
                    
                elif op16 == 1:
                    result = (self.Registers.read_16bitgpr(self.resolve_16gpr(op8_2)) | self.Registers.read_16bitgpr(self.resolve_16gpr(op8_1)))
                    self.ALU.z(result)
                    self.Registers.write_16bitgpr(reg=self.resolve_16gpr(op8_2), value=result)
                    
                else:
                    raise self.InvalidOpcode      
                    
            elif opcode == self.Opcodes.AND:
                if op16 == 0:
                    result = (self.Registers.read_8bitgpr(op8_2) & self.Registers.read_8bitgpr(op8_1))
                    self.ALU.z(result)
                    self.Registers.write_8bitgpr(reg=op8_2, value=result)
                    
                elif op16 == 1:
                    result = (self.Registers.read_16bitgpr(self.resolve_16gpr(op8_2)) & self.Registers.read_16bitgpr(self.resolve_16gpr(op8_1)))
                    self.ALU.z(result)
                    self.Registers.write_16bitgpr(reg=self.resolve_16gpr(op8_2), value=result)
                    
                else:
                    raise self.InvalidOpcode      
                
            elif opcode == self.Opcodes.AND_TEST:
                if op16 == 0:
                    result = (self.Registers.read_8bitgpr(op8_2) & self.Registers.read_8bitgpr(op8_1))
                    self.ALU.z(result)
                    
                elif op16 == 1:
                    result = (self.Registers.read_16bitgpr(self.resolve_16gpr(op8_2)) & self.Registers.read_16bitgpr(self.resolve_16gpr(op8_1)))
                    self.ALU.z(result)
                    
                else:
                    raise self.InvalidOpcode  
                
            elif opcode == self.Opcodes.PUSH:
                if op8_2 == 0:
                    self.push8(self.Registers.read_8bitgpr(op8_1))
                    
                elif op8_2 == 1:
                    self.push16(self.Registers.read_16bitgpr(self.resolve_16gpr(op8_1)))
                    
                else:
                    raise self.InvalidOpcode
                
            elif opcode == self.Opcodes.POP:
                if op8_2 == 0:
                    self.Registers.write_8bitgpr(reg=op8_1, value=self.pop8())
                    
                elif op8_2 == 1:
                    self.Registers.write_16bitgpr(reg=self.resolve_16gpr(op8_1), value=self.pop16())
                    
                else:
                    raise self.InvalidOpcode
                
            elif opcode == self.Opcodes.CALL:
                self.push16(self.PC)
                self.PC = op16
                
            elif opcode == self.Opcodes.MOVE_SP:
                self.SP = op16
                                         
            elif opcode == self.Opcodes.ADD_UNM:
                if op16 == 0:
                    self.ALU.add_unmatched_widths8(dest8bitgpr=op8_2, src16bitgpr=self.resolve_16gpr(op8_1))
                    
                elif op16 == 1:
                    self.ALU.add_unmatched_widths16(dest16bitgpr=self.resolve_16gpr(op8_1), src8bitgpr=op8_2)
                    
                else:
                    raise self.InvalidOpcode
                    
            elif opcode == self.Opcodes.SUB_UNM:
                if op16 == 0:
                    self.ALU.sub_unmatched_widths8(dest8bitgpr=op8_2, src16bitgpr=self.resolve_16gpr(op8_1))
                    
                elif op16 == 1:
                    self.ALU.sub_unmatched_widths16(dest16bitgpr=self.resolve_16gpr(op8_1), src8bitgpr=op8_2)
                    
                else:
                    raise self.InvalidOpcode
                    
            elif opcode == self.Opcodes.MUL_UNM:
                if op16 == 0:
                    self.ALU.mul_unmatched_widths8(dest8bitgpr=op8_2, src16bitgpr=self.resolve_16gpr(op8_1))
                    
                elif op16 == 1:
                    self.ALU.mul_unmatched_widths16(dest16bitgpr=self.resolve_16gpr(op8_1), src8bitgpr=op8_2)
                    
                else:
                    raise self.InvalidOpcode
                    
            elif opcode == self.Opcodes.DIV_UNM:
                if op16 == 0:
                    self.ALU.div_unmatched_widths8(dest8bitgpr=op8_2, src16bitgpr=self.resolve_16gpr(op8_1))
                    
                elif op16 == 1:
                    self.ALU.div_unmatched_widths16(dest16bitgpr=self.resolve_16gpr(op8_1), src8bitgpr=op8_2)
                    
                else:
                    raise self.InvalidOpcode
                    
            elif opcode == self.Opcodes.MUL:
                self.ALU.mul_regs(regA=op8_2, regB=op8_1)
                
            elif opcode == self.Opcodes.DIV:
                self.ALU.div_regs(regA=op8_2, regB=op8_1)
                
            elif opcode == self.Opcodes.MUL16:
                self.ALU.mul_regs(regA=self.resolve_16gpr(op8_2), regB=self.resolve_16gpr(op8_1))
                
            elif opcode == self.Opcodes.DIV16:
                self.ALU.div_regs(regA=self.resolve_16gpr(op8_2), regB=self.resolve_16gpr(op8_1))
                
            elif opcode == self.Opcodes.MOVE:
                # Just ignore the attempt to write a 16-bit value to a 8-bit register here, write_8bitgpr() does masking anyway.
                
                if op16 == 0:
                    self.Registers.write_8bitgpr(reg=op8_2, value=self.Registers.read_8bitgpr(op8_1))
                    
                elif op16 == 1:
                    self.Registers.write_16bitgpr(reg=self.resolve_16gpr(op8_2), value=self.Registers.read_16bitgpr(self.resolve_16gpr(op8_1)))
                    
                elif op16 == 2:
                    self.Registers.write_16bitgpr(reg=self.resolve_16gpr(op8_2), value=self.Registers.read_8bitgpr(op8_1))
                    
                elif op16 == 3:
                    self.Registers.write_8bitgpr(reg=op8_2, value=self.Registers.read_16bitgpr(self.resolve_16gpr(op8_1)))
                    
                else:
                    raise self.InvalidOpcode
        
            elif opcode == self.Opcodes.COMPARE_Z:
                if op16 == 0:
                    arg1 = self.Registers.read_8bitgpr(op8_1)
                    arg2 = self.Registers.read_8bitgpr(op8_2)
                    
                    self.ALU.z((arg1 - arg2) & 0xFF)
                    self.ALU.cf_negative(arg1 - arg2)
                    
                elif op16 == 1:
                    arg1 = self.Registers.read_16bitgpr(self.resolve_16gpr(op8_1))
                    arg2 = self.Registers.read_16bitgpr(self.resolve_16gpr(op8_2))
                    
                    self.ALU.z((arg1 - arg2) & 0xFFFF)   
                    self.ALU.cf_negative(arg1 - arg2)   
                    
                elif op16 == 2:
                    arg1 = self.Registers.read_16bitgpr(self.resolve_16gpr(op8_1))
                    arg2 = self.Registers.read_8bitgpr(op8_2)
                    
                    self.ALU.z((arg1 - arg2) & 0xFFFF)  
                    self.ALU.cf_negative(arg1 - arg2)  
                
                else:
                    raise self.InvalidOpcode
                    
            elif opcode == self.Opcodes.SHR:
                if op8_2 == 0:
                    self.Registers.write_8bitgpr(reg=op8_1, value=(self.Registers.read_8bitgpr(op8_1) >> 1))
                    
                elif op8_2 == 1:
                    self.Registers.write_16bitgpr(reg=self.resolve_16gpr(op8_1), value=(self.Registers.read_16bitgpr(self.resolve_16gpr(op8_1)) >> 1))
                    
                else:
                    raise self.InvalidOpcode
                
            elif opcode == self.Opcodes.SHL:
                if op8_2 == 0:
                    self.Registers.write_8bitgpr(reg=op8_1, value=(self.Registers.read_8bitgpr(op8_1) << 1) & 0xFF)
                    
                elif op8_2 == 1:
                    self.Registers.write_16bitgpr(reg=self.resolve_16gpr(op8_1), value=(self.Registers.read_16bitgpr(self.resolve_16gpr(op8_1)) << 1) & 0xFFFF)
                    
                else:
                    raise self.InvalidOpcode    
        
            elif opcode == self.Opcodes.CMPZ_IMM:
                # op8_1 = reg, op16 = compare, op8_2 = regtype (0 = 8 bit, 1 = 16 bit)
                if op8_2 == 0:
                    raw = (self.Registers.read_8bitgpr(op8_1) - op16) 
                    self.ALU.cf_negative(raw)
                    result = raw & 0xFF
                    self.ALU.z(result)
        
                elif op8_2 == 1:
                    raw = (self.Registers.read_16bitgpr(self.resolve_16gpr(op8_1)) - op16)
                    self.ALU.cf_negative(raw)
                    result = raw & 0xFFFF
                    self.ALU.z(result)
                    
                else:
                    raise self.InvalidOpcode
                
            elif opcode == self.Opcodes.SUB_IMM:
                if op8_1 == 0:
                    raw = ((self.Registers.read_8bitgpr(op8_2) - op16))
                    self.ALU.cf_negative(raw)
                    result = raw & 0xFF
                    self.ALU.z(result)
                    self.Registers.write_8bitgpr(reg=op8_2, value=result)
                    
                elif op8_1 == 1:
                    raw = ((self.Registers.read_16bitgpr(self.resolve_16gpr(op8_2)) - op16))
                    self.ALU.cf_negative(raw)
                    result = raw & 0xFFFF
                    self.ALU.z(result)
                    
                    self.Registers.write_16bitgpr(reg=self.resolve_16gpr(op8_2), value=result)
                    
                else:
                    raise self.InvalidOpcode
                
            elif opcode == self.Opcodes.JUMP_CARRY:
                if self.ALU.carry:
                    self.PC = op16 
                    
            elif opcode == self.Opcodes.JUMP_NOT_CARRY:
                if not self.ALU.carry:
                    self.PC = op16
        
            else:
                raise self.InvalidOpcode     
      
      
      
      
      
        elif prefix == 1: # Small opcode
            if opcode == self.Opcodes.HALT:
                self.halted = True
            
            elif opcode == self.Opcodes.JMP_REG:
                self.PC = self.Registers.read_16bitgpr(self.resolve_16gpr(op8_1))
                
            elif opcode == self.Opcodes.RET:
                self.PC = self.pop16()
                
            elif opcode == self.Opcodes.IRET:
                self.out_interrupt()
                
            elif opcode == self.Opcodes.INT:
                self.interrupt(op8_1, True)   
                
            elif opcode == self.Opcodes.INTERRUPT_C:
                if op8_1 not in [0, 1]:
                    raise self.InvalidOpcode
              
                self.IF = op8_1 
                
            elif opcode == self.Opcodes.PUSH_ALL:
                # push every register in order r0, r1, r2, r3, a, b, c, d
                
                # Push 8-bit regs
                for i in range(4):
                    self.push8(value=self.Registers.read_8bitgpr(i)) # 0, 1, 2, 3
                  
                # Push 16-bit regs
                for i in range(4):
                    self.push16(value=self.Registers.read_16bitgpr(self.resolve_16gpr(i)))# 0, 1, 2, 3
                    
            elif opcode == self.Opcodes.POP_ALL:
                # pop in reverse order of push_all
                
                # Pop 16-bit regs
                for i in range(3, -1, -1):
                    self.Registers.write_16bitgpr(reg=self.resolve_16gpr(i), value=self.pop16())
                    
                # Pop 8-bit regs
                for i in range(3, -1, -1):
                    self.Registers.write_8bitgpr(reg=i, value=self.pop8())
                  
            else:    
                raise self.InvalidOpcode # DONETHIS: add more opcodes so we can remove the return from HALT and use elif
                
        
                
                


