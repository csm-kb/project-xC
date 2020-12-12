# test 004 - xC assembler
# written by Gabe Svolenka
#
# this test is designed to fail, "'XYZ' not a valid instruction, line 14"
#
# copyright Spectre 1970

MOV 10  $S0
JAL DECREMENT
BEQ $S0 $NIL END
MOV 1   $VC
XYZ 0   $RA

END:NOP
    JMP END

DECREMENT:
    SUB 1 $S0
    BNE $S0 $NIL DECREMENT
    JR  $RA

    UNUSED: NOP