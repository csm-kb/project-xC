# test 003 - xC assembler
# written by Gabe Svolenka
#
# this test is designed to fail, "invalid symbol declaration after instruction at line 15"
#
# copyright Spectre 1970

MOV 10  $S0
JAL DECREMENT
BEQ $S0 $NIL END
MOV 1   $VC

END:NOP E2: E3:
    JMP END

DECREMENT:
    SUB 1 $S0
    BNE $S0 $NIL DECREMENT
    JR  $RA