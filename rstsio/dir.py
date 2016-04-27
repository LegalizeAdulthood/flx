#!

import re
from .common import *
from .fldef import *
from .rstsfile import Filedata

class Dir (object):
    """Base class for RSTS directories of all types
    """
    def __init__ (self, pack, dcn, type = UFD):
        self.clusters = list ()
        self.type = type
        self.pack = pack
        #print ("dir cluster 0 at", dcn)
        c1 = pack.read (dcn)
        self.dirlabel = l = c1.map (ufdlabel, 0)
        if dcn == 1:
            # RDS0 MFD
            self.ppn = [1, 1]
        else:
            self.ppn = l.lppn
        cmap = c1.map (fdcm, fdcm_off)
        dclus = cmap.uclus
        # Weirdness: normally clustersize must be >= pack cluster size,
        # but directories are limited to clustersize 16.  So on "large packs",
        # clustersize 16 is used even if pcs is larger.
        if (pack.pcs > 16 and dclus != 16) or \
           (dclus % pack.pcs) != 0:
            raise Badclu
        #print ("dir cluster size", dclus)
        if dclus != c1.clusters:
            # Need to re-read the first cluster
            pack.invalidate (dcn)
            c1 = pack.read (dcn, dclus)
            cmap = c1.map (fdcm, fdcm_off)
        self.clusters.append (c1)
        for c in range (1, 7):
            dcn = cmap.uent[c]
            #print ("clumap", c, "is", dcn)
            if dcn:
                self.clusters.append (pack.read (dcn, dclus))
        self.clusiz = cmap.uclus

    def extend (self):
        """Add another cluster to this directory.
        """
        if len (self.clusters) == 7:
            raise Noroom
        self.clusters.extend (self.pack.getclu (self.clusiz))
        newdcn = self.clusters[-1].dcn
        # reload cluster map in block 0
        # note that we update all of it; this matters in the case
        # where prior to the extent there was no allocation at all,
        # as can happen for UFDs.
        cmap = self.clusters[0].map (fdcm, fdcm_off)
        cmap.uclus = self.clusiz
        cmap.uflag = fd_new if not isinstance (self, Ufd) else 0
        for i, c in enumerate (self.clusters):
            cmap.uent[i] = c.dcn
        # copy updated cluster map to rest of cluster 0, skipping
        # table blocks in GFD/MFD
        for b in range (3 if cmap.uflag & fd_new else 1, self.clusiz):
            cmap2 = self.clusters[0].map (fdcm, fdcm_off + (b * BLKSIZE))
            cmap2.uclus = cmap.uclus
            cmap2.uflag = cmap.uflag
            cmap2.uent[:] = cmap.uent
        self.clusters[0].touch ()
        # copy updated cluster map to each block of the other clusters
        for c in self.clusters[1:]:
            for b in range (self.clusiz):
                cmap2 = c.map (fdcm, fdcm_off + (b * BLKSIZE))
                cmap2.uclus = cmap.uclus
                cmap2.uflag = cmap.uflag
                cmap2.uent[:] = cmap.uent
            c.touch ()

    def getent (self) -> int:
        """Get a free directory entry.  Returns the link word for
        that entry.  The directory is extended if necessary.
        If there is no space, Noroom is raised.
        The entry in memory is updated to set the ul_use bit in
        the first word, which will make it appear allocated so
        subsequent calls to this method will not return the same
        entry again.  It's up to the caller to write the actual
        intended value and to call the "touch" method.  Conversely,
        if the entry is not needed after all, it must be freed.
        """
        for c in range (len (self.clusters)):
            for b in range (self.clusiz):
                for off in range (0, fdcm_off, ent_size):
                    if c == 0 and b in ( 1, 2 ) and not isinstance (self, Ufd):
                        # Skip MFD/GFD table blocks
                        continue
                    l = self.pack (c, b, off)
                    r = self.map (ufdre, l)
                    if r.ulnk == 0 and r.uent[0] == 0:
                        r.ulnk = ul_use
                        return l
        # No room, extend if possible
        self.extend ()
        # If the extend succeeded, the first entry in the new
        # cluster is now available
        l = self.pack (len (self.clusters) - 1, 0)
        r = self.map (ufdre, l)
        r.ulnk = ul_use
        return l

    def retent (self, l: int):
        """Free a directory entry, given its link word.  Note that
        only the first two words of the entry are freed, which is
        the minimum required; that leaves part of the original data
        still in place.
        """
        r = self.map (ufdre, l)
        if r.ulnk == 0 and r.uent[0] == 0:
            raise Internal ("Freeing a directory entry that is already free")
        r.ulnk = r.uent[0] = 0
        self.touch (l)
        
    def pack (self, c: int, b: int, off: int  = None) -> int:
        """Pack an entry pointer into a link word.  Arguments
        are cluster number, block number, and offset in block,
        or alternatively cluster number and offset within cluster.
        Return value is a link word.
        """
        if off is not None:
            b = b * BLKSIZE + off
        b, off = divmod (b, BLKSIZE)
        if off == 0o760 or b >= self.clusiz or c >= len (self.clusters) \
               or (c == 0 and b in ( 1, 2 ) and not isinstance (self, Ufd)) \
               or off % ent_size != 0:
            raise Badlnk
        return (c << sl_clo) + (b << sl_blo) + off
    
    def unpack (self, l: ulk) -> int:
        """Unpack a directory link word.  Returns cluster buffer and
        byte offset within cluster.
        """
        c = l.ul_clo
        b = l.ul_blo
        off = l.ul_eno << 4
        #print (l, c, b, off)
        if off == 0o760 or b >= self.clusiz or c >= len (self.clusters) \
               or (c == 0 and b in ( 1, 2 ) and not isinstance (self, Ufd)):
            raise Badlnk
        off += b * BLKSIZE
        return self.clusters[c], off

    def map (self, struct: type, l: int):
        """Map the supplied structure on the directory data at the
        offset defined by the given link.
        """
        c, off = self.unpack (l)
        return c.map (struct, off)

    def touch (self, l: int):
        """Touch (mark as modified) the directory block that the
        supplied link points to.
        """
        c, off = self.unpack (l)
        c.touch ()
        
    def walklist (self, struct: type, lnk: int):
        """Iterator to walk the list starting at the supplied link,
        using the ulnk word in the supplied struct as the list link.
        Yields instances of the struct.
        """
        while not lnk:
            ent = self.map (struct, lnk)
            yield ent
            lnk = ent.ulnk

    def readlist (self, lnk: int) -> list:
        """Read the list of entries starting at the specified
        link.  Return a list containing the values (omitting link words).
        """
        return [ r for e in self.walklist (ufdre, lnk) for r in e.uent ]

    def readlistnz (self, lnk: int) -> list:
        """Read the list of non-zero entries starting at the specified
        link.  Return a list containing the values (omitting link words).
        """
        return [ r for e in self.walklist (ufdre, lnk) for r in e.uent if r ]

class Ufd (Dir):
    """A UFD (which doubles as MFD if it's [1,1] on an RDS 0 pack).
    """
    def __init__ (self, pack, dcn, type = UFD):
        super ().__init__ (pack, dcn, type)

    def __str__ (self):
        prog, proj = self.ppn
        return "[%d,%d]" % ( proj, prog )

    def __len__ (self):
        return len (list (self.walklist (ufdne, self.dirlabel.ulnk)))
        
    def findfiles (self, firqb: Firqb):
        """Find file entries matching the parsed file data in firqb.
        Each iteration returns a Filedata object reflecting what
        was found.  
        """
        fn = ascname (firqb.name, firqb.ext)
        fnre = re.compile (fn.replace (".", r"\.").replace ('?', '.') + '$', re.I)
        for ne in self.walklist (ufdne, self.dirlabel.ulnk):
            #print ("findfiles", oct(ne.ustat), ne.unam[0])
            if not (ne.ustat & us_ufd):
                fn2 = ascname (ne.unam[:2], ne.unam[2])
                if fnre.match (fn2):
                    yield Filedata (self, ne)
    
    def finddir (self, firqb):
        """Find directory entries matching the parsed file data in firqb.
        Each iteration returns a Filedata object reflecting what
        was found.  If nothing is found and no wildcard flags were
        present, raises Nosuch.  Note that this method is only valid
        on the [1,1] directory, which is the RDS0 MFD.
        """
        if self.type != MFD:
            raise Nosuch
        proj, prog = firqb.proj, firqb.prog
        matched = False
        for ne in self.walklist (gfdne, self.dirlabel.ulnk):
            #print ("finddir", oct(ne.ustat), ne.uproj, ne.uprog)
            if ne.ustat & us_ufd:
                if (prog == 255 or prog == ne.uprog) and \
                   (proj == 255 or proj == ne.uproj):
                    if proj == prog == 1:  # [1,1]
                        u = self
                    else:
                        if not ne.uar:
                            # PPN is defined but directory is not
                            # allocated, so skip (since we're interested
                            # in directory contents, so empty ones are
                            # irrelevant)
                            continue
                        u = Ufd (self.pack, ne.uar)
                    matched = True
                    fd = Filedata (u)
                    # On RDS0, the UFD label doesn't necessarily have
                    # the PPN in it, so supply it explicitly.
                    fd.dir.ppn = [ ne.uprog, ne.uproj ]
                    yield fd
        if not matched and prog != 255 and proj != 255:
            raise Nosuch
        
class Gfd (Dir):
    """A GFD or MFD on an RDS 1 pack.
    """
    def __init__ (self, pack, dcn, type = GFD):
        super ().__init__ (pack, dcn, type)

    def __str__ (self):
        if self.type == MFD:
            return "[*,*]"
        else:
            return "[%d,*]" % self.ppn[1]

    def __len__ (self):
        t = self.maptable ()
        l = 0
        for r in range (255):
            if t.ent[r]:
                l += 1
        return l
    
    def maptable (self, attr = False):
        """Map the child cluster table (default) or attribute table
        (if attr is True).  Returns the table object.
        """
        off = BLKSIZE
        if attr:
            off = 2 * BLKSIZE
        return self.clusters[0].map (gfdtable, off)
    
    def finddir (self, firqb):
        """Find directory entries matching the parsed file data in firqb.
        Each iteration returns a Filedata object reflecting what
        was found.  
        """
        if self.type == MFD:
            p = firqb.proj
            lower = Gfd
        else:
            p = firqb.prog
            lower = Ufd
        t = self.maptable ()
        if p is not None and p != 255:
            e = t.ent[p]
            if e:
                yield Filedata (lower (self.pack, e))
        else:
            for r in range (255):
                e = t.ent[r]
                if e:
                    yield Filedata (lower (self.pack, e))
                
    def getattr (self, firqb):
        """Lookup the entry matching the parsed data in firqb.
        Returns the attribute list.  Raises Nosuch if entry
        not found.
        """
        if self.type == MFD:
            p = firqb.proj
        else:
            p = firqb.prog
        t = self.maptable (attr = True)
        e = t.ent[p]
        if e:
            return readlist (e)
        raise Nosuch
