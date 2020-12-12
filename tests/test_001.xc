# test 001 - xC assembler
# written by Gabe Svolenka
#
# this test is designed to pass
#
# copyright Spectre 1970

.GLOBAL _START
_START:
MOV     10  $S0
JAL         DECREMENT
BEQ     $S0 $NIL        END
MOV     1   $VC
STOR    $VC   0($SP)

END:NOP     # the program ends here with older xC architectures
    JMP     END

__sub = 10

DECREMENT:
    SUB     1   $S0
    BNE         $S0 $NIL DECREMENT
    JR          $RA

    .ALIGN 2
    UNUSED: NOP
    ADD     __sub   $T0   #__sub is a named literal
    JMP     END