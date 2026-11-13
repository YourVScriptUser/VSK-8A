import os, core 

class Disk:
    def __init__(self, computer: core.vsk8a, path):
        self.computer = computer 
        self.path     = path
        self.handle   = None
        
        if os.path.exists(self.path):
            sectors = self.sectors()
            if sectors is None:
                return
            
            self.handle = open(self.path, "r+b")
            self.computer.PMIO.write_port(0xB, sectors & 0xFF)
            self.computer.PMIO.write_port(0xC, (sectors >> 8) & 0xFF)
            
            self.computer.PMIO.write_port(0xA, value=0)
            
        else:
            self.computer.PMIO.write_port(port=0xA, value=1)
        
    def error(self):
        self.computer.PMIO.write_port(port=0xA, value=2)    
        
    def read(self, sector):
        self.handle.seek(sector * 512)
        data = self.handle.read(512)
        if len(data) != 512:
            self.error()
            return None
        
        return data

        
    def sectors(self):
        size = os.path.getsize(self.path)
        
        if size % 512 != 0:
            self.error()
            return None
        
        return size // 512
      
    def write(self, sector, data):
        if len(data) != 512:
            self.error()
            return False
    
        self.handle.seek(sector * 512)
        written = self.handle.write(data)
    
        if written != 512:
            self.error()
            return False
    
        self.handle.flush()
        return True  
        
    def check_status(self):
        # STUPID: Ports that indicate disk errors are only set upon instance.... that is horrible design... this function is to fix it.
        
        # Check that the path exists and that self.handle is not none to ensure it is alive
        if not self.handle:
            self.computer.PMIO.write_port(port=0xA, value=1) # write no_disk to status
            return False
        
        if not os.path.exists(self.path):
            self.computer.PMIO.write_port(port=0xA, value=1) # write no_disk to status
            return False 
        
        # self.sectors() checks if the byte count fits into 512 sectors
        # self.sectors() also writes disk_error to status port upon error
        t = self.sectors() 
        
        # self.sectors() returns none if the byte count does NOT fit into 512 sectors
        if t is None:
            return False
        
        # If all pass, return true
        return True
        
            
        
    def tick(self):
        command = self.computer.PMIO.read_port(0x5)
        irqmode = self.computer.PMIO.read_port(0x14)
        
        sectors = self.sectors()
        self.computer.PMIO.write_port(0xB, sectors & 0xFF)
        self.computer.PMIO.write_port(0xC, (sectors >> 8) & 0xFF)
        
        if not self.check_status():
            return
        
        if command not in [1, 2]:
            return
        
        if command == 1:
            # read
            
            dma_low   = self.computer.PMIO.read_port(0x6)
            dma_high  = self.computer.PMIO.read_port(0x7)
            
            dma = dma_low | (dma_high << 8)
            
            sec_low   = self.computer.PMIO.read_port(0x8)
            sec_high  = self.computer.PMIO.read_port(0x9)
            
            sector = sec_low | (sec_high << 8)
            
            self.computer.Memory.memory[dma:dma+512] = self.read(sector)
            
            self.computer.PMIO.write_port(0x5, 0)
            
            if irqmode:
                self.computer.pending_irq = irqmode
        
        elif command == 2:
            # write
        
            dma_low = self.computer.PMIO.read_port(0x6)
            dma_high = self.computer.PMIO.read_port(0x7)
        
            dma = dma_low | (dma_high << 8)
        
            sec_low = self.computer.PMIO.read_port(0x8)
            sec_high = self.computer.PMIO.read_port(0x9)
        
            sector = sec_low | (sec_high << 8)
        
            data = self.computer.Memory.memory[dma:dma+512]
        
            self.write(sector, data)
        
            self.computer.PMIO.write_port(0x5, 0)
            
            if irqmode:
                self.computer.pending_irq = irqmode
            
# DISK UPDATE (9/11/26):
# port             purpose
# 0x14             IRQ to raise when disk is done (disk is in polling mode if this is null)
#                                                  It is convention that IRQ 0 cannot be used for most devices.             
            
# 0x5     disk command (read/write) (1 = read, 2 = write, else NOP)
# 0x6     DMA memory address (low)   
# 0x7     DMA memory address (high)
# 0x8     linear sector (low)
# 0x9     linear sector (high)
# 0xA     status (0 = success, 1 = no disk, 2 = error)
# 0xB     amount of sectors (low)
# 0xC     amount of sectors (high)

# To wait until the disk is done, do a loop and break the loop once port 0x5 turns back to 0.
# Or use port 0x14 if you care about speed
