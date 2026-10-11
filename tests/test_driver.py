"""Actual UDP datagrams against simulated HM2 PWM, GPIO and watchdog modules."""
import math
import socket
import struct
import threading
import time
import unittest

from mesa7i80hdt import (Mesa7i80hdt, Lbp16, FirmwareError, MesaError,
                        CommunicationError, command)


class Simulator:
    GPIO, PWM, WD = 0x2000, 0x7000, 0x7800
    STRIDE = 0x80

    def __init__(self, connector=1, first_channel=0):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(('127.0.0.1', 0))
        self.sock.settimeout(0.02)
        self.port = self.sock.getsockname()[1]
        self.memory = {0x100: 0x55AACAFE, 0x104: 0x54534F48,
                       0x108: 0x32544F4D, 0x10C: 0x800}
        header = [3, 64, 384, *struct.unpack('<II', b'MESA7I80'), 20, 256,
                  3, 72, 24, 100000000, 200000000, 4, 16, self.STRIDE, 0x100]
        for i, value in enumerate(header):
            self.memory[0x800 + i * 4] = value
        for i, (tag, base, regs, instances, bitmap, clock_tag) in enumerate(
                [(3, self.GPIO, 5, 3, 31, 1), (6, self.PWM, 5, 12, 3, 2),
                 (2, self.WD, 3, 1, 0, 1)]):
            self.memory[0x840 + i * 12] = tag | clock_tag << 16 | instances << 24
            self.memory[0x844 + i * 12] = base | regs << 16
            self.memory[0x848 + i * 12] = bitmap
        for axis, pins in enumerate(((15, 19, 23), (13, 17, 21), (39, 43, 47), (37, 41, 45))):
            for role, physical in enumerate(pins, 0x81):
                index = connector * 24 + (physical - 1) // 2
                self.memory[0x980 + index * 4] = 3 << 24 | (first_channel + axis) << 16 | 6 << 8 | role
        for p in range(3):
            for r in range(1, 5):
                self.memory[self.GPIO + r * self.STRIDE + p * 4] = 0x800001
        self.initial = dict(self.memory)
        self.model = b'7I80HDT'
        self.writes = []
        self.drop_ack = False
        self.truncate = False
        self.running = True
        self.errors = []
        self.wd_period = None
        self.wd_feed = None
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()

    def expire(self):
        if self.wd_period is not None and time.monotonic() - self.wd_feed > self.wd_period:
            self.memory[self.WD + self.STRIDE] = 1
            for p in range(3):
                self.memory[self.GPIO + self.STRIDE + p * 4] = 0
                self.memory[self.GPIO + 3 * self.STRIDE + p * 4] = 0

    def run(self):
        while self.running:
            try:
                packet, peer = self.sock.recvfrom(2048)
            except socket.timeout:
                self.expire()
                continue
            except OSError:
                return
            try:
                self.expire()
                response, wrote = self.process(packet)
                if self.drop_ack and wrote:
                    continue
                self.sock.sendto(response[:1] if self.truncate else response, peer)
            except Exception as exc:
                self.errors.append(exc)

    def process(self, packet):
        offset, response, wrote = 0, b'', False
        while offset < len(packet):
            cmd, address = struct.unpack_from('<HH', packet, offset)
            offset += 4
            count, space = cmd & 127, (cmd >> 10) & 7
            assert count and cmd & 0x4000
            if space == 7:
                assert cmd == 0x5D88 and address == 0
                response += self.model.ljust(16, b'\0')
                continue
            assert space == 0 and (cmd & 0x300) == 0x200
            for _ in range(count):
                if cmd & 0x8000:
                    value = struct.unpack_from('<I', packet, offset)[0]
                    offset += 4
                    self.writes.append((address, value))
                    self.memory[address] = value
                    if address == self.WD:
                        self.wd_period = None if value & 0x80000000 else (value + 1) / 100000000
                        self.wd_feed = time.monotonic()
                    if address == self.WD + 2 * self.STRIDE and value == 0x5A000000:
                        self.wd_feed = time.monotonic()
                    wrote = True
                else:
                    response += struct.pack('<I', self.memory.get(address, 0))
                if cmd & 0x80:
                    address += 4
        return response, wrote

    def stop(self):
        self.running = False
        self.thread.join(0.2)
        self.sock.close()
        if self.errors:
            raise AssertionError(self.errors)


class DriverTests(unittest.TestCase):
    def test_generic_connector_split_and_zero_before_outputs_and_shutdown(self):
        sim = Simulator(connector=0)
        self.addCleanup(sim.stop)
        board = Mesa7i80hdt('127.0.0.1', port=sim.port, timeout=0.04)
        board.configure_7i33ta('P1')
        before = dict(sim.memory)
        start = len(sim.writes)
        board.configure_generic_io('P2')
        self.assertEqual(sim.memory[sim.GPIO + sim.STRIDE + 4] & 0xFFFFFF, 0xFFF000)
        self.assertEqual(sim.memory[sim.GPIO + 4], 0)
        for r in (2, 3, 4):
            self.assertEqual(sim.memory[sim.GPIO + r * sim.STRIDE + 4] & 0xFFFFFF, 0)
        for r in range(5):
            for p in (0, 2):
                address = sim.GPIO + r * sim.STRIDE + p * 4
                self.assertEqual(sim.memory.get(address, 0), before.get(address, 0))
        port_writes = [(a, v) for a, v in sim.writes[start:] if a in
                       [sim.GPIO + r * sim.STRIDE + 4 for r in range(5)]]
        self.assertEqual(port_writes[0], (sim.GPIO + sim.STRIDE + 4, 0))
        self.assertEqual(port_writes[1], (sim.GPIO + 4, 0))
        self.assertEqual(port_writes[-1], (sim.GPIO + sim.STRIDE + 4, 0xFFF000))
        writes = len(sim.writes)
        with self.assertRaises(MesaError):
            board.configure_generic_io('P1')
        self.assertEqual(len(sim.writes), writes)
        board.close()
        self.assertEqual(sim.memory[sim.GPIO + sim.STRIDE + 4] & 0xFFFFFF, 0)
        self.assertEqual(sim.memory[sim.GPIO + 4], 0)

    def setUp(self):
        self.sim = Simulator()
        self.addCleanup(self.sim.stop)
        self.board = Mesa7i80hdt('127.0.0.1', port=self.sim.port, timeout=0.04)

    def test_identification_and_mapping_are_read_only(self):
        info = self.board.inspect()
        self.assertEqual(info['model'], '7I80HDT')
        self.assertEqual((info['io_width'], info['port_width']), (72, 24))
        self.assertTrue(info['connectors']['P2']['pinout_7i33ta_compatible'])
        self.assertFalse(info['connectors']['P1']['pinout_7i33ta_compatible'])
        self.assertEqual(info['connectors']['P2']['pwm_channels'], [0, 1, 2, 3])
        self.assertEqual(self.sim.writes, [])

    def test_initialize_pdm_disabled_and_preserve_unrelated_gpio(self):
        self.board.configure_7i33ta('P2')
        self.assertEqual(self.sim.memory[self.sim.PWM + 4 * self.sim.STRIDE], 0)
        for channel in range(4):
            self.assertEqual(self.sim.memory[self.sim.PWM + channel * 4], 0)
            self.assertEqual(self.sim.memory[self.sim.PWM + self.sim.STRIDE + channel * 4], 0x1B)
        self.assertEqual(self.sim.memory[self.sim.PWM + 3 * self.sim.STRIDE], 1966)
        self.assertEqual(self.sim.memory[self.sim.WD], 9999999)
        for p in (0, 2):
            for r in range(1, 5):
                address = self.sim.GPIO + r * self.sim.STRIDE + p * 4
                self.assertEqual(self.sim.memory[address], self.sim.initial[address])
        for r in (2, 4):
            address = self.sim.GPIO + r * self.sim.STRIDE + 4
            self.assertEqual(self.sim.memory[address] & ~self.board.output_mask,
                             self.sim.initial[address] & ~self.board.output_mask)
        self.assertEqual(self.sim.memory[self.sim.GPIO + self.sim.STRIDE + 4], self.board.output_mask)
        self.assertEqual(self.sim.memory[self.sim.GPIO + 3 * self.sim.STRIDE + 4], 0)
        self.board.close()

    def test_voltage_encoding_and_polarity(self):
        self.assertEqual(self.board.voltage_word(0), 0)
        self.assertEqual(self.board.voltage_word(5), 0x88000000)
        self.assertEqual(self.board.voltage_word(-5), 0x08000000)
        self.assertEqual(self.board.voltage_word(10), 0x8FFF0000)
        self.assertEqual(self.board.voltage_word(-10), 0x0FFF0000)
        for value in (math.nan, math.inf, -math.inf, 10.001, -10.001, '5'):
            with self.assertRaises(ValueError):
                self.board.voltage_word(value)

    def test_voltage_does_not_enable_and_disable_zeroes_setpoint(self):
        self.board.configure_7i33ta('P2')
        self.board.set_voltages({0: 5, 1: -5, 2: 10, 3: -10})
        self.assertEqual(self.sim.memory[self.sim.PWM], 0x88000000)
        self.assertEqual(self.sim.memory[self.sim.PWM + 4], 0x08000000)
        self.assertEqual(self.sim.memory[self.sim.PWM + 4 * self.sim.STRIDE], 0)
        self.board.set_enabled(0, True)
        self.board.set_enabled(2, True)
        self.assertEqual(self.sim.memory[self.sim.PWM + 4 * self.sim.STRIDE], 5)
        self.board.set_enabled(0, False)
        self.assertEqual(self.sim.memory[self.sim.PWM], 0)
        self.assertEqual(self.sim.memory[self.sim.PWM + 4 * self.sim.STRIDE], 4)
        self.board.close()

    def test_close_zeroes_disables_and_leaves_output_pins_as_inputs(self):
        self.board.configure_7i33ta('P2')
        mask = self.board.output_mask
        self.board.set_voltage(1, 2.5)
        self.board.set_enabled(1, True)
        self.board.close()
        self.assertEqual(self.sim.memory[self.sim.PWM + 4], 0)
        self.assertEqual(self.sim.memory[self.sim.PWM + 4 * self.sim.STRIDE], 0)
        self.assertEqual(self.sim.memory[self.sim.GPIO + self.sim.STRIDE + 4] & mask, 0)
        self.assertFalse(self.sim.memory[self.sim.WD] & 0x80000000)
        with self.assertRaises(MesaError):
            self.board.set_voltage(0, 1)

    def test_other_connector_and_nonzero_pwm_instances(self):
        sim = Simulator(connector=2, first_channel=4)
        self.addCleanup(sim.stop)
        board = Mesa7i80hdt('127.0.0.1', port=sim.port)
        board.configure_7i33ta('P3')
        board.set_voltage(0, 5)
        board.set_enabled(0, True)
        self.assertEqual(sim.memory[sim.PWM + 4 * 4], 0x88000000)
        self.assertEqual(sim.memory[sim.PWM + 4 * sim.STRIDE], 1 << 4)
        self.assertFalse(any(a == sim.PWM for a, v in sim.writes))
        board.close()

    def test_wrong_pin_mapping_refuses_all_writes(self):
        self.board.pins[24 + 7] = self.board.pins[24 + 6]
        with self.assertRaises(FirmwareError):
            self.board.configure_7i33ta('P2')
        self.assertEqual(self.sim.writes, [])

    def test_missing_watchdog_refuses_all_writes(self):
        del self.board.modules[2]
        with self.assertRaises(FirmwareError):
            self.board.configure_7i33ta('P2')
        self.assertEqual(self.sim.writes, [])

    def test_already_enabled_board_refuses_takeover(self):
        self.sim.memory[self.sim.PWM + 4 * self.sim.STRIDE] = 1
        with self.assertRaises(MesaError):
            self.board.configure_7i33ta('P2')
        self.assertEqual(self.sim.writes, [])

    def test_expired_watchdog_drops_ddr_and_cannot_auto_resume(self):
        self.board.configure_7i33ta('P2', watchdog_ms=20)
        self.board.set_enabled(0, True)
        time.sleep(0.04)
        with self.assertRaises(CommunicationError):
            self.board.keepalive()
        self.assertEqual(self.sim.memory[self.sim.WD + self.sim.STRIDE], 1)
        self.assertEqual(self.sim.memory[self.sim.GPIO + self.sim.STRIDE + 4], 0)
        with self.assertRaises(MesaError):
            self.board.set_enabled(0, True)
        self.board.close()

    def test_hardware_watchdog_status_rejected(self):
        self.board.configure_7i33ta('P2')
        self.sim.memory[self.sim.WD + self.sim.STRIDE] = 1
        with self.assertRaises(CommunicationError):
            self.board.keepalive()
        self.assertTrue(self.board.faulted)
        self.board.close()

    def test_lost_ack_never_retransmits_output(self):
        self.board.configure_7i33ta('P2')
        self.sim.drop_ack = True
        with self.assertRaises(CommunicationError):
            self.board.set_voltage(0, 5)
        self.assertEqual(self.sim.writes.count((self.sim.PWM, 0x88000000)), 1)
        with self.assertRaises(MesaError):
            self.board.set_voltage(0, 5)
        self.assertEqual(self.sim.writes.count((self.sim.PWM, 0x88000000)), 1)

    def test_lost_config_ack_blocks_use(self):
        self.sim.drop_ack = True
        with self.assertRaises(CommunicationError):
            self.board.configure_7i33ta('P2')
        with self.assertRaises(MesaError):
            self.board.set_voltage(0, 1)

    def test_wrong_physical_model_rejected(self):
        self.sim.model = b'7I80HD-16'
        with self.assertRaises(FirmwareError):
            Mesa7i80hdt('127.0.0.1', port=self.sim.port)
        self.assertEqual(self.sim.writes, [])

    def test_malformed_reply_and_wire_encoding(self):
        self.assertEqual(command(0x100, 1), bytes.fromhex('81420001'))
        self.sim.truncate = True
        with self.assertRaises(CommunicationError):
            Lbp16('127.0.0.1', port=self.sim.port).read(0x100)

    def test_invalid_arguments_do_not_write(self):
        for connector in ('P1', 'P3'):
            with self.assertRaises(FirmwareError):
                self.board.configure_7i33ta(connector)
        with self.assertRaises(ValueError):
            self.board.configure_7i33ta('P4')
        with self.assertRaises(ValueError):
            self.board.configure_7i33ta('P2', watchdog_ms=0)
        self.assertEqual(self.sim.writes, [])
        self.board.configure_7i33ta('P2')
        for axis in (-1, 4, 1.1):
            with self.assertRaises(ValueError):
                self.board.set_voltage(axis, 0)
        self.board.close()


if __name__ == '__main__':
    unittest.main()
