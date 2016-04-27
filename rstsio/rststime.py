#!

"""This module implements conversions to/from RSTS date and time
encodings, in the same manner as the standard "time" module.
"""

import time as _time
import datetime
from .fldef import at_msk as _at_msk

def time (rdate: int, rtime: int = 1440) -> int:
    """Convert a time in RSTS encoding to a UNIX time value, converting
    from local time to UTC.
    If time is not supplied, midnight (start of the day) is assumed.
    """
    yr, day = divmod (rdate, 1000)
    day += yr * 365 + (yr + 1) // 4 - 1
    rtime = 1440 - (rtime & _at_msk)
    t = day * 86400 + rtime * 60
    return datetime.datetime.utcfromtimestamp (t).timestamp ()

def localtime (rdate: int, rtime: int = 1440) -> _time.struct_time:
    """Convert a time in RSTS encoding to a time structure.
    If time is not supplied, midnight (start of the day) is assumed.
    """
    return _time.gmtime (time (rdate, rtime))

def mktime (t: _time.struct_time) -> (int, int):
    """Convert a time structure into the corresponding RSTS date and time
    values.
    """
    yr = t.tm_year - 1970
    if yr > 65:
        raise ValueError ("Date out of RSTS range")
    return yr * 1000 + t.tm_yday - 1, 1440 - (t.tm_hour * 60 + t.tm_min)

def ascdate (t: _time.struct_time) -> str:
    """Format the supplied struct_time to the conventional RSTS format
    date string -- except that the year is 4 digits.
    """
    return _time.strftime ("%d-%b-%Y", t)

def ascdate2 (t: _time.struct_time) -> str:
    """Format the supplied struct_time to the conventional RSTS format
    date string, with a 2 digit year.
    """
    return _time.strftime ("%d-%b-%y", t)

def asctime (t: _time.struct_time) -> str:
    """Format the supplied struct_time to the conventional RSTS format
    time string.
    """
    return _time.strftime ("%I:%M %p", t)

