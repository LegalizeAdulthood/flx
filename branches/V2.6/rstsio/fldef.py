#!

""" fldef.py -- RSTS file system definitions

    This module defines classes which use ctypes to define data layouts
    to be mapped onto buffers holding RSTS file system data structures.
    In addition, it defines symbolic constants for those data structures.
    
    Derived from fldef.mac, RSTS V10.1.
"""

import re
import ctypes
from .common import *

# We'll define a whole pile of classes which define the layouts of
# on-disk structures.  They will be laid on the applicable directory
# buffer using the ctypes.from_buffer function.  They are all derived
# from base class "rds".
class rds (ctypes.LittleEndianStructure):
    _pack_ = 1
    def touch (self):
        self.clu.touch ()

class ulk (ctypes.LittleEndianStructure):
    """A RSTS directory link word."""
    _pack_ = 1
    _fields_ = (
        ( "ul_use", ctypes.c_uint16, 1 ), # On to ensure entry is "in use"
        ( "ul_bad", ctypes.c_uint16, 1 ), # Some bad block exists in file
        ( "ul_che", ctypes.c_uint16, 1 ), # Cache (NE) or sequential (AE)
        ( "ul_cln", ctypes.c_uint16, 1 ), # Reserved for UU.CLN
        ( "ul_eno", ctypes.c_uint16, 5 ), # Entry offset within block (5 bits)
        ( "ul_clo", ctypes.c_uint16, 3 ), # Cluster offset within UFD (3 bits)
        ( "ul_blo", ctypes.c_uint16, 4 )) # Block offset in cluster   (4 bits)

    def __bool__ (self):
        """Tests whether a directory link is null, i.e., the link fields
        are all zero.  The flag bits are not included in the test.
        """
        return self.ul_eno == 0 and self.ul_clo == 0 and self.ul_blo == 0

    def __str__ (self):
        return "%d.%d.%d" % (self.ul_clo, self.ul_blo, self.ul_eno)

class rms_long (ctypes.LittleEndianStructure):
    """A "pdp-11 endian" long integer as used in RMS attributes."""
    _fields_ = (( "i", ctypes.c_uint32 ),)

    @property
    def value (self):
        i = self.i
        return ((i & 0xffff) << 16) | (i >> 16)

    @value.setter
    def value (self, i):
        self.i = ((i & 0xffff) << 16) | (i >> 16)
    
# rad50 constants we need
MFD = 0o051064                          # rad50 "MFD"
GFD = 0o026264                          # rad50 "GFD"
UFD = 0o102064                          # rad50 "UFD"
TMP = 0o077430                          # rad50 "TMP"
STAR = 0o134745                         # rad50 "???"

# Disk file structure definitions 
# Any definitions that apply only for certain disk structure levels
# are marked accordingly.  They apply to the rev level stated and those
# after it.

# Note: except for the pack label, each of these struct definitions
# must define a struct of size 16 bytes.

class packlabel (rds):
    """Pack label entry.  Fields are:
    - unlk: link to first name entry if RDS0 structure
    - mdcn: starting DCN of MFD (RDS1.1 and later)
    - plvl: pack revision level (two bytes, major << 8 + minor)
    - ppcs: pack cluster size
    - pstat: pack status flags
    - pckid: pack ID, 2 words, RAD50 encoding
    - bckdat: date of last full backup by TAP (RDS1.1 and later)
    - bcktim: date of last full backup by TAP (RDS1.1 and later)
    - mntdat: date of last mount/dismount (RDS1.2)
    - mnttim: date of last mount/dismount (RDS1.2)
    """
    _fields_ = (  
        ( "ulnk", ulk ),                # Link if RDS0.0, otherwise 1 
        ( "fill1", ctypes.c_uint16 ),   # Reserved (-1)
        ( "mdcn", ctypes.c_uint16 ),    # Starting DCN of MFD (RDS1.1)
        ( "plvl", ctypes.c_uint16 ),    # Pack revision level
        ( "ppcs", ctypes.c_uint16 ),    # Pack cluster size
        ( "pstat", ctypes.c_uint16 ),   # Pack status/flags
        ( "pckid", ctypes.c_uint16 * 2 ),  # Pack ID
        ( "tapgvn", ctypes.c_uint16 * 2 ), # TAP generation-version number (RDS1.1)
        ( "bckdat", ctypes.c_uint16 ),  # Date of last TAP full backup (RDS1.1)
        ( "bcktim", ctypes.c_uint16 ),  # Time of last TAP full backup (RDS1.1)
        ( "mntdat", ctypes.c_uint16 ),  # Date of last mount/dismount (RDS1.2)
        ( "mnttim", ctypes.c_uint16 ),  # Time of last mount/dismount (RDS1.2)
        ( "fill2", ctypes.c_uint8 * (BLKSIZE-(14 * 2)) )) # Reserved


# Flag bits in pack label field

uc_top = 0o001000                       # New files first
uc_dlw = 0o004000                       # Maintain date of last write
uc_ro  = 0o010000                       # Read-only pack
uc_new = 0o020000                       # "New" pack (RDS1.1)
uc_pri = 0o040000                       # Pack is private/system
uc_mnt = 0o100000                       # Pack is mounted (dirty)

# Rev levels
RDS0  = 0                               # RDS 0 -- V7.x and before
RDS11 = ((1<<8)+1)                      # RDS 1.1 -- V8
RDS12 = ((1<<8)+2)                      # RDS 1.2 -- V9.0 and beyond

# MFD and GFD are new as of RDS1.1

class mfdlabel (rds):
    """MFD label entry.  Applicable to RDS1.1 and later.  Fields are:
    - malnk: link to pack attributes
    - lppn: PPN, [255,255] for the MFD
    - lid: identification word, "MFD" in RAD50 encoding
    """
    _fields_ = (  
        ( "fill1", ctypes.c_uint16 ),   # Reserved (0)
        ( "fill2", ctypes.c_uint16 ),   # Reserved (-1)
        ( "fill3", ctypes.c_uint16 * 3 ), # Reserved (0)
        ( "malnk", ulk ),               # Link to pack attributes
        ( "lppn", ctypes.c_uint8 * 2 ), # PPN [255,255]
        ( "lid", ctypes.c_uint16 ))     # Identification (RAD50 "MFD")

ent_size = 0o20                         # size of a directory entry
fdcm_off = 0o000760                     # offset to directory cluster map
class fdcm (rds):
    """Directory cluster map.  Found at the last 8 words of every directory
    block except for the table blocks in MFD and GFD.  Fields are:
    - uclus: directory clustersize (byte)
    - uflag: flags (byte), high bit set for RDS1 GFD and MFD
    - uent: 7 words, the DCNs of the 7 directory clusters or 0 if not used.
    """
    _fields_ = (  
        ( "uclus", ctypes.c_uint8 ),    # Directory clustersize
        ( "uflag", ctypes.c_uint8 ),    # RDS1 GFD/MFD flag in high bit
        ( "uent", ctypes.c_uint16 * 7 )) # The dcn's of the cluster(s)

fd_new = 0o200                          # flag bit for GFD/MFD in uflag (RDS1.1)

class gfdtable (rds):
    """MFD or GFD table block.  Found in the second and third blocks of
    MFD and GFD.  Indexed by group number (for MFD) or user number (GFD).
    For the second block, contains the DCN of the next level directory;
    for the third block, contains the link to attributes for this group or
    user.
    """
    _fields_ = (
        ( "ent", ctypes.c_uint16 * 255 ), # table entries
        ( "fill1", ctypes.c_uint16 ))   # filler
    
class gfdlabel (rds):
    """GFD label entry.  Fields are:
    - lppn: PPN, [x,255] for the group x
    - lid: identification word, "GFD" in RAD50 encoding    
    """
    _fields_ = (  
        ( "fill1", ctypes.c_uint16 ),   # Reserved (0)
        ( "fill2", ctypes.c_uint16 ),   # Reserved (-1)
        ( "fill3", ctypes.c_uint16 * 4 ), # Reserved (0)
        ( "lppn", ctypes.c_uint8 * 2 ), # PPN [x,255]
        ( "lid", ctypes.c_uint16 ))     # Identification (RAD50 "GFD")

# mfd/gfd offsets
gfddcntbl = 1                           # block with DCN pointer table
gfdatrtbl = 2                           # block with attribute link table

# For RDS0, the "GFD NE" and "GFD AE" live in the MFD ([1,1] directory)
# which starts at DCN 1.  They are in a linked list, possibly mixed
# with files, in the usual UFD fashion.

class gfdne (rds):
    """GFD name entry
    """
    _fields_ = (  
        ( "ulnk", ulk ),                # Link to attributes
        ( "uprog", ctypes.c_uint8 ),    # Programmer number
        ( "uproj", ctypes.c_uint8 ),    # Project number
        ( "upass", ctypes.c_uint16 * 2 ), # Password
        ( "ustat", ctypes.c_uint8 ),    # Status byte
        ( "uprot", ctypes.c_uint8 ),    # Protection code
        ( "uacnt", ctypes.c_uint16 ),   # Access count
        ( "uaa", ulk ),                 # Link to accounting entry
        ( "uar", ctypes.c_uint16 ))     # Dcn of start of UFD

class gfdae (rds):
    """GFD accounting entry
    """
    _fields_ = (  
        ( "ulnk", ulk ),                # Flags
        ( "mcpu", ctypes.c_uint16 ),    # Accum cpu time (LSB)
        ( "mcon", ctypes.c_uint16 ),    # Accum connect time
        ( "mkct", ctypes.c_uint16 ),    # Accum kct's (LSB)
        ( "mdev", ctypes.c_uint16 ),    # Accum device time
        ( "mmsb", ctypes.c_uint16 ),    # Accum cpu time and kct's (MSB's)
        ( "mdper", ctypes.c_uint16 ),   # Disk quota
        ( "uclus", ctypes.c_uint16 ))   # UFD cluster size

class ufdlabel (rds):
    """UFD label entry.  Fields are:
    - ulnk: link to first UFD name entry (ufdne)
    - lppn: PPN, [x,y] for the UFD [x,y]
    - lid: identification word, "UFD" in RAD50 encoding    
    """
    _fields_ = (  
        ( "ulnk", ulk ),                # Link to first name block in UFD
        ( "fill2", ctypes.c_uint16 ),   # Reserved (-1)
        ( "fill3", ctypes.c_uint16 * 4 ), # Reserved (0)
        ( "lppn", ctypes.c_uint8 * 2 ), # PPN [x,y]
        ( "lid", ctypes.c_uint16 ))     # Identification (RAD50 "UFD")

class ufdne (rds):
    """UFD name entry.  These form a linked list, and list the files
    in a directory.  In the case of RDS0, the [1,1] directory doubles as
    MFD and also lists accounts.  Those have essentially the same name
    entries, with a flag in ustat to distinguish a directory, but a
    different accounting entry.
    Fields are:
    - ulnk: link to next name entry
    - unam: 3 words RAD50 encoded name.ext.  For accounts, the first
      word is the PPN and the second and third are the RAD50 encoded
      password
    - ustat: status (byte)
    - uprot: protection code (byte)
    - uaa: link to UFD account entry.  For RDS0 entries for accounts,
      this points to a "gfdae" structure instead.
    - uar: link to list of retrieval entries, if file is not zero length.
    """
    _fields_ = (  
        ( "ulnk", ulk ),                # Link to next name entry
        ( "unam", ctypes.c_uint16 * 3 ), # File name and extension
        ( "ustat", ctypes.c_uint8 ),    # Status byte
        ( "uprot", ctypes.c_uint8 ),    # Protection code
        ( "uacnt", ctypes.c_uint16 ),   # Access count
        ( "uaa", ulk ),                 # Link to UFD accounting entry
        ( "uar", ulk ))                 # Link to retrieval entries

class ufdae (rds):
    """UFD accounting entry.  This contains additional file information.
    Fields are:
    - ulnk: link to RMS attributes, if present
    - udla: date of last access (more often, date of last write)
    - usiz: low order 16 bits of file size
    - udc: date of creation
    - utc: time of creation
    - urts: file's run-time system, in RAD50.  For "large files" the
      first word is zero and the second word contains the upper bits
      of the file size
    - uclus: file cluster size
    """
    _fields_ = (  
        ( "ulnk", ulk ),                # Link to attributes and flags
        ( "udla", ctypes.c_uint16 ),    # Date of last access (or write)
        ( "usiz", ctypes.c_uint16 ),    # File size
        ( "udc", ctypes.c_uint16 ),     # Date of creation
        ( "utc", ctypes.c_uint16 ),     # Time of creation
        ( "urts", ctypes.c_uint16 * 2 ), # File's run-time system name or 0/MSB size
        ( "uclus", ctypes.c_uint16 ))   # File cluster size

class ufdrms1 (rds):
    """UFD first RMS attributes part 1.  Fields are:
    - ulnk: link to RMS attributes part 2, if needed
    - fa_typ: RMS file type, file organization, and record attributes
    - fa_rsx: record size
    - fa_siz: file size in blocks, 32 bits, high half first
    - fa_eof: EOF block number, 1-based, 32 bits, high half first
    - fa_eofb: EOF byte offset within EOF block
    """
    _fields_ = (  
        ( "ulnk", ulk ),                # Link to second attributes blockette
        ( "fa_typ", ctypes.c_uint16 ),  # File type (rfm, org, rat)
        ( "fa_rsz", ctypes.c_uint16 ),  # Record size
        ( "fa_siz", rms_long ),         # File size (32 bits)
        ( "fa_eof", rms_long ),         # File EOF block number (32 bits)
        ( "fa_eofb", ctypes.c_uint16 )) # EOF byte offset

fa_rfm = 0o000007                       # record format field in fa_typ
rf_udf = 0                              # undefined organization
rf_fix = 1                              # fixed length records
rf_var = 2                              # variable length records
rf_vfc = 3                              # variable with fixed control header
rf_stm = 4                              # stream (cr/lf delimiter)
fa_org = 0o000070                       # file organization format in fa_typ
fo_seq = 0o000                          # sequential organization
fo_rel = 0o020                          # relative organization
fo_idx = 0o040                          # indexed organization
fa_rat = 0o017400                       # record attribute flags
ra_ftn = 0o000400                       # fortran carriage control
ra_imp = 0o001000                       # implied carriage control
ra_prn = 0o002000                       # print format
ra_spn = 0o004000                       # no-span records
ra_emb = 0o010000                       # embedded

class ufdrms2 (rds):
    """UFD RMS attributes part 2.  Fields are
    - fa_bkt: bucket size
    - fa_hsz: header size
    - fa_msz: maximum record size
    - fa_ext: default extension amount
    """
    _fields_ = (  
        ( "ulnk", ulk ),                # Link (reserved)
        ( "fa_bkt", ctypes.c_uint8 ),   # Bucket size
        ( "fa_hsz", ctypes.c_uint8 ),   # Header size
        ( "fa_msz", ctypes.c_uint16 ),  # Max record size
        ( "fa_ext", ctypes.c_uint16 ),  # Default extension amount
        ( "filler", ctypes.c_uint16 * 4 )) # Reserved

# All directory attributes are new as of RDS1.1 or later

class uattr (rds):
    """MFD/GFD attribute entry.  This is the generic layout.  MFD/GFD
    attributes apply to RDS1.1 and later.  Fields are:
    - ulnk: link to next attribute
    - uatyp: attribute type (byte)
    - uadat: 13 bytes of attribute data
    """
    _fields_ = (  
        ( "ulnk", ulk ),                # Link to next, flags
        ( "uatyp", ctypes.c_uint8 ),    # Type
        ( "uadat", ctypes.c_uint8 * (16 - 3) )) # Data

# Time of creation flag bit definitions

utc_tm = 0o003777                       # Bits needed for the time field
utc_ig = 0o004000                       # IGNORE flag (RDS1.2)
utc_bk = 0o010000                       # NOBACKUP flag (RDS1.2)
                                        # Other bits reserved

class ufdre (rds):
    """UFD retrieval entry.  Points to where the file data lives.
    Fields are:
    - ulnk: link to next retrieval entry
    - uent: 7 words, the starting DCNs of the next 7 file clusters,
      zero if not used.
    """
    _fields_ = (  
        ( "ulnk", ulk ),                # Link to next retrieval entry
        ( "uent", ctypes.c_uint16 * 7 )) # The dcn's of the cluster(s)

# Bit assignments in ustat and f$stat

us_out = 0o001                          # File is 'out of sat' (historical)
us_plc = 0o002                          # File is "placed"
us_wrt = 0o004                          # Write access given out (not on disk)
us_upd = 0o010                          # Open in update mode (not on disk)
us_nox = 0o020                          # No extending allowed (contiguous)
us_nok = 0o040                          # No delete and/or rename allowed
us_ufd = 0o100                          # Entry is MFD type entry
us_del = 0o200                          # File marked for deletion

# Bit assignments in uprot and f$prot

up_rpo = 0o001                          # Read  protect against owner
up_wpo = 0o002                          # Write  "       "       "
up_rpg = 0o004                          # Read   "       "      group
up_wpg = 0o010                          # Write  "       "       "
up_rpw = 0o020                          # Read   "       "      world
up_wpw = 0o040                          # Write  "       "       "
up_run = 0o100                          # Executable file
up_prv = 0o200                          # Clear on delete, privileged if executable file

# Account attribute codes

aa_quo = 1                              # Quotas
aa_prv = 2                              # Privilege masks
aa_pas = 3                              # Password
aa_dat = 4                              # Date/time recording (creation, change, login)
aa_nam = 5                              # User name (RDS1.2)
aa_qt2 = 6                              # Quotas part 2 (RDS1.2)

# Attribute blockette layouts

class ua_quo (rds):
    """Disk Quota Attribute Blockette.  Fields are:
    - ulnk: link to next
    - uatyp: type (byte) = 1
    - aq_djb: Detached job quota
    - aq_lol: Logged out quota (LSB)
    - aq_lil: Logged in quota  (LSB)
    - aq_lim: Logged in quota  (MSB)
    - aq_lom: Logged out quota (MSB)
    - aq_crm: Current usage    (MSB)
    - aq_crl: Current usage    (LSB)
    """
    _fields_ = (  
        ( "ulnk", ulk ),                # Link to next, flags
        ( "uatyp", ctypes.c_uint8 ),    # Type
        ( "aq_djb", ctypes.c_uint8 ),   # Detached job quota
        ( "aq_lol", ctypes.c_uint16 ),  # Logged out quota (LSB)
        ( "aq_lil", ctypes.c_uint16 ),  # Logged in quota  (LSB)
        ( "aq_lim", ctypes.c_uint8 ),   # Logged in quota  (MSB)
        ( "aq_lom", ctypes.c_uint8 ),   # Logged out quota (MSB)
        ( "aq_rsm", ctypes.c_uint8 ),   # Reserved
        ( "aq_crm", ctypes.c_uint8 ),   # Current usage    (MSB)
        ( "aq_rsl", ctypes.c_uint16 ),  # Reserved
        ( "aq_crl", ctypes.c_uint16 ))  # Current usage    (LSB)

privsz = 6                              # number of privilege bytes

class ua_prv (rds):
    """Privilege mask data.  Fields are:
    - ulnk: Link to next, flags
    - uatyp: Type (byte) = 2
    - ap_prv: Authorized privileges
    """
    _fields_ = (  
        ( "ulnk", ulk ),                # Link to next, flags
        ( "uatyp", ctypes.c_uint8 ),    # Type
        ( "fill1", ctypes.c_uint8 ),    # Filler
        ( "ap_prv", ctypes.c_uint8 * privsz ), # Authorized privileges
        ( "fill2", ctypes.c_uint8 * (0o020 - privsz - 1 - 3) )) # Filler

class ua_dat (rds):
    """Date/time data.  Fields are:
    - ulnk: Link to next, flags
    - uatyp: Type (byte) = 4
    - at_kb: Keyboard of last login
    - at_lda: Date of last login
    - at_lti: Time of last login
    - at_pda: Date of last password16 change
    - at_pti: Time of last password change
    - at_cda: Date of creation
    - at_exp: Expiration date (RDS1.2)
    """
    _fields_ = (  
        ( "ulnk", ulk ),                # Link to next, flags
        ( "uatyp", ctypes.c_uint8 ),    # Type
        ( "at_kb", ctypes.c_uint8 ),    # Keyboard of last login
        ( "at_lda", ctypes.c_uint16 ),  # Date of last login
        ( "at_lti", ctypes.c_uint16 ),  # Time of last login
        ( "at_pda", ctypes.c_uint16 ),  # Date of last password16 change
        ( "at_pti", ctypes.c_uint16 ),  # Time of last password change
        ( "at_cda", ctypes.c_uint16 ),  # Date of creation
        ( "at_exp", ctypes.c_uint16 ))  # Expiration date (RDS1.2)
                                        # Account creation time (RDS1.1 only)

# Fields within at_lti
at_msk = 0o003777                       # Bits needed for the time field
at_npw = 0o004000                       # No password required
                                        # Other bits reserved

# Fields within at_pti
at_nlk = 0o004000                       # Not readable password if set
at_ndl = 0o010000                       # No-dialups flag
at_nnt = 0o020000                       # No-network flag
at_nlg = 0o040000                       # No-login account
at_cap = 0o100000                       # Captive account

class ua_qt2 (rds):
    """Second quota and date/time block.  Fields are:
    - ulnk: Link to next, flags
    - uatyp: Type (byte) = 6
    - a2_job: Total job quota
    - a2_rib: RIB quota
    - a2_msg: Message limit quota
    - a2_pwf: Password failed count
    - a2_ndt: Date of Last non-interactive login
    - a2_nti: Time of Last non-interactive login
    """
    _fields_ = (  
        ( "ulnk", ulk ),                # Link to next, flags
        ( "uatyp", ctypes.c_uint8 ),    # Type
        ( "a2_job", ctypes.c_uint8 ),   # Total job quota
        ( "a2_rib", ctypes.c_uint16 ),  # RIB quota
        ( "a2_msg", ctypes.c_uint16 ),  # Message limit quota
        ( "fill1", ctypes.c_uint16 ),   # Reserved
        ( "fill2", ctypes.c_uint8 ),    # Reserved
        ( "a2_pwf", ctypes.c_uint8 ),   # Password failed count
        ( "a2_ndt", ctypes.c_uint16 ),  # Date of Last non-interactive login
        ( "a2_nti", ctypes.c_uint16 ))  # Time of Last non-interactive login
