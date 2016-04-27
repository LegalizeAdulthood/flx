#!

"""This module provides the command handlers for the "rstsflx"
utility, for accessing files and directories on RSTS disks.
"""

import sys
if sys.version_info.major < 3:
    raise ImportError ("Python version 3 required")
import os

import rstsio
from .common import *
from . import filecommands
from . import utilcommands
from . import packcommands

curpackname = os.getenv ("RSTSDISK", "rsts.dsk")
curpack = None

def docmd (argv):
    cmd = argv[0].lower ()
    argv = argv[1:]
    try:
        parser, fun = cmddict[cmd]
    except KeyError:
        print ("Invalid command:", cmd)
        return
    try:
        args = parser.parse_args (argv)
    except ParseError:
        return
    # Find out if this command refers to a pack.  Default is "r"
    # meaning yes, read-only.  Other possibility are "w" (yes, write)
    # and None (no disk use).
    diskflags = getattr (parser, "diskopt", "r")
    if diskflags is not None:
        if args.disk:
            selectcontainer (args.disk, diskflags)
        p = curpack
        if not p:
            print ("No disk selected")
            return
    else:
        p = None
    fun (p, args)

def main ():
    while True:
        try:
            cmd = input ("flx> ")
            argv = cmd.split ()
            if not argv:
                continue
            docmd (argv)
        except (EOFError, KeyboardInterrupt):
            print ()
            break

# Set the specified name as the current RSTS pack.  Note that it isn't
# mounted yet.
def selectcontainer (pn, diskflags = "r"):
    global curpack, curpackname
    if curpackname != pn:
        curpackname = pn
        if curpack:
            curpack.umount ()
            curpack = None
        curpack = rstsio.pack.Pack (pn, ronly = (diskflags == "r"))

# This needs to be here to refer to "selectcontainer"
disk_parser = CmdParser (prog = "disk", diskflags = None,
                         short = "Select the RSTS file system container.",
                         description = """Select the RSTS file system
                         container or device to access.  The selected
                         disk is used for subsequent commands
                         unless -d is used on particular command,
                         in which case that becomes the selected disk.
                         At program startup, the default disk is given
                         by environment variable RSTSDISK, or "rsts.dsk"
                         if that variable is not defined.""")
disk_parser.add_argument ("filename", metavar = "FN",
                          help = "Container file name")

@command (disk_parser)
def dodisk (p, args):
    selectcontainer (args.filename)

