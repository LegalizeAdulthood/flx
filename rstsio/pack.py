#!

import io
from .common import *
from .fldef import *
from . import disk
from . import dir
from . import rstsfile
from . import satt

class Pack (disk.Disk):
    """Defines the operations on a RSTS pack (disk or container
    file with RSTS file structure).
    """
    
    def __init__ (self, name: str, ronly: bool = True):
        """Open a container file or device for use as a RSTS pack.
        Mode is read-only by default, unless ronly is passed as False.
        """
        super ().__init__ (name, ronly)
        self.mounted = False

    def mount (self, ronly: bool = True, *, override: bool = False):
        """Mount a pack (set up its file system state).
        The pack is mounted read-only unless ronly is False; if so,
        the read-only flag in the pack label will prevent writing
        unless the keyword-only argument "override" is supplied as True.
        This function will fail with an exception if called on a
        disk that does not exist ("exists" method returns False),
        or does not contain a valid RSTS file system.
        If mounting read-write, the pack is flagged as mounted and
        should be dismounted by calling "umount" when done.
        """
        if not self.exists ():
            raise Internal ("attempt to mount a non-existent disk")
        if self.ronly and not ronly:
            raise Internal ("attempt to mount read/write on read-only disk")
        if self.mounted:
            return
        plclu = self.read (1)
        pl = plclu.map (packlabel)
        if pl.ppcs < self.dcs or pl.ppcs not in (1, 2, 4, 8, 16, 32, 64):
            raise Corrupt
        if pl.pstat & uc_ro:
            if not ronly and not override:
                raise Ropack
        self.ronlypack = ronly
        self.label = pl
        self.clurat, t = divmod (pl.ppcs, self.dcs)
        if self.clurat < 1 or t != 0:
            raise Badclu
        self.pcs = pl.ppcs
        if pl.plvl == RDS0:
            mfd = dir.Ufd (self, 1, MFD)
            plclu = mfd.clusters[0]
            pl = plclu.map (packlabel)
        elif pl.plvl in (RDS11, RDS12):
            mfd = dir.Gfd (self, pl.mdcn, MFD)
        else:
            raise Corrupt
        self.mfd = mfd
        self.satt = satt.Satt (self)
        if not ronly:
            self.mounted = True

    def umount (self):
        """Dismount a pack.
        """
        if self.mounted:
            self.flush ()
            self.mounted = False
            self.label = self.clurat = self.pcs = self.mfd = self.satt = None
            
    def initialize (self, packid: str,
                    override: bool = False, ronly: bool = True,
                    pcs: int = None, plevel: int = RDS12,
                    public: bool = False):
        """(Re)initialize a RSTS pack.  If called on a pack
        that already appears to have a valid file structure,
        "override" must be True.  The remaining arguments
        specify the pack parameters.  On completion, the
        file system is all set up and the pack is not
        mounted.
        """
        if self.mounted:
            raise Internal ("attempt to initialize a mounted disk")
        if not self.exists ():
            raise Internal ("attempt to initialize a non-existent disk")
        try:
            self.mount ()
            self.umount ()
        except FlxError:
            override = True
        if not override:
            raise Internal ("attempt to reinitialize a pack without -force")
        if pcs < self.dcs or pcs not in (1, 2, 4, 8, 16, 32, 64):
            raise Badclu
        if '?' in packid:
            raise Badfn ("invalid pack label")
        id = [ rad50 (packid[0:3]), rad50 (packid[3:6]) ]
        if plevel not in (RDS0, RDS11, RDS12):
            raise ValueError ("invalid pack level")
        self.pcs = pcs
        self._invalidate_all ()
        
    def pcntodcn (self, pcn: int) -> int:
        return pcn * self.clurat + 1

    def dcntopcn (self, dcn: int, check = False) -> int:
        ret, t = divmod ((dcn - 1), self.clurat)
        if check and t:
            raise Corrupt ("Misaligned pack cluster: %d" % dcn)
        return ret

    def getclu (self, clusiz: int = 0, count = 1, startpos: int = None):
        """Allocate "count" free clusters of size "clusiz".  Returns a list
        of new buffers (zeroed buffer) for that cluster.  Start search at 
        supplied DCN, or the most recent allocation position if none.
        """
        return self.satt.getclu (clusiz, count, startpos)
    
    def retclu (self, dcn: int, clusiz: int):
        """Free a cluster.  The arguments are starting DCN and cluster size.
        """
        self.satt.retclu (dcn, clusiz)
        
    def lookup (self, f: (str, Firqb), dirok = False) -> rstsfile.Filedata:
        """Look up the entry by file name or firqb contents.
        Returns a Filedata object, or raises Nosuch if the
        entry is not found.  The filespec must not be wild.

        If dirok is True, a directory is returned if the name
        is null; if false, the name must not be null and only
        fils are returned.
        """
        f = parse (f)
        if f.wild:
            raise Badfn
        if not f.name[0]:
            # Looking for a directory; find out what kind.
            if not dirok:
                raise Nosuch
            if f.proj is None:
                # MFD
                return rstsfile.Filedata (self.mfd)
            if f.prog is None:
                # GFD.  On RDS0 there is no such thing, so we
                # will return the MFD, but only if there is a matching
                # project number.
                if self.label.plvl == RDS0:
                    f.prog = 255
                    try:
                        next (self.mfd.finddir (f))
                        return rstsfile.Filedata (self.mfd)
                    except StopIteration:
                        raise Nosuch
                else:
                    try:
                        return next (self.mfd.finddir (f))
                    except StopIteration:
                        raise Nosuch
            else:
                # UFD.  Look for it and return it.
                return self.findufd (f)
        # File lookup.  First find the UFD, then look in it.
        u = self.findufd (f).dir
        try:
            return next (u.findfiles (f))
        except StopIteration:
            raise Nosuch

    def findufds (self, f: (str, Firqb)) -> rstsfile.Filedata:
        """Iterate through the directories matched by the firqb.
        Yield Filedate objects for each UFD that matches the
        supplied Firqb.  If there are no matches, nothing
        is yielded (no error is generated).
        """
        f = parse (f)
        if f.proj is None or f.prog is None:
            raise Badfn
        if self.label.plvl == RDS0:
            # Simply iterate through the MFD
            for u in self.mfd.finddir (f):
                yield u
        else:
            for g in self.mfd.finddir (f):
                for u in g.dir.finddir (f):
                    yield u
    
    def findufd (self, f: (str, Firqb)) -> rstsfile.Filedata:
        """Look up a UFD by file name or firqb contents.
        Returns a Filedata object, or raises Nosuch if the
        UFD is not found.  The filespec must not be wild.
        """
        f = parse (f)
        if f.wild:
            raise Badfn
        try:
            return next (self.findufds (f))
        except StopIteration:
            raise Nosuch

    def open (self, f: str, mode: str = "r",
              encoding: str = None, errors: str = None):
        """Open a file on the pack.  Return a file object suitable for
        reading and/or writing (depending on what the mode says) as usual.
        
        The arguments are the same as the built-in open() function except for:
        - "buffering" is not supported (buffered mode is always used).
        - "encoding" defaults to "dec-mcs" (if text mode)
        - "newline" is not supported; instead, the newlines in the
          file are translated to and from \\n unconditionally.
        """
        if not isinstance (f, (rstsfile.Filedata, Firqb, str)):
            raise TypeError ("Pack.open argument 1 must be Filedata, Firqb, or string, not %s" % type(f).__name__)
        if not isinstance (f, rstsfile.Filedata):
            f = parse (f)
            f = self.lookup (f)
        return f.open (mode, encoding, errors)
