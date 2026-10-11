import json
from pathlib import Path
import queue
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from dataclasses import asdict

from loopback import Loopback
from servo import AxisConfig
from test_servo import ServoSimulator


class LoopbackTests(unittest.TestCase):
    def test_exact_on_off_timestamps_and_100_separate_samples(self):
        test = Loopback(2, 0)
        test.observe(False, 0)
        test.observe(False, 50_000_000)
        now = 51_000_000
        for iteration in range(100):
            self.assertTrue(test.pending)
            self.assertTrue(test.output)
            test.written(now)
            test.observe(True, now - 1)  # A stale snapshot cannot count as a response.
            self.assertEqual(len(test.on_ns), iteration)
            test.observe(True, now + 2_000_000)
            test.observe(True, now + 52_000_000)
            self.assertFalse(test.output)
            test.written(now + 53_000_000)
            test.observe(False, now + 56_000_000)
            if iteration < 99:
                test.observe(False, now + 106_000_000)
            now += 107_000_000
        report = test.report()
        self.assertFalse(report['active'])
        self.assertIsNone(report['error'])
        self.assertEqual(report['completed'], 100)
        self.assertEqual(report['on']['mean_ms'], 2)
        self.assertEqual(report['off']['mean_ms'], 3)
        self.assertEqual(report['on']['stddev_ms'], 0)
        self.assertEqual(len(report['off_samples_ms']), 100)

    def test_missing_wire_and_cancel_request_off_before_finishing(self):
        for cancel in (False, True):
            test = Loopback(0, 0)
            test.observe(False, 0)
            test.observe(False, 50_000_000)
            test.written(51_000_000)
            if cancel:
                test.cancel()
            else:
                test.observe(False, 552_000_000)
            self.assertTrue(test.active)
            self.assertFalse(test.output)
            self.assertTrue(test.pending)
            test.written(553_000_000)
            self.assertFalse(test.active)
            self.assertIsNotNone(test.error)
            self.assertEqual(test.off_ns, [])

    def test_unstable_return_and_stuck_high_baseline_do_not_report_success(self):
        test = Loopback(0, 0)
        test.observe(True, 1_001_000_000)
        self.assertEqual(test.phase, 'cleanup')
        self.assertFalse(test.output)
        test = Loopback(0, 0)
        test.observe(False, 0)
        test.observe(False, 50_000_000)
        test.written(51_000_000)
        test.observe(True, 53_000_000)
        test.observe(False, 54_000_000)
        self.assertEqual(test.phase, 'cleanup')
        self.assertTrue(test.error)


class LoopbackSimulator(ServoSimulator):
    def __init__(self):
        self.wired = True
        self.analog_mode = False
        self.observed_words = set()
        self.observed_masks = set()
        self.analog_was_nonzero = False
        super().__init__(connector=2, first_encoder=8)
        for axis, pins in enumerate(((15, 19, 23), (13, 17, 21), (39, 43, 47), (37, 41, 45))):
            for role, physical in enumerate(pins, 0x81):
                index = 48 + (physical - 1) // 2
                self.memory[0x980 + index * 4] = 3 << 24 | (8 + axis) << 16 | 6 << 8 | role

    def process(self, packet):
        mask = self.memory.get(self.PWM + 4 * self.STRIDE, 0)
        levels = 0
        for axis, bit in enumerate((3, 1, 15, 13)):
            word = self.memory.get(self.PWM + (8 + axis) * 4, 0)
            high = bool(mask & (1 << (8 + axis)))
            if self.analog_mode:
                high = high and word == 0x86660000
            if not (self.wired and high):
                levels |= 1 << bit
        self.memory[self.GPIO + 8] = levels
        reply = super().process(packet)
        self.observed_masks.add(self.memory.get(self.PWM + 4 * self.STRIDE, 0))
        self.observed_words.add(tuple(self.memory.get(self.PWM + axis * 4, 0) for axis in range(8, 12)))
        self.analog_was_nonzero |= any(self.memory.get(self.PWM + axis * 4, 0) >> 16 & 4095
                                      for axis in range(8, 12))
        return reply


class LoopbackBackendTests(unittest.TestCase):
    def setUp(self):
        self.sim = LoopbackSimulator()
        self.addCleanup(self.sim.stop)
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        path = Path(temporary.name) / 'config.json'
        path.write_text(json.dumps(dict(schema=1, connector='P3', ip='127.0.0.1',
                                        axes=[asdict(AxisConfig()) for _ in range(4)])))
        backend = Path(__file__).resolve().parents[1] / 'driver/backend.py'
        self.process = subprocess.Popen([sys.executable, '-u', str(backend), '--config', str(path),
                                         '--port', str(self.sim.port)], stdin=subprocess.PIPE,
                                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.addCleanup(self.cleanup)
        self.messages = queue.Queue()
        def receive():
            for line in self.process.stdout:
                self.messages.put(json.loads(line))
        threading.Thread(target=receive, daemon=True).start()
        self.wait_for(lambda m: m['type'] == 'ready')

    def cleanup(self):
        if self.process.poll() is None:
            self.process.kill()
        self.process.wait(timeout=2)
        for stream in (self.process.stdin, self.process.stdout, self.process.stderr):
            stream.close()

    def send(self, op, **data):
        self.process.stdin.write(json.dumps(dict(op=op, **data)) + '\n')
        self.process.stdin.flush()

    def wait_for(self, predicate, timeout=3):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            self.send('heartbeat')
            try:
                message = self.messages.get(timeout=.05)
            except queue.Empty:
                continue
            if message['type'] == 'fault':
                self.fail(str(message))
            if predicate(message):
                return message
        self.fail('Backend did not return expected loopback result')

    def test_100_cycles_via_real_udp_packets_and_only_selected_enable(self):
        self.send('loopback_start', axis=3)
        result = self.wait_for(lambda m: m['type'] == 'loopback' and not m['active'], timeout=17)
        self.assertIsNone(result['error'])
        self.assertEqual(result['completed'], 100)
        for edge in ('on', 'off'):
            self.assertGreater(result[edge]['mean_ms'], 0)
            self.assertEqual(len(result[edge + '_samples_ms']), 100)
        self.assertEqual(self.sim.observed_masks, {0, 1 << 11})
        self.assertFalse(self.sim.analog_was_nonzero)
        self.assertEqual(self.sim.memory[self.sim.PWM + 4 * self.sim.STRIDE], 0)
        self.assertIsNone(self.process.poll())

    def test_missing_wire_times_out_and_cancel_clears_enable(self):
        self.sim.wired = False
        self.send('loopback_start', axis=0)
        result = self.wait_for(lambda m: m['type'] == 'loopback' and not m['active'])
        self.assertIn('Timeout', result['error'])
        self.assertEqual(result['completed'], 0)
        self.assertEqual(self.sim.memory[self.sim.PWM + 4 * self.sim.STRIDE], 0)
        self.sim.wired = True
        self.send('loopback_start', axis=1)
        self.wait_for(lambda m: m['type'] == 'loopback' and m['active'])
        self.send('enable', axis=2)
        self.wait_for(lambda m: m['type'] == 'rejected')
        self.send('loopback_stop')
        result = self.wait_for(lambda m: m['type'] == 'loopback' and not m['active'])
        self.assertIn('Cancelado', result['error'])
        self.assertEqual(self.sim.memory[self.sim.PWM + 4 * self.sim.STRIDE], 0)

    def test_analog_100_cycles_only_positive_4v_and_cancel_returns_zero(self):
        self.sim.analog_mode = True
        # A zero-valued manual field does not supply the automatic amplitude.
        self.send('pwm_test_set', axis=0, percent=0)
        self.wait_for(lambda m: m['type'] == 'pwm_test' and m['active'])
        self.send('pwm_test_stop')
        self.wait_for(lambda m: m['type'] == 'pwm_test' and not m['active'])
        self.send('loopback_start', axis=0, mode='analog')
        result = self.wait_for(lambda m: m['type'] == 'loopback' and not m['active'], timeout=17)
        self.assertIsNone(result['error'])
        self.assertEqual(result['mode'], 'analog')
        self.assertEqual(result['high_volts'], 4.0)
        self.assertEqual(result['completed'], 100)
        self.assertEqual(self.sim.observed_words, {(0, 0, 0, 0), (0x86660000, 0, 0, 0)})
        self.assertEqual(self.sim.observed_masks, {0, 1 << 8})
        self.assertEqual(self.sim.memory[self.sim.PWM + 8 * 4], 0)
        self.assertEqual(self.sim.memory[self.sim.PWM + 4 * self.sim.STRIDE], 0)
        self.send('loopback_start', axis=0, mode='analog')
        self.wait_for(lambda m: m['type'] == 'loopback' and m['active'] and m['completed'] >= 1)
        self.send('loopback_stop')
        result = self.wait_for(lambda m: m['type'] == 'loopback' and not m['active'])
        self.assertIn('Cancelado', result['error'])
        self.assertEqual(self.sim.memory[self.sim.PWM + 8 * 4], 0)
        self.assertEqual(self.sim.memory[self.sim.PWM + 4 * self.sim.STRIDE], 0)

    def test_manual_pwm_magnitude_bounds_exclusivity_and_stop(self):
        for percent, word in ((0, 0), (50, 0x88000000), (100, 0x8FFF0000)):
            self.send('pwm_test_set', axis=2, percent=percent)
            result = self.wait_for(lambda m: m['type'] == 'pwm_test' and m['active'] and m['percent'] == percent)
            self.assertEqual(result['nominal_volts'], percent / 10)
            self.assertEqual(self.sim.memory[self.sim.PWM + 10 * 4], word)
            self.assertEqual(self.sim.memory[self.sim.PWM + 4 * self.sim.STRIDE], 1 << 10)
        for value in (-1, 101, float('nan')):
            self.send('pwm_test_set', axis=2, percent=value)
            self.wait_for(lambda m: m['type'] == 'rejected')
            self.assertEqual(self.sim.memory[self.sim.PWM + 10 * 4], 0x8FFF0000)
        self.send('loopback_start', axis=0)
        self.wait_for(lambda m: m['type'] == 'rejected')
        self.send('enable', axis=0)
        self.wait_for(lambda m: m['type'] == 'rejected')
        self.send('pwm_test_stop')
        self.wait_for(lambda m: m['type'] == 'pwm_test' and not m['active'])
        self.assertEqual(self.sim.memory[self.sim.PWM + 10 * 4], 0)
        self.assertEqual(self.sim.memory[self.sim.PWM + 4 * self.sim.STRIDE], 0)

    def test_scope_pulse_automatically_applies_40_percent_without_encoder_return(self):
        self.sim.wired = False
        self.send('pwm_test_pulse', axis=1)
        active = self.wait_for(lambda m: m['type'] == 'pwm_test' and m['active'])
        self.assertEqual(active['percent'], 40.0)
        self.assertEqual(active['nominal_volts'], 4.0)
        self.assertEqual(self.sim.memory[self.sim.PWM + 9 * 4], 0x86660000)
        self.wait_for(lambda m: m['type'] == 'pwm_test' and not m['active'])
        self.assertEqual(self.sim.memory[self.sim.PWM + 9 * 4], 0)
        self.assertEqual(self.sim.memory[self.sim.PWM + 4 * self.sim.STRIDE], 0)
        self.assertEqual(self.sim.observed_words, {(0, 0, 0, 0), (0, 0x86660000, 0, 0)})
