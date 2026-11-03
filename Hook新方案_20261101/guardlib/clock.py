"""A continuous monotonic clock: elapsed sleep counts against exam leases."""

import ctypes
import sys
import time


class ContinuousClock:
    def __init__(self):
        if sys.platform == "darwin":
            class Timebase(ctypes.Structure):
                _fields_ = [("numer", ctypes.c_uint32), ("denom", ctypes.c_uint32)]
            self._library = ctypes.CDLL("/usr/lib/libSystem.B.dylib")
            self._library.mach_continuous_time.restype = ctypes.c_uint64
            self._library.mach_continuous_time.argtypes = []
            self._library.mach_timebase_info.argtypes = [ctypes.POINTER(Timebase)]
            self._library.mach_timebase_info.restype = ctypes.c_int
            info = Timebase()
            if self._library.mach_timebase_info(ctypes.byref(info)) != 0 or not info.denom:
                raise RuntimeError("continuousClockUnavailable")
            self._scale = info.numer / info.denom / 1_000_000_000
            self.source = "mach_continuous_time"
            self._read = lambda: self._library.mach_continuous_time() * self._scale
        elif hasattr(time, "CLOCK_BOOTTIME"):
            self.source = "CLOCK_BOOTTIME"
            self._read = lambda: time.clock_gettime(time.CLOCK_BOOTTIME)
        else:
            raise RuntimeError("sleepInclusiveClockUnavailable")

    def __call__(self):
        return self._read()
