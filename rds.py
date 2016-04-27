#!/usr/bin/env python3

"""Mount a RSTS/E file system image

Copyright (c) 2016 Paul Koning
"""

import logging
import rstsio
from rstsio import rststime
from rstsio.common import r50toasc
from rstsio.fldef import *
from errno import *
from sys import argv
import os
import stat
import getopt
from fuse import FUSE, FuseOSError, Operations, LoggingMixIn

class RDS (LoggingMixIn, Operations):
    def __init__ (self, fn, writable = False):
        self.ro = not writable
        self.fs = rstsio.pack.Pack (fn, ronly = self.ro)
        self.fs.mount (ronly = self.ro)
        self.fds = { }
        self.fd = 0

    def __call__(self, op, path, *args):
        # Lifted from LoggingMixIn
        self.log.debug ('-> %s %s %s', op, path, repr(args))
        ret = '[Unhandled Exception]'
        try:
            ret = getattr (self, op)(path, *args)
            return ret
        except rstsio.common.FlxError as e:
            if e.errno:
                ret = "{} ({})".format (e, os.strerror (e.errno))
                raise FuseOSError (e.errno)
            ret = "{}".format (e)
            raise
        except OSError as e:
            ret = str (e)
            raise
        finally:
            self.log.debug ('<- %s %s', op, repr (ret))

    def checkrw (self):
        if self.ro:
            raise FuseOSError (EROFS)
        
    def todo (self):
        # To be implemented.
        raise FuseOSError (ENODEV)
    
    # Some operations are rejected because they don't apply to RSTS.
    def chown (self, path, uid, gid):
        raise FuseOSError (ENOTSUP)

    def link (self, target, source):
        raise FuseOSError (ENOTSUP)
        
    def mknod (self, path, mode, dev):
        raise FuseOSError (ENOTSUP)

    def readlink (self, path):
        raise FuseOSError (ENOTSUP)
    
    def symlink (self, target, source):
        raise FuseOSError (ENOTSUP)

    # Here are the operations we do support.
    def chmod (self, path, mode):
        self.todo ()
        self.checkrw ()

    def create (self, path, mode):
        self.todo ()
        self.checkrw ()

    def destroy (self, path):
        """Called on filesystem destruction (unmount). Path is always /
        """
        self.fs.umount ()
        
    def getattr (self, path, fh = None):
        ent = self.fs.lookup (path, dirok = True)
        if ent.isdir:
            # Directory
            mode = stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH | \
                   stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH | stat.S_IFDIR
            return dict (st_mode = mode, st_nlink = len (ent.dir),
                         st_uid = 0, st_gid = 0,
                         st_size = 512, st_atime = 0,
                         st_mtime = 0,
                         st_ctime = 0)
        # Regular file
        mode = stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH | \
               stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH | stat.S_IFREG
        prot = ent.ne.uprot
        if prot & 64:
            mode |= stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH
        if prot & 1:
            mode &= ~(stat.S_IRUSR | stat.S_IXUSR)
        if prot & 2:
            mode &= ~stat.S_IWUSR
        if prot & 4:
            mode &= ~(stat.S_IRGRP | stat.S_IXGRP)
        if prot & 8:
            mode &= ~stat.S_IWGRP
        if prot & 16:
            mode &= ~(stat.S_IROTH | stat.S_IXOTH)
        if prot & 32:
            mode &= ~stat.S_IWOTH
        if prot & 128:
            mode |= stat.S_ISUID
        # Make a last change/access timestamp from just the date.
        mtime = rststime.time (ent.ae.udla)
        return dict (st_mode = mode, st_nlink = 1, st_uid = 0, st_gid = 0,
                     st_size = ent.bsize, st_blocks = ent.size,
                     st_atime = mtime, st_mtime = mtime,
                     st_ctime = rststime.time (ent.ae.udc, ent.ae.utc))

    def xattr (self, path):
        """Get current attributes of named file/dir.
        """
        YES = b'1'
        ret = dict ()
        ent = self.fs.lookup (path, dirok = True)
        if ent.isdir:
            # Directory
            ret = dict () # TODO
        else:
            # Regular file
            ustat = ent.ne.ustat
            if ustat & us_plc:
                ret["user.placed"] = YES
            if ustat & us_nox:
                ret["user.contiguous"] = YES
            if ustat & us_nok:
                ret["user.protected"] = YES
            ret["user.clustersize"] = str (ent.ae.uclus).encode ("ascii")
            if ent.rms1:
                ret["user.rms"] = bytes (ent.rms1)
                if ent.rms2:
                    ret["user.rms"] += bytes (ent.rms2)
            if ent.ae.urts[0]:
                rts = r50toasc (ent.ae.urts[0]) + r50toasc (ent.ae.urts[1])
                rts = rts.rstrip (" ")
                ret["user.rts"] = rts.encode ("ascii")
        return ret
        
    def getxattr (self, path, name, position = 0):
        attr = self.xattr (path)
        try:
            return attr[name]
        except KeyError:
            raise FuseOSError (ENODATA)

    def listxattr (self, path):
        attr = self.xattr (path)
        return list (attr)

    def mkdir (self, path, mode):
        self.todo ()
        self.checkrw ()

    def open (self, path, flags):
        if flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT |
                    os.O_APPEND | os.O_TRUNC):
            self.checkrw ()
        ent = self.fs.lookup (path)
        f = ent.open ("rb")
        self.fd += 1
        self.fds[self.fd] = f
        return self.fd
    
    def opendir (self, path):
        return 0

    def read (self, path, size, offset, fh):
        print ("read", size, offset)
        f = self.fds[fh]
        f.seek (offset)
        return f.read (size)
    
    def readdir (self, path, fh):
        f = rstsio.Firqb (path)
        if f.name[0] or f.wild:
            raise FuseOSError (ENOENT)
        # Special case handling for RDS 0
        if f.prog is None and self.fs.label.plvl == RDS0:
            # Asking for MFD or GFD content.  For RDS 1 we simply return
            # strings corresponding to non-empty child index table entries,
            # but for RDS 0 we have to fake it.
            f.prog = 255
            mfd = self.fs.mfd
            if f.proj is None:
                # MFD.  Return the group numbers (but each one just once).
                f.proj = 255
                return [ str (p) for p in
                         { u.dir.ppn[1] for u in mfd.finddir (f) } ]
            else:
                return [ str (u.dir.ppn[0]) for u in mfd.finddir (f) ]
        # RDS 1, or RDS 0 UFD.  Look up the directory that was requested
        ent = self.fs.lookup (f, dirok = True)
        if f.prog is None:
            # GFD or MFD.  Just walk the cluster index table and return
            # strings corresponding to each non-zero entry.
            t = ent.dir.maptable ()
            return [ str (i) for i in range (255) if t.ent[i] ]
        # UFD.  Walk through the file entries (skipping UFD entries, if
        # this is RDS 0 and [1,1]).
        f = parse (f, "*.*")
        return [ l.strname () for l in ent.dir.findfiles (f) ]
    
    def release (self, path, fh):
        del self.fds[fh]
        
    def releasedir (self, path, fh):
        return 0

    def removexattr (self, path, name):
        self.todo ()
        self.checkrw ()

    def rename (self, old, new):
        self.todo ()
        self.checkrw ()

    def rmdir (self, path):
        self.todo ()
        self.checkrw ()

    def statfs (self, path):
        # Fake the file count (which we don't want to look up)
        # and free file count (not meaningful)
        fb = self.fs.satt.inuse * self.fs.pcs
        return dict (f_bsize = 512, f_frsize = 512, f_iosize = 512,
                     f_blocks = self.fs.sz, f_bfree = fb, f_bavail = fb,
                     f_files = 1, f_ffree = 1, 
                     f_flag = 1, f_namemax = 10)
    
    def truncate (self, path, length, fh = None):
        self.todo ()
        self.checkrw ()

    def unlink (self, path):
        self.todo ()
        self.checkrw ()

    def utimens (self, path, times = None):
        self.todo ()
        self.checkrw ()

    def write (self, path, data, offset, fh):
        self.todo ()
        self.checkrw ()

if __name__ == "__main__":
    debug = writable = False
    opts, args = getopt.getopt (argv[1:], "dW")
    if len (args) != 2:
        print ("usage: %s [-dW] <rds_file> <mountpoint>" % argv[0])
        exit (1)
    for opt, optarg in opts:
        if opt == "-d":
            debug = True
            logging.basicConfig (level = logging.DEBUG)
        elif opt == "-W":
            writable = True
    fuse = FUSE (RDS (args[0], writable),
                 args[1], encoding = "dec-mcs",
                 foreground = debug,
                 nothreads = True, fsname = "rsts",
                 direct_io = True, hard_remove = True,
                 allow_other = True)
    
