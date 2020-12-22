import sys
import os
import threading
import bitstring
from bitstring import BitArray
import queue
import time
from datetime import date
import binascii
import abi

# help function
def show_help():
    print("spvm: Spectre-xC arch emulator, written in Python 3.8")
    print("-\tto show this help menu, run spvm with '-h'.")
    print("-\tto run the emulator: 'spvm'")
    print()
    sys.exit(0)

spgl_crext = {
    'halt' : 0,
    'run_once' : 0,
    'old_exit' : [1,0]
}

class CPU:
    def __init__(self, mem_ref, mem_lock):
        # general-purpose registers
        self.gp_registers = {
            0   : BitArray(length=64), # $nil    [zero register, always equal to zero]
            1   : BitArray(length=64), # $t0     [temp 0 register]
            2   : BitArray(length=64), # $t1     [temp 1 register]
            3   : BitArray(length=64), # $mp     [memory pointer register]
            4   : BitArray(length=64), # $a0     [arg 0 register]
            5   : BitArray(length=64), # $a1     [arg 1 register]
            6   : BitArray(length=64), # $a2     [arg 2 register]
            7   : BitArray(length=64), # $s0     [saved 0 register]
            8   : BitArray(length=64), # $s1     [saved 1 register]
            9   : BitArray(length=64), # $vc     [value return register]
            10  : BitArray(length=64), # $sp     [stack pointer register]
            11  : BitArray(length=64)  # $ra     [return address register]
        }
        # reserved registers
        self.rs_registers = {
            'rf': BitArray(length=64), # rflags register (represents bool values to store operation results and processor state)
            # 0 - (CF) carry flag // sets if the last arithmetic operation carried (addition) or borrowed (subtraction) a bit beyond the size of register
            # 1 - (PF) parity flag // sets if the number of set bits in the least significant byte is a multiple of 2
            # 2 - (ZF) zero flag // sets if the result of an operation is zero (0)
            # 3 - (SF) sign flag // sets if the result of an operation is negative
            # 4 - (IF) interrupt flag // sets if interrupts are enabled
            # 5 - (OF) overflow flag // sets if signed arithmetic operations result in a value too large for the register to contain
            # 6-7 - (IOPL) I/O privilege level field // determines I/O privilege level of current process
            # 8-63 - << RESERVED >>
            'ip': BitArray(length=64), # instruction pointer register
            'ir': BitArray(length=64), # current instruction register
            'halt': 0 # halt bit, when set causes the CPU to only execute 'NOP' instructions until unset
        }
# 'nop'   : 0,
# 'mov'   : 1,
# 'add'   : 2,
# 'sub'   : 3,
# 'beq'   : 4,
# 'bne'   : 5,
# 'blt'   : 6,
# 'bgt'   : 7,
# 'jmp'   : 8,
# 'jal'   : 9,
# 'jr'    : 10,
# 'load'  : 11,
# 'stor'  : 12,
# 'sysc'  : 13,
# # alternate imms
# 'movi'  : 14,
# 'addi'  : 15,
# 'subi'  : 16,
# 'loadi' : 17,
# 'stori' : 18
# -----> function handlers for inst opcodes
        self.__inst_arch = {
            0  : self.__inst_nop,
            1  : self.__inst_mov,
            2  : self.__inst_add,
            3  : self.__inst_sub,
            4  : self.__inst_beq,
            5  : self.__inst_bne,
            6  : self.__inst_blt,
            7  : self.__inst_bgt,
            8  : self.__inst_jmp,
            9  : self.__inst_jal,
            10 : self.__inst_jr,
            11 : self.__inst_load,
            12 : self.__inst_stor,
            13 : self.__inst_sysc,
            14 : self.__inst_movi,
            15 : self.__inst_addi,
            16 : self.__inst_subi,
            17 : self.__inst_loadi,
            18 : self.__inst_stori
        }
        # store reference to memory and bus (to acquire lock)
        self.__mem : RAM = mem_ref
        self.__memlock : threading.Lock = mem_lock
        self.__rvec = 0x0 # reset vector: the first place the cpu will attempt to execute instructions from
        self.rs_registers['ip'].uint = self.__rvec
        # set stack pointer to top of memory
        # self.gp_registers[10].uint = self.__mem.size_bytes

    def set_rvec(self, rvec):
        if rvec not in range(0, self.__mem.size_bytes):
            print('! cpu: invalid reset vector {}'.format( hex(rvec) ))
            return -1
        self.__rvec = rvec
        return 0
    # resets the instruction pointer to the reset vector only
    def soft_reset(self):
        self.rs_registers['ip'].uint = self.__rvec
        return

    # THE HOLY NOP
    def __inst_nop(self):
        global spgl_crext
        if spgl_crext['old_exit'][0]:
            spgl_crext['old_exit'][1] += 1
        return
    # arithmetic
    def __inst_mov(self):
        _src : int = self.rs_registers['ir'][6:12].uint
        _dst : int = self.rs_registers['ir'][12:18].uint
        self.gp_registers[_dst].int = self.gp_registers[_src].int
        return
    def __inst_add(self):
        _src : int = self.rs_registers['ir'][6:12].uint
        _dst : int = self.rs_registers['ir'][12:18].uint
        _ovf = (self.gp_registers[_src][0],self.gp_registers[_dst][0])
        self.gp_registers[_dst].int += self.gp_registers[_src].int
        # if MSB is different from the other two, if they were equal, then an overflow has occurred
        # add: (-) plus (-) == (+) plus (+) == unsafe
        #      (+) plus (-) == (-) plus (+) == safe
        if (_ovf[0] == _ovf[1]) and (self.gp_registers[_dst][0] != _ovf[0]):
            self.rs_registers['rf'][5] = 1
        return
    def __inst_sub(self):
        _src : int = self.rs_registers['ir'][6:12].uint
        _dst : int = self.rs_registers['ir'][12:18].uint
        _ovf = (self.gp_registers[_src][0],self.gp_registers[_dst][0])
        self.gp_registers[_dst].int -= self.gp_registers[_src].int
        # if MSB is different from the other two, if they were equal, then an overflow has occurred
        # sub: (-) minus (-) == (+) minus (+) == safe
        #      (+) minus (-) == (-) minus (+) == unsafe
        if (_ovf[0] != _ovf[1]) and (self.gp_registers[_dst][0] != _ovf[0]):
            self.rs_registers['rf'][5] = 1
        return
    def __inst_movi(self):
        _dst : int = self.rs_registers['ir'][6:12].uint
        self.gp_registers[_dst].int = self.rs_registers['ir'][12:64].int
        return
    def __inst_addi(self):
        _dst : int = self.rs_registers['ir'][6:12].uint
        _ovf = (self.gp_registers[_dst][0],self.rs_registers['ir'][12])
        self.gp_registers[_dst].int += self.rs_registers['ir'][12:64].int
        # if MSB is different from the other two, if they were equal, then an overflow has occurred
        # add: (-) plus (-) == (+) plus (+) == unsafe
        #      (+) plus (-) == (-) plus (+) == safe
        if (_ovf[0] == _ovf[1]) and (self.gp_registers[_dst][0] != _ovf[0]):
            self.rs_registers['rf'][5] = 1
        return
    def __inst_subi(self):
        _dst : int = self.rs_registers['ir'][6:12].uint
        _ovf = (self.gp_registers[_dst][0],self.rs_registers['ir'][12])
        self.gp_registers[_dst].int -= self.rs_registers['ir'][12:64].int
        # if MSB is different from the other two, if they were equal, then an overflow has occurred
        # sub: (-) minus (-) == (+) minus (+) == safe
        #      (+) minus (-) == (-) minus (+) == unsafe
        if (_ovf[0] != _ovf[1]) and (self.gp_registers[_dst][0] != _ovf[0]):
            self.rs_registers['rf'][5] = 1
        return
    # branches
    def __inst_beq(self):
        _r1 : int = self.rs_registers['ir'][6:12].uint
        _r2 : int = self.rs_registers['ir'][12:18].uint
        _addr : int = self.rs_registers['ir'][18:64].uint
        # if contents of r1 equals contents of r2, then branch to address
        if (self.gp_registers[_r1].int == self.gp_registers[_r2].int):
            self.rs_registers['ip'].uint = _addr
        return
    def __inst_bne(self):
        _r1 : int = self.rs_registers['ir'][6:12].uint
        _r2 : int = self.rs_registers['ir'][12:18].uint
        _addr : int = self.rs_registers['ir'][18:64].uint
        # if contents of r1 doesn't equal contents of r2, then branch to address
        if (self.gp_registers[_r1].int != self.gp_registers[_r2].int):
            self.rs_registers['ip'].uint = _addr
        return
    def __inst_blt(self):
        _r1 : int = self.rs_registers['ir'][6:12].uint
        _r2 : int = self.rs_registers['ir'][12:18].uint
        _addr : int = self.rs_registers['ir'][18:64].uint
        # if contents of r1 is less than contents of r2, then branch to address
        if (self.gp_registers[_r1].int < self.gp_registers[_r2].int):
            self.rs_registers['ip'].uint = _addr
        return
    def __inst_bgt(self):
        _r1 : int = self.rs_registers['ir'][6:12].uint
        _r2 : int = self.rs_registers['ir'][12:18].uint
        _addr : int = self.rs_registers['ir'][18:64].uint
        # if contents of r1 is greater than contents of r2, then branch to address
        if (self.gp_registers[_r1].int > self.gp_registers[_r2].int):
            self.rs_registers['ip'].uint = _addr
        return
    # jumps
    def __inst_jmp(self):
        # jump to address
        self.rs_registers['ip'].uint = self.rs_registers['ir'][6:64].uint
        return
    def __inst_jal(self):
        # jump to address, but save pointer to next instruction in $ra
        self.gp_registers[11].uint = self.rs_registers['ip'].uint
        self.rs_registers['ip'].uint = self.rs_registers['ir'][6:64].uint
        return
    def __inst_jr(self):
        # jump to address, pointed to by register
        _rr : int = self.rs_registers['ir'][6:12].uint
        self.rs_registers['ip'].uint = self.gp_registers[_rr].uint
        return
    # load/store memory
    def __inst_load(self):
        _rs : int = self.rs_registers['ir'][6:12].uint
        _rm : int = self.rs_registers['ir'][12:18].uint
        _ro : int = self.rs_registers['ir'][18:24].int
        # read the 4 bytes from offset of memptr into src register
        self.__memlock.acquire()
        self.gp_registers[_rs].int = self.__mem.read_qwrd(self.gp_registers[_rm].uint + self.gp_registers[_ro].int)
        self.__memlock.release()
        return
    def __inst_stor(self):
        _rs : int = self.rs_registers['ir'][6:12].uint
        _rm : int = self.rs_registers['ir'][12:18].uint
        _ro : int = self.rs_registers['ir'][18:24].uint
        # save the 4 bytes from src register to offset of memptr
        self.__memlock.acquire()
        self.__mem.write_qwrd(self.gp_registers[_rs], self.gp_registers[_rm].uint + self.gp_registers[_ro].int)
        self.__memlock.release()
        return
    def __inst_loadi(self):
        _rs : int = self.rs_registers['ir'][6:12].uint
        _rm : int = self.rs_registers['ir'][12:18].uint
        _of : int = self.rs_registers['ir'][18:64].int
        # read the 4 bytes from offset of memptr into src register
        self.__memlock.acquire()
        self.gp_registers[_rs].int = self.__mem.read_qwrd(self.gp_registers[_rm].uint + _of)
        self.__memlock.release()
        return
    def __inst_stori(self):
        _rs : int = self.rs_registers['ir'][6:12].uint
        _rm : int = self.rs_registers['ir'][12:18].uint
        _of : int = self.rs_registers['ir'][18:64].int
        # save the 4 bytes from src register to offset of memptr
        self.__memlock.acquire()
        self.__mem.write_qwrd(self.gp_registers[_rs], self.gp_registers[_rm].uint + _of)
        self.__memlock.release()
        return
    # syscall
    def __inst_sysc(self):
        return

    # handles instruction in 'ir' register
    def __handle_ir(self):
        print('#\tcpu executing {}'.format(abi.op_lookup[self.rs_registers['ir'][0:6].uint]))
        self.__inst_arch[self.rs_registers['ir'][0:6].uint]()

    # executes an instruction
    def exec(self):
        global spgl_crext

        if self.rs_registers['halt'] or spgl_crext['halt']:
            return
        else:
            self.__memlock.acquire()
            _inst = self.__mem.read_qwrd(self.rs_registers['ip'].uint)
            self.rs_registers['ip'].int += 0x40
            self.__memlock.release()
            if not isinstance(_inst, BitArray):
                # mem read error / interrupt
                print('! cpu: mem read error (interrupt), halting')
                self.rs_registers['halt'] = 1
                return
            self.rs_registers['ir'].int = _inst.int
            # TODO: execute this instruction
            # self.rs_registers['ir'][0:6] = inst opcode, which determines rest of inst bit layout
            # print('# cpu: executing instruction {}'.format(self.rs_registers['ir'][0:6].bin))
            self.__handle_ir()
            if spgl_crext['run_once'] or (spgl_crext['old_exit'][0] and spgl_crext['old_exit'][1] >= 5):
                spgl_crext['halt'] = 1
                spgl_crext['old_exit'][1] = 0
            return


spgl_memdump : BitArray = None
spgl_mdflag0 = 0
spgl_mdflock = threading.Lock()
spgl_runnext = 0

class RAM:
    def __init__(self, size):
        self.size_bytes = int(size / 8)
        self.__mem = BitArray(length=size)

    def __validate_pddr(self, pddr, offset_end):
        return ( pddr in range( 0, len(self.__mem.bin) - offset_end ) )

    def __write_mem(self, data, pddr, size=None):
        assert(size is not None)
        assert(isinstance(data, BitArray))
        if (len(data.bin) == size and self.__validate_pddr(pddr,size)):
            self.__mem.overwrite(data,pddr)
            if pddr % size != 0:
                return 1    # success, but unaligned
            else:
                return 0    # success
        else:
            return -1   # failure / interrupt

    def write_byte(self, data, pddr):   # byte
        return self.__write_mem(data, pddr, size=8)
    def write_word(self, data, pddr):   # word
        return self.__write_mem(data, pddr, size=16)
    def write_dwrd(self, data, pddr):   # dword
        return self.__write_mem(data, pddr, size=32)
    def write_qwrd(self, data, pddr):   # qword
        return self.__write_mem(data, pddr, size=64)

    def __read_mem(self, pddr, size):
        if self.__validate_pddr(pddr, size):
            return BitArray(self.__mem[pddr:pddr+size]) # success / the data piece
        else:
            return -1   # failure / interrupt

    def read_byte(self, pddr):  # byte
        return self.__read_mem(pddr, 8)
    def read_word(self, pddr):  # word
        return self.__read_mem(pddr, 16)
    def read_dwrd(self, pddr):  # dword
        return self.__read_mem(pddr, 32)
    def read_qwrd(self, pddr):  # qword
        return self.__read_mem(pddr, 64)

    # FOR DEBUG ONLY
    def debug_full_memdump(self):
        global spgl_mdflag0
        global spgl_mdflock
        global spgl_memdump

        spgl_mdflock.acquire()
        spgl_memdump = BitArray(self.__mem)
        spgl_mdflag0 = 0
        spgl_mdflock.release()
        return


# internal states of machine
class SPECTRE_VM(threading.Thread):
    # run_state:
    #   0 : stopped
    #   1 : running, will loop forever through instructions
    #   2 : will execute an instruction at a time with 'step' command
    def __init__(self, run_state=1, run_next_inst=False):
        super(SPECTRE_VM,self).__init__()
        # this must be a daemon, so it exits with the main program
        self.setDaemon(True)

        # cpu registers
        self.mem = RAM(2**11) # 2048 bits (0.25 kB = 256 bytes)
        self.memlock = threading.Lock()
        self.cpu = CPU(self.mem, self.memlock)
        self.__run_state = run_state

        return

    def set_run(self, run_state):
        self.__run_state = run_state
    def get_run(self):
        return self.__run_state

    # TODO: - specify 'bios.spvm' file required, it will be "mapped" to memory at cpu.__rvec and CPU will execute its instructions there first
    #       - write memory management unit that maps physical address space to pages, divides RAM and ROM (so CPU cannot access ROM addrs)

    def run(self):
        global spgl_mdflag0
        global spgl_runnext

        print('spectre_cpu running...')
        while True:
            if (self.__run_state == 1) or (self.__run_state == 2 and spgl_runnext):
                self.cpu.exec()
            if (self.__run_state == 2 and spgl_runnext):
                spgl_runnext = 0
            if spgl_mdflag0 != 0:
                self.mem.debug_full_memdump()

spvm : SPECTRE_VM = None

def pf_print(sh_prefix):
    print(sh_prefix,end='')

# main runner for emulator
def main(main__debug=False):
    global spvm
    global spgl_crext
    # validate flags and args
    if "-h" in sys.argv or "--help" in sys.argv:
        show_help()
        return 0

    # shell function
    __spvm_shell = True
    __retc = None
    __sh_prefix = '#> '
    __bios = None

    # the machine itself
    spvm = SPECTRE_VM()
    spgl_crext['halt'] = 1
    spvm.start()

    while __spvm_shell:
        pf_print(__sh_prefix)
        try:
            retc = parse_shell(input())
            if retc != -1:
                __spvm_shell = False
                __retc = retc
        except EOFError:
            pass

    return __retc


def parse_shell(line):
    global spvm
    global spgl_crext
    global spgl_mdflock
    global spgl_mdflag0
    global spgl_memdump

    argv = line.split()

    if len(argv) < 1:
        return -1

    # -----------
    #    TODO:
    # -----------
    # - 'load <file>'
    #   > flags:
    #       "--rxe" : special flag for simple loader to run and execute raw code (all bytecode is in a single line)
    #
    # - 'exec' > runs the loaded assembly code
    #
    #
    # sample command sequence for executing raw 0x0-loaded code and viewing memory:
    # - load "file" --rxe
    # - cpu-unhalt
    # - memdump -f

    # validate flags and args
    if 'exit' == argv[0]:
        return 0
    elif 'memdump' == argv[0]:
        __fout = os.path.join(os.getcwd(), 'memdump_{}.txt'.format(date.today().strftime("%m-%d-%Y")))
        if len(argv) == 1:
            pass
        elif '-f' == argv[1]:
            spgl_mdflock.acquire()
            spgl_mdflag0 = 1
            spgl_mdflock.release()
            while spgl_mdflag0 == 1:
                continue
            __memd = spgl_memdump.bin
            n = 64
            f = open(__fout, "w")
            __memlines = [__memd[i:i+n] for i in range(0, len(__memd), n)]
            i = 0
            current_mem = 0x00000000
            while i < len(__memlines):
                cl = __memlines[i]
                ol = '0x{:08x} || '.format(current_mem)
                _spaces_left = n / 8
                _idx = 0
                while _spaces_left > 0:
                    ol += cl[_idx:_idx+8] + ' '
                    _idx += 8
                    _spaces_left -= 1
                f.write(ol + '\n')
                i += 1
                current_mem += n
            f.close()
    elif 'load' == argv[0]:
        if len(argv) < 2:
            pass
        elif len(argv) == 2:
            pass
        elif len(argv) == 3:
            if not os.path.exists(argv[1]):
                pass
            else:
                if '--rxe' == argv[2]:
                    # simple rxe loader --> loads rxe data directly to mem location 0x00000000
                    # - does halt CPU, so requires follow-up 'cpu-unhalt' command
                    # !! EXTREMELY VOLATILE, USE WITH CARE !!
                    __fdin = open(argv[1],mode='rb')
                    __rxe_bin = BitArray()
                    while True:
                        __rxe_in = __fdin.read(1024)
                        if not __rxe_in:
                            break
                        _hex = binascii.hexlify(__rxe_in).decode('utf-8')
                        __rxe_bin.append( '0x{}'.format(_hex) )
                    __fdin.close()

                    _data = [BitArray(__rxe_bin[i:i+64]) for i in range(0, len(__rxe_bin), 64)]
                    assert(len(inst)%64==0 for inst in _data)
                    _paddr = 0x0 # load it straight into the reset vector

                    spgl_crext['halt'] = 1
                    time.sleep(0.5)

                    for _inst in _data:
                        _retc = spvm.mem.write_qwrd(_inst,_paddr)
                        _paddr += 0x40

    elif 'cpu-perline' == argv[0]:
        spgl_crext['run_once'] = True

    elif argv[0] in ['cpu-unhalt', 'run']:
        spgl_crext['halt'] = 0

    elif argv[0] in ['cpu-halt', 'stop']:
        spgl_crext['halt'] = 1

    elif 'runstate' == argv[0]:
        if len(argv) < 2:
            pass
        else:
            try:
                _runstate = int(argv[1])
                spvm.set_run(_runstate)
            except ValueError:
                print('[!] spvm: "{}" not a valid int'.format(argv[1]))

    elif 'set-rvec' == argv[0]:
        if len(argv) not in [2,3]:
            pass
        else:
            try:
                _rv = int(argv[1],0)
                spvm.cpu.set_rvec(_rv)
            except ValueError:
                print('[!] spvm: "{}" not a valid int'.format(argv[1]))
            if len(argv) == 3:
                try:
                    _sr = int(argv[2],0)
                    if _sr == 1:
                        spvm.cpu.soft_reset()
                except ValueError:
                    print('[!] spvm: "{}" not a valid int'.format(argv[1]))

    return -1

if __name__ == "__main__":
    rc = main(main__debug=True)
    sys.exit(rc)