import cmd
import locale
import os
#import pprint
import shlex
import sys

from dropbox import DropboxOAuth2FlowNoRedirect
from dropbox import dropbox

# XXX Fill in the application's key and secret below.
# You can find (or generate) these at http://www.dropbox.com/developers/apps
# After about 50 users, it becomes full and you need to generate another key or
# need to make the project official (add icons, docs at Dropbox).
APP_KEY = '6a7ixdngv5ujexe'
APP_SECRET = '8abyxqjc7g4o44d'

ACCESS_TYPE = 'app_folder'
# should be 'dropbox' or 'app_folder' as configured for your app

# General error message display is to stderr, since the output from this
# program may be piped into another program.  Use stdout only for actual
# output, headers and status info go to stderr, status messages (non-errors)
# surrounded by [].

def wrap_dropbox_errors(func):
    """A decorator that inserts a wrapper function for handling Dropbox exceptions."""
    def wrapper(self, *args):
        """A wrapper function for handling Dropbox exceptions."""
        try:
            return func(self, *args)
        except Exception as e:
            print >> sys.stderr, e
            print >> sys.stderr, "Exception while calling Dropbox API, quitting."
            quit(1)
    wrapper.__doc__ = func.__doc__
    return wrapper

class DropboxTerm(cmd.Cmd):
    TOKEN_FILE = "token_store.txt"

    def __init__(self):
        cmd.Cmd.__init__(self)

        # First try loading the saved DropBox authorisation token.
        stored_token = ""
        try:
            with open(self.TOKEN_FILE, 'r') as f:
                stored_token = f.read()
            print >> sys.stderr, "[using previously saved Dropbox access " \
                "token from \"" + self.TOKEN_FILE + "\"]"
        except IOError as e:
            print >> sys.stderr, "Failed to read Dropbox access token from " \
              "file"
            print >> sys.stderr, e
            print >> sys.stderr, "Will prompt the user for a new token..."
            stored_token = ""

        if len(stored_token) <= 0:
            # Ask the user to get a token from the Dropbox web site.
            auth_flow = DropboxOAuth2FlowNoRedirect(APP_KEY, APP_SECRET)
            authorize_url = auth_flow.start()
            print "1. Go to:", authorize_url
            print "2. Click \"Allow\" (you might have to log in first)."
            print "3. Copy the authorisation code."
            auth_code = raw_input("Enter the authorization code here: ").strip()
            
            try:
                oauth_result = auth_flow.finish(auth_code)
                stored_token = oauth_result.access_token
            except Exception as e:
                print >> sys.stderr, "Authorisation Error:", e
                raise

            # Got a new token, save it permanently.
            with open(self.TOKEN_FILE, 'w') as f:
                f.write(stored_token)
            print >> sys.stderr, "[Dropbox access token saved for later runs "\
              "in file \"" + self.TOKEN_FILE + "\"]"

        self.dbx = dropbox.Dropbox(stored_token, user_agent="DBForHaiku/1.0")
        self.current_path = ""
        self.prompt = "DBForHaiku> "

    @wrap_dropbox_errors
    def do_ls(self, arglist): # cmd passes us a list of argment strings.
        """list files in current remote directory, with optional absolute path argument"""
        path = self.current_path
        if len(arglist) > 0:
            path = arglist[0]
        print >> sys.stderr, '[Contents of directory "' + path + '" are:]'
        resp = self.dbx.files_list_folder(path)
        while True:
            for metadata in resp.entries:
                print metadata.name
            if not resp.has_more:
                break
            # More listings available, read the next batch.
            print >> sys.stderr, "[Lots of listings, getting next batch]"
            resp = self.dbx.files_list_folder_continue(resp.cursor)

    @wrap_dropbox_errors
    def do_cd(self, arglist):
        """change current working directory to a specified path, root if none"""
        if len(arglist) <= 0:
            self.current_path = "" # Root is empty string, not "/".
        else:
            path = arglist[0]
            if path == "..":
                self.current_path = \
                    "/".join(self.current_path.split("/")[0:-1])
            else:
                self.current_path += "/" + path
        print >> sys.stderr, "[Current directory now is \"" + \
            self.current_path + "\"]"

    @wrap_dropbox_errors
    def do_cat(self, path):
        """display the contents of a file"""
        f, metadata = self.dropbox.get_file_and_metadata(self.current_path + "/" + path)
        self.stdout.write(f.read())
        self.stdout.write("\n")

    @wrap_dropbox_errors
    def do_mkdir(self, path):
        """create a new directory"""
        self.dropbox.file_create_folder(self.current_path + "/" + path)

    @wrap_dropbox_errors
    def do_rm(self, path):
        """delete a file or directory"""
        self.dropbox.file_delete(self.current_path + "/" + path)

    @wrap_dropbox_errors
    def do_mv(self, from_path, to_path):
        """move/rename a file or directory"""
        self.dropbox.file_move(self.current_path + "/" + from_path,
                                  self.current_path + "/" + to_path)
    @wrap_dropbox_errors
    def do_delta(self, cursor):
        """request remote changes"""
        def pretty_print_deltas(deltas):
          for [n,d] in deltas:
            #print "%s %s %s %s %s" % (n,d['is_dir'],d['path'],d['rev'],d['revision'])
            if d == None:
                print "REMOVE %s" % n
            else:
              if d['is_dir']:
                start = 'FOLDER'
              else:
                start = 'FILE'
              print "%s %s %s" % (start,d['path'],d['rev'])

        response = self.dropbox.delta(cursor)
        if response['reset']:
          print "RESET"
        pretty_print_deltas(response['entries'])
        return response['cursor']

    @wrap_dropbox_errors
    def do_account_info(self, *args):
        """display account information"""
        f = self.dropbox.account_info()
        pprint.PrettyPrinter(indent=2).pprint(f)

    def do_exit(self, *args):
        """exit"""
        return True

    @wrap_dropbox_errors
    def do_get(self, from_path, to_path):
        """
        Copy file from Dropbox to local file and print out out the metadata.

        Examples:
        Dropbox> get file.txt ~/dropbox-file.txt
        """
        to_file = open(os.path.expanduser(to_path), "wb")

        f, metadata = self.dropbox.get_file_and_metadata(self.current_path + "/" + from_path)
        print 'Metadata:', metadata
        to_file.write(f.read())

    @wrap_dropbox_errors
    def do_thumbnail(self, from_path, to_path, size='large', format='JPEG'):
        """
        Copy an image file's thumbnail to a local file and print out the
        file's metadata.

        Examples:
        Dropbox> thumbnail file.txt ~/dropbox-file.txt medium PNG
        """
        to_file = open(os.path.expanduser(to_path), "wb")

        f, metadata = self.dropbox.thumbnail_and_metadata(
                self.current_path + "/" + from_path, size, format)
        print 'Metadata:', metadata
        to_file.write(f.read())

    @wrap_dropbox_errors
    def do_put(self, from_path, to_path, rev):
        """
        Copy local file to Dropbox

        Examples:
        Dropbox> put ~/test.txt dropbox-copy-test.txt
        """
        from_file = open(os.path.expanduser(from_path), "rb")

        if rev == None:
            return self.dropbox.put_file(self.current_path + "/" + to_path, from_file)
        else:
            return self.dropbox.put_file(self.current_path + "/" + to_path, from_file, parent_rev=rev)

    @wrap_dropbox_errors
    def do_search(self, string):
        """Search Dropbox for filenames containing the given string."""
        results = self.dropbox.search(self.current_path, string)
        for r in results:
            self.stdout.write("%s\n" % r['path'])

    def do_help(self, topic):
        # Replace the default cmd.do_help with a listing of every docsctring
        # from every "do_" attribute.
        all_names = dir(self)
        cmd_names = []
        for name in all_names:
            if name[:3] == 'do_':
                cmd_names.append(name[3:])
        cmd_names.sort()
        for cmd_name in cmd_names:
            f = getattr(self, 'do_' + cmd_name)
            if f.__doc__:
                self.stdout.write('%s: %s\n' % (cmd_name, f.__doc__))

    # the following are for command line magic and aren't Dropbox-related
    def emptyline(self):
        pass

    def do_EOF(self, line):
        self.stdout.write('\n')
        return True

    def parseline(self, line):
        try:
            parts = shlex.split(line)
        except Exception as e:
            print >> sys.stderr, e
            parts = []
        if len(parts) == 0:
            return None, None, line
        else:
            return parts[0], parts[1:], line


def main():
    term = DropboxTerm()
    term.do_ls([])
    term.cmdloop()

if __name__ == '__main__':
    main()
