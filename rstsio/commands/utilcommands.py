#!

import sys
from .common import *
import rstsio

help_parser = CmdParser (prog = "help", diskflags = None,
                         short = "Print help message for a command.",
                         description = """Print the help message for a command.
                         If no argument is supplied, prints one-line summaries
                         of all commands.""")
help_parser.add_argument ("command", nargs = "*", help = "Command to describe")

@command (help_parser)
def dohelp (p, args):
    if args.command:
        for cmd in args.command:
            try:
                parser, fun = cmddict[cmd]
            except KeyError:
                print ("Invalid command:", cmd)
                continue
            prog = parser.prog
            parser.prog = cmd
            parser.print_help ()
            parser.prog = prog
    else:
        syns = dict ()
        for cmd, ent in cmddict.items ():
            parser, fun = ent
            try:
                syns[fun].add (cmd)
            except KeyError:
                syns[fun] = set ((cmd,))
        print ('For details on any command, type "help" followed by '
               "the command name.\n\n"
               "The following commands are supported:")
        for cmd in sorted (cmddict):
            parser, fun = cmddict[cmd]
            if cmd != parser.prog:
                continue        # skip synonyms
            cmdsyns = syns[fun]
            cmdsyns.discard (cmd)
            print ("  {:<14s} {}".format (cmd, parser.shortdesc), end = "")
            if cmdsyns:
                if len (cmdsyns) == 1:
                    print ("  (Synonym: {})".format (cmdsyns.pop ()))
                else:
                    print ("  (Synonyms: {})".format (", ".join (sorted (c for c in cmdsyns))))
            else:
                print ()

vers_parser = CmdParser (prog = "version", diskflags = None,
                         description = """Print the version number.""")
@command (vers_parser)
def doversion (p, args):
    print ("rstsflx V3.0.0")

exit_parser = CmdParser (prog = "exit", diskflags = None,
                         description = """Exit rstsflx.""")

@command (exit_parser, ("quit", "q", "bye"))
def doexit (p, args):
    sys.exit (0)
