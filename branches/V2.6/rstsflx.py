#!/usr/bin/env python3

"""Program to manipulate RSTS disks and disk container files
"""

import sys
import os
import atexit
import readline
import rstsio.commands

if __name__ == "__main__":
    if len (sys.argv) > 1:
        rstsio.commands.docmd (sys.argv[1:])
        if sys.argv[1] != "disk":
            sys.exit (0)
    histfile = os.path.join (os.environ["HOME"], ".flx_history")
    try:
        readline.read_history_file (histfile)
    except IOError:
        pass
    atexit.register (readline.write_history_file, histfile)
    rstsio.commands.main ()
    
