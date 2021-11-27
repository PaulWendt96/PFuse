#!/usr/bin/env python

import glob
import os
import sys
import inspect
import time
import errno

from functools import wraps

from fuse import FUSE, FuseOSError, Operations
from passthrough import Passthrough

'''
Next step should be a path level abstraction that automatically aliases
and deals with complex files (e.g. files which are named in the same directory
multiple times). 

Handling this well will open up a world of possibilities. For instance, to 
compare two git commits, we might be able to do

  python union.py /tmp/inspect /tmp/commit1 -name=old /tmp/commit2 -name=new

and, in /tmp/inspect, see files as 

  /tmp/inspect/TODO_new
  /tmp/inspect/TODO_old    # suffixes 'new' and 'old' to indicate different versions
  /tmp/inspect/README      # same name -- hasn't changed version to version

this would need to be a specific mode of the Filesystem, since this is not the 
functionality that we would want all the time

the basic idea would be to:
  - on every file name based operation
    - determine number of times file_path appears
      - if 0, this is probably a write. in this mode, it might make sense to write
        to one directory or all directories, depending on the mode ("mirror mode")
      - if 1, we have a unique file -- just return an underlying reference to that
      - if 2+, we have multiple versions of the file -- attach a suffix or something
        (to make the paths all unique), and use those as part of ls/...
      - if the user wants a reference to the underlying file and does not
        specify the version, assume that they want the file corresponding with
        the first one in the directory (or raise an error if we are in mirror mode) 
'''

def duplicates(iterable):
    unique = set(iterable)
    copy = [e for e in iterable]
    for u in unique:
        copy.remove(u)
    return set(copy)

def strip_leading_slash(path : str) -> str:
    while path and path[0] == '/':
        path = path[1:]
    return path

def log(f):
    """ log a FUSE system call """
    arguments = inspect.getfullargspec(f) 

    @wraps(f)
    def call(*args, **kwargs):
        #print('*'*25)
        #print(f.__name__)
        #print(arguments)
        #s = time.time()
        #print('({}) {} called (args = {}, kwargs = {})'.format(s, f.__name__, args, kwargs))
        #import pdb; pdb.set_trace()
        #print('*'*25)
        return f(*args, **kwargs)
    return call

def attr_of_interest(attr: str) -> bool:
    of_interest = {'read'}
    return attr in of_interest

class UnionFS(Passthrough):
    def __init__(self, paths, debug=False, debug_condition=None, debug_log=None):
        super().__init__(root=paths[0])
        self.union = paths
        self.debug = debug
        self.debug_condition = debug_condition
        self.debug_log = debug_log

    def _full_path(self, partial_path: str) -> str:
        """ get full file path. 

            use union directory paths to try and lookup the file

            if the file turns out not to exist in any directory, return 
            first directory in the union by default """
        partial_path = strip_leading_slash(partial_path)
        paths_to_check = [os.path.join(path, partial_path) for path in self.union]
        existing_paths = [path for path in paths_to_check if os.path.exists(path)]
        if existing_paths:
            if len(existing_paths) > 1:
                print(f"multiple paths -- '{existing_paths}' (lookup on partial_path '{partial_path}'))")
            return existing_paths[0]

        for path in self.union:
            directory = os.path.dirname(path)
            if os.path.exists(directory):
                full_path = os.path.join(path, partial_path)
                return full_path

    def __getattribute__(self, name):
        """ subclass __getattribute__ to dynamically add debug functionality
            to selected object methods

            __getattribute__ will log a method call if its name matches the
            debugging condition

            for FUSE, this effectively allows us to trace specific system calls 
            that are being made throughout the system  """
        attr = object.__getattribute__(self, name)
        if object.__getattribute__(self, 'debug'):
            if inspect.ismethod(attr):
                attr_name = attr.__name__
                if (not self.debug_condition or self.debug_condition(attr_name)) and self.debug_log:
                    return self.debug_log(attr)
        return attr

    def getattr(self, path: str, fh=None):
        """ Fix from DFS -- adds st_blocks attr """
        full_path = self._full_path(path)
        st = os.lstat(full_path)
        return dict((key, getattr(st, key)) for key in ('st_atime', 'st_ctime',
                                                        'st_gid', 'st_mode', 'st_mtime', 'st_nlink', 'st_size', 'st_uid', 'st_blocks')) 
    def readdir(self, partial_path, fh):
        """ read a directory

            you need this if you want 'ls' to work """
        partial_path = strip_leading_slash(partial_path)
        dirents = ['.', '..']
        seen = set()
        for path in self.union:
            full_path = os.path.join(path, partial_path)
            if full_path not in seen and os.path.isdir(full_path):
                seen.add(full_path)
                dirents.extend(os.listdir(full_path)) 

        for r in list(set(dirents)):
            yield r
            
def main(mountpoint, paths, foreground=True):
    FUSE(UnionFS(paths, debug=True, debug_condition=attr_of_interest, debug_log=log), mountpoint, nothreads=True,
         foreground=foreground, **{'allow_other': True})

if __name__ == '__main__':
    if len(sys.argv) < 3:
        print('Usage: python union.py <mount> <p1> ...')
    else:
        mountpoint = sys.argv[1]
        path_args = sys.argv[2:]
        paths = []
        for path in path_args:
            if '*' in path:
                glob_paths = glob.glob(path)
                glob_paths.sort()
                paths.extend(glob_paths)
            else:
                paths.append(path)

        main(mountpoint, paths, foreground=True)

