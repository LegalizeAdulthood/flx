#!

import argparse

class ParseError (Exception): pass

class CmdParser (argparse.ArgumentParser):
    """A subclass of the standard argparse.ArgumentParser with modified
    error handling.
    """
    def __init__ (self, diskflags = "r", short = "", description = "", **kw):
        self.diskopt = diskflags
        if not short and '\n' not in description:
            short = description
        self.shortdesc = short
        super ().__init__ (add_help = False, description = description, **kw)
        # This might seem redundant with the default help; the difference is
        # that it doesn't show the switch.
        self.add_argument ("-h", "--help", action = "help",
                           help = argparse.SUPPRESS)
        if diskflags is not None:
            self.add_argument ("-d", "--disk",
                               help = "set FILE as the RSTS container",
                               metavar = "FILE")

    def _print_message (self, message, file = None):
        print (message)

    def error (self, message):
        self.print_usage ()
        print (message)
        raise ParseError (message)

cmddict = dict ()
def addcmd (cmds, parser, fun):
    global cmddict
    if isinstance (cmds, str):
        cmds = ( cmds, )
    for cmd in cmds:
        cmddict[cmd] = (parser, fun)

# This is a decorator for command handlers.  Its arguments are the
# parser for this command, and an optional list of synonyms.
def command (p, syns = [ ]):
    def ac (fun, parser = p, cmds = [ p.prog ] + list (syns)):
        global cmddict
        for cmd in cmds:
            cmddict[cmd] = (parser, fun)
        return fun
    return ac
