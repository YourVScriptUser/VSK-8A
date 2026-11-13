# VSK-8A Memory components
# Supports 16-64KB of RAM

class InvalidMemoryAccess(Exception): pass

class RAM:
    def __init__(self, size):
        self.max_address   = size - 1 # FIX: due to 0-index, minus the max address by 1
        self.memory = bytearray(size)
        
    def clear(self):
        self.memory.clear() 
        
    def bound(self, address):
        if address > self.max_address or address < 0:   
            raise InvalidMemoryAccess
        
    def read_byte(self, address):
        self.bound(address)
        
        return self.memory[address]
    
    def write_byte(self, address, value):
        self.bound(address)
        
        value &= 0xFF
        self.memory[address] = value
        
    def read_word(self, address):
        self.bound(address + 1) # +1 because a word takes up 2 memory addresses
        
        return self.memory[address] | self.memory[address + 1] << 8
    
    def write_word(self, address, value):
        self.bound(address + 1) 
        
        self.memory[address] = value & 0xFF
        self.memory[address + 1] = (value >> 8) & 0xFF