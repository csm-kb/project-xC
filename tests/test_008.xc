# test 008 - xC assembler
# written by Gabe Svolenka
#
# this test is designed to fail, "'$xy' not a valid register, line 12"
#
# copyright Spectre 1971

MOV     10  $S0
JAL         DECREMENT
BEQ     $S0 $NIL        END
MOV     1   $VC
STOR    $VC 0($XY)

END:NOP     # the program ends here with older xC architectures
    JMP     END

DECREMENT:
    SUB     1   $S0
    BNE         $S0 $NIL DECREMENT
    JR          $RA

    .ALIGN 2
    UNUSED: NOP
    ADD     __sub   $T0   #__sub is a named literal
    JMP     END