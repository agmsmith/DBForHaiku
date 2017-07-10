import sys
from cli_client import DropboxTerm

def main(*args):
    term = DropboxTerm()
    term.do_ls(*args)

if __name__ == '__main__':
    main(sys.argv[1:])
