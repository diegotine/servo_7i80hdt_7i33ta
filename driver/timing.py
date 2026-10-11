"""Monotonic cycle scheduling and bounded timing statistics; no hardware I/O."""
from collections import deque
import ctypes
import errno
import math
import os
import time


NOMINAL_PERIOD_NS = 2_000_000


class Timespec(ctypes.Structure):
    _fields_ = [('tv_sec', ctypes.c_long), ('tv_nsec', ctypes.c_long)]


class AbsoluteSleeper:
    def __init__(self):
        self.libc = ctypes.CDLL(None, use_errno=True)
        self.sleep = self.libc.clock_nanosleep
        self.sleep.argtypes = [ctypes.c_int, ctypes.c_int,
                               ctypes.POINTER(Timespec), ctypes.c_void_p]
        self.sleep.restype = ctypes.c_int

    def __call__(self, target_ns):
        target = Timespec(*divmod(target_ns, 1_000_000_000))
        while True:
            # Absolute CLOCK_MONOTONIC time: EINTR never restarts a relative delay.
            result = self.sleep(time.CLOCK_MONOTONIC, 1, ctypes.byref(target), None)
            if result == 0:
                return
            if result != errno.EINTR:
                raise OSError(result, os.strerror(result))


class CycleTimer:
    def __init__(self, period_ns=NOMINAL_PERIOD_NS, clock=time.monotonic_ns, sleeper=None):
        if type(period_ns) is not int or period_ns <= 0:
            raise ValueError('Período deve ser um número positivo de nanossegundos')
        self.period_ns = period_ns
        self.clock = clock
        self.sleep_until = sleeper if sleeper is not None else AbsoluteSleeper()
        self.next_ns = clock() + period_ns
        self.skipped = 0

    def wait(self):
        now = self.clock()
        if now > self.next_ns:
            # Drop expired slots rather than running a burst of catch-up cycles.
            lost = (now - self.next_ns) // self.period_ns + 1
            self.next_ns += lost * self.period_ns
            self.skipped += lost
        target = self.next_ns
        self.sleep_until(target)
        woke = self.clock()
        self.next_ns = target + self.period_ns
        return max(0, woke - target)


class Samples:
    def __init__(self):
        self.window = deque(maxlen=256)
        self.count = 0
        self.mean = self.m2 = 0.0
        self.minimum = math.inf
        self.maximum = 0.0

    def add(self, value_ns):
        value = value_ns / 1e6
        self.window.append(value)
        self.count += 1
        delta = value - self.mean
        self.mean += delta / self.count
        self.m2 += delta * (value - self.mean)
        self.minimum = min(self.minimum, value)
        self.maximum = max(self.maximum, value)

    def report(self):
        if not self.count:
            return None
        ordered = sorted(self.window)
        return dict(count=self.count, last_ms=self.window[-1], mean_ms=self.mean,
                    min_ms=self.minimum, max_ms=self.maximum,
                    stddev_ms=math.sqrt(max(0, self.m2 / self.count)),
                    p95_recent_ms=ordered[math.ceil(len(ordered) * .95) - 1])


class CycleMetrics:
    def __init__(self, period_ns=NOMINAL_PERIOD_NS):
        self.period_ns = period_ns
        self.work_overruns = 0
        self.values = {name: Samples() for name in
                       ('interval', 'wake_lateness', 'read', 'control', 'write', 'work')}
        self.skipped = 0

    def add(self, **values):
        if values.get("work", 0) > self.period_ns:
            self.work_overruns += 1
        for name, value in values.items():
            self.values[name].add(value)

    def report(self):
        return dict(nominal_ms=self.period_ns / 1e6, work_overruns=self.work_overruns,
                    skipped_slots=self.skipped, recent_window=256,
                    **{name: samples.report() for name, samples in self.values.items()})


def configure_runtime(environ=None):
    """Apply to the calling servo thread only, without elevating privileges.

    Reader thread must already exist so it retains ordinary scheduling/affinity.
    Failures are visible metadata, never implicit claims of realtime operation.
    """
    env = os.environ if environ is None else environ
    priority = int(env.get('T3D_RT_PRIORITY', '10'))
    if not 0 <= priority <= 50:
        raise ValueError('T3D_RT_PRIORITY: use 0 (normal) ou 1–50')
    requested_cpu = env.get('T3D_CPU', 'auto')
    allowed = os.sched_getaffinity(0)
    cpu = max(allowed) if requested_cpu == 'auto' and len(allowed) > 1 else None
    if requested_cpu not in ('auto', 'none'):
        cpu = int(requested_cpu)
        if cpu not in allowed:
            raise ValueError('T3D_CPU fora dos processadores permitidos')
    errors = []
    if cpu is not None:
        try:
            os.sched_setaffinity(0, {cpu})
        except OSError as exc:
            errors.append('Afinidade: ' + str(exc))
    # Lock only current resident mappings; MCL_FUTURE can make later Python
    # allocations fail under RLIMIT_MEMLOCK. Do not silently change system limits.
    memory_locked = False
    if env.get('T3D_MLOCK', '1') == '1':
        libc = ctypes.CDLL(None, use_errno=True)
        libc.mlockall.argtypes = [ctypes.c_int]
        libc.mlockall.restype = ctypes.c_int
        memory_locked = libc.mlockall(1) == 0
        if not memory_locked:
            errors.append('Memória atual: ' + os.strerror(ctypes.get_errno()))
    try:
        os.sched_setscheduler(0, os.SCHED_FIFO if priority else os.SCHED_OTHER,
                              os.sched_param(priority))
    except OSError as exc:
        errors.append('Escalonamento solicitado: ' + str(exc))
    policy = os.sched_getscheduler(0)
    return dict(scheduler={os.SCHED_FIFO: 'SCHED_FIFO', os.SCHED_OTHER: 'SCHED_OTHER'}.get(policy, str(policy)),
                priority=os.sched_getparam(0).sched_priority,
                cpus=sorted(os.sched_getaffinity(0)), memory_current_locked=memory_locked,
                warnings=errors, timer='CLOCK_MONOTONIC / TIMER_ABSTIME',
                native_servo=False)
