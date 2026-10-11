"""One board owner, one cyclic software servo, JSON-lines pipe to Qt.

No LinuxCNC dependency. A GUI heartbeat never feeds the hardware watchdog:
only a complete feedback -> control -> acknowledged output cycle does that.
"""
import argparse
import fcntl
import gc
import hashlib
import json
import math
import os
import queue
import sys
import tempfile
import threading
import time
from dataclasses import asdict

from mesa7i80hdt import Mesa7i80hdt, MesaError
from servo import Axis, AxisConfig, ServoFault
from loopback import Loopback
from timing import CycleTimer, CycleMetrics, configure_runtime, NOMINAL_PERIOD_NS


def emit(kind, **data):
    print(json.dumps(dict(type=kind, **data), allow_nan=False), flush=True)


def load_config(path):
    with open(path, encoding='utf-8') as source:
        config = json.load(source)
    if config.get('schema') != 1 or config.get('connector') != 'P3':
        raise ValueError('Unsupported configuration or connector')
    if len(config.get('axes', [])) != 4:
        raise ValueError('Exactly four local axes are required')
    # Ignore the removed voltage cap in configurations saved by version 0.1.
    for value in config['axes']:
        value.pop('voltage_limit', None)
    axes = [Axis(AxisConfig(**value)) for value in config['axes']]
    # Runtime timing is deliberately fixed; do not silently relax fault limits.
    return config, axes


class Session:
    period = NOMINAL_PERIOD_NS / 1e9
    deadline = 0.020
    client_timeout = 0.5

    def __init__(self, board, axes, commands, output=emit, clock=time.monotonic, runtime=None):
        self.board, self.axes, self.commands = board, axes, commands
        self.output, self.clock = output, clock
        self.previous = self.last_client = clock()
        self.last_status = 0.0
        self.cycles = 0
        self.max_cycle_ms = 0.0
        self.runtime = runtime or {}
        self.metrics = CycleMetrics(round(self.period * 1e9))
        self.wake_lateness_ns = 0
        self.running = True
        self.generic_outputs = {'P1': 0, 'P2': 0}
        self.loopback = None
        self.loopback_progress = None
        self.pwm_test = None
        self.pwm_report = None
        self.pwm_pulse_until = None

    def dispatch(self, message):
        operation = message.get('op')
        if operation == 'heartbeat':
            return
        if operation == 'pwm_test_stop':
            self.pwm_test = None
            self.pwm_pulse_until = None
            return
        if operation in ('pwm_test_set', 'pwm_test_pulse'):
            if self.loopback is not None and self.loopback.active:
                raise ValueError('Cancele o loopback antes do teste PWM/PDM')
            index = message.get('axis')
            percent = 40.0 if operation == 'pwm_test_pulse' else message.get('percent')
            if type(index) is not int or not 0 <= index < 4:
                raise ValueError('Canal inválido')
            if type(percent) not in (int, float) or not math.isfinite(percent) or not 0 <= percent <= 100:
                raise ValueError('Magnitude deve estar entre 0 e 100%')
            if any(axis.enabled for axis in self.axes):
                raise ValueError('Desabilite os quatro motores antes do teste PWM/PDM')
            if self.pwm_test is not None and self.pwm_test[0] != index:
                raise ValueError('Desligue o teste antes de trocar o canal')
            self.pwm_test = (index, percent)
            self.pwm_pulse_until = self.clock() + .5 if operation == "pwm_test_pulse" else None
            return
        if self.pwm_test is not None:
            if operation in ('quit', 'stop_all', 'disable', 'stop'):
                self.pwm_test = None
            else:
                raise ValueError('Desligue o teste PWM/PDM antes de outros comandos')
        if operation == 'loopback_start':
            if self.loopback is not None and self.loopback.active:
                raise ValueError('Loopback já está em andamento')
            if any(axis.enabled for axis in self.axes):
                raise ValueError('Desabilite os quatro motores antes do loopback')
            self.loopback = Loopback(message.get('axis'), time.monotonic_ns(), message.get('mode', 'digital'))
            self.loopback_progress = None
            self.output('loopback', **self.loopback.report(), timing=self.metrics.report(), runtime=self.runtime)
            return
        if operation == 'loopback_stop':
            if self.loopback is not None and self.loopback.active:
                self.loopback.cancel()
            return
        if self.loopback is not None and self.loopback.active:
            if operation in ('quit', 'stop_all', 'disable', 'stop'):
                self.loopback.cancel()
            else:
                raise ValueError('Aguarde ou cancele o loopback antes de alterar os comandos')
        if operation == 'io_output':
            connector, channel, value = message.get('connector'), message.get('channel'), message.get('value')
            if (connector not in self.generic_outputs or type(channel) is not int
                    or not 0 <= channel < 12 or type(value) is not bool):
                raise ValueError('Invalid generic output command')
            bit = 1 << channel
            self.generic_outputs[connector] = ((self.generic_outputs[connector] | bit) if value
                                               else (self.generic_outputs[connector] & ~bit))
            return
        if operation in ('quit', 'stop_all'):
            self.generic_outputs = {'P1': 0, 'P2': 0}
            for axis in self.axes:
                axis.disable()
            if operation == 'quit':
                self.running = False
            return
        index = message.get('axis')
        if type(index) is not int or not 0 <= index < 4:
            raise ValueError('Invalid axis')
        axis = self.axes[index]
        if operation == 'enable':
            if axis.enabled:
                raise ValueError('Axis already enabled')
            axis.enable()
        elif operation == 'output_test':
            axis.set_output_test(message['value'])
        elif operation == 'stop':
            axis.stop_motion()
        elif operation in ('acceleration', 'deceleration'):
            axis.set_acceleration(message['value'], operation == 'deceleration')
            self.output('axis_config', axis=index, acceleration_rpm_s=axis.c.acceleration_rpm_s,
                        deceleration_rpm_s=axis.c.deceleration_rpm_s)
        elif operation == 'configure':
            disabled = axis.configure(message['config'])
            self.output('axis_config', axis=index, config=asdict(axis.c), motor_disabled=disabled)
        elif operation == 'disable':
            axis.disable()
        elif operation == 'zero':
            axis.zero()
        elif operation == 'move':
            axis.move(float(message['value']))
        elif operation == 'jog':
            rpm = float(message['value'])
            axis.jog(rpm)
            effective = max(-axis.c.vmax * 60, min(axis.c.vmax * 60, rpm))
            self.output('jog_command', axis=index, requested_rpm=rpm, effective_rpm=effective)
        elif operation == 'jog_stop':
            axis.jog_stop()
        else:
            raise ValueError('Unknown operation')

    def step(self):
        start = self.clock()
        dt = start - self.previous
        if not 0 < dt <= self.deadline:
            raise ServoFault('Servo cycle exceeded 20 ms; session latched off')
        if start - self.last_client > self.client_timeout:
            raise ServoFault('Interface heartbeat missing; session latched off')
        counts = self.board.read_encoders()
        read_finished = self.clock()
        loopback = self.loopback
        if loopback is not None and loopback.active:
            loopback.observe(self.board.encoder_a_levels[loopback.axis], self.board.last_feedback_received_ns)
        for axis, raw in zip(self.axes, counts):
            axis.feedback(raw, dt)
        for _ in range(32):
            try:
                received, message = self.commands.get_nowait()
            except queue.Empty:
                break
            if start - received > self.client_timeout:
                if message.get('op') == 'heartbeat':
                    continue  # Discovery can take longer than a client heartbeat interval.
                raise ServoFault('Stale interface command')
            self.last_client = received
            try:
                self.dispatch(message)
            except (ValueError, KeyError, TypeError) as exc:
                self.output('rejected', message=str(exc))
        volts = []
        for index, axis in enumerate(self.axes, 1):
            try:
                volts.append(axis.calculate(dt))
            except ServoFault as exc:
                raise ServoFault(f'Motor {index}: {exc}') from exc
        if self.clock() - start >= self.deadline:
            raise ServoFault('Feedback/control exceeded deadline; outputs not refreshed')
        enabled = [axis.enabled for axis in self.axes]
        loopback = self.loopback
        if loopback is not None and (loopback.active or self.loopback_progress is not None):
            volts = [0.0] * 4
            enabled = [False] * 4
            if loopback.mode == "analog":
                # Keep the analog gate enabled at zero throughout OFF detection.
                enabled[loopback.axis] = loopback.active and loopback.phase != "cleanup"
                volts[loopback.axis] = loopback.analog_high_volts if enabled[loopback.axis] and loopback.output else 0.0
            else:
                enabled[loopback.axis] = loopback.active and loopback.output
        if self.pwm_pulse_until is not None and self.clock() >= self.pwm_pulse_until:
            self.pwm_test = None
            self.pwm_pulse_until = None
        if self.pwm_test is not None:
            index, percent = self.pwm_test
            volts, enabled = [0.0] * 4, [False] * 4
            volts[index], enabled[index] = percent / 10.0, True
        write_started = self.clock()
        self.board.write_servo(volts, enabled, generic_outputs=self.generic_outputs)
        write_finished = self.clock()
        if loopback is not None:
            loopback.written(self.board.last_output_sent_ns)
        if self.clock() - start >= self.deadline:
            raise ServoFault('Output acknowledgement exceeded deadline')
        self.metrics.add(interval=round(dt * 1e9), wake_lateness=self.wake_lateness_ns,
                         read=round((read_finished - start) * 1e9),
                         control=round((write_started - read_finished) * 1e9),
                         write=round((write_finished - write_started) * 1e9),
                         work=round((write_finished - start) * 1e9))
        if self.pwm_test != self.pwm_report:
            self.output('pwm_test', active=self.pwm_test is not None,
                        axis=self.pwm_test[0] if self.pwm_test else None,
                        percent=self.pwm_test[1] if self.pwm_test else 0,
                        nominal_volts=self.pwm_test[1] / 10.0 if self.pwm_test else 0)
            self.pwm_report = self.pwm_test
        if loopback is not None:
            progress = (loopback.active, loopback.phase, len(loopback.off_ns), loopback.error)
            if progress != self.loopback_progress:
                self.output('loopback', **loopback.report(), timing=self.metrics.report(), runtime=self.runtime)
                self.loopback_progress = progress if loopback.active else None
                if not loopback.active:
                    self.loopback = None
        self.previous = start
        self.cycles += 1
        self.max_cycle_ms = max(self.max_cycle_ms, dt * 1000)
        if start - self.last_status >= 0.05:
            self.output('status', axes=[axis.telemetry() for axis in self.axes], cycle_ms=dt * 1000,
                        diagnostics=dict(raw_counts=counts, cycles=self.cycles,
                                         max_cycle_ms=self.max_cycle_ms,
                                         watchdog_ok=True, timing=self.metrics.report()),
                        io={connector: dict(inputs=self.board.generic_inputs.get(connector, 0), outputs=value)
                            for connector, value in self.generic_outputs.items()})
            self.last_status = start

    def rearm(self, index):
        peer = self.board.bus.peer
        candidate = None
        try:
            candidate = Mesa7i80hdt(peer[0], port=peer[1], timeout=0.25)
            candidate.encoder_mapping('P3')
            candidate.bus.timeout = 0.008
            candidate.configure_servo('P3', watchdog_ms=100)
            for connector in ('P1', 'P2'):
                candidate.configure_generic_io(connector)
            counts = candidate.read_encoders()
            for axis, raw in zip(self.axes, counts):
                axis.feedback(raw, self.deadline)
            time.sleep(self.period)
            counts = candidate.read_encoders()
            for axis, raw in zip(self.axes, counts):
                axis.feedback(raw, self.period)
            self.axes[index].enable()
        except (MesaError, ServoFault, ValueError, OSError):
            if candidate is not None:
                try:
                    candidate.close()
                except MesaError:
                    pass
            for axis in self.axes:
                axis.disable()
            raise
        self.board = candidate
        self.previous = self.last_client = self.clock()
        self.last_status = 0.0
        self.output('rearmed', axis=index)

    def diagnose_fault(self, fault):
        self.pwm_test = self.pwm_report = None
        self.pwm_pulse_until = None
        self.output("pwm_test", active=False, percent=0, nominal_volts=0)
        if self.loopback is not None:
            self.loopback.cancel('Teste interrompido por falha: ' + str(fault))
            self.loopback.active = False
            self.output('loopback', **self.loopback.report(), timing=self.metrics.report(), runtime=self.runtime)
            self.loopback = self.loopback_progress = None
        for axis in self.axes:
            axis.disable()
        self.generic_outputs = {'P1': 0, 'P2': 0}
        shutdown_error = None
        try:
            self.board.close()
        except MesaError as exc:
            shutdown_error = str(exc)
        self.output('fault', message=str(fault), diagnostic_mode=True, shutdown_error=shutdown_error)
        self.last_client = self.clock()
        gc.collect()
        last_error = None
        while self.running:
            for _ in range(128):
                try:
                    received, message = self.commands.get_nowait()
                except queue.Empty:
                    break
                operation = message.get('op')
                if operation == 'quit':
                    self.running = False
                    return
                if self.clock() - received > self.client_timeout:
                    continue
                self.last_client = received
                if operation in ('enable', 'output_test', 'acceleration', 'deceleration', 'configure'):
                    try:
                        index = message.get('axis')
                        if type(index) is not int or not 0 <= index < 4:
                            raise ValueError('Invalid axis')
                        if operation == 'enable':
                            self.rearm(index)
                            return True
                        self.dispatch(message)
                    except (MesaError, ServoFault, ValueError, OSError, KeyError, TypeError) as exc:
                        self.output('rejected', message='Rearme / ajuste: ' + str(exc))
                    continue
                if operation not in ('heartbeat', 'stop_all', 'disable', 'stop', 'jog_stop'):
                    self.output('rejected', message='Use ENABLE para rearmar antes de comandar movimento')
            if self.clock() - self.last_client > self.client_timeout:
                return
            try:
                self.output('diagnostic_status', **self.board.read_diagnostics())
                last_error = None
            except (MesaError, OSError) as exc:
                error = str(exc)
                if error != last_error:
                    self.output('diagnostic_error', message=error)
                last_error = error
            time.sleep(0.1)

    def run(self):
        collect_automatically = gc.isenabled()
        gc.disable()  # Refcounting remains active; no cyclic collection in the servo loop.
        try:
            timer = CycleTimer(round(self.period * 1e9))
            self.previous = self.clock()
            while self.running:
                self.wake_lateness_ns = timer.wait()
                self.metrics.skipped = timer.skipped
                try:
                    self.step()
                except (MesaError, ServoFault) as exc:
                    if self.clock() - self.last_client > self.client_timeout:
                        raise
                    # Collect outside cyclic control, after shutdown, in diagnosis.
                    if self.diagnose_fault(exc):
                        timer = CycleTimer(round(self.period * 1e9))
                        self.metrics = CycleMetrics(round(self.period * 1e9))
                        continue
                    return
        finally:
            if collect_automatically:
                gc.enable()


def read_commands(commands):
    try:
        for line in sys.stdin:
            if len(line) > 4096:
                break
            message = json.loads(line)
            if not isinstance(message, dict):
                break
            commands.put_nowait((time.monotonic(), message))
    except (ValueError, queue.Full):
        pass
    # EOF/invalid input is never permission to keep moving unattended.
    try:
        commands.put_nowait((time.monotonic(), {'op': 'quit'}))
    except queue.Full:
        pass  # Queue overflow will fail the client/deadline checks.


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', required=True)
    parser.add_argument('--port', type=int, default=27181, help='UDP simulator or LBP16 port')
    args = parser.parse_args()
    board = None
    lock = None
    result = 0
    session = None
    try:
        config, axes = load_config(args.config)
        name = hashlib.sha256(f"{config['ip']}:{args.port}".encode()).hexdigest()[:24]
        lock = open(os.path.join(tempfile.gettempdir(), f't3d-analog-{name}.lock'), 'a', encoding='ascii')
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        commands = queue.Queue(maxsize=128)
        threading.Thread(target=read_commands, args=(commands,), daemon=True).start()
        board = Mesa7i80hdt(config['ip'], port=args.port, timeout=0.25)
        # Discovery is read-only; validate all encoder/output pins before writes.
        board.encoder_mapping(config['connector'])
        board.bus.timeout = 0.008
        board.configure_servo(config['connector'], watchdog_ms=100)
        for connector in ('P1', 'P2'):
            board.configure_generic_io(connector)
        session = Session(board, axes, commands)
        runtime = configure_runtime()
        from run_backend import native_modules
        runtime['native_modules'] = native_modules()
        session.runtime = runtime
        emit('ready', model=board.model, connector=config['connector'],
             identification=board.inspect(), encoder_channels=board.encoder_channels,
             watchdog_ms=100, pdm_hz=board.pdm_frequency, runtime=runtime)
        # Absolute timer waits for the first period; all outputs are still disabled.
        session.run()
    except (MesaError, ServoFault, ValueError, OSError, KeyError, TypeError) as exc:
        emit('fault', message=str(exc))
        result = 1
    finally:
        if session is not None:
            board = session.board
        if board is not None:
            try:
                board.close()
            except MesaError as exc:
                emit('fault', message=f'Output shutdown not acknowledged; hardware watchdog active: {exc}')
                result = 1
        if lock is not None:
            lock.close()
    return result


if __name__ == '__main__':
    # Compatibility with the already installed privileged helper: its fixed
    # backend.py entry delegates to the compiled module before any board I/O.
    from run_backend import native_modules
    native_modules()
    import backend as native_backend
    sys.exit(native_backend.main())
