import re
import os
import sys
from collections import defaultdict
from . import abi
import operator
from anytree import Node
import bitstring
from bitstring import BitArray

class xcParser:
    def __init__(self, src_content, _asm_debug=False, _asm_pass0_only=False, _asm_odir=os.path.curdir, _asm_objexec=0):
        self.__asm_debug = _asm_debug
        self.__asm_pass0_only = _asm_pass0_only
        self.__asm_objexec = _asm_objexec
        self.src_content = src_content
        self.LC = 0
        self.reg_table = {
            'nil':0,'t0':1,'t1':2,'mp':3,'a0':4,'a1':5,'a2':6,'s0':7,'s1':8,'vc':9,'sp':10,'ra':11
        }
        self.mne_table = {
            # table to define the supported xC assembly language
            #inst   : {6+2-bit opc, #exp. args, len of inst in bytes}
            'nop'   : {'opcode': 0, 'args' : 0, 'len':4},
            'mov'   : {'opcode': 1, 'args' : 2, 'len':4},
            'add'   : {'opcode': 2, 'args' : 2, 'len':4},
            'sub'   : {'opcode': 3, 'args' : 2, 'len':4},
            'beq'   : {'opcode': 4, 'args' : 3, 'len':4},
            'bne'   : {'opcode': 5, 'args' : 3, 'len':4},
            'blt'   : {'opcode': 6, 'args' : 3, 'len':4},
            'bgt'   : {'opcode': 7, 'args' : 3, 'len':4},
            'jmp'   : {'opcode': 8, 'args' : 1, 'len':4},
            'jal'   : {'opcode': 9, 'args' : 1, 'len':4},
            'jr'    : {'opcode': 10,'args' : 1, 'len':4},
            'load'  : {'opcode': 11,'args' : 2, 'len':4},
            'stor'  : {'opcode': 12,'args' : 2, 'len':4},
            'sysc'  : {'opcode': 13,'args' : 0, 'len':4},
        }
        self.pse_table = {
            # table to define supported assembler directives (must begin with a dot <i.e. '.name'>)
            '.align'    : {'args' : 1},     # align next data or instruction to boundary
            '.global'   : {'args' : 1},     # define global entry point to program
            '.extern'   : {'args' : 1},     # define symbol as externally-defined
            '.text'     : {'args' : 1},     # mark all following lines as program code
            '.data'     : {'args' : 1}      # mark all following lines as program data
        }
        # symbols defined in this table are either relocatable or absolute
            # symbol table format:     (notype, object, func)
            # { 'name' : ['LC offset', 'type (N/O/F)', 'relative? (R/A)', 'internal? (I/E)']}
        self.sym_table = defaultdict(list)
        # the program's entry-point label, if defined within the source [ format: 'name' ]
            # > if this value is empty by the end of the second pass, the assembler will throw a warning
            #   and set the default entry point to the beginning of the '.text' segment
        self.entry_point = None
        # empty-line and comment-line filtering of src_content
            # ( for getting rid of empty newlines, use 'if s.strip()' after 's for s in self.src_content.strip().splitlines(True)' )
        self.src_content = [l.split('#')[0].strip(' \t') for l in "".join([s for s in self.src_content.strip().splitlines(True)]).lower().splitlines()]
        # intermediate binary container for the object file
        self.obj_bin = None
        # raw instruction code
        self.obj_raw = BitArray()
        # data structure for the object contents
        self.obj_dat = { # = 64 bytes (64-bit)
            'magic':None,           # MAGIC (4) (bytes)
            'ident.class':None,     # ident.class (1)   # '0':64-bit|'1':128-bit
            'ident.data':None,      # ident.data (1)    # '0':little-endian|'1':big-endian
            'ident.version':None,   # ident.version (1) # always '1'
            'ident.osabi':None,     # ident.osabi (1)   # always '0', deprecated
            'pad':None,             # padding (8)
            'type':None,            # type (2)          # '0':NONE|'1':REL|'2':EXEC
            'machine':None,         # machine (2)       # '0' for spectre arch, others reserved
            'version':None,         # version (4)       # '0' for original 0xC spec
            'entry':None,           # entry (8)         # memory address of program entry point
            'phoff':None,           # phoff (8)         # program header offset
            'shoff':None,           # shoff (8)         # section header offset
            'flags':None,           # flags (4)         # varies per architecture
            'ehsize':None,          # ehsize (2)        # size of entry header (this one)
            'phentsize':None,       # phentsize (2)     # size of program header entry
            'phnum':None,           # phnum (2)         # number of program header entries
            'shentsize':None,       # shentsize (2)     # size of section header entry
            'shnum':None,           # shnum (2)         # number of section header entries
            'shstrndx':None,        # shstrndx (2)      # index of section header entry with section names
        }
        self.obj_dat['magic'] = '0x7f307843'
        self.obj_dat['ident.class'] = '0x00'
        self.obj_dat['ident.data'] = '0x01'
        self.obj_dat['ident.version'] = '0x01'
        self.obj_dat['ident.osabi'] = '0x00'
        self.obj_dat['pad'] = '0x00000000'
        if self.__asm_objexec == 0:
            self.obj_dat['type'] = '0x00'
        elif self.__asm_objexec == 1:
            self.obj_dat['type'] = '0x01'
        else:
            self.obj_dat['type'] = '0x02'
        self.obj_dat['machine'] = '0x00'  
        self.obj_dat['version'] = '0x0000'
        self.obj_dat['ehsize'] = '0x40'

        if self.__asm_debug:
            print("xcParser.src_content:\n{}\n<end>".format(self.src_content))

    def pass_0_assem(self, tokens, line_idx):
        # if this is a valid assembler directive
        if tokens[0] in self.pse_table:
            # if directive has at least one argument
            if len(tokens) > 1:
                if tokens[0] == '.align':
                    # check valid alignment range
                    if re.match('^[0-9]+$',tokens[1]) and int(tokens[1]) > 0:
                        # pad alignment of LC to alignment arg
                        _asm_align = int(tokens[1])
                        if (_asm_align & (_asm_align-1) == 0):
                            # if power of two and LC is unaligned, make it happen
                            if (self.LC % _asm_align != 0):
                                self.LC += _asm_align - (self.LC % _asm_align)
                            return 0
                        else:
                            print("[!]xcasm: alignment specified is not a power of two, line {}".format(line_idx+1), file=sys.stderr)
                        return 1
                    else:
                        print("[!]xcasm: invalid alignment specified, line {}".format(line_idx+1), file=sys.stderr)
                        return 1
                elif tokens[0] == '.global':
                    # must be followed by a label declaration considered to be the entry point of executable program
                    # check for existing one
                    if self.entry_point is not None:
                        print("[!]xcasm: global entry point already defined, line {}".format(line_idx+1), file=sys.stderr)
                        return 1
                    else:
                        if tokens[1] not in self.sym_table:
                            self.sym_table[tokens[1]] = [ None, 'F', 'R', '?' ]
                        self.entry_point = tokens[1]
                        return 0
        # check if literal declaration
        elif len(tokens) == 3 and tokens[1] in ['=','equ']:
            # if undefined, define it
            if tokens[0] not in self.sym_table or self.sym_table[tokens[0]][0] is None:
                if re.match('^([0-9]+|0x([0-9a-f])+)$',tokens[2]):
                    # constant numeric value or address
                    self.sym_table[tokens[0]] = [ int(tokens[2],0), 'O', 'A', 'I' ]
                elif re.match('^([^.\-+\*/\n]+)(([+]|[-]|[*]|[/])([0-9]+|0x([0-9a-f]+)))+$',tokens[2]):
                    # symbol-relative value (address)
                    _ari_expr = re.split('([+]|[-]|[*]|[/])',tokens[2])
                    if self.__asm_debug:
                        print('\t_ari_expr: {}'.format(_ari_expr))
                    if _ari_expr[0] not in self.sym_table:
                        print("[!]xcasm: '{}' not a valid symbol, line {}".format(_ari_expr[0], line_idx+1), file=sys.stderr)
                        return 1
                    self.sym_table[tokens[0]] = [ _ari_expr, 'O', 'R', 'I' ]
                else:
                    print("[!]xcasm: invalid assignment to symbol '{}', line {}".format(tokens[0], line_idx+1), file=sys.stderr)
                    return 1
            else:
                print("[!]xcasm: symbol '{}' already defined, line {}".format(tokens[0], line_idx+1), file=sys.stderr)
                return 1
            return 0
        else:
            return 1

    def pass_0_inst(self, line, line_idx):
        # parse instruction
        tokens = list(filter(None, re.split('\s|\t', line)))
        if self.__asm_debug:
            print("\tinst token check, line {} '{}'".format(line_idx+1, tokens))
        # check if valid instruction
        if tokens[0] not in self.mne_table:
            # if not, this line might be a literal declaration or assembler directive
            _assem_iret = self.pass_0_assem(tokens, line_idx)
            if _assem_iret:
                print("[!]xcasm: '{}' not a valid instruction, literal declaration, or assembler directive. line {}".format(tokens[0],line_idx+1), file=sys.stderr)
            return _assem_iret
        # if not a zero-arg instruction, there's more to do
        if len(tokens) > 1:
            # TODO: finish with this set of tokens

            # one-arg variable jump instructions (58-bit addr)
            if tokens[0] in ['jmp', 'jal']:
                if len(tokens) != 2:
                    print("[!]xcasm: invalid number of arguments for '{}', line {}".format(tokens[0],line_idx+1), file=sys.stderr)
                    return 1
                # if this is a register
                if tokens[1].startswith('$'):
                    # make sure it is a valid register
                    if tokens[1].split('$')[1] not in self.reg_table:
                        print("[!]xcasm: '{}' not a valid register, line {}".format(tokens[1],line_idx+1), file=sys.stderr)
                        return 1
                # else, if this is an immediate value
                elif re.match('^([0-9]+|0x([0-9a-f])+)$',tokens[1]):
                    # make sure it is in the valid range for these instructions
                    if int(tokens[1],0) not in range(0, (2**58)):
                        print("[!]xcasm: immediate value too large for instruction, line {}".format(line_idx+1), file=sys.stderr)
                        return 1
                # else, this must be a symbol
                else:
                    # if symbol isn't in table, document it as a symbol
                    if tokens[1] not in self.sym_table:
                        self.sym_table[tokens[1]] = [ None, '?', '?', '?' ]

            # one-arg register jump instruction
            elif tokens[0] == 'jr':
                if len(tokens) != 2:
                    print("[!]xcasm: invalid number of arguments for '{}', line {}".format(tokens[0],line_idx+1), file=sys.stderr)
                    return 1
                # this must be a register
                if tokens[1].startswith('$'):
                    # if so, make sure it is a valid register
                    if tokens[1].split('$')[1] not in self.reg_table:
                        print("[!]xcasm: '{}' not a valid register, line {}".format(tokens[1],line_idx+1), file=sys.stderr)
                        return 1
                else:
                    print("[!]xcasm: '{}' must point to a valid register, line {}".format(tokens[0],line_idx+1), file=sys.stderr)
                    return 1

            # two-arg non-memory instructions (50-bit immediate)
            elif tokens[0] in ['mov', 'add', 'sub']:
                if len(tokens) != 3:
                    print("[!]xcasm: invalid number of arguments for '{}', line {}".format(tokens[0],line_idx+1), file=sys.stderr)
                    return 1
                # if first arg is a register
                if tokens[1].startswith('$'):
                    # make sure it is a valid register
                    if tokens[1].split('$')[1] not in self.reg_table:
                        print("[!]xcasm: '{}' not a valid register, line {}".format(tokens[1],line_idx+1), file=sys.stderr)
                        return 1
                # else, if this is an immediate value
                elif re.match('(^[0-9]+$|^0x([0-9a-f])+$)',tokens[1]):
                    # make sure it is in the valid range for these instructions
                    if int(tokens[1],0) not in range(-(2**51), (2**51)):
                        print("[!]xcasm: immediate value too large for instruction, line {}".format(line_idx+1), file=sys.stderr)
                        return 1
                # else, this must be a named literal
                else:
                    # if literal isn't in table, document it
                    if tokens[1] not in self.sym_table:
                        self.sym_table[tokens[1]] = [ None, 'O', '?', '?' ]
                # second arg must be a register
                if tokens[2].startswith('$'):
                    # if so, make sure it is a valid register
                    if tokens[2].split('$')[1] not in self.reg_table:
                        print("[!]xcasm: '{}' not a valid register, line {}".format(tokens[2],line_idx+1), file=sys.stderr)
                        return 1
                else:
                    print("[!]xcasm: '{}' must point to a valid register, line {}".format(tokens[0],line_idx+1), file=sys.stderr)
                    return 1

            # three-arg memory instructions (46-bit addr) [format: 'LOAD reg off(mem)']
            elif tokens[0] in ['load', 'stor']:
                if len(tokens) != 3:
                    print("[!]xcasm: invalid number of arguments for '{}', line {}".format(tokens[0],line_idx+1), file=sys.stderr)
                    return 1
                # first arg must be a register
                if tokens[1].startswith('$'):
                    # if so, make sure it is a valid register
                    if tokens[1].split('$')[1] not in self.reg_table:
                        print("[!]xcasm: '{}' not a valid register, line {}".format(tokens[1],line_idx+1), file=sys.stderr)
                        return 1
                else:
                    print("[!]xcasm: '{}' must point to a valid register, line {}".format(tokens[0],line_idx+1), file=sys.stderr)
                    return 1
                # valid offset(memptr) format
                if re.match('^([0-9]+|0x[0-9a-f]+|[$][0-9a-z]+)[(][$][0-9a-z]+[)]$', tokens[2]):
                    tokspl = tokens[2].split('(')
                    tokspl[1] = tokspl[1][:-1]
                    # tokspl = ['offset', 'memptr']
                    # if offset starts with '$', is a register
                    if tokspl[0].startswith('$'):
                        if tokspl[0].split('$')[1] not in self.reg_table:
                           print("[!]xcasm: '{}' not a valid register, line {}".format(tokspl[0],line_idx+1), file=sys.stderr)
                           return 1
                    else:
                        # check immediate value
                        if int(tokspl[0],0) not in range(-(2**45), (2**45)):
                            print("[!]xcasm: immediate value too large for instruction, line {}".format(line_idx+1), file=sys.stderr)
                            return 1
                    # then check memptr -- must be a register
                    if tokspl[1].startswith('$'):
                        if tokspl[1].split('$')[1] not in self.reg_table:
                           print("[!]xcasm: '{}' not a valid register, line {}".format(tokspl[1],line_idx+1), file=sys.stderr)
                           return 1
                else:
                    print("[!]xcasm: '{}' has invalid offset-pointer format, line {}".format(tokens[0],line_idx+1), file=sys.stderr)
                    return 1

            # three-arg conditional jump instructions (46-bit addr)
            elif tokens[0] in ['beq', 'bne', 'blt', 'bgt']:
                if len(tokens) != 4:
                    print("[!]xcasm: invalid number of arguments for '{}', line {}".format(tokens[0],line_idx+1), file=sys.stderr)
                    return 1
                # check middle two arguments
                for i in range(1,3):
                    # this must be a register
                    if tokens[1].startswith('$'):
                        # if so, make sure it is a valid register
                        if tokens[1].split('$')[1] not in self.reg_table:
                           print("[!]xcasm: '{}' not a valid register, line {}".format(tokens[1],line_idx+1), file=sys.stderr)
                           return 1
                    else:
                        print("[!]xcasm: '{}' must point to a valid register, line {}".format(tokens[0],line_idx+1), file=sys.stderr)
                        return 1
                # last value should be a symbol
                if tokens[3] not in self.sym_table:
                    # if symbol isn't in table, document it
                    self.sym_table[tokens[3]] = [ None, '?', '?', '?' ]

        self.LC += 4
        return 0

    # analysis phase pass of source file
    def pass_0(self):
        # for each line in the source file:
        for line_idx in range(0, len(self.src_content)):
            # skip comment-only lines
            if len(self.src_content[line_idx]) == 0:
                continue
            if self.__asm_debug:
                print("xcasm (p0): parsing line '{}'".format(self.src_content[line_idx]))
            # check for symbol definition
            if len(self.src_content[line_idx].split(':')) > 1:
                _sub_pms = self.src_content[line_idx].split(':')
                # if self.__asm_debug:
                #     print("\traw sym check, line {} {}".format(line_idx+1, _sub_pms))
                if _sub_pms[len(_sub_pms)-1] is '' and any([any( b in self.mne_table for b in re.split('\s|\t',_sub_pms[i]) ) for i in range(0,len(_sub_pms))]):
                    # invalid symbol declaration after instruction
                    print("[!]xcasm: invalid symbol declaration after instruction at line {}".format(line_idx+1), file=sys.stderr)
                    return 1

                _sub_pms = list(filter(None, self.src_content[line_idx].split(':')))
                if self.__asm_debug:
                    print("\tsymbol check, line {} {}".format(line_idx+1, _sub_pms))
                _lsym_idx = 0
                # get all the symbols in this line, not the instruction (if line has one)
                # instruction should always be last result in this split, else it is invalid
                while (_lsym_idx < len(_sub_pms) and (_sub_pms[_lsym_idx].strip(' \t') not in self.mne_table)):
                    # check if symbol has been defined or has unknown pointer
                    if _sub_pms[_lsym_idx].strip(' \t') not in self.sym_table or self.sym_table[_sub_pms[_lsym_idx].strip(' \t')][0] is None:
                        if self.__asm_debug:
                            print("\tadding symbol '{}' from line {}".format(_sub_pms[_lsym_idx].strip(' \t'),line_idx+1))
                        self.sym_table[_sub_pms[_lsym_idx].strip(' \t')] = [ self.LC, 'F', 'R', 'I' ]
                    else:
                        print("[!]xcasm: multiple-defined symbol '{}' at line {}".format(_sub_pms[_lsym_idx],line_idx+1), file=sys.stderr)
                        return 1
                    _lsym_idx += 1
                # then, handle the instruction if there is one
                if len(_sub_pms) > 1:
                    _inst_retcode = self.pass_0_inst(_sub_pms[len(_sub_pms)-1], line_idx)
                    if _inst_retcode:
                        return _inst_retcode
            # else, this is an instruction line
            else:
                _inst_retcode = self.pass_0_inst(self.src_content[line_idx], line_idx)
                if _inst_retcode:
                    return _inst_retcode

        return 0

    # helper for parsing simple arithmetic expressions -- must validate expressions prior to passing them into this function
    def parse_ari(self, exp_arr):
        loc_exp = exp_arr
        opprec = ['*/','+-']
        opdict = {
            '*':operator.mul,
            '/':operator.truediv,
            '+':operator.add,
            '-':operator.sub
        }
        i = 0
        while i < len(loc_exp):
            if str(loc_exp[i]) in '*/':
                b = loc_exp.pop(i+1)
                op = loc_exp.pop(i)
                loc_exp[i-1] = int(opdict[op](loc_exp[i-1],b))
                i -= 1
            i += 1
        i = 0
        while i < len(loc_exp):
            if str(loc_exp[i]) in '+-':
                b = loc_exp.pop(i+1)
                op = loc_exp.pop(i)
                loc_exp[i-1] = int(opdict[op](loc_exp[i-1],b))
                i -= 1
            i += 1
        return loc_exp[0]

    # helper for object construction, converting instructions into raw machine code
    def pass_1_inst(self, line, line_idx):
        # TODO: create another class that deals with ABI definitions of xC architecture
        tokens = list(filter(None, re.split('\s|\t', line)))
        if self.__asm_debug:
            print('\tinst\t: {}'.format(tokens))
        # skip assembler directives
        if tokens[0] not in self.mne_table and tokens[0] not in self.sym_table:
            if self.__asm_debug:
                print("\t// skipping assembler directive '{}'".format(tokens[0]))
            return 0
        # tokens[0] is either instruction, label, or symbol
        if tokens[0] in abi.optable:
            # instruction
            _bytecode = BitArray( '{}'.format( hex(abi.optable[tokens[0]]) ) )
            while len(_bytecode) < 6:
                _bytecode.insert('0b0',0)

            if tokens[0] in ['nop']:
                while len(_bytecode) < 64:
                    _bytecode.insert('0b0',0)

            # one-arg variable jump instructions (58-bit addr)
            if tokens[0] in ['jmp', 'jal']:
                # if this is a register
                if tokens[1].startswith('$'):
                    _regval = BitArray( '{}'.format( hex(abi.regtable[tokens[1]]) ) )
                    while len(_regval) < 6:
                        _regval.insert('0b0',0)
                    _bytecode.append(_regval)
                # else, if this is an immediate value
                elif re.match('^([0-9]+|0x([0-9a-f])+)$',tokens[1]):
                    _immval = BitArray( '{}'.format( hex(int(tokens[1],0) * 16) ) )
                    while len(_immval) < 58:
                        _immval.insert('0b0',0)
                    _bytecode.append(_immval)
                # else, this must be a symbol
                else:
                    _syment = self.sym_table[tokens[1]]
                    # { 'name' : ['LC offset', 'type (N/O/F)', 'relative? (R/A)', 'internal? (I/E)']}
                    _valid_imm_internal = (_syment[1] == 'O' and _syment[2] == 'A' and _syment[3] == 'I') \
                        or (_syment[1] == 'F' and _syment[2] == 'R' and _syment[3] == 'I')
                    # if this is a value we can immediately substitute into the instruction
                    if _valid_imm_internal:
                        _subval = BitArray( '{}'.format( hex(_syment[0] * 16) ) )
                        while len(_subval) < 58:
                            _subval.insert('0b0',0)
                        _bytecode.append(_subval)
                    elif (_syment[1] == 'O' and _syment[2] == 'R' and _syment[3] == 'I'):
                        # this is most likely a calculatable value, let's just do it now for immediate bytecode "linking purposes"
                        _sym_ariexp = _syment[0]
                        for idx in range(0, len(_sym_ariexp)):
                            if _sym_ariexp[idx] in self.sym_table:
                                _sym_ariexp[idx] = self.sym_table[_sym_ariexp[idx]][0]
                            elif _sym_ariexp[idx].isdigit():
                                _sym_ariexp[idx] = int(_sym_ariexp[idx])
                        _sym_endval = self.parse_ari(_sym_ariexp)
                        _subval = BitArray( '{}'.format( hex(_sym_endval * 8) ) )
                        while len(_subval) < 58:
                            _subval.insert('0b0',0)
                        _bytecode.append(_subval)

            # one-arg register jump instruction
            elif tokens[0] == 'jr':
                _regval = BitArray( '{}'.format( hex(abi.regtable[tokens[1]]) ) )
                while len(_regval) < 58:
                    if len(_regval) < 6:
                        _regval.insert('0b0',0)
                    else:
                        _regval.append('0b0')
                _bytecode.append(_regval)

            # two-arg non-memory instructions (50-bit immediate)
            elif tokens[0] in ['mov', 'add', 'sub']:
                _regval = None
                _immval = None
                # if first arg is a register
                if tokens[1].startswith('$'):
                    _immval = BitArray( '{}'.format( hex(abi.regtable[tokens[1]]) ) )
                    while len(_immval) < 52:
                        if len(_immval) < 6:
                            _immval.insert('0b0',0)
                        else:
                            _immval.append('0b0')
                # else, if this is an immediate value
                elif re.match('(^[0-9]+$|^0x([0-9a-f])+$)',tokens[1]):
                    # make sure it is in the valid range for these instructions
                    _tok_imm = tokens[0] + 'i'
                    _bytecode = None
                    _bytecode = BitArray( '{}'.format( hex(abi.optable[_tok_imm]) ) )
                    while len(_bytecode) < 6:
                        _bytecode.insert('0b0',0)
                    while len(_bytecode) > 6:
                        _bytecode = _bytecode[1:]
                    _immval = BitArray( '{}'.format( hex(int(tokens[1])) ) )
                    while len(_immval) < 52:
                        if int(tokens[1]) < 0:
                            _immval.insert('0b1',0)
                        else:
                            _immval.insert('0b0',0)
                # else, this must be a named literal
                else:
                    _tok_imm = tokens[0] + 'i'
                    _bytecode = None
                    _bytecode = BitArray( '{}'.format( hex(abi.optable[_tok_imm]) ) )
                    while len(_bytecode) < 6:
                        _bytecode.insert('0b0',0)
                    while len(_bytecode) > 6:
                        _bytecode = _bytecode[1:]
                    # symbol val processing
                    _syment = self.sym_table[tokens[1]]
                    # { 'name' : ['LC offset', 'type (N/O/F)', 'relative? (R/A)', 'internal? (I/E)']}
                    _valid_imm_internal = (_syment[1] == 'O' and _syment[2] == 'A' and _syment[3] == 'I') \
                        or (_syment[1] == 'F' and _syment[2] == 'R' and _syment[3] == 'I')
                    # if this is a value we can immediately substitute into the instruction
                    if _valid_imm_internal:
                        _immval = BitArray( '{}'.format( hex(_syment[0]) ) )
                        while len(_immval) < 52:
                            _immval.insert('0b0',0)
                    elif (_syment[1] == 'O' and _syment[2] == 'R' and _syment[3] == 'I'):
                        # this is most likely a calculatable value, let's just do it now for immediate bytecode "linking purposes"
                        _sym_ariexp = _syment[0]
                        for idx in range(0, len(_sym_ariexp)):
                            if _sym_ariexp[idx] in self.sym_table:
                                _sym_ariexp[idx] = self.sym_table[_sym_ariexp[idx]][0]
                            elif _sym_ariexp[idx].isdigit():
                                _sym_ariexp[idx] = int(_sym_ariexp[idx])
                        _sym_endval = self.parse_ari(_sym_ariexp)
                        _immval = BitArray( '{}'.format( hex(_sym_endval) ) )
                        while len(_immval) < 52:
                            _immval.insert('0b0',0)
                # second arg must be a register
                if tokens[2].startswith('$'):
                    _regval = BitArray( '{}'.format( hex(abi.regtable[tokens[2]]) ) )
                    while len(_regval) < 6:
                        _regval.insert('0b0',0)
                    while len(_regval) > 6:
                        _regval = _regval[1:]
                _bytecode.append(_regval)
                _bytecode.append(_immval)

            # three-arg memory instructions (46-bit addr) [format: 'LOAD reg off(mem)']
            elif tokens[0] in ['load', 'stor']:
                _rsrcvl = BitArray( '{}'.format( hex(abi.regtable[tokens[1]]) ) )
                _roffvl = None
                _rmemvl = None
                while len(_rsrcvl) < 6:
                    _rsrcvl.insert('0b0',0)
                # valid offset(memptr) format
                if re.match('^([0-9]+|0x[0-9a-f]+|[$][0-9a-z]+)[(][$][0-9a-z]+[)]$', tokens[2]):
                    tokspl = tokens[2].split('(')
                    tokspl[1] = tokspl[1][:-1]
                    # tokspl = ['offset', 'memptr']
                    # if offset starts with '$', is a register
                    if tokspl[0].startswith('$'):
                        _roffvl = BitArray( '{}'.format( hex(abi.regtable[tokspl[0]]) ) )
                        while len(_roffvl) < 46:
                            if len(_roffvl) < 6:
                                _roffvl.insert('0b0',0)
                            else:
                                _roffvl.append('0b0')
                    else:
                        _bytecode = None
                        _iminst = tokens[0] + 'i'
                        _bytecode = BitArray( '{}'.format( hex(abi.optable[_iminst]) ) )
                        while len(_bytecode) < 6:
                            _bytecode.insert('0b0',0)
                        while len(_bytecode) > 6:
                            _bytecode = _bytecode[1:]
                        _roffvl = BitArray( '{}'.format( hex(int(tokspl[0])) ) )
                        while len(_roffvl) < 46:
                            if int(tokspl[0]) < 0:
                                _roffvl.insert('0b1',0)
                            else:
                                _roffvl.insert('0b0',0)
                    # then check memptr -- must be a register
                    _rmemvl = BitArray( '{}'.format( hex(abi.regtable[tokspl[1]]) ) )
                    while len(_rmemvl) < 6:
                        _rmemvl.insert('0b0',0)

                _bytecode.append(_rsrcvl)
                _bytecode.append(_rmemvl)
                _bytecode.append(_roffvl)

            # three-arg conditional jump instructions (46-bit addr)
            elif tokens[0] in ['beq', 'bne', 'blt', 'bgt']:
                _rsrcvl = BitArray( '{}'.format( hex(abi.regtable[tokens[1]]) ) )
                while len(_rsrcvl) < 6:
                    _rsrcvl.insert('0b0',0)
                while len(_rsrcvl) > 6:
                    _rsrcvl = _rsrcvl[1:]
                _rcmpvl = BitArray( '{}'.format( hex(abi.regtable[tokens[2]]) ) )
                while len(_rcmpvl) < 6:
                    _rcmpvl.insert('0b0',0)
                while len(_rcmpvl) > 6:
                    _rcmpvl = _rcmpvl[1:]
                _bytecode.append(_rsrcvl)
                _bytecode.append(_rcmpvl)

                # symbol val processing
                _syment = self.sym_table[tokens[3]]
                # { 'name' : ['LC offset', 'type (N/O/F)', 'relative? (R/A)', 'internal? (I/E)']}
                _valid_imm_internal = (_syment[1] == 'O' and _syment[2] == 'A' and _syment[3] == 'I') \
                    or (_syment[1] == 'F' and _syment[2] == 'R' and _syment[3] == 'I')
                # if this is a value we can immediately substitute into the instruction
                if _valid_imm_internal:
                    _subval = BitArray( '{}'.format( hex(_syment[0] * 16) ) )
                    while len(_subval) < 46:
                        _subval.insert('0b0',0)
                    _bytecode.append(_subval)
                elif (_syment[1] == 'O' and _syment[2] == 'R' and _syment[3] == 'I'):
                    # this is most likely a calculatable value, let's just do it now for immediate bytecode "linking purposes"
                    _sym_ariexp = _syment[0]
                    for idx in range(0, len(_sym_ariexp)):
                        if _sym_ariexp[idx] in self.sym_table:
                            _sym_ariexp[idx] = self.sym_table[_sym_ariexp[idx]][0]
                        elif _sym_ariexp[idx].isdigit():
                            _sym_ariexp[idx] = int(_sym_ariexp[idx])
                    _sym_endval = self.parse_ari(_sym_ariexp)
                    _subval = BitArray( '{}'.format( hex(_sym_endval * 16) ) )
                    while len(_subval) < 46:
                        _subval.insert('0b0',0)
                    _bytecode.append(_subval)

            if self.__asm_debug:
                print( ">>\tbytecode: {} | len: {}".format(_bytecode.bin, len(_bytecode)) )
            self.obj_raw.append(_bytecode)
        else:
            # label or symbol, reference symtable
            if self.__asm_debug:
                print("\tsymbol: address {}".format(self.sym_table[tokens[0]]))
        return 0

    # object construction phase pass of source file
    def pass_1(self):
        # TODO: construct object file, write header.
        #       then, go line-by-line for each instruction.

        # begin the object file in memory
        self.obj_bin = BitArray()

        self.LC = 0
        # for each line in the source file:
        for line_idx in range(0, len(self.src_content)):
            # skip comment-only lines
            if len(self.src_content[line_idx]) == 0:
                continue
            if self.__asm_debug:
                print("xcasm (p1): parsing line '{}'".format(self.src_content[line_idx]))
            # check for symbol definition
            if len(self.src_content[line_idx].split(':')) > 1:
                _sub_pms = list(filter(None, self.src_content[line_idx].split(':')))
                # skip all the symbols in this line
                _lsym_idx = 0
                # get all the symbols in this line, not the instruction (if line has one)
                # instruction should always be last result in this split, else it is invalid
                while (_lsym_idx < len(_sub_pms) and (_sub_pms[_lsym_idx].strip(' \t') not in self.mne_table)):
                    # check if symbol has been defined or has unknown pointer
                    if _sub_pms[_lsym_idx].strip(' \t') in self.sym_table:
                        print("",end='')
                    _lsym_idx += 1
                # instruction will always be last result in this split, so handle it
                if len(_sub_pms) > 1:
                    _inst_retcode = self.pass_1_inst(_sub_pms[len(_sub_pms)-1], line_idx)
                    if _inst_retcode:
                        return _inst_retcode
            # else, this is an instruction line
            else:
                _inst_retcode = self.pass_1_inst(self.src_content[line_idx], line_idx)
                if _inst_retcode:
                    return _inst_retcode

        return 0

    # actual two-pass object generation algorithm
    def parse(self):
        _rets = []
        # run pass 0
        _rets.append(self.pass_0())
        if _rets[0]:
            return _rets[0]
        if self.__asm_debug:
            print('=== pass 0 complete ===')
            print('sym_table:<')
            for sym in self.sym_table.keys():
                print('\t{}:\t{}'.format(sym, self.sym_table[sym]))
            print('>\nentry_point:\n\t{}'.format(self.entry_point))
            print('=======================')
        if self.__asm_pass0_only:
            return 0
            
        # run pass 1
        _rets.append(self.pass_1())
        if _rets[1]:
            return _rets[1]
        if self.__asm_debug:
            print('len of total bytecode: {}'.format(len(self.obj_raw)))
        
        return 0

    def get_raw_xe_code(self):
        return self.obj_raw