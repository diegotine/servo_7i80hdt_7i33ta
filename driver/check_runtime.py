"""Check real OS scheduling/memory permissions without opening the Mesa board."""
import json
import os
import resource
import sys
import tempfile
import threading

# Load the same modules and create an ordinary reader thread before mlock,
# without constructing a board, opening UDP, or executing a simulated servo.
import backend
ready = threading.Event()
stop = threading.Event()

def reader():
    ready.set()
    stop.wait()

thread = threading.Thread(target=reader, daemon=True)
thread.start()
ready.wait()
tempfile.gettempdir()

from timing import configure_runtime

from run_backend import native_modules
result = configure_runtime()
result['native_modules'] = native_modules()
result['uid'] = os.getuid()
result['limits'] = dict(rtprio=resource.getrlimit(resource.RLIMIT_RTPRIO),
                        memlock_bytes=resource.getrlimit(resource.RLIMIT_MEMLOCK))
with open('/proc/self/status', encoding='ascii') as status:
    result['capabilities'] = {line.split(':', 1)[0]: line.split(':', 1)[1].strip()
                              for line in status if line.startswith(('CapEff:', 'CapPrm:', 'NoNewPrivs:'))}
with open('/proc/self/status', encoding='ascii') as status:
    result['memory'] = {line.split(':', 1)[0]: line.split(':', 1)[1].strip()
                        for line in status if line.startswith(('VmSize:', 'VmLck:', 'Threads:'))}
stop.set()
thread.join()
print(json.dumps(result, ensure_ascii=False, indent=2))
sys.exit(0 if result['scheduler'] == 'SCHED_FIFO' and result['memory_current_locked'] else 1)
