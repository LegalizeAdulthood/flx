#!

import os
from stat import *
import re
import ctypes
from .common import *
from ..common import *
from ..fldef import *
from ..rstsfile import Filedata
from .. import rststime

def _namekey (fd: Filedata):
    return list (fd.ne.unam)

_rfm = ( "udf", "fix", "var", "vfc", "stm" )
def fmtrms (rms1: ufdrms1, rms2: ufdrms2):
    """Return a string which is the interpretation of the supplied RMS file
    attributes.
    """
    extra = ""
    try:
        rfm = _rfm[rms1.fa_typ & fa_rfm]
    except IndexError:
        rfm = "???"
    org = rms1.fa_typ & fa_org
    if org & fo_rel:
        org = "rel"
    elif org & fo_idx:
        org = "idx"
    elif org:
        org = "???"
    else:
        org = "seq"
    rat = rms1.fa_typ & fa_rat
    ratl = list ()
    if rat & ra_ftn:
        ratl.append ("ftn")
    if rat & ra_imp:
        ratl.append ("imp")
    if rat & ra_spn:
        ratl.append ("spn")
    if ratl:
        rat = " rat:%s" % ':'.join (ratl)
    else:
        rat = ""
    if rms2:
        extra = " bkt:%d hdr:%d msz:%d ext:%d" % (rms2.fa_bkt, rms2.fa_hsz,
                                                 rms2.fa_msz, rms2.fa_ext)
    return "rfm:%s:%s%s rsz:%d size:%d eof:%d:%d%s" % \
           (rfm, org, rat, rms1.fa_rsz, rms1.fa_siz.value,
            rms1.fa_eof.value, rms1.fa_eofb, extra)
    
# list mode values -- less than "long" means name-only listing
list_brief = 0
list_onecol = 1
list_long = 2
list_full = 3
list_octattr = 4
list_parser = CmdParser (prog = "list",
                         short = "Prints a directory listing.",
                         description = """Prints a directory listing.
                         Defaults are wildcard for both file and directory.
                         Names within a directory are shown in alphabetical
                         order.  If no argument is given, [*,*]*.* is
                         the default.""")
list_parser.add_argument ("filename", metavar = "FN",
                          nargs = "*",
                          help = "File/directory spec to list")
list_parser.add_argument ("-b", "--brief",
                        action = "store_const",
                        const = list_brief, default = list_brief,
                        dest = "list_mode",
                        help = "brief listing (filenames only, default)")
list_parser.add_argument ("-1", "--one-col", action = "store_const",
                        const = list_onecol, 
                        dest = "list_mode", help = "brief listing, one column")
list_parser.add_argument ("-l", "--long",
                        action = "store_const", dest = "list_mode",
                        const = list_long,
                        help = "long listing (name, size, dates, etc.)")
list_parser.add_argument ("-f", "--full",
                        action = "store_const", dest = "list_mode",
                        const = list_full,
                        help = "full listing (long plus RMS attributes)")
list_parser.add_argument ("-o", "--octal",
                        action = "store_const", dest = "list_mode",
                        const = list_octattr,
                        help = "full listing (long plus attributes in octal)")

@command (list_parser, ("list", "ls"))
def dolist (p, args):
    """Execute a "list" ("dir", "ls") command.
    """
    p.mount ()
    fns = args.filename
    if not fns:
        fns = [ "[*,*]*.*" ]
    for fn in fns:
        ff = parse (fn, "*.*")
        for dd in p.findufds (ff):
            prog, proj = dd.dir.ppn
            hdrdone = False
            if args.list_mode < list_long:
                fl = [ fd for fd in  sorted (dd.dir.findfiles (ff),
                                             key = _namekey) ]
                if not fl:
                    continue
                if args.list_mode == list_onecol:
                    ch = len (fl)
                else:
                    ch = (len (fl) + 3) // 4
                for i in range (0, ch):
                    if not hdrdone:
                        hdrdone = True
                        print ("[%d,%d]" % (proj, prog))
                    nl = [ ascname (fl[j].ne.unam[:2],
                                    fl[j].ne.unam[2])
                           for j in range (i, len (fl), ch) ]
                    print ("    ".join (nl))
            else:
                for fd in sorted (dd.dir.findfiles (ff), key = _namekey):
                    if not hdrdone:
                        hdrdone = True
                        print ("\nDirectory of [%d,%d]\n"
                               " Name .Ext    Size    Prot    Access"
                               "          Creation      Clu"
                               "  RTS      Pos" % (proj, prog))
                    stat = ""
                    if fd.ne.ustat & us_nox:
                        stat += 'C'
                    if fd.ne.ustat & us_nok:
                        stat += 'P'
                    if fd.ne.ustat & us_plc:
                        stat += 'L'
                    if fd.rlist:
                        pos = "%6d" % fd.rlist[0]
                    else:
                        pos = " -----"
                    if fd.ae.urts[0]:
                        rts = r50toasc (fd.ae.urts[0]) + r50toasc (fd.ae.urts[1])
                    else:
                        rts = "      "
                    ctime = rststime.localtime (fd.ae.udc, fd.ae.utc)
                    mtime = rststime.localtime (fd.ae.udla)
                    print ("%-10s%8d%-3s <%3d> %9s %9s %8s %3d %-6s %6s" %
                           (ascname (fd.ne.unam[:2], fd.ne.unam[2]),
                            fd.size, stat, fd.ne.uprot,
                            rststime.ascdate (mtime),
                            rststime.ascdate (ctime), rststime.asctime (ctime),
                            fd.ae.uclus, rts, pos))
                    if fd.rms1:
                        # Attributes are present
                        if args.list_mode == list_octattr:
                            print (" ", " ".join ([ "%06o" % i for i in fd.dir.readlist (fd.ae.ulnk)[:11] ]))
                        elif args.list_mode == list_full:
                            print (" ", fmtrms (fd.rms1, fd.rms2))

type_parser = CmdParser (prog = "type", description = """Type file contents.""")
type_parser.add_argument ("filename", metavar = "FN",
                          nargs = "+", help = "File to type")
type_parser.add_argument ("-v", "--verbose",
                        action = "store_true", default = False,
                        help = "verbose (show file names)")

@command (type_parser, [ "cat" ])
def dotype (p, args):
    """Execute a "type" ("cat") command.
    """
    p.mount ()
    for fn in args.filename:
        ff = parse (fn, "$")
        ff2 = ff.copy ()
        if not ff.name[0]:
            print ("No file name given in", fn)
            continue
        fcount = 0
        for dd in p.findufds (ff):
            fl = [ fd for fd in  sorted (dd.dir.findfiles (ff), key = _namekey) ]
            for fd in fl:
                f = fd.open ("r")
                if args.verbose:
                    print ("----- %s -----" % fd)
                while True:
                    d = f.read ()
                    if not d:
                        break
                    print (d)
                f.close ()
                fcount += 1
        if not fcount:
            print ("No files matching %s" % ff2)

mode_auto = 0
mode_ascii = 1
mode_bin = 2
get_parser = CmdParser (prog = "get",
                        short = "Get file from the RSTS file system.",
                        description = """Get file from the RSTS file system.
                        If "dest" is a file, and there are multiple inputs,
                        they are concatenated into "dest".  If "dest" is a
                        directory, each input file produces a separate
                        output file of the same name in that directory.""")
get_parser.add_argument ("filename", metavar = "src",
                         nargs = "+",
                         help = "File to copy")
get_parser.add_argument ("dest", help = "Destination spec")
get_parser.add_argument ("-v", "--verbose",
                         action = "store_true", default = False,
                         help = "verbose (show file names)")
get_parser.add_argument ("-a", "--ascii",
                         action = "store_const", const = mode_ascii,
                         dest = "mode", default = mode_auto,
                         help = "force ASCII (text) mode transfer")
get_parser.add_argument ("-b", "--binary",
                         action = "store_const", const = mode_bin,
                         dest = "mode", 
                         help = "force binary mode transfer")
get_parser.add_argument ("-R", "--recursive",
                         action = "store_true", default = False,
                         help = """Copy recursively (build directory tree).
                         "dest" must be a directory.  Output file names are
                         xxxyyy/name.ext where xxx and yyy are
                         the project and programmer number of the RSTS file.""")
get_parser.add_argument ("-p", "--preserve",
                         action = "store_true", default = False,
                         help = """Preserve timestamps and (to the extent they
                         carry over) file modes (protection code, in RSTS
                         terms).""")

@command (get_parser)
def doget (p, args):
    """Execute a "get" command.
    """
    fns = args.filename
    dest = args.dest
    try:
        destdir = S_ISDIR (os.stat (dest)[ST_MODE])
    except OSError:
        destdir = False
    if args.recursive and not destdir:
        print ("--recursive requires destination to be a directory")
        return
    p.mount ()
    for fn in fns:
        ff = parse (fn, "$")
        ff2 = ff.copy ()
        if not ff.name[0]:
            print ("No file name given in", fn)
            continue
        fcount = 0
        tbytes = 0
        for dd in p.findufds (ff):
            fl = [ fd for fd in  sorted (dd.dir.findfiles (ff), key = _namekey) ]
            for fd in fl:
                bin = False
                if args.mode == mode_bin:
                    bin = True
                elif args.mode == mode_auto and \
                         r50toasc (fd.ne.unam[2]) not in deftext:
                    bin = True
                if bin:
                    mode = "rb"
                    omode = "wb"
                    tmode = "block"
                else:
                    mode = "r"
                    omode = "w"
                    tmode = "line"
                f = fd.open (mode)
                # todo: wild copies, recursive copies
                if destdir:
                    if args.recursive:
                        dirfn = "%03d%03d" % (fd.dir.ppn[1], fd.dir.ppn[0])
                        ofn = "%s/%s" % (dirfn, fd.strname ())
                    else:
                        ofn = fd.strname ()
                    ofn = os.path.join (dest, ofn)
                else:
                    ofn = dest
                if destdir or fcount == 0:
                    if args.recursive:
                        dirfn = os.path.join (dirfn)
                        try:
                            os.stat (dirfn)
                        except OSError:
                            os.mkdir (dirfn)
                    outf = open (ofn, omode)
                flen = 0
                while True:
                    d = f.read ()
                    if not d:
                        break
                    flen += len (d)
                    outf.write (d)
                f.close ()
                if destdir:
                    outf.close ()
                fcount += 1
                tbytes += flen
                if args.verbose:
                    if destdir or fcount == 1:
                        print ("%s => %s (%d bytes) in %s mode" % \
                               ( fd, ofn, flen, tmode))
                    else:
                        print ("%s =>> %s (%d bytes) in %s mode" % \
                               ( fd, ofn, flen, tmode))
        if not fcount:
            print ("No files matching %s" % ff2)
    if fcount and not destdir:
        outf.close ()
    if fcount > 1 and args.verbose:
        print ("Total files: %d, total bytes: %d" % (fcount, tbytes))

defrts = { "tsk" : "...rsx",
           "sav" : "rt11  ",
           "4th" : "forth ",
           "bas" : "basic ",
           "tec" : "teco  ",
           "com" : "dcl   ",
           "alc" : "algol ",
           "wps" : "wpsedt" }

# Regular expression for all the 8-bit values that aren't printable characters
# in the DEC MCS (DEC Std 170) character set.  That includes C0 and C1 control
# characters, plus the unused codes in the GR range.
_re_noprint = re.compile (b"[\x00-\x1f\x7f-\xa0\xa4\xa6\xac-\xaf\xb4\xb8\xbe\xd0\xde\xf0\xfe\xff]")
linedata = ctypes.c_ushort * 8
dump_parser = CmdParser (prog = "dump",
                         short = "Dump file contents.",
                         description = """Dump file contents.  If a PPN is
                         given but no name, dumps the directory.  If no
                         filespecs are given, dumps the disk
                         (non-file-structured)""")
dump_parser.add_argument ("filename", metavar = "FN",
                          nargs = "*",
                          help = "File to dump")
dump_parser.add_argument ("-x", "--hex", action = "store_true", default = False,
                          help = "hex output (instead of default octal)")
dump_parser.add_argument ("-w", "--wide",
                          action = "store_true", default = False,
                          help = "wide output (add rad50)")
dump_parser.add_argument ("-s", "--start", metavar = "BLK",
                          help = "start at block BLK")
dump_parser.add_argument ("-e", "--end", metavar = "BLK",
                          help = "end at block BLK")
def _dumpfile (f, args, start, end, name):
    blk = start
    f.seek (blk * BLKSIZE)
    while True:
        b = f.read (BLKSIZE)
        if not b:
            break
        print ("%s block %d" % (name, blk))
        blk += 1
        if len (b) < BLKSIZE:
            b += bytes (BLKSIZE - len (b))
        for offset in range (0, BLKSIZE, 16):
            d = b[offset:offset + 16]
            l = linedata.from_buffer_copy (d)
            if args.hex:
                print ("%03x/" % offset, end = "")
                for w in l:
                    print (" %04x" % w, end = "")
            else:
                print ("%03o/" % offset, end = "")
                for w in l:
                    print (" %06o" % w, end = "")
            asc = _re_noprint.sub (b".", d).decode ("dec-mcs")
            if args.wide:
                pass
                print (" ", asc, end = "")
                for w in l:
                    print ("", r50toasc (w), end = "")
                print ()
            else:
                print (" ", asc)
        if end is not None and blk > end:
            break
    f.close ()

@command (dump_parser)
def dodump (p, args):
    """Execute a "dump" command.
    """
    start = args.start
    end = args.end
    if start:
        start = int (start)
    else:
        start = 0
    if end is not None:
        end = int (end)
    if not args.filename:
        _dumpfile (p.f, args, start, end, "RSTS disk")
        return
    fcount = 0
    p.mount ()
    for fn in args.filename:
        ff = parse (fn, "$")
        ff2 = ff.copy ()
        if 0:#not ff.name[0]:
            print ("No file name given in", fn)
            continue
        for dd in p.findufds (ff):
            if ff.name[0]:
                fl = [ fd for fd in  sorted (dd.dir.findfiles (ff),
                                             key = _namekey) ]
            else:
                fl = [ dd ]
            for fd in fl:
                f = fd.open ("rb")
                _dumpfile (f, args, start, end, "File: %s" % fd)
                fcount += 1
        if not fcount:
            print ("No files matching %s" % ff2)

put_parser = CmdParser (prog = "put",
                        short = "Put file to the RSTS file system.",
                        description = """Put file to the RSTS file system.
                        If "dest" is a file, and there are multiple inputs,
                        they are concatenated into "dest".  If "dest" is a
                        directory, each input file produces a separate
                        output file of the same name in that directory.""")
put_parser.add_argument ("filename", metavar = "src",
                         nargs = "+",
                         help = "File to copy")
put_parser.add_argument ("dest", help = "Destination spec")
put_parser.add_argument ("-v", "--verbose",
                         action = "store_true", default = False,
                         help = "verbose (show file names)")
put_parser.add_argument ("-a", "--ascii",
                         action = "store_const", const = mode_ascii,
                         dest = "mode", default = mode_auto,
                         help = "force ASCII (text) mode transfer")
put_parser.add_argument ("-b", "--binary",
                         action = "store_const", const = mode_bin,
                         dest = "mode", 
                         help = "force binary mode transfer")
put_parser.add_argument ("-R", "--recursive",
                         action = "store_true", default = False,
                         help = """Copy recursively (build directory tree).
                         FIXME:
                         "dest" must be a directory.  Output file names are
                         xxxyyy/name.ext where xxx and yyy are
                         the project and programmer number of the RSTS file.""")
put_parser.add_argument ("-p", "--preserve",
                         action = "store_true", default = False,
                         help = """Preserve timestamps and (to the extent they
                         carry over) file modes (protection code, in RSTS
                         terms).""")

@command (put_parser)
def doput (p, args):
    """Execute a "put" command.
    """
    print (args)
    fns = args.filename
    dest = args.dest
    try:
        srcdir = len (fns) == 1 and S_ISDIR (os.stat (fns[0])[ST_MODE])
    except OSError:
        srcdir = False
    if args.recursive and not srcdir:
        print ("--recursive requires source to be a directory")
        return
    return # TEMP TEMP TEMP
    p.mount ()
    for fn in fns:
        ff = parse (fn, "$")
        ff2 = ff.copy ()
        if not ff.name[0]:
            print ("No file name given in", fn)
            continue
        fcount = 0
        tbytes = 0
