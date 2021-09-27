# ################################################
# xC assembler written in Python 3.8
# designed to emulate the old Spectre xC assembler
# with various language versions/features.
# ################################################

import os
import sys
import importlib

import asm_util as asmu

__xcasm_ver = '1.1'

def get_parser_module():
    parser = importlib.import_module("parser_{__xcasm_ver}")
    return parser

def show_help():
    print("xcasm: xC assembler, written in Python 3.9")
    print("-\tto show this help menu, run xcasm in a terminal alone or with '-h'.")
    print("-\tto run the assembler: 'xcasm [source].xc -o=[out_file]'\n")
    print("-\t-o=[out_file] : specifies the output file.\n\t\tif '.xe' or no extension is used, the assembler assumes an xC executable.\n\t\tif '.xo' is used, the assembler assumes an xC object file.")
    print()
    sys.exit(0)

def main(main__asm_debug=False):
    # validate params and file existence
    if len(sys.argv) == 1 or "-h" in sys.argv:
        show_help()
        sys.exit(0)
    if len(sys.argv) < 2:
        print("[!]xcasm: incorrect number of arguments\n\tpass the name of an xC source file to create an xC executable out of\n\te.g. 'xcasm.py test.xc -o=test.xe'", file=sys.stderr)
        sys.exit(1)

    if main__asm_debug:
        print('argv:\t{}'.format(sys.argv))

    main__asm_pass0_only = False
    path_fdsrc = []
    path_fdout = ""
    is_execute = -1

    for i in range(0, len(sys.argv)):
        if i == 0:
            continue
        if ".xc" in sys.argv[i]:
            # source file to process
            if not os.path.exists(sys.argv[i]):
                print("[!]xcasm: specified source file '{}' doesn't exist".format(sys.argv[i]), file=sys.stderr)
                sys.exit(1)
            else:
                path_fdsrc.append(sys.argv[i])
        elif "-o=" in sys.argv[i]:
            __out_tmp = sys.argv[i].split('=', 1)
            print(__out_tmp)
            if path_fdout == "":
                if (not __out_tmp[1].endswith('.xe')) and (not __out_tmp[1].endswith('xo')):
                    path_fdout = __out_tmp[1].strip() + '.xe'
                    is_execute = 2
                else:
                    path_fdout = __out_tmp[1].strip()
                    is_execute = 2 if __out_tmp[1].endswith('.xe') else 1
            else:
                print("[!]xcasm: already specified output\n\tonly specify one output file in argument list", file=sys.stderr)
                sys.exit(1)
        elif '-pass0' in sys.argv[i]:
            main__asm_pass0_only = True

    if path_fdout == "":
        # if we haven't set the output name by this point:
        # > we assume executable by default and use the first source file's name as the output
        path_fdout = os.path.splitext(os.path.basename(path_fdsrc[0]))[0] + '.xe'
        is_execute = 2

    if main__asm_debug:        
        print('fdsrc:\t{}'.format(path_fdsrc))
        print('fdout:\t{}'.format(path_fdout))

    # parse all source files
    for src_file in path_fdsrc:
        fdsrc = open(sys.argv[1], 'r')
        parser = asmu.parser.xcParser(fdsrc.read(), _asm_debug=main__asm_debug, _asm_pass0_only=main__asm_pass0_only, _asm_objexec=is_execute)
        retcode = parser.parse()
        if retcode:
            sys.exit(retcode)
        if main__asm_debug:
            if os.path.exists(path_fdout + '.rxe'):
                os.remove(path_fdout + '.rxe')
            _out_debug = open(path_fdout + '.rxe', 'wb')
            _out_debug.write( parser.get_raw_xe_code().bytes )
            _out_debug.close()

        fdsrc.close()

    return

if __name__ == "__main__":
    main(main__asm_debug=True)
    sys.exit(0)