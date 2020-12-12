import os
import sys
from tqdm import tqdm
import subprocess

class bcolors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

def test_exec(test_scr, test_show_stderrs, args=[]):
    test = subprocess.Popen([sys.executable, 'xcasm.py', sys.argv[1]+'/'+test_scr, '-o="test_{}.xe"'.format(test_itr)] + args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    t_stdout, t_stderr = test.communicate()

    a = test.returncode == 0
    b = test_asserts[test_scr][0]
    test_expected = ((a and b) or (not(a or b)))
    test_reasoned = (test_asserts[test_scr][1] in str(t_stderr))
    if test_force_assert:
        # test results must be as expected (XNOR gate logic)
        assert( test_expected and test_reasoned )
    else:    
        if test_expected and test_reasoned:
            if test_show_stderrs:
                print("[{}*{}]\t{}\t".format(bcolors.OKGREEN, bcolors.ENDC, test_scr), end='')
                print("[stderr]\t{}".format(t_stderr))
            else:
                print("[{}*{}]\t{}".format(bcolors.OKGREEN, bcolors.ENDC, test_scr))
        else:
            print("[{}x{}]\t{}\t".format(bcolors.FAIL, bcolors.ENDC, test_scr), end='')
            print("[stderr]\t{}".format(t_stderr))

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("[!]tests: please specify the test script directory", file=sys.stderr)
        sys.exit(1)
    if not os.path.exists(sys.argv[1]):
        print("[!]tests: test dir does not exist", file=sys.stderr)
        sys.exit(1)
    test_force_assert = False
    test_show_stderrs = False
    test_pass0_tests  = False
    if len(sys.argv) > 2:
        for i in range(2, len(sys.argv)):
            if sys.argv[i] == '-a':
                test_force_assert = True
            elif sys.argv[i] == '-e':
                test_show_stderrs = True
            elif sys.argv[i] == '-p0':
                test_pass0_tests = True
    test_scripts = [f for f in os.listdir(sys.argv[1]) if os.path.isfile(os.path.join(sys.argv[1],f))]
    test_itr = 1
    test_asserts = {
        # is this test supposed to pass? if not, why?
        'test_001.xc':[True,''],
        'test_002.xc':[False,'multiple-defined symbol \'end\' at line 21'],
        'test_003.xc':[False,'invalid symbol declaration after instruction at line 13'],
        'test_004.xc':[False,'\'xyz\' not a valid instruction, literal declaration, or assembler directive. line 12'],
        'test_005.xc':[False,'\'$xy\' not a valid register, line 10'],
        'test_006.xc':[False,'immediate value too large for instruction, line 11'],
        'test_007.xc':[False,'\'stor\' has invalid offset-pointer format, line 12'],
        'test_008.xc':[False,'\'$xy\' not a valid register, line 12'],
        'test_009.xc':[False,'\'$xy\' not a valid register, line 12'],
        'test_010.xc':[True,''],
    }

    if test_pass0_tests:
        print("=== Running xC assembler pass 0 tests ===")
        if test_force_assert:
            for test_scr in tqdm(test_scripts):
                test_exec(test_scr, test_show_stderrs, args=['-pass0'])
        else:
            for test_scr in test_scripts:
                test_exec(test_scr, test_show_stderrs, args=['-pass0'])