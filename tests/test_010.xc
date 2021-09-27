# test 010 - xC assembler
# written by Gabe Svolenka
#
# this test is designed to pass
#
# copyright Spectre 1971

.GLOBAL _START
TEST1:
        # test jr
    JR  $RA
_START:
        # test mov
    MOV     0       $T0
    MOV     $T1     $T0
        # test add
    ADD     0       $T0
    ADD     $T1     $T0
        # test sub
    SUB     _VAL    $T0
    SUB     $T1     $T0
        # test jmp
    JMP TEST0
TEST0:
        # test jal and =
    _TEST = TEST1+4-4
    JAL _TEST
        # test beq
    BEQ     $T0     $NIL    TEST2
TEST2:
    MOV     1       $T1
        # test bne
    BNE     $T0     $T1     TEST3
TEST3:
        # test blt
    BLT     $T0     $T1     TEST4
TEST4:
        # test bgt
    BGT     $T1     $T0     TEST5
TEST5:
        # test stor
    STOR    $T0     0($SP)
        # test load
    LOAD    $T0     $T0($SP)
        # test equ directive
    _VAL EQU 0x0
        # test nop
END:NOP
    JMP END