#!

"""This module defines file stream classes for files on RSTS packs.
"""

from .common import *
from .fldef import *
import io

class RstsRawIO (io.RawIOBase):
    def __init__ (self, fd, mode = "rb"):
        if not isinstance (mode, str):
            raise TypeError ("mode must be string, not %s" % type(mode).__name__)
        modes = set (mode)
        if modes - set ("arwb+t"):
            raise ValueError ("invalid mode: %r" % mode)
        reading = "r" in modes
        writing = "w" in modes
        appending = "a" in modes
        updating = "+" in modes
        binary = "b" in modes
        text = "t" in modes or not binary
        if text and binary:
            raise ValueError ("can't have text and binary modes at once")
        if reading + writing + appending != 1:
            raise ValueError ("must have exactly one of read/write/append mode")
        p = fd.dir.pack
        if not reading and (p.ronly or p.ronlypack):
            raise Ropack
        self.ronly = reading
        self.fd = fd
        if appending:
            self.seek (0, io.SEEK_END)
        else:
            self.seek (0)

        # Unlike regular Python files, we do line translation here,
        # if text mode is used.
        # The main reason is that RMS variable length records have to
        # be handled in binary form, and with awareness of block boundaries,
        # so it works well here.  And by doing it in the raw I/O stage,
        # the fact that I/O lenths may be shortened isn't a problem.
        #
        # set default = no newline translation, no rms records
        self.newline = b'\n'
        self.rms = 0
        self.recsize = 0
        self.attr = 0
        if text:
            if not fd.rms1:
                # Native RSTS file, so CRLF line endings
                self.newline = b"\r\n"
            elif (fd.rms1.fa_typ & fa_org) == fo_seq:
                rfm = fd.rms1.fa_typ & fa_rfm
                rat = fd.rms1.fa_typ & fa_rat
                # Stream and undefined are treated as stream formats.
                # For now, treat VFC that way also, pending later implementation.
                if rfm == rf_stm or rfm == rf_udf or rfm == rf_stm:
                    self.newline = b"\r\n"
                else:
                    self.rms = rfm
                    self.recsize = fd.rms1.fa_rsz
                    self.attr = rat
                
    def readable (self) -> bool:
        return True

    def seekable (self) -> bool:
        return True

    def writable (self) -> bool:
        return not self.ronly

    def isatty (self) -> bool:
        return False
    
    def seek (self, offset: int, whence: int = io.SEEK_SET) -> int:
        """Change stream position.

        Change the stream position to byte offset offset. offset is
        interpreted relative to the position indicated by whence.  Values
        for whence are:

        * 0 -- start of stream (the default); offset should be zero or positive
        * 1 -- current stream position; offset may be negative
        * 2 -- end of stream; offset is usually negative

        Return the new absolute position.
        """
        if whence == io.SEEK_CUR:
            offset += self.pos
        elif whence == io.SEEK_END:
            offset = self.fd.bsize - offset
        self.pos = offset
        return offset

    def tell (self) -> int:
        """Return current stream position."""
        return self.pos

    def _read (self, n = -1):
        fd = self.fd
        clusiz = fd.clusiz
        cnum, coff = divmod (self.pos, clusiz * BLKSIZE)
        if fd.isdir:
            # Reading a directory.  Those are read-ahead, into fd.dir.clusters.
            if cnum >= len (fd.dir.clusters):
                return b''
        else:
            if cnum >= len (fd.rlist):
                return b''
        rlen = clusiz * BLKSIZE - coff
        if n >= 0 and n < rlen:
            rlen = n
        if self.pos + rlen > self.fd.bsize:
            rlen = self.fd.bsize - self.pos
            if rlen <= 0:
                return b''
        if fd.isdir:
            self.pos += rlen
            return fd.dir.clusters[cnum][coff:coff + rlen]
        b = fd.dir.pack.read (fd.rlist[cnum], clusiz)
        if not self.rms:
            self.pos += rlen
            ret = b[coff:coff + rlen]
            if self.newline != b"\n":
                ret = ret.replace (self.newline, b"\n")
            return ret
        # Bytes left in current block
        left = BLKSIZE - (coff & (BLKSIZE - 1))
        if self.rms == rf_fix:
            reclen = self.recsize
            # If span, check if we have to go to the next block
            if self.attr & ra_spn:
                if left < reclen:
                    self.pos += left
                    return self._read (n)
                
            ret = b[coff:coff + reclen]
            self.pos += reclen
        else:
            # Variable length record
            reclen = b[coff] + b[coff + 1] * 256
            if reclen == 65535:
                # Skip rest of block marker.  Position at next block
                # and handle that by recursion
                self.pos += left
                return self._read (n)
            
            ret = b[coff + 2:coff + 2 + reclen]
            if reclen & 1:
                self.pos += reclen + 3
            else:
                self.pos += reclen + 2
        if len (ret) < reclen:
            # Record crosses end of cluster.  Note that this code works
            # for both fixed and variable record formats
            b2 = fd.dir.pack.read (fd.rlist[cnum + 1], clusiz)
            ret += b2[:reclen - len (ret)]
        if self.attr & ra_imp:
            reclen += 1
        if rlen > reclen:
            rlen = reclen
        if self.attr & ra_imp:
            ret += b'\n'
        else:
            ret = ret.replace (b"\r\n", b"\n")
        return ret[:rlen]

    def read(self, n: int = -1) -> bytes:
        """Read and return up to n bytes.

        Returns an empty bytes object on EOF.
        """
        return bytes (self._read (n))
    
    def readinto(self, b: bytearray) -> int:
        """Read up to len(b) bytes into b.

        Returns number of bytes read (0 for EOF).
        """
        b2 = self._read (len (b))
        ret = len (b2)
        if ret:
            b[:ret] = b2
        return ret
    
class RstsTextIOWrapper (io.TextIOWrapper):
    def __init__ (self, bfile, encoding = "dec-mcs", errors = None):
        super ().__init__ (bfile, encoding = encoding, errors = errors,
                           newline = '\n')

_re_eofpad = re.compile (b"\000*$")
class Filedata (object):
    """A container for information about a file found.
    """
    def __init__ (self, d, ne = None):
        """Build the file information for directory d.  If ne is
        supplied, that's the name entry for the file; otherwise
        store information for the directory itself.
        """
        self.dir = d
        if ne is None:
            self.isdir = True
            self.clusiz = d.clusiz
            self.bsize = len (d.clusters) * self.clusiz * BLKSIZE
        else:
            self.isdir = False
            self.ne = ne
            self.ae = d.map (ufdae, ne.uaa)
            cs = self.clusiz = self.ae.uclus
            self.rlist = d.readlistnz (ne.uar)
            self.size = sz = self.ae.usiz
            if self.ae.urts[0] == 0:
                self.size = sz = sz + (self.ae.urts[1] << 16)
            if (sz + cs - 1) // cs > len (self.rlist):
                # Too few retrieval entries for file...
                raise Corrupt
            self.rms1 = self.rms2 = None
            if not self.ae.ulnk:
                self.rms1 = d.map (ufdrms1, self.ae.ulnk)
                self.bsize = (self.rms1.fa_eof.value - 1) * BLKSIZE + \
                             self.rms1.fa_eofb
                if not self.rms1.ulnk:
                    self.rms2 = d.map (ufdrms2, self.rms1.ulnk)
            else:
                # Adjust size to account for any padding in the last block,
                # provided this looks like a text file (based on extension).
                self.bsize = sz * BLKSIZE
                if self.rlist and r50toasc (self.ne.unam[2]) in deftext:
                    lastclu = d.pack.read (self.rlist[-1], cs)
                    lastblkoff = ((sz - 1) % cs) * BLKSIZE
                    m = _re_eofpad.search (lastclu[lastblkoff:lastblkoff + BLKSIZE])
                    if m:
                        self.bsize = (sz - 1) * BLKSIZE + m.start ()

    def strname (self):
        """Returns the file name.ext only.
        """
        if self.isdir:
            ret = ""
        else:
            ret = ascname (self.ne.unam[:2], self.ne.unam[2]).replace (' ', '')
        return ret
    
    def __str__ (self):
        """Returns the full name of the file (directory plus name.ext)
        """
        return str (self.dir) + self.strname ()
        
    def open (self, mode: str = "r",
              encoding: str = None, errors: str = None):
        """Open a file given its Filedata.  Return a file object suitable for
        reading and/or writing (depending on what the mode says) as usual.
        
        The arguments are the same as the built-in open() function except for:
        - "buffering" is not supported (buffered mode is always used).
        - "encoding" defaults to "dec-mcs" (if text mode)
        - "newline" is not supported; instead, the newlines in the
          file are translated to and from \\n unconditionally.
        """
        if not isinstance (mode, str):
            raise TypeError ("mode must be string, not %s" % type(mode).__name__)
        modes = set (mode)
        if modes - set ("arwb+t"):
            raise ValueError ("invalid mode: %r" % mode)
        reading = "r" in modes
        writing = "w" in modes
        appending = "a" in modes
        updating = "+" in modes
        binary = "b" in modes
        text = "t" in modes or not binary
        if self.isdir:
            if text or writing or appending or updating:
                raise ValueError ("invalid mode for directories")
        if text and binary:
            raise ValueError ("can't have text and binary modes at once")
        if reading + writing + appending != 1:
            raise ValueError ("must have exactly one of read/write/append mode")
        if binary and encoding is not None:
            raise ValueError ("binary mode doesn't take an encoding argument")
        if binary and errors is not None:
            raise ValueError ("binary mode doesn't take an errors argument")
        if text and encoding is None:
            encoding = "dec-mcs"
        rawfile = RstsRawIO (self, mode)
        if updating:
            bfile = io.BufferedRandom (rawfile)
        elif writing or appending:
            bfile = io.BufferedWriter (rawfile)
        else:
            bfile = io.BufferedReader (rawfile)
        if text:
            bfile = RstsTextIOWrapper (bfile, encoding = encoding, errors = errors)
        if appending:
            bfile.seek (0, io.SEEK_END)
        else:
            bfile.seek (0)
        return bfile
    
        
