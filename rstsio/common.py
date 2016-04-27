#!

import re
from errno import *

BLKSIZE = 512

class FlxError (Exception):
    errno = None

    def __str__ (self):
        return self.__doc__

# For historic amusement, many of the messages here are taken
# straight from the analogous message text in RSTS.  For those where
# the analogy applies, the equivalent errno value is supplied.
class Diskio (FlxError):
    "Device hung or write locked"
    errno = EIO
    #perror (progname);			/* print details */
class Badblk (FlxError):
    "End of file on device"
    errno = EIO
class Badbuf (FlxError):
    "Illegal byte count for I/O"
    errno = EINVAL
class Badclu (FlxError):
    "Illegal cluster size"
    errno = EINVAL
class Badfn (FlxError):
    "Illegal file name"
    errno = EINVAL
class Badlnk (FlxError):
    "Bad directory for device"
    errno = ENXIO
class Badsw (FlxError):
    "Illegal switch usage"
    errno = EINVAL
class Corrupt (FlxError):
    "Corrupted file structure"
    errno = ENXIO
class Dirty (FlxError):
    "Disk pack needs cleaning"
    errno = EPERM
class Nosuch (FlxError):
    "Can't find file or account"
    errno = ENOENT
class Noroom (FlxError):
    "No room for user on device"
    errno = ENOSPC
class Ropack (FlxError):
    "Disk is read-only and --force was not specified"
    errno = EROFS
class Badpak (FlxError):
    "Disk cannot be rebuilt"
    errno = ENXIO
class Internal (FlxError):
    "Program lost-Sorry"
    errno = EFAULT

# Extensions that by default are treated as text
deftext = frozenset (( "txt", "lst", "map", "sid", "log", "lis",
                       "rno", "doc", "mem", "bas", "b2s", "mac",
                       "for", "ftn", "fth", "cbl", "dbl", "com",
                       "cmd", "bat", "tec", "ctl", "odl", "ps ",
                       "tes", "c  ", "h  ", "src", "alg" ))

_r50chars = " abcdefghijklmnopqrstuvwxyz$.?0123456789 "
def rad50 (s):
    ret = 0
    mul = 1600
    for c in s[:3].lower ():
        i = _r50chars.find (c)
        if i < 0:
            raise Badfn
        ret += i * mul
        mul //= 40
    return ret

def r50toasc (r):
    r = r or 0
    ret = list ()
    for d in ( 1600, 40, 1):
        i, r = divmod (r, d)
        ret.append (_r50chars[i])
    return ''.join (ret)

def ascname (nam, ext):
    """Convert a rad50 name.ext to ascii.  Note that name and ext
    are padded with spaces to 6 and 3 characters respectively.
    """
    return "%s%s.%s" % (r50toasc (nam[0]), r50toasc (nam[1]),
                        r50toasc (ext))

# Regular expression for RSTS filespec
_re_fq = re.compile (r"""
    (?:                                       # First an optional PPN
     /(\*|(?:\d+))(?:/(\*|(?:\d+)))?(?:/|$) | # PPN Unix style
     [[(](\*|(?:\d+)),(\*|(?:\d+))[])] |      # PPN RSTS style [ ] or ( )
     ([$!%&])                                 # Special PPN characters
    )?
    ([a-z0-9?]*\*?)                           # Optional file name
    (?:.([a-z0-9?]*\*?))?                     # Optional extension
    (?:<(\d+)>)?                              # Optional protection code
    ((?:/[a-z]+(?:[=:].+?)*)*)                # Optional filespec switch
    $""", re.IGNORECASE | re.VERBOSE)
# For now just allow a single numeric switch argument
_re_switch = re.compile (r"/([a-z]+)(?:[=:](\d+))?", re.I)

# Directionary to map PPN shorthand chars to the actual PPN
_ppnchar = { '$' : (1, 2),
             '!' : (1, 3),
             '%' : (1, 4),
             '&' : (1,5) }
# Dictionary for switch lookup.  Value is a pair, the optional part of the
# switch name and the Firqb object's attribute that holds the value.
# Special case: None for the attribute means this is the /ronly switch
_switches = { "cl" : ( "ustersize", "clusiz"),
              "fi" : ( "lesize", "size" ),
              "si" : ( "ze", "size" ),
              "mo" : ( "de", "mode" ),
              "ro" : ( "nly", None ),
              "po" : ( "sition", "pos" ),
              "pr" : ( "otect", "prot" ) }
# Wild element flags:
WPROJ = 1
WPROG = 2
WNAME = 3
WEXT  = 4

class Firqb (object):
    """A parsed RSTS file name, roughly like a FIRQB structure in
    the actual OS which is why we call it by the same name.

    Special case: if the PPN is given Unix style -- /proj/prog -- but
    only the first element is supplied, that is accepted provided there
    is nothing else, and if so, Firqb.prog is returned as None.
    """
    def __init__ (self, fn: str = None):
        self.name = [ None, None ]
        self.proj = self.prog = self.ext = self.mode = self.pos = None
        self.prot = self.clusiz = self.size = self.rms = None
        self.wild = set ()
        if not fn:
            return
        fn = fn.replace (" ", "")
        m = _re_fq.match (fn)
        if not m:
            raise Badfn
        if m.group (1):
            proj, prog = m.group (1), m.group (2)
            if prog is None:
                if m.group (3) or m.group (4) or m.group (5) or m.group (6):
                    raise Badfn
        elif m.group (3):
            proj, prog = m.group (3), m.group (4)
        elif m.group (5):
            proj, prog = _ppnchar[m.group (5)]
        else:
            proj, prog = None, None
        if proj:
            if proj == '*':
                proj = 255
                self.wild.add (WPROJ)
            else:
                proj = int (proj)
                if proj < 0 or proj > 254:
                    raise Badfn
        if prog:
            if prog == '*':
                prog = 255
                self.wild.add (WPROG)
            else:
                prog = int (prog)
                if prog < 0 or prog > 254:
                    raise Badfn
        self.proj = proj
        self.prog = prog
        n = m.group (6)
        if n:
            if n[-1] == '*':
                n = n[:-1] + "??????"
            self.name[0] = rad50 (n[0:3])
            self.name[1] = rad50 (n[3:6])
            if '?' in n:
                self.wild.add (WNAME)
        e = m.group (7)
        if e:
            if e[-1] == '*':
                e = e[:-1] + "???"
            self.ext = rad50 (e)
            if '?' in e:
                self.wild.add (WEXT)
        p = m.group (8)
        if p:
            try:
                self.prot = int (p)
            except ValueError:
                raise Badfn
        sw = m.group (9)
        if sw:
            for m2 in _re_switch.finditer (sw):
                try:
                    swtail, attr = _switches[m2.group (1)[:2]]
                    #print (m2.groups (), swtail, attr)
                    if not swtail.startswith (m2.group (1)[2:]):
                        raise Badsw
                    if attr is None:
                        # /ronly doesn't take an argument
                        if m2.group (2):
                            raise Badsw
                        if self.mode is None:
                            self.mode = 0
                        self.mode |= 8192
                    else:
                        # all other switches require an argument
                        if not m2.group (2):
                            raise Badsw
                        # currently we just handle a single integer argument
                        setattr (self, attr, int (m2.group (2)))
                except (KeyError, ValueError):
                    raise Badsw

    def _applydefaults (self, deffn):
        """Apply the fields in deffn as defaults for this Firqb.
        """
        defused = set ()
        if self.proj is None and deffn.proj:
            self.proj = deffn.proj
            defused.add (WPROJ)
        if self.prog is None and deffn.prog:
            self.prog = deffn.prog
            defused.add (WPROG)
        if self.name[0] is None and deffn.name:
            self.name = deffn.name
            defused.add (WNAME)
        if self.ext is None and deffn.ext:
            self.ext = deffn.ext
            defused.add (WEXT)
        self.wild |= deffn.wild & defused

    def copy (self):
        """Return a copy of a Firqb.
        """
        other = Firqb ()
        other.name = list (self.name)
        other.proj = self.proj
        other.prog = self.prog
        other.ext = self.ext
        other.mode = self.mode
        other.pos = self.pos
        other.prot = self.prot
        other.clusiz = self.clusiz
        other.size = self.size
        other.rms = self.rms
        other.wild = self.wild
        return other
    
    def __str__ (self):
        ret = ""
        if self.proj is not None or self.prog is not None:
            if self.proj == 255:
                proj = '*'
            else:
                proj = str (self.proj)
            if self.prog == 255:
                prog = '*'
            else:
                prog = str (self.prog)
            ret = "[%s,%s]" % (proj, prog)
        if self.name[0] or self.ext:
            ret += ascname (self.name, self.ext).replace (' ', '')
        if self.prot:
            ret += "<%d>" % self.prot
        return ret

def parse (fn: (str, Firqb), deffn: (str, Firqb) = None) -> Firqb:
    """Parse a RSTS file spec, and return a Firqb object which contains
    the file name components in RSTS internal form.  "deffn", if supplied,
    is another file spec whose components are used as the defaults
    for elements of the first file spec.

    Either argument may be a string or a Firqb; if a string, it is first
    converted to a Firqb.
    """
    if not isinstance (fn, Firqb):
        fn = Firqb (fn)
    if deffn:
        if not isinstance (deffn, Firqb):
            deffn = Firqb (deffn)
        fn._applydefaults (deffn)
    return fn

