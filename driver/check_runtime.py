"""Check real OS scheduling/memory permissions without opening the Mesa board."""
import json
import os
import resource
import sys

from timing import configure_runtime

result = configure_runtime()
result['uid'] = os.getuid()
result['limits'] = dict(rtprio=resource.getrlimit(resource.RLIMIT_RTPRIO),
                        memlock_bytes=resource.getrlimit(resource.RLIMIT_MEMLOCK))
with open('/proc/self/status', encoding='ascii') as status:
    result['capabilities'] = {line.split(':', 1)[0]: line.split(':', 1)[1].strip()
                              for line in status if line.startswith(('CapEff:', 'CapPrm:', 'NoNewPrivs:'))}
print(json.dumps(result, ensure_ascii=False, indent=2))
sys.exit(0 if result['scheduler'] == 'SCHED_FIFO' and result['memory_current_locked'] else 1)
