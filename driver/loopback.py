"""ENA or analog 0/+4 V -> TTL encoder-A latency through the normal serialized control cycle."""
import math
import statistics


class Loopback:
    analog_high_volts = 4.0
    repetitions = 100
    dwell_ns = 50_000_000
    timeout_ns = 500_000_000

    def __init__(self, axis, now_ns, mode="digital"):
        if type(axis) is not int or not 0 <= axis < 4:
            raise ValueError('Canal de loopback inválido')
        if mode not in ("digital", "analog"):
            raise ValueError("Modo de loopback inválido")
        self.mode = mode
        self.axis = axis
        self.active = True
        self.phase = 'baseline'
        self.output = False
        self.pending = False
        self.started_ns = now_ns
        self.low_since = None
        self.sent_ns = None
        self.due_ns = None
        self.on_ns, self.off_ns = [], []
        self.error = None

    def cancel(self, reason='Cancelado pelo operador'):
        self.error = reason
        self.phase, self.output, self.pending = 'cleanup', False, True

    def observe(self, level, received_ns):
        if not self.active or self.pending or self.phase == 'cleanup':
            return
        if self.phase == 'baseline':
            if level:
                self.low_since = None
            elif self.low_since is None:
                self.low_since = received_ns
            if received_ns - self.started_ns > 1_000_000_000:
                self.cancel('Entrada A não confirmou OFF estável. Confira fio, canal e jumper TTL.')
            elif self.low_since is not None and received_ns - self.low_since >= self.dwell_ns:
                self.phase, self.output, self.pending = 'on', True, True
        elif self.phase in ('on', 'off'):
            if received_ns < self.sent_ns:
                return
            if received_ns - self.sent_ns > self.timeout_ns:
                self.cancel('Timeout na borda ' + self.phase.upper() + ': retorno ausente ou atrasado.')
            elif level == self.output:
                (self.on_ns if self.output else self.off_ns).append(received_ns - self.sent_ns)
                self.phase = 'hold_on' if self.output else 'hold_off'
                self.due_ns = received_ns + self.dwell_ns
                if not self.output and len(self.off_ns) == self.repetitions:
                    self.active, self.phase = False, 'complete'
        elif self.phase in ('hold_on', 'hold_off'):
            if level != self.output:
                self.cancel('Entrada mudou sem comando; confira ruído, ligação e encoder desconectado.')
            elif received_ns >= self.due_ns:
                self.output = not self.output
                self.phase = 'on' if self.output else 'off'
                self.pending = True

    def written(self, sent_ns):
        if not self.pending:
            return
        self.pending = False
        self.sent_ns = sent_ns
        if self.phase == 'cleanup':
            self.active = False

    @staticmethod
    def stats(samples):
        if not samples:
            return None
        values = sorted(value / 1e6 for value in samples)
        return dict(mean_ms=statistics.mean(values), min_ms=values[0], max_ms=values[-1],
                    stddev_ms=statistics.pstdev(values), p95_ms=values[math.ceil(len(values) * .95) - 1])

    def report(self):
        return dict(axis=self.axis, mode=self.mode, high_volts=self.analog_high_volts if self.mode == "analog" else None, active=self.active, phase=self.phase,
                    completed=len(self.off_ns), repetitions=self.repetitions, error=self.error,
                    on=self.stats(self.on_ns), off=self.stats(self.off_ns),
                    on_samples_ms=[value / 1e6 for value in self.on_ns],
                    off_samples_ms=[value / 1e6 for value in self.off_ns])
