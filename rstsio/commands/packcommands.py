#!

from .common import *
from ..common import *
from ..fldef import *
from .. import rststime

ident_parser = CmdParser (prog = "ident",
                          description = "Prints label information for the pack.")

@command (ident_parser)
def doident (p, args):
    p.mount ()
    pl = p.label
    if True or pl.fill1 == 65535 and pl.ppcs > pl.ppcs and \
       ((pl.ppcs & (-pl.ppcs)) == pl.ppcs):
        print ("RSTS disk on %s -- \"%s\"" % 
               (p.name, (r50toasc (pl.pckid[0]) + r50toasc (pl.pckid[1])).strip ()))
        print     ("   Device clustersize:", p.dcs)
        print     ("   Pack clustersize:  ", pl.ppcs)
        if p.dcs > 1:
            print ("   Device size:        %d (%d DCNs)" % (p.sz, p.sz // p.dcs))
        else:
            print ("   Device size:       ", p.sz)
        print     ("   Revision level:     %d.%d" % (pl.plvl >> 8,
                                                     pl.plvl & 0o377))
        if pl.plvl >= RDS12:
            lmount = rststime.localtime (pl.mntdat, pl.mnttim)
            print ("   Last mount date:   ", rststime.ascdate (lmount))
            print ("   Last mount time:   ", rststime.asctime (lmount))
        print     ("   Pack flags:        ", end="")
        if pl.pstat & uc_mnt:
            print (" Dirty", end = "")
        if pl.pstat & uc_pri:
            print (" Private/system", end = "")
        else:
            print (" Public", end = "")
        if pl.pstat & uc_ro:
            print (" Read-only", end = "")
        if pl.pstat & uc_dlw:
            print (" DLW", end = "")
        if pl.pstat & uc_top:
            print (" NFF", end = "")
        print ()
    else:
        print ("Disk on %s does not appear to be a RSTS format disk", p.name)
