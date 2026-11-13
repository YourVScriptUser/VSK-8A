# PMIO system for vsk-8a

class PMIO:
    def __init__(self):
        self.pmio = bytearray(64) 
        
    def write_port(self, port, value):
        value &= 0xFF
        
        self.pmio[port] = value 
        
    def read_port(self, port):
        return self.pmio[port]