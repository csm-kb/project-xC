# test 006 - xC assembler
# written by Gabe Svolenka
#
# this test is designed to fail, "immediate value too large for instruction, line 11"
#
# copyright Spectre 1970

MOV 10  $S0
JAL DECREMENT
BEQ $S0 $NIL END
MOV 562949953421312   $VC  # = +(2^49), value range must be [-2^49, 2^49 - 1]

END:NOP
    JMP END

DECREMENT:
    SUB 1 $S0
    BNE $S0 $NIL DECREMENT
    JR  $RA

    UNUSED: NOP