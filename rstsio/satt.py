#!

from .fldef import *
from . import disk

# Compute a table of bitcounts for integers in range (1<<BCBITS):
BCBITS = 8
bctable = [ 0 ]
for i in range (BCBITS):
    bctable.extend ([c + 1 for c in bctable])
bctable = bytes (bctable)
bcmask = (1 << BCBITS) - 1

def bitcount (n):
    if n < 0:
        raise ValueError (n)
    b = 0
    while n:
        b += bctable[n & bcmask]
        n >>= BCBITS
    return b

class _dummydisk (object):
    def __init__ (self):
        self.ronly = self.ronlypack = False
        
class Satt (object):
    """This class wraps the [0,1]satt.sys file and defines operations
    on it, such as allocating or releasing clusters.
    """
    def __init__ (self, p, newsatt = False):
        """Create the Satt object for the supplied pack.  If "newsatt"
        is True, build a new Satt for a newly initialized file system.
        In that case, the dcs, pcs, and clurat attributes of the
        supplied pack must be already set.  The new Satt will have
        pack cluster 0 (for the pack label) marked as allocated,
        as well as the clusters for the Satt, but no others.  The
        current satt position will be set to the middle of the disk,
        as is the usual default for placement of initial file system
        items.
        """
        self.pack = p
        self.sattpos = 0
        self.sattsize = (p.sz - p.dcs) // p.pcs   # Number of pack clusters
        # Calculate number of clusters in satt.sys
        sattrc, t = divmod (self.sattsize, p.pcs * BLKSIZE * 8)
        if t:
            sattrc += 1
        self.pcs = p.pcs
        self.clurat = p.clurat
        if newsatt:
            dd = _dummydisk ()
            pcs = p.pcs
            self.clusters = [ disk.Cluster (disk = dd, dcn = None,
                                            clusters = pcs)
                              for i in range (sattrc) ]
            # To get started, mark in use:
            # a. pack cluster 0 (pack label)
            # b. pack clusters beyond the end
            self.clusters[0][0] = 1
            off, bitpos = divmod (self.sattsize, 8)
            lc, off = self._satbuf (off)
            if off:
                if bitpos:
                    lc[off] = (0xff << bitpos) & 0xff
                    off += 1
                for i in range (off, len (lc)):
                    lc[i] = 0xff
            self.sattpos = self.sattsize // 2
            realclu = self.getclu (pcs, sattrc)
            # Copy the temporary bitmap buffers to the allocated
            # cluster buffers, then make the allocated ones the
            # buffers we use (freeing the others).
            for i in range (sattrc):
                realclu[i][:] = self.clusters[i]
                realclu[i].touch ()
            self.clusters = realclu
        else:
            sattfd = p.lookup ("[0,1]satt.sys")
            if sattfd.ae.uclus != p.pcs:
                raise Corrupt ("satt.sys cluster size is not pack cluster size")
            self.clusters = [ p.read (c, sattfd.ae.uclus)
                              for c in sattfd.rlist if c  ]
            if len (self.clusters) != sattrc:
                raise Corrupt ("satt.sys cluster count is %d, expecting %d" % (len (self.clusters), sattrc))
        self.inuse = 0
        for c in self.clusters:
            for b in c:
                self.inuse += bitcount (b)
        
    def _checkclu (self, clusiz):
        # Note that clusiz 16 is legal for large cluster packs,
        # for use by directories.
        if not (clusiz == 16 and self.pcs > 16):
            if (clusiz % self.pcs) != 0 or clusiz > 256:
                raise Badclu
        bitcnt = clusiz // self.pcs
        if not bitcnt:
            # special case clusiz 16 on large packs, use one cluster
            bitcnt = 1
        mask = (1 << bitcnt) - 1
        return bitcnt, mask

    def _satbuf (self, off):
        # Return the buffer which contains SATT byte offset "off",
        # and the offset within that buffer
        clu, off = divmod (off, self.pcs * BLKSIZE)
        return self.clusters[clu], off

    def _isfree (self, pos, bytecnt, mask):
        if bytecnt == 0:
            # Partial byte search
            off, bitpos = divmod (pos, 8)
            b, boff = self._satbuf (off)
            return (b[boff] & (mask << bitpos)) == 0
        else:
            b, boff = self._satbuf (pos // 8)
            return b[boff:boff + bytecnt] == b'\x00' * bytecnt

    def _mark (self, pos, bytecnt, mask):
        if bytecnt == 0:
            # Partial byte search
            off, bitpos = divmod (pos, 8)
            b, boff = self._satbuf (off)
            if (b[boff] & (mask << bitpos)) == 0:
                b[boff] |= mask << bitpos
                b.touch ()
            else:
                raise Internal ("Marking in-use but cluster is not free")
        else:
            b, boff = self._satbuf (pos // 8)
            if b[boff:boff + bytecnt] == b'\x00' * bytecnt:
                b[boff:boff + bytecnt] = b'\xff' * bytecnt
                b.touch ()
            else:
                raise Internal ("Marking in-use but cluster is not free")
        
    def getclu (self, clusiz: int = 0, count = 1, startpos: int = None):
        """Allocate "count" free clusters of size "clusiz".  Returns a list
        of new buffers (zeroed buffer) for that cluster.  Start search at 
        supplied DCN, or the most recent allocation position if none.
        """
        if not clusiz:
            clusiz = self.pcs
        # bitcnt is the number of bits per file cluster.
        bitcnt, mask = self._checkclu (clusiz)
        if startpos is None:
            startpos = self.sattpos
        else:
            startpos = self.pack.dcntopcn (startpos)
        pos = startpos
        wrapped = False
        # Align the starting position to a cluster boundary
        pos = (pos // bitcnt) * bitcnt
        bytecnt = bitcnt // 8
        while True:
            spos = pos
            for i in range (count):
                if not self._isfree (pos, bytecnt, mask):
                    break
                pos += bitcnt
                if pos >= self.sattsize:
                    break
            else:
                self.inuse += bitcnt
                pos = spos
                for i in range (count):
                    self._mark (pos, bytecnt, mask)
                    pos += bitcnt
                spos = self.pack.pcntodcn (spos)
                self.sattpos = spos
                return [ self.pack.newclu (spos + i, clusiz)
                         for i in range (count) ]
            pos += bitcnt
            if pos > self.sattsize - count * bitcnt:
                if wrapped:
                    raise Noroom
                wrapped = True
                pos = 0
    
    def retclu (self, dcn: int, clusiz: int):
        """Free a cluster.  The arguments are starting DCN and cluster size.
        """
        bitcnt, mask = self._checkclu (clusiz)
        pos = self.pack.dcntopcn (dcn, check = True)
        if pos % bitcnt:
            raise Corrupt ("Misaligned file cluster: %d" % dcn)
        self.pack.invalidate (dcn, clusiz)
        off, bitpos = divmod (pos, 8)
        # Note that we only reference one buffer, because clusters
        # are naturally aligned.
        b, off = self._satbuf (off)
        if bitcnt < 8:
            # Partial byte free
            mask <<= bitpos
            if (b[off] & mask) != mask:
                raise Internal ("Freeing a cluster that is not in use: %d" % dcn)
            b[off] &= ~mask
        else:
            bytecount = bitcnt // 8
            if b[off:off + bytecount] != b'\xff' * bytecount:
                raise Internal ("Freeing a cluster that is not in use: %d" % dcn)
            b[off:off + bytecount] = bytes (bytecount)
        self.inuse -= bitcnt
        b.touch ()
