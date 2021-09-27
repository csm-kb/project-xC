import sys
import os
import threading
from typing import List
from bitstring import BitArray
import time
from datetime import date
import binascii
import graphics

from ram import RAM
from cpu import CPU
from spgl import \
    spgl_memdump, \
    spgl_mdflag0, \
    spgl_mdflock, \
    spgl_runnext, \
    spgl_crext


# help function
def show_help():
    print("spvm: Spectre-xC arch emulator, written in Python 3.8")
    print("-\tto show this help menu, run spvm with '-h'.")
    print("-\tto run the emulator: 'spvm'")
    print()


# internal states of machine
class SPECTRE_VM(threading.Thread):
    # run_state:
    #   0 : stopped
    #   1 : running, will loop forever through instructions
    #   2 : will execute an instruction at a time with 'step' command
    def __init__(self, run_state=1, run_next_inst=False, mem_size=2**12):
        super(SPECTRE_VM,self).__init__()
        # this must be a daemon, so it exits with the main program
        self.setDaemon(True)

        # cpu registers
        # self.mem = RAM(2**11) # 2048 bits | 0.25 kB = 256 bytes
        self.mem = RAM(mem_size) # 4096 bits | 0.50 kB = 512 bytes
        print(f'mem size: {self.mem.size_bytes} bytes')
        # self.mem = RAM(2**13) # 8192 bits | 1.00 kB = 1024 bytes
        self.memlock = threading.Lock()
        self.cpu = CPU(self.mem, self.memlock)
        self.__run_state = run_state

        return

    def set_run(self, run_state):
        self.__run_state = run_state
    def get_run(self):
        return self.__run_state

    # TODO: - specify 'bios.spvm' file, it can be "mapped" to memory (e.g at cpu.__rvec and CPU will execute its instructions there first)
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
        # exit program
        return 0
    elif 'memdump' == argv[0]:
        # dump contents of memory to a file
        __fout = os.path.join(os.getcwd(), 'memdump_{}.txt'.format(date.today().strftime("%m-%d-%Y")))
        if len(argv) == 1:
            # no params means do nothing
            pass
        elif '-f' == argv[1]:
            # -f param means dump to file
            spgl_mdflock.acquire()
            spgl_mdflag0 = 1
            spgl_mdflock.release()
            while spgl_mdflag0 == 1:
                # wait for memory to shift contents around and unset flag for dump
                continue
            # get binary contents of memory from dump
            __memd: str = spgl_memdump.bin
            n = 64 # 64 bits = 8 hexes
            f = open(__fout, "w")
            # split binary into sublists of length 64 bits each
            __memlines: List[str] = [__memd[i:i+n] for i in range(0, len(__memd), n)]
            i = 0
            current_mem = 0x00000000 # pointer to current memory line, for display
            while i < len(__memlines):
                cl = __memlines[i]
                ol = '0x{:08x} || '.format(current_mem)
                _spaces_left = n // 8
                _idx = 0
                while _spaces_left > 0:
                    if len(argv) > 2 and argv[2] == 'hex':
                        # get the hex representation of this character and separate '0x' from it
                        ol += '{:02x}'.format( int(cl[_idx:_idx+8],2) ) + ' '
                    else:
                        # format the binary directly for this line
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
                    _paddr = 0x0 # load it straight into the base (as reset vector)

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
                print('rvec set to address 0x{:08x}'.format(_rv))
            except ValueError:
                print('[!] spvm: "{}" not a valid int'.format(argv[1]))
            # passing a '1' indicates that we would like to soft-reset the instruction pointer to the new rvec
            if len(argv) == 3:
                try:
                    _sr = int(argv[2],0)
                    if _sr == 1:
                        spvm.cpu.soft_reset()
                        print('*IP reset to new rvec')
                except ValueError:
                    print('[!] spvm: "{}" not a valid int'.format(argv[1]))

    return -1

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
    __sh_prefix = os.getcwd() + '> '
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

if __name__ == "__main__":
    rc = main(main__debug=True)
    sys.exit(rc)