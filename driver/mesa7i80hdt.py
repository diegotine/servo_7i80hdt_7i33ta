"""7I80HDT Ethernet -> HostMot2 PWM/PDM -> 7I33TA +/-10 V. Python 3.10+, standard library only.

Register definitions: Mesa regmap, pwmpdmgenh.vhd and board manuals (see README).
No LinuxCNC/HAL runtime. Firmware pin descriptors must match the 7I33TA.
Output updates/keepalive must be called before the hardware watchdog expires.
"""

import argparse
from dataclasses import dataclass, asdict
import json
import math
import socket
import struct
import threading
import time


class MesaError(Exception):
    pass


class FirmwareError(MesaError):
    pass


class CommunicationError(MesaError):
    """Outcome may be unknown; commands must not be retried automatically."""


def command(address: int, count: int, *, write=False, increment=True) -> bytes:
    if not 1 <= count <= 127 or address % 4 or not 0 <= address <= 0xFFFC:
        raise ValueError('Invalid aligned HM2 address or LBP16 count')
    if increment and address + 4 * count > 0x10000:
        raise ValueError('LBP16 address range overflow')
    return struct.pack('<HH', 0x4200 | count | (0x8000 if write else 0)
                       | (0x80 if increment else 0), address)


def write_command(address: int, values, *, increment=True) -> bytes:
    values = tuple(values)
    return command(address, len(values), write=True, increment=increment) + struct.pack(
        '<' + 'I' * len(values), *values)


class Lbp16:
    """Single request per UDP socket; no retries of destructive FIFO operations.

    A fresh source port isolates late replies from a timed-out transaction.
    The host/board must be on a trusted LAN; LBP16 has no authentication.
    """

    def __init__(self, ip='192.168.1.121', timeout=0.25, port=27181):
        socket.inet_pton(socket.AF_INET, ip)
        if timeout <= 0 or not 1 <= port <= 65535:
            raise ValueError('Invalid UDP timeout/port')
        self.peer = (ip, port)
        self.timeout = timeout

    def exchange(self, packet: bytes, reply_bytes: int, timeout=None) -> bytes:
        if len(packet) > 1400 or not 0 < reply_bytes <= 1400:
            raise ValueError('LBP16 packet exceeds driver limit')
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.settimeout(self.timeout if timeout is None else timeout)
            sock.connect(self.peer)
            try:
                self.last_send_ns = time.monotonic_ns()
                sock.send(packet)
                reply = sock.recv(2048)
                self.last_receive_ns = time.monotonic_ns()
            except OSError as exc:
                raise CommunicationError(f'UDP {self.peer}: {exc}; outcome unknown') from exc
        if len(reply) != reply_bytes:
            raise CommunicationError(f'LBP16 reply size {len(reply)}, expected {reply_bytes}')
        return reply

    def read(self, address, count=1, *, increment=True, timeout=None):
        raw = self.exchange(command(address, count, increment=increment), count * 4, timeout)
        return struct.unpack('<' + 'I' * count, raw)

    def write(self, packet: bytes):
        # Reads execute after preceding writes in the same datagram. This confirms
        # processing, but does not justify a retry if the acknowledgement is lost.
        raw = self.exchange(packet + command(0x100, 1), 4)
        if struct.unpack('<I', raw)[0] != 0x55AACAFE:
            raise CommunicationError('Invalid HM2 cookie after write')


@dataclass(frozen=True)
class Module:
    tag: int
    version: int
    instances: int
    base: int
    registers: int
    register_stride: int
    instance_stride: int
    clock: int
    bitmap: int

    def address(self, register, channel=0):
        if not 0 <= register < self.registers or not 0 <= channel < self.instances:
            raise FirmwareError('Register/channel unavailable')
        address = self.base + register * self.register_stride + channel * self.instance_stride
        if address % 4 or not 0 <= address <= 0xFFFC:
            raise FirmwareError('Invalid module address')
        return address


class Mesa7i80hdt:
    """Exclusive owner of the board while open. Calls are serialized per instance.

    Constructing/inspect() only read identification. configure_7i33ta() owns
    one connector, the shared PDM rate and board-wide watchdog. No other client (HAL,
    mesaflash, second process) may control the board concurrently.
    """

    def __init__(self, ip='192.168.1.121', *, timeout=0.25, port=27181):
        self.bus = Lbp16(ip, timeout, port)
        self.lock = threading.RLock()
        self.configured = False
        self.faulted = False
        self.pwm = self.watchdog = None
        self.connector_port = None
        self.generic_ports = set()
        self.generic_inputs = {}
        self.output_mask = 0
        self.enable_mask = 0
        self.enabled = 0
        self._discover()

    def _discover(self):
        cookie, name0, name1, offset = self.bus.read(0x100, 4)
        if cookie != 0x55AACAFE or struct.pack('<II', name0, name1) != b'HOSTMOT2':
            raise FirmwareError('Not a HostMot2 image')
        header = self.bus.read(offset, 16)
        self.board = struct.pack('<II', *header[3:5]).decode('ascii', errors='replace').strip('\0 ')
        if header[0] != 3:
            # The separate LBP board information identifies the physical model.
            raise FirmwareError(f'Unsupported IDROM type/board: {header[0]}, {self.board}')
        board_info = self.bus.exchange(struct.pack('<HH', 0x5D88, 0), 16)
        self.model = board_info.decode('ascii', errors='replace').strip('\0 ')
        if self.model.upper() != '7I80HDT':
            raise FirmwareError(f'Expected physical 7I80HDT, found {self.model!r}')
        self.io_ports, self.io_width, self.port_width = header[7:10]
        if (self.io_ports, self.io_width, self.port_width) != (3, 72, 24):
            raise FirmwareError('Invalid I/O geometry')
        self.modules = {}
        for index in range(32):
            a, b, bitmap = self.bus.read(offset + header[1] + index * 12, 3)
            tag = a & 255
            if not tag:
                break
            clock_tag, rs, ins = (a >> 16) & 255, (b >> 24) & 15, b >> 28
            if clock_tag not in (1, 2) or rs not in (0, 1) or ins not in (0, 1):
                raise FirmwareError('Unsupported module descriptor')
            if tag in self.modules:
                raise FirmwareError('Duplicate module descriptor')
            self.modules[tag] = Module(tag, (a >> 8) & 255, a >> 24, b & 65535,
                                       (b >> 16) & 255, header[14 + rs],
                                       header[12 + ins], header[9 + clock_tag], bitmap)
        else:
            raise FirmwareError('Missing module descriptor terminator')
        self.pins = []
        for index in range(self.io_width):
            self.pins.append(self.bus.read(offset + header[2] + index * 4)[0])

    def _servo_mapping(self, connector):
        if connector not in ('P1', 'P2', 'P3'):
            raise ValueError('Expected connector P1, P2 or P3')
        port = int(connector[1]) - 1
        # 7I33TA J1 controller pinout, manual p.5: PWM, DIR, /ENA per axis.
        local_pins = ((15, 19, 23), (13, 17, 21), (39, 43, 47), (37, 41, 45))
        channels = []
        mask = 0
        for axis_pins in local_pins:
            units = set()
            for role, physical_pin in enumerate(axis_pins, 0x81):
                index = port * 24 + (physical_pin - 1) // 2
                descriptor = self.pins[index]
                if descriptor >> 24 != 3 or descriptor & 0xFFFF != (6 << 8 | role):
                    raise FirmwareError(f'{connector}-{physical_pin}: firmware does not match 7I33TA PWM/DIR/enable')
                units.add((descriptor >> 16) & 255)
                mask |= 1 << ((physical_pin - 1) // 2)
            if len(units) != 1:
                raise FirmwareError('PWM/DIR/enable pins must refer to the same PWMGen instance')
            channels.append(units.pop())
        if len(set(channels)) != 4:
            raise FirmwareError('7I33TA needs four distinct PWMGen instances')
        pwm = self.modules.get(6)
        if pwm is None or any(channel >= min(pwm.instances, 32) for channel in channels):
            raise FirmwareError('PWMGen instance missing')
        for channel in channels:
            pins = [i for i, p in enumerate(self.pins)
                    if ((p >> 8) & 255) == 6 and ((p >> 16) & 255) == channel]
            if len(pins) != 3 or any(i // 24 != port for i in pins):
                raise FirmwareError('Ambiguous PWMGen pin mapping/fanout')
        return port, channels, mask

    def inspect(self):
        connectors = {}
        for connector in ('P1', 'P2', 'P3'):
            try:
                _, channels, _ = self._servo_mapping(connector)
                connectors[connector] = {'pinout_7i33ta_compatible': True,
                                         'pwm_channels': channels}
            except FirmwareError as exc:
                connectors[connector] = {'pinout_7i33ta_compatible': False, 'reason': str(exc)}
        return {'model': self.model, 'board': self.board, 'ip': self.bus.peer[0],
                'io_ports': self.io_ports, 'io_width': self.io_width, 'port_width': self.port_width,
                'connectors': connectors,
                'modules': [asdict(module) for module in self.modules.values()]}

    def encoder_mapping(self, connector):
        """Validate 7I33TA A/B/index inputs before ANY configuration writes."""
        port, _, _ = self._servo_mapping(connector)
        encoder = self.modules.get(4)
        if (encoder is None or encoder.version not in (2, 3, 0x83)
                or encoder.registers != 5 or encoder.bitmap != 3
                or encoder.instance_stride != 4 or encoder.register_stride < 4):
            raise FirmwareError('Requires non-multiplexed HM2 Encoder v2/v3, five registers')
        channels = []
        for pins in ((7, 5, 11), (3, 1, 9), (31, 29, 35), (27, 25, 33)):
            units = set()
            for role, physical in enumerate(pins, 1):
                descriptor = self.pins[port * 24 + (physical - 1) // 2]
                if descriptor >> 24 != 3 or descriptor & 0xFFFF != (4 << 8 | role):
                    raise FirmwareError(f'{connector}-{physical}: expected encoder A/B/index')
                units.add((descriptor >> 16) & 255)
            if len(units) != 1:
                raise FirmwareError('Encoder A/B/index must belong to one instance')
            channels.append(units.pop())
        if len(set(channels)) != 4 or max(channels) >= encoder.instances:
            raise FirmwareError('Requires four distinct encoder instances')
        for channel in channels:
            for role in (1, 2, 3):
                inputs = [i for i, p in enumerate(self.pins)
                          if (p & 0xFFFF) == (4 << 8 | role) and (p >> 16 & 255) == channel]
                if len(inputs) != 1 or inputs[0] // 24 != port:
                    raise FirmwareError('Ambiguous encoder input mapping')
        # Refuse overlapping descriptors, including collisions with output registers.
        addresses = [encoder.address(r, c) for c in channels for r in (0, 1)]
        addresses += [encoder.address(r) for r in (2, 3, 4)]
        for tag, registers in ((6, range(5)), (2, range(3)), (3, range(5))):
            module = self.modules[tag]
            for r in registers:
                instances = range(module.instances) if module.bitmap & (1 << r) else (0,)
                addresses += [module.address(r, c) for c in instances]
        if len(set(addresses)) != len(addresses):
            raise FirmwareError('Overlapping encoder/output module registers')
        return encoder, channels

    def configure_servo(self, connector, *, watchdog_ms=100):
        encoder, channels = self.encoder_mapping(connector)
        self.configure_7i33ta(connector, watchdog_ms=watchdog_ms)
        self.encoder, self.encoder_channels = encoder, channels
        # Quadrature, filter=15 clocks, no clear/latch on index. Never clear counts.
        packet = b''.join(write_command(encoder.address(1, channel), [0x8800])
                          for channel in channels)  # bit15 clears old quadrature errors
        packet += write_command(encoder.address(4), [0xFFF])  # 12-bit divider MSB: ClockLow
        packet += write_command(self.watchdog.address(2), [0x5A000000])
        self._commit(packet)

    def read_encoders(self):
        """Return low-16-bit counts; timestamp upper halves are NOT position bits."""
        with self.lock:
            self._live()
            packet = b''.join(command(self.encoder.address(0, c), 1)
                              + command(self.encoder.address(1, c), 1)
                              for c in self.encoder_channels)
            ports = sorted(self.generic_ports | {self.connector_port})
            packet += b''.join(command(self.gpio.address(0, p), 1) for p in ports)
            packet += command(self.watchdog.address(1), 1) + command(0x100, 1)
            try:
                count = 10 + len(ports)
                data = struct.unpack(f'<{count}I', self.bus.exchange(packet, count * 4))
                if data[-2] & 1 or data[-1] != 0x55AACAFE:
                    raise CommunicationError('Watchdog expired or invalid encoder response')
                if any(data[i] & 0x8000 for i in (1, 3, 5, 7)):
                    raise CommunicationError('Encoder quadrature sequence error')
                self.generic_inputs = {f'P{p + 1}': data[8 + i] & 0xFFF for i, p in enumerate(ports)
                                       if p in self.generic_ports}
                servo_levels = data[8 + ports.index(self.connector_port)]
                # 7i33TA TTL input conditioning inverts A before it reaches HM2.
                self.encoder_a_levels = [not bool(servo_levels & (1 << bit)) for bit in (3, 1, 15, 13)]
                self.last_feedback_received_ns = self.bus.last_receive_ns
                return [data[i] & 0xFFFF for i in (0, 2, 4, 6)]
            except CommunicationError:
                self.faulted = True
                raise

    def read_diagnostics(self):
        """Read-only after shutdown/fault: never configure, clear or feed watchdog."""
        with self.lock:
            packet = b''.join(command(self.encoder.address(0, c), 1)
                              + command(self.encoder.address(1, c), 1)
                              for c in self.encoder_channels)
            packet += b''.join(command(self.gpio.address(0, p), 1)
                               + command(self.gpio.address(1, p), 1) for p in range(3))
            packet += command(self.watchdog.address(1), 1)
            packet += command(self.pwm.address(4), 1) + command(0x100, 1)
            data = struct.unpack('<17I', self.bus.exchange(packet, 68))
            if data[-1] != 0x55AACAFE:
                raise CommunicationError('Invalid diagnostic cookie')
            return dict(raw_counts=[data[i] & 0xFFFF for i in (0, 2, 4, 6)],
                        quadrature_errors=[bool(data[i] & 0x8000) for i in (1, 3, 5, 7)],
                        watchdog_expired=bool(data[14] & 1), enable_mask=data[15],
                        gpio={f'P{p + 1}': dict(levels=data[8 + p * 2] & 0xFFFFFF,
                                               directions=data[9 + p * 2] & 0xFFFFFF)
                              for p in range(3)})

    def write_servo(self, volts, enabled, *, generic_outputs=None):
        """Single cycle: four voltages, enable mask, then watchdog, with acknowledgement."""
        if len(volts) != 4 or len(enabled) != 4 or any(type(x) is not bool for x in enabled):
            raise ValueError('Expected four voltages and four boolean enable states')
        words = [self.voltage_word(v if on else 0) for v, on in zip(volts, enabled)]
        with self.lock:
            self._live()
            outputs = dict(generic_outputs or {})
            if any(connector not in ('P1', 'P2', 'P3')
                   or int(connector[1]) - 1 not in self.generic_ports
                   or type(value) is not int or not 0 <= value <= 0xFFF
                   for connector, value in outputs.items()):
                raise ValueError('Expected a 12-bit output mask for a configured generic connector')
            packet = b''.join(write_command(self.pwm.address(0, c), [v])
                              for c, v in zip(self.channels, words))
            mask = sum(1 << c for c, on in zip(self.channels, enabled) if on)
            packet += write_command(self.pwm.address(4), [mask])
            packet += b''.join(write_command(self.gpio.address(0, int(connector[1]) - 1), [value << 12])
                               for connector, value in sorted(outputs.items()))
            packet += write_command(self.watchdog.address(2), [0x5A000000])
            self._commit(packet)
            self.enabled = mask

    def configure_7i33ta(self, connector, *, watchdog_ms=100):
        """Configure four outputs at 0 V, all disabled. No automatic keepalive.

        The watchdog is global: use this driver as the exclusive board owner.
        PDM master rate is also shared by all PWMGen instances.
        """
        with self.lock:
            if self.configured or self.connector_port is not None or self.faulted:
                raise MesaError('Create a fresh driver instance before configuring again')
            if not isinstance(watchdog_ms, int) or not 20 <= watchdog_ms <= 1000:
                raise ValueError('watchdog_ms must be 20..1000 ms')
            try:
                pwm, gpio, watchdog = (self.modules[tag] for tag in (6, 3, 2))
            except KeyError as exc:
                raise FirmwareError('Firmware requires PWMGen, GPIO and watchdog modules') from exc
            if (pwm.version not in (0, 1) or pwm.registers != 5 or pwm.bitmap != 3
                    or watchdog.version != 0 or watchdog.registers != 3 or watchdog.bitmap != 0
                    or watchdog.instances != 1 or gpio.registers < 5 or gpio.instances != 3):
                raise FirmwareError('Unsupported PWMGen/GPIO/watchdog descriptor')
            if any(m.register_stride < 4 or m.instance_stride < 4 or m.clock <= 0
                   for m in (pwm, gpio, watchdog)):
                raise FirmwareError('Invalid module clock/stride')
            port, channels, mask = self._servo_mapping(connector)
            addresses = [pwm.address(r, c) for c in channels for r in (0, 1)]
            addresses += [pwm.address(r) for r in (2, 3, 4)]
            addresses += [watchdog.address(r) for r in range(3)]
            addresses += [gpio.address(r, port) for r in range(5)]
            if len(addresses) != len(set(addresses)):
                raise FirmwareError('Overlapping register addresses')
            pdm_rate = round(6_000_000 * 65536 / pwm.clock)
            timer = watchdog.clock * watchdog_ms // 1000 - 1
            if not 1 <= pdm_rate <= 65535 or not 0 <= timer < 0x80000000:
                raise FirmwareError('Clock cannot represent PDM frequency/watchdog period')
            if self.bus.read(pwm.address(4))[0]:
                raise MesaError('PWM outputs already enabled; this driver requires an idle board')
            # This driver owns the entire connector. Encoder wires must be
            # inputs, even if a previous GPIO configuration made them outputs.
            registers = {r: self.bus.read(gpio.address(r, port))[0] for r in range(1, 5)}
            port_mask = (1 << 24) - 1
            packet = write_command(gpio.address(1, port), [registers[1] & ~port_mask])
            packet += write_command(pwm.address(4), [0])
            for channel in channels:
                packet += write_command(pwm.address(0, channel), [0])
                packet += write_command(pwm.address(1, channel), [0x1B])  # 12-bit PDM, no double buffer
            packet += write_command(pwm.address(3), [pdm_rate])
            packet += write_command(watchdog.address(0), [timer])
            packet += write_command(watchdog.address(1), [0])  # Explicit initialization only
            packet += write_command(watchdog.address(2), [0x5A000000])
            for r, value in ((3, registers[3] & ~port_mask), (4, registers[4] & ~mask),
                             (2, registers[2] | mask), (1, (registers[1] & ~port_mask) | mask)):
                packet += write_command(gpio.address(r, port), [value])
            self.pwm, self.gpio, self.watchdog = pwm, gpio, watchdog
            self.connector_port, self.channels, self.output_mask = port, channels, mask
            self.enable_mask = sum(1 << channel for channel in channels)
            self.watchdog_seconds = watchdog_ms / 1000
            self.pdm_frequency = pwm.clock * pdm_rate / 65536
            self.enabled = 0
            self._commit(packet)
            self.configured = True

    def configure_generic_io(self, connector):
        """GPIO bits 0..11 inputs, 12..23 push-pull outputs initially low."""
        if connector not in ('P1', 'P2', 'P3'):
            raise ValueError('Expected connector P1, P2 or P3')
        with self.lock:
            self._live()
            port = int(connector[1]) - 1
            if port == self.connector_port:
                raise MesaError('Generic I/O cannot replace the active servo connector')
            mask = (1 << 24) - 1
            registers = {r: self.bus.read(self.gpio.address(r, port))[0] for r in range(1, 5)}
            # Remove output drive before disconnecting any secondary function.
            packet = write_command(self.gpio.address(1, port), [registers[1] & ~mask])
            packet += write_command(self.gpio.address(0, port), [0])
            packet += write_command(self.gpio.address(3, port), [registers[3] & ~mask])
            packet += write_command(self.gpio.address(4, port), [registers[4] & ~mask])
            packet += write_command(self.gpio.address(2, port), [registers[2] & ~mask])
            packet += write_command(self.gpio.address(1, port), [(registers[1] & ~mask) | 0xFFF000])
            self.generic_ports.add(port)  # Include partial configuration in shutdown.
            self._commit(packet)

    def _commit(self, packet):
        # Check watchdog status in the same datagram as the output writes.
        packet += command(self.watchdog.address(1), 1)
        packet += command(0x100, 1)
        try:
            sent_at = time.monotonic()
            status, cookie = struct.unpack('<II', self.bus.exchange(packet, 8))
            if cookie != 0x55AACAFE or status & 1:
                raise CommunicationError('Invalid cookie or hardware watchdog expired')
            self.last_update = sent_at
            self.last_output_sent_ns = self.bus.last_send_ns
        except CommunicationError:
            self.faulted = True
            raise

    def _live(self):
        if not self.configured or self.faulted:
            raise MesaError('Configure a healthy 7I33TA session first')
        if time.monotonic() - self.last_update >= self.watchdog_seconds:
            self.faulted = True
            raise CommunicationError('Watchdog deadline missed; explicit new session required')

    @staticmethod
    def voltage_word(volts):
        if not isinstance(volts, (int, float)) or not math.isfinite(volts) or not -10 <= volts <= 10:
            raise ValueError('Expected finite nominal voltage between -10 and +10 V')
        # HM2 PDM output B is the stored direction bit. 7I33TA DIR HIGH
        # generates positive voltage (manual p.10), hence bit31=1 for +V.
        magnitude = round(abs(volts) * 4095 / 10)
        return magnitude << 16 | ((1 << 31) if volts > 0 else 0)

    def set_voltage(self, axis, volts):
        """Set a nominal voltage on local 7I33TA axis 0..3; does not enable it."""
        self.set_voltages({axis: volts})

    def set_voltages(self, values):
        """Update one or more axes in one datagram and renew the watchdog."""
        values = dict(values)
        if not values or any(type(axis) is not int or not 0 <= axis <= 3 for axis in values):
            raise ValueError('Expected one or more local axes 0..3')
        words = {axis: self.voltage_word(volts) for axis, volts in values.items()}
        with self.lock:
            self._live()
            packet = b''.join(write_command(self.pwm.address(0, self.channels[axis]), [word])
                              for axis, word in words.items())
            packet += write_command(self.watchdog.address(2), [0x5A000000])
            self._commit(packet)

    def set_enabled(self, axis, enabled):
        """Enable/disable one local axis. Disabling also zeroes its setpoint."""
        if type(axis) is not int or not 0 <= axis <= 3 or type(enabled) is not bool:
            raise ValueError('Expected axis 0..3 and boolean enabled')
        with self.lock:
            self._live()
            bit = 1 << self.channels[axis]
            updated = self.enabled | bit if enabled else self.enabled & ~bit
            packet = b'' if enabled else write_command(self.pwm.address(0, self.channels[axis]), [0])
            packet += write_command(self.pwm.address(4), [updated])
            packet += write_command(self.watchdog.address(2), [0x5A000000])
            self._commit(packet)
            self.enabled = updated

    def keepalive(self):
        """Application must call this regularly when not updating outputs."""
        with self.lock:
            self._live()
            self._commit(write_command(self.watchdog.address(2), [0x5A000000]))

    def close(self):
        """Disable and zero owned axes; leave their pins as inputs.

        Does not restore previous nonzero setpoints or disable the watchdog.
        If the network is lost, the watchdog is responsible for dropping DDR.
        """
        with self.lock:
            self.configured = False
            if self.connector_port is None:
                return
            try:
                packet = write_command(self.pwm.address(4), [0])
                for channel in self.channels:
                    packet += write_command(self.pwm.address(0, channel), [0])
                address = self.gpio.address(1, self.connector_port)
                current = self.bus.read(address)[0]
                packet += write_command(address, [current & ~((1 << 24) - 1)])
                for port in sorted(self.generic_ports):
                    packet += write_command(self.gpio.address(0, port), [0])
                    address = self.gpio.address(1, port)
                    current = self.bus.read(address)[0]
                    packet += write_command(address, [current & ~((1 << 24) - 1)])
                self.bus.write(packet)
            except CommunicationError:
                self.faulted = True
                raise
            self.connector_port = None
            self.enabled = 0


def main():
    parser = argparse.ArgumentParser(description='7I80HDT Ethernet / 7I33TA analog driver')
    parser.add_argument('--ip', default='192.168.1.121')
    sub = parser.add_subparsers(dest='action', required=True)
    sub.add_parser('inspect', help='Read identification and check 7I33TA-compatible pin mappings')
    args = parser.parse_args()
    try:
        board = Mesa7i80hdt(args.ip)
        print(json.dumps(board.inspect(), indent=2))
    except (MesaError, ValueError, OSError) as exc:
        parser.exit(1, f'{exc}\n')


if __name__ == '__main__':
    main()
