import cmd
import haikuglue.storage
import locale
import os
import shlex
import sys

from dropbox import DropboxOAuth2FlowNoRedirect
from dropbox import dropbox
import dateutil.tz

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
        """A wrapper function for handling Dropbox exceptions.
        Will return True if something goes wrong, usually False if success."""
        try:
            return func(self, *args)
        except Exception as e:
            print >> sys.stderr, e
            print >> sys.stderr, \
                "Something went wrong while using the Dropbox API, exiting."
            return True # Stop the command.
    wrapper.__doc__ = func.__doc__
    return wrapper

class DropboxTerm(cmd.Cmd):
    TOKEN_FILE = "login_token_store.txt"
    VERSION_ATTRIBUTE_NAME = "DropBoxVersion"

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
            print >> sys.stderr, "Failed to read saved Dropbox access token."
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
                print >> sys.stderr, "Maybe delete file \"" + self.TOKEN_FILE + \
                    "\" and try again?"
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
                if 'size' in dir(metadata):
                    # We have a file, not a directory, has size and a date
                    # stamp.  Convert the time to the local time zone.  By
                    # default (no time zone specified) it is in universal
                    # coordinated time (UTC).
                    if metadata.client_modified.tzinfo == None:
                        metadata.client_modified = \
                            metadata.client_modified.replace(tzinfo =
                            dateutil.tz.tzutc())
                    # Convert to local time for printing, use UTC internally.
                    localdate = metadata.client_modified.astimezone(
                        dateutil.tz.tzlocal())
                    print metadata.name, '<date', localdate, 'size', \
                        metadata.size, 'bytes>'
                else:
                    print metadata.name, '<directory>'
            if not resp.has_more:
                break
            # More listings available, read the next batch.
            print >> sys.stderr, "[Lots of listings, getting next batch]"
            resp = self.dbx.files_list_folder_continue(resp.cursor)
        return False

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
        return False

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
    def do_account_info(self, arglist):
        """display account information"""
        f = self.dbx.users_get_current_account()
        print f
        return False

    def do_exit(self, arglist):
        """exit"""
        return True

    @wrap_dropbox_errors
    def do_get(self, arglist):
        """Copy (download) a file from Dropbox to a local file.

        It takes 2 or 3 arguments: the DropBox file path, the local file
        path and an optional DropBox version of the file.

        If successful, it returns the version string of the downloaded file.

        Examples:
        DBForHaiku> get file.txt ~/local-file.txt 6589781a4
        [using previously saved Dropbox access token from "token_store.txt"]
        [Get: download file from "file.txt" to "/boot/home/local-file.txt", version 6589781a4 ]
        [Downloaded 76 bytes]
        6589781a4"""
        if len(arglist) < 2:
            print >> sys.stderr, "Get needs 2 or 3 arguments: the Dropbox from " \
                "file path, the local destination path, the revision."
            return True # Something went wrong.
        from_path = arglist[0]
        to_path = arglist[1]
        to_file = os.path.expanduser(to_path)
        if len(arglist) >= 3:
            version = arglist[2]
        else:
            version = None
        print >> sys.stderr, "[Get: download file from \"" + from_path + \
            "\" to \"" + to_file + "\", version", version, "]"
        metadata = self.dbx.files_download_to_file(
            to_file, self.current_path + "/" + from_path, version)
        # TODO: Set file date from metadata.
        print >> sys.stderr, "[Downloaded", metadata.size, "bytes]"
        haikuglue.storage.write_attr(to_file, self.VERSION_ATTRIBUTE_NAME,
            haikuglue.storage.types['B_STRING_TYPE'], metadata.rev)
        print metadata.rev
        return False

    @wrap_dropbox_errors
    def do_put(self, from_path, to_path, rev):
        """
        Copy local file to Dropbox; uploading it.

        Examples:
        DBForHaiku> put ~/test.txt dropbox-copy-test.txt
        """
        from_file = open(os.path.expanduser(from_path), "rb")

        if rev == None:
            return self.dropbox.put_file(self.current_path + "/" + to_path, from_file)
        else:
            return self.dropbox.put_file(self.current_path + "/" + to_path, from_file, parent_rev=rev)

    def do_quit(self, arglist):
        """quit"""
        return True

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
