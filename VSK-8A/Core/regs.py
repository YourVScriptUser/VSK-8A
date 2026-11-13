# VSK-8A Registers

class InvalidRegister(Exception): pass

class Registers:
    def __init__(self):
        # How it works:
        # 12 General purpose 8-bit registers (r0, r1, r2, r3, r4, r5, r6, r7, r8, r9, r10, r11 + A, B, C, D)
        # Registers A and B are:
        #  A: combination of r4+r5   (little-endian)
        #  B: combination of r6+r7   (little-endian)
        #  C: combination of r8+r9   (little-endian)
        #  D: combination of r10+r11 (little-endian)
        
        self.registers = bytearray(12)
        
    def bound(self, reg):
        if reg < 0 or reg > 11:
            raise InvalidRegister    
        
    def write_8bitgpr(self, reg, value):
        self.bound(reg)
        value &= 0xFF
        
        self.registers[reg] = value
        
    def read_8bitgpr(self, reg):
        self.bound(reg)
        return self.registers[reg]
    
    def write_16bitgpr(self, reg, value):
        # reg is a string, "A" or "B" or "C" or "D"
        
        match reg:
            case "A":
                self.registers[4] = value & 0xFF
                self.registers[5] = (value >> 8) & 0xFF
                
            case "B":
                self.registers[6] = value & 0xFF
                self.registers[7] = (value >> 8) & 0xFF
                
            case "C":
                self.registers[8] = value & 0xFF
                self.registers[9] = (value >> 8) & 0xFF
                
            case "D":
                self.registers[10] = value & 0xFF
                self.registers[11] = (value >> 8) & 0xFF
                
            case _:
                raise InvalidRegister
                
    def read_16bitgpr(self, reg):
        # reg is also a string here ("A" or "B")
        
        match reg:
            case "A":
                return self.registers[4] | self.registers[5] << 8
            
            case "B":
                return self.registers[6] | self.registers[7] << 8
            
            case "C":
                return self.registers[8] | self.registers[9] << 8
            
            case "D":
                return self.registers[10] | self.registers[11] << 8
            
            case _:
                raise InvalidRegister