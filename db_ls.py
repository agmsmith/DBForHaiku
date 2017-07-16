import sys
from cli_client import DropboxTerm

def main(*args):
    term = DropboxTerm()
    return term.do_ls(*args)

if __name__ == '__main__':
    quit (main(sys.argv[1:]))
