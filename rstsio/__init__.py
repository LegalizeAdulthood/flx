#!

"""This module provides a set of file services similar to what
is found in the "os" and "io" modules, for accessing files and
directories on RSTS disks.

The main interface is via the Pack class.

In addition, this module defines and registers the "dec-mcs" codec.
"""
__all__ = ( "parse", "Firqb", "Pack", "Filedata" )

import os

import sys
if sys.version_info.major < 3:
    raise ImportError ("Python version 3 required")

import codecs
from . import dec_mcs
from .common import parse, Firqb
from .pack import Pack

codecs.register(dec_mcs.getregentry)
