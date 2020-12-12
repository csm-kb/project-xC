# test 005 - xC assembler
# written by Gabe Svolenka
#
# this test is designed to fail, "'$xy' not a valid register, line 10"
#
# copyright Spectre 1970

MOV 10  $S0
JAL DECREMENT
BEQ $XY $NIL END
MOV 1   $VC

END:NOP
    JMP END

DECREMENT:
    SUB 1 $S0
    BNE $S0 $NIL DECREMENT
    JR  $RA

    UNUSED: NOP