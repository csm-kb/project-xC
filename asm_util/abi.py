# // opcode table //
optable = {
    'nop'   : 0,
    'mov'   : 1,
    'add'   : 2,
    'sub'   : 3,
    'beq'   : 4,
    'bne'   : 5,
    'blt'   : 6,
    'bgt'   : 7,
    'jmp'   : 8,
    'jal'   : 9,
    'jr'    : 10,
    'load'  : 11,
    'stor'  : 12,
    'sysc'  : 13,
    # alternate imms
    'movi'  : 14,
    'addi'  : 15,
    'subi'  : 16,
    'loadi' : 17,
    'stori' : 18
}
# // register table //
regtable = {
    '$nil'  : 0,
    '$t0'   : 1,
    '$t1'   : 2,
    '$mp'   : 3,
    '$a0'   : 4,
    '$a1'   : 5,
    '$a2'   : 6,
    '$s0'   : 7,
    '$s1'   : 8,
    '$vc'   : 9,
    '$sp'   : 10,
    '$ra'   : 11
}