class UnmatchingWidths(Exception): pass

class ALU:
    def __init__(self, regs):
      self.registers = regs
      self.zero      = 0
      self.carry     = 0
      
    def cf_positive(self, a, m):
        """Give this the raw result, masking it then giving it to this wont work."""
        self.carry = int(a > m)
      
    def cf_negative(self, a):
        """Give this the raw result, masking it then giving it to this wont work."""
        self.carry = int(a < 0) 
      
    def z(self, r):
        """Updates the zero flag according to r (zf = r == 0)"""
        self.zero = int(r == 0)
        
    def div_unmatched_widths8(self, dest8bitgpr, src16bitgpr):
        # Auto-handles 16 bit registers
        
        # This ALU function lets you do math on 2 registers that are not matchning bit widths
        result = (self.registers.read_8bitgpr(dest8bitgpr) // self.registers.read_16bitgpr(src16bitgpr)) & 0xFF
        self.z(result)
        
        self.registers.write_8bitgpr(reg=dest8bitgpr, value=result)
        
    def div_unmatched_widths16(self, dest16bitgpr, src8bitgpr):
        # Auto-handles 16 bit registers
        
        # This ALU function lets you do math on 2 registers that are not matchning bit widths
        result = (self.registers.read_16bitgpr(dest16bitgpr) // self.registers.read_8bitgpr(src8bitgpr)) & 0xFFFF
        self.z(result)
        
        self.registers.write_16bitgpr(reg=dest16bitgpr, value=result)         
        
    def mul_unmatched_widths8(self, dest8bitgpr, src16bitgpr):
        # Auto-handles 16 bit registers
        
        # This ALU function lets you do math on 2 registers that are not matchning bit widths
        raw = (self.registers.read_8bitgpr(dest8bitgpr) * self.registers.read_16bitgpr(src16bitgpr))
        self.cf_positive(raw, 0xFF)
        result = raw & 0xFF
        self.z(result)
        
        self.registers.write_8bitgpr(reg=dest8bitgpr, value=result)
        
    def mul_unmatched_widths16(self, dest16bitgpr, src8bitgpr):
        # Auto-handles 16 bit registers
        
        # This ALU function lets you do math on 2 registers that are not matchning bit widths
        raw = (self.registers.read_16bitgpr(dest16bitgpr) * self.registers.read_8bitgpr(src8bitgpr)) 
        self.cf_positive(raw, 0xFFFF)
        result = raw & 0xFFFF
        self.z(result)
        
        self.registers.write_16bitgpr(reg=dest16bitgpr, value=result)            
        
    def sub_unmatched_widths8(self, dest8bitgpr, src16bitgpr):
        # Auto-handles 16 bit registers
        
        # This ALU function lets you do math on 2 registers that are not matchning bit widths
        raw = (self.registers.read_8bitgpr(dest8bitgpr) - self.registers.read_16bitgpr(src16bitgpr)) 
        self.cf_negative(raw)
        result = raw & 0xFF
        self.z(result)
        
        self.registers.write_8bitgpr(reg=dest8bitgpr, value=result)
        
    def sub_unmatched_widths16(self, dest16bitgpr, src8bitgpr):
        # Auto-handles 16 bit registers
        
        # This ALU function lets you do math on 2 registers that are not matchning bit widths
        raw = (self.registers.read_16bitgpr(dest16bitgpr) - self.registers.read_8bitgpr(src8bitgpr))
        self.cf_negative(raw)
        result = raw & 0xFFFF
        self.z(result)
        
        self.registers.write_16bitgpr(reg=dest16bitgpr, value=result)    
    
    def add_unmatched_widths8(self, dest8bitgpr, src16bitgpr):
        # Auto-handles 16 bit registers
        
        # This ALU function lets you do math on 2 registers that are not matchning bit widths
        raw = (self.registers.read_8bitgpr(dest8bitgpr) + self.registers.read_16bitgpr(src16bitgpr)) 
        self.cf_positive(raw, 0xFF)
        result = raw & 0xFF
        self.z(result)
        
        self.registers.write_8bitgpr(reg=dest8bitgpr, value=result)
        
    def add_unmatched_widths16(self, dest16bitgpr, src8bitgpr):
        # Auto-handles 16 bit registers
        
        # This ALU function lets you do math on 2 registers that are not matchning bit widths
        raw = (self.registers.read_16bitgpr(dest16bitgpr) + self.registers.read_8bitgpr(src8bitgpr))
        self.cf_positive(raw, 0xFFFF)
        result = raw & 0xFFFF
        self.z(result)
        
        self.registers.write_16bitgpr(reg=dest16bitgpr, value=result)
      
    def div_regs(self, regA, regB):
        # Auto-handles 16 bit registers
        
        # Check types, so if it tries to do math on an 8-bit reg to a 16-bit one, it wont work.
        if type(regA) is not type(regB):
            raise UnmatchingWidths 
        
        else:
            if isinstance(regA, str):
                result = (self.registers.read_16bitgpr(regA) // self.registers.read_16bitgpr(regB)) & 0xFFFF
                self.z(result)
                
                self.registers.write_16bitgpr(reg=regA, value=result)
                
            elif isinstance(regA, int):
                result = (self.registers.read_8bitgpr(regA) // self.registers.read_8bitgpr(regB)) & 0xFF
                self.z(result)
                
                self.registers.write_8bitgpr(reg=regA, value=result)           
      
    def mul_regs(self, regA, regB):
        # Auto-handles 16 bit registers
        
        # Check types, so if it tries to do math on an 8-bit reg to a 16-bit one, it wont work.
        if type(regA) is not type(regB):
            raise UnmatchingWidths 
        
        else:
            if isinstance(regA, str):
                raw = (self.registers.read_16bitgpr(regA) * self.registers.read_16bitgpr(regB)) 
                self.cf_positive(raw, 0xFFFF)
                result = raw & 0xFFFF
                self.z(result)
                
                self.registers.write_16bitgpr(reg=regA, value=result)
                
            elif isinstance(regA, int):
                raw = (self.registers.read_8bitgpr(regA) * self.registers.read_8bitgpr(regB))
                self.cf_positive(raw, 0xFF)
                result = raw & 0xFF
                self.z(result)
                
                self.registers.write_8bitgpr(reg=regA, value=result)      
      
    def add_regs(self, regA, regB):
        # Auto-handles 16 bit registers
        
        # Check types, so if it tries to do math on an 8-bit reg to a 16-bit one, it wont work.
        if type(regA) is not type(regB):
            raise UnmatchingWidths 
        
        else:
            if isinstance(regA, str):
                raw = (self.registers.read_16bitgpr(regA) + self.registers.read_16bitgpr(regB)) 
                self.cf_positive(raw, 0xFFFF)
                result = raw & 0xFFFF
                self.z(result)
                
                self.registers.write_16bitgpr(reg=regA, value=result)
                
            elif isinstance(regA, int):
                raw = (self.registers.read_8bitgpr(regA) + self.registers.read_8bitgpr(regB))
                self.cf_positive(raw, 0xFF)
                result = raw & 0xFF
                self.z(result)
                
                self.registers.write_8bitgpr(reg=regA, value=result)
                
    def sub_regs(self, regA, regB):
        # Auto-handles 16 bit registers
        
        # Check types, so if it tries to do math on  a 8-bit reg to a 16-bit one, it wont work.
        if type(regA) is not type(regB):
            raise UnmatchingWidths 
        
        else:
            if isinstance(regA, str):
                raw = (self.registers.read_16bitgpr(regA) - self.registers.read_16bitgpr(regB))
                self.cf_negative(raw)
                result = raw & 0xFFFF
                self.z(result)
                
                self.registers.write_16bitgpr(reg=regA, value=result)
                
            elif isinstance(regA, int):
                raw = (self.registers.read_8bitgpr(regA) - self.registers.read_8bitgpr(regB))
                self.cf_negative(raw)
                result = raw & 0xFF
                self.z(result)
                
                self.registers.write_8bitgpr(reg=regA, value=result)
        
        