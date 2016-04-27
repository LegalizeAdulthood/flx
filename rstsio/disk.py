
import io
import os
import errno
import stat
from .common import *

# Dictionary of disk types; the values are triples of total size,
# rsts used size, and dec166 (bad block list) flag
_sizetbl = { "rx50" : ( 800, 800, False ),
            "rf11" : ( 1024, 1024, False ),
            "rs03" : ( 1024, 1024, False ),
            "rs04" : ( 2048, 2048, False ),
            "rk05" : ( 4800, 4800, False ),
            "rl01" : ( 10240, 10220, True ),
            "rl02" : ( 20480, 20460, True ),
            "rk06" : ( 27126, 27104, True ),
            "rk07" : ( 53790, 53768, True ),
            "rp04" : ( 171798, 171796, False ),
            "rp05" : ( 171798, 171796, False ),
            "rp06" : ( 340670, 340664, False ),
            "rp07" : ( 1008000, 1007950, True ),
            "rm02" : ( 131680, 131648, True ),
            "rm03" : ( 131680, 131648, True ),
            "rm05" : ( 500384, 500352, True ),
            "rm80" : ( 251328, 242575, True ) }

def _rstssize (s):
    for t, r, dec166 in _sizetbl.values ():
        if t == s:
            return r, dec166, _getdcs (r)
    return s, False, _getdcs (s)

def _getdcs (s):
    s = (s - 1) >> 16
    dcs = 1
    while s:
        s >>= 1
        dcs <<= 1
    if dcs > 64:
        raise Baddcs
    return dcs

class Disk: pass

class Cluster (bytearray):
    """A buffer holding some disk cluster
    """
    def __init__ (self, disk: Disk, dcn: int , clusters: int):
        super ().__init__ (clusters * BLKSIZE)
        self.disk = disk
        self.dcn = dcn
        self.clusters = clusters
        self.dirty = False

    def map (self, struct: type, off: int = 0):
        """Map a ctypes struct onto the buffer of a Cluster, at
        the supplied offset.  Return the object.
        """
        s = struct.from_buffer (self, off)
        s.clu = self
        return s
    
    def touch (self):
        """Mark the buffer of the cluster as modified.
        """
        if self.disk.ronly or self.disk.ronlypack:
            raise Internal ("attempt to change data on a read-only disk")
        self.dirty = True

zlen = BLKSIZE
zero = bytes (zlen)

class Disk (object):
    """A disk for use by FLX.  Here we do the block level I/O
    and the device size handling.
    """
    def __init__ (self, name, ronly = True):
        self.name = name
        self.ronly = self.ronlypack = ronly
        self.clucache = dict ()
        if ronly:
            mode = "rb"
        else:
            mode = "r+b"
        try:
            self.f = io.open (name, mode)
        except FileNotFoundError:
            self.f = None
            if ronly:
                raise
            self.fd = None
            self.tsz = self.sz = 0
            self.dec166 = self.raw = False
            return
        s = os.fstat (self.f.fileno ())
        self.raw = not stat.S_ISREG (s.st_mode)
        if self.raw:
            self.tsz = 0 # TBD
        else:
            self.tsz = s.st_size // BLKSIZE
        self.sz, self.dec166, self.dcs = _rstssize (self.tsz)

    def exists (self):
        """Returns True if the disk container file currently exists.
        (If not, it can be created with the "create" method.)
        """
        return self.f is not None
    
    def create (self, sz: (int, str)):
        """Create a container, if the specified container doesn't
        currently exist.
        """
        if self.exists ():
            raise Internal ("attempt to create a container that already exists")
        try:
            self.tsz = int (sz)
            self.sz, self.dec166, self.dcs = _rstssize (self.tsz)
        except ValueError:
            try:
                self.tsz, self.sz, self.dec166 = _sizetbl[sz.lower ()]
                self.dcs = _getdcs (self.sz)
            except KeyError:
                raise FlxError ("invalid disk size")
        if self.exists ():
            raise Internal ("disk already exists after it didn't")
        if self.ronly:
            raise Ropack
        self.f = io.open (self.name, "w+b")
        # Extend the new container
        self.f.truncate (self.tsz * BLKSIZE)
        
    def _seekblk (self, b):
        if b >= self.tsz or b < 0:
            raise Badblk
        self.f.seek (b * BLKSIZE, io.SEEK_SET)

    def _seekdcn (self, d):
        self._seekblk (d * self.dcs)

    def _readinto (self, dcn, cluster):
        if dcn in self.clucache:
            raise Internal ("block cache conflict")
        self._seekdcn (dcn)
        self.f.readinto (cluster)

    def read (self, dcn: int, clusiz: int = 0) -> Cluster:
        """Return a Cluster object (basically a buffer) holding
        the requested data.  The read starts at the supplied
        device cluster number; the resulting CLuster buffer
        size is "clusiz" blocks.  The default for clusiz is
        the device cluster size.
        """
        if not clusiz:
            clusiz = self.dcs
        elif clusiz < self.dcs or clusiz > 256:
            raise Badbuf
        try:
            return self.clucache[dcn]
        except KeyError:
            pass
        clu = Cluster (self, dcn, clusiz)
        self._readinto (dcn, clu)
        self.clucache[dcn] = clu
        return clu
    
    def newclu (self, dcn: int, clusiz: int = 0) -> Cluster:
        """Return a Cluster object (basically a buffer) for the
        given dcn, zeroed.  This avoids the read if we're going
        to write the dcn.  Typically this method would be used
        to operate on newly allocated clusters.
        """
        if not clusiz:
            clusiz = self.dcs
        elif (clusiz % self.dcs) != 0 or clusiz > 256:
            raise Badclu
        self.invalidate (dcn)
        clu = Cluster (self, dcn, clusiz)
        self.clucache[dcn] = clu
        return clu

    def flush (self, dcn: int = None):
        """Flush a cluster, or the whole cache.
        """
        if dcn is None:
            for clu in self.clucache.values ():
                self._flush (clu)
        else:
            try:
                self._flush (self.clucache[dcn])
            except KeyError:
                pass

    def _flush (self, clu):
        if clu.dirty:
            if self.ronly or self.ronlypack:
                print ("ignoring write on read-only disk, dcn", clu.dcn)
                return
            self._seekdcn (clu.dcn)
            self.f.write (clu)
            clu.dirty = False

    def invalidate (self, dcn: int):
        """Discard a Cluster from the cache.
        """
        try:
            clu = self.clucache[dcn]
            self._flush (clu)
            del self.clucache[dcn]
        except KeyError:
            pass

    def _invalidate_all (self):
        self.clucache = dict ()
        
