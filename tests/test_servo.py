import json
import math
from pathlib import Path
import queue
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from dataclasses import asdict

from backend import Session
from mesa7i80hdt import Mesa7i80hdt, FirmwareError, CommunicationError
from servo import Axis, AxisConfig, Encoder, ServoFault, Trajectory
from test_driver import Simulator


class ServoSimulator(Simulator):
    ENC = 0x3000

    def __init__(self, connector=0, first_encoder=0, plant=False):
        super().__init__(connector=connector)
        self.memory[0x864] = 4 | 3 << 8 | 1 << 16 | 12 << 24
        self.memory[0x868] = self.ENC | 5 << 16
        self.memory[0x86C] = 3
        for axis, pins in enumerate(((7, 5, 11), (3, 1, 9), (31, 29, 35), (27, 25, 33))):
            for role, physical in enumerate(pins, 1):
                index = connector * 24 + (physical - 1) // 2
                self.memory[0x980 + index * 4] = 3 << 24 | (first_encoder + axis) << 16 | 4 << 8 | role
        self.first_encoder = first_encoder
        self.plant = plant
        self.positions = [0.0] * 4
        self.last_plant = time.monotonic()

    def process(self, packet):
        if getattr(self, 'plant', False):
            now = time.monotonic()
            dt, self.last_plant = now - self.last_plant, now
            enabled = self.memory.get(self.PWM + 4 * self.STRIDE, 0)
            for axis in range(4):
                word = self.memory.get(self.PWM + axis * 4, 0)
                voltage = (word >> 16 & 4095) * 10 / 4095 * (1 if word & 0x80000000 else -1)
                if not enabled & (1 << axis) or self.memory.get(self.WD + self.STRIDE, 0) & 1:
                    voltage = 0
                self.positions[axis] += voltage * 5 * dt
                self.memory[self.ENC + (self.first_encoder + axis) * 4] = round(self.positions[axis] * 10000) & 65535
        reply, wrote = super().process(packet)
        # Bit15 is write-one-to-clear, unlike a plain memory register.
        for channel in range(12):
            address = self.ENC + self.STRIDE + channel * 4
            if any(a == address for a, _ in self.writes[-12:]):
                self.memory[address] = self.memory.get(address, 0) & ~0x8000
        return reply, wrote


class EncoderDriverTests(unittest.TestCase):
    def setUp(self):
        self.sim = ServoSimulator(first_encoder=4)
        self.addCleanup(self.sim.stop)
        self.board = Mesa7i80hdt('127.0.0.1', port=self.sim.port, timeout=0.03)

    def test_feedback_module_and_mapping_before_writes(self):
        module, channels = self.board.encoder_mapping('P1')
        self.assertEqual(channels, [4, 5, 6, 7])
        self.assertEqual(module.tag, 4)
        self.assertEqual(self.sim.writes, [])
        self.board.pins[3] ^= 1
        with self.assertRaises(FirmwareError):
            self.board.configure_servo('P1')
        self.assertEqual(self.sim.writes, [])

    def test_position_low16_only_and_no_counter_reset(self):
        self.board.configure_servo('P1')
        for axis, count in enumerate((65535, 2, 32768, 0)):
            self.sim.memory[self.sim.ENC + (axis + 4) * 4] = 0x12340000 | count
        self.assertEqual(self.board.read_encoders(), [65535, 2, 32768, 0])
        self.assertFalse(any(self.sim.ENC <= a < self.sim.ENC + 48 for a, _ in self.sim.writes))
        self.assertEqual(self.sim.memory[self.sim.ENC + 4 * self.sim.STRIDE], 0xFFF)
        self.board.close()

    def test_quadrature_error_latches_driver(self):
        self.board.configure_servo('P1')
        self.sim.memory[self.sim.ENC + self.sim.STRIDE + 16] = 0x8800
        with self.assertRaises(CommunicationError):
            self.board.read_encoders()
        self.assertTrue(self.board.faulted)
        self.board.close()

    def test_cyclic_writes_zero_disabled_axes(self):
        self.board.configure_servo('P1')
        self.board.write_servo([1, -1, 2, -2], [True, True, False, False])
        self.assertEqual(self.sim.memory[self.sim.PWM + 4 * self.sim.STRIDE], 3)
        self.assertEqual(self.sim.memory[self.sim.PWM], self.board.voltage_word(1))
        self.assertEqual(self.sim.memory[self.sim.PWM + 4], self.board.voltage_word(-1))
        self.assertEqual(self.sim.memory[self.sim.PWM + 8], 0)
        self.board.close()

    def test_generic_inputs_and_outputs_share_encoder_and_servo_packets(self):
        self.board.configure_servo('P1')
        self.board.configure_generic_io('P2')
        self.board.configure_generic_io('P3')
        self.sim.memory[self.sim.GPIO + 4] = 0xABC123
        self.sim.memory[self.sim.GPIO + 8] = 0xDEF456
        self.board.read_encoders()
        self.assertEqual(self.board.generic_inputs, {'P2': 0x123, 'P3': 0x456})
        self.board.write_servo([0]*4, [False]*4, generic_outputs={'P2': 0x801, 'P3': 0x402})
        self.assertEqual(self.sim.memory[self.sim.GPIO + 4], 0x801000)
        self.assertEqual(self.sim.memory[self.sim.GPIO + 8], 0x402000)
        before = len(self.sim.writes)
        for invalid in ({'P1': 1}, {'P2': 4096}, {'P2': -1}, {'P2': True}, {'P4': 0}):
            with self.assertRaises(ValueError):
                self.board.write_servo([0]*4, [False]*4, generic_outputs=invalid)
        self.assertEqual(len(self.sim.writes), before)
        self.board.close()
        self.assertEqual(self.sim.memory[self.sim.GPIO + 4], 0)
        self.assertEqual(self.sim.memory[self.sim.GPIO + 8], 0)


class ControlTests(unittest.TestCase):
    def test_encoder_wrap_both_directions_and_sign(self):
        encoder = Encoder(AxisConfig())
        self.assertEqual(encoder.update(65530, 0.005), (0, 0))
        self.assertAlmostEqual(encoder.update(4, 0.005)[0], 0.001)
        self.assertAlmostEqual(encoder.update(65530, 0.005)[0], 0)
        inverse = Encoder(AxisConfig(encoder_sign=-1))
        inverse.update(4, 0.005)
        self.assertAlmostEqual(inverse.update(65530, 0.005)[0], 0.001)

    def test_encoder_rejects_ambiguous_wrap_and_jump(self):
        encoder = Encoder(AxisConfig())
        encoder.update(0, 0.005)
        with self.assertRaises(ServoFault): encoder.update(32000, 0.005)
        with self.assertRaises(ServoFault): encoder.update(0, 0.1)

    def test_trajectory_bounds_and_exact_endpoints(self):
        for target in (0, 0.01, -0.01, 3, -3):
            trajectory = Trajectory(0, target, 1, 2)
            previous_velocity = 0
            previous_position = 0
            for n in range(math.ceil(trajectory.duration / 0.001) + 2):
                position, velocity, _ = trajectory.sample(n * 0.001)
                self.assertLessEqual(abs(velocity), 1 + 1e-10)
                self.assertLessEqual(abs(velocity - previous_velocity), 0.002 + 1e-10)
                self.assertGreaterEqual(position * (1 if target >= 0 else -1), -1e-10)
                self.assertLessEqual(abs(position), abs(target) + 1e-10)
                self.assertLessEqual(abs(position - previous_position), 0.001 + 1e-10)
                previous_velocity, previous_position = velocity, position
            self.assertEqual(trajectory.sample(trajectory.duration + 1), (target, 0, True))

    def test_no_implicit_enable_and_optional_calibration_record(self):
        axis = Axis(AxisConfig())
        axis.feedback(0, 0.005)
        self.assertEqual(axis.calculate(0.005), 0)
        with self.assertRaises(ValueError): axis.move(0.1)
        axis.enable()
        self.assertTrue(axis.enabled)
        self.assertFalse(axis.c.verified)

    def exercise_move(self, target):
        axis = Axis(AxisConfig(verified=True))
        position = velocity = 0.0
        axis.feedback(0, 0.005)
        axis.enable()
        # Initial enable delay and position coincidence dwell.
        for _ in range(60):
            axis.feedback(0, 0.005)
            axis.calculate(0.005)
        self.assertTrue(axis.in_position)
        axis.move(target)
        for _ in range(1600):
            axis.feedback(round(position * 10000) & 65535, 0.005)
            volts = axis.calculate(0.005)
            self.assertLessEqual(abs(volts), 0.2 + 1e-10)  # maxRPM=60 at 300RPM/V
            # Independent first order velocity amplifier, tau=20ms.
            velocity += (volts * 5 - velocity) * 0.005 / 0.02
            position += velocity * 0.005
        self.assertAlmostEqual(position, target, delta=0.0002)
        self.assertTrue(axis.in_position)
        axis.disable()
        self.assertEqual(axis.calculate(0.005), 0)
        self.assertEqual(axis.integral, 0)

    def test_replanned_trajectory_continuity_and_acceleration(self):
        for target, velocity, accel in ((1, 0.4, 0.2), (-1, -0.4, 0.2),
                                        (0.01, 0.4, 0.1), (-0.01, -0.4, 0.1),
                                        (1, -0.4, 0.3)):
            with self.subTest(target=target, velocity=velocity):
                trajectory = Trajectory(0, target, 1, accel, velocity)
                self.assertEqual(trajectory.sample(0), (0, velocity, False))
                previous = velocity
                for n in range(1, math.ceil(trajectory.duration / 0.005) + 1):
                    _, current, _ = trajectory.sample(n * 0.005)
                    self.assertLessEqual(abs(current - previous), accel * 0.005 + 1e-10)
                    self.assertLessEqual(abs(current), 1 + 1e-10)
                    previous = current
                self.assertEqual(trajectory.sample(trajectory.duration + 1), (target, 0, True))

    def test_stop_move_and_jog_preserve_enable_and_brake_reference(self):
        for operation, value in (('move', 1), ('jog', 30), ('jog', -30)):
            with self.subTest(operation=operation, value=value):
                axis = self.ready_axis()
                getattr(axis, operation)(value)
                for _ in range(40):
                    axis.feedback(round(axis.reference * 10000) & 65535, 0.005)
                    axis.calculate(0.005)
                previous = axis.reference_velocity
                self.assertNotEqual(previous, 0)
                axis.stop_motion()
                self.assertTrue(axis.enabled)
                self.assertEqual(axis.mode, 'stopping')
                for _ in range(100):
                    axis.feedback(round(axis.reference * 10000) & 65535, 0.005)
                    axis.calculate(0.005)
                    self.assertLessEqual(abs(axis.reference_velocity - previous), axis.c.accel * 0.005 + 1e-10)
                    previous = axis.reference_velocity
                self.assertEqual(axis.reference_velocity, 0)
                self.assertTrue(axis.enabled)
                self.assertEqual(axis.mode, 'hold')
                axis.disable()
                self.assertFalse(axis.enabled)
                self.assertEqual(axis.calculate(0.005), 0)

    def test_live_acceleration_replans_move_and_updates_jog(self):
        axis = self.ready_axis()
        axis.move(1)
        for _ in range(20):
            axis.feedback(round(axis.reference * 10000) & 65535, 0.005)
            axis.calculate(0.005)
        reference, velocity = axis.reference, axis.reference_velocity
        axis.set_acceleration(60)
        self.assertEqual(axis.trajectory.sample(0), (reference, velocity, False))
        self.assertEqual(axis.c.acceleration_rpm_s, 60)
        axis.feedback(round(reference * 10000) & 65535, 0.005)
        axis.calculate(0.005)
        self.assertLessEqual(abs(axis.reference_velocity - velocity), 0.005 + 1e-10)
        axis.stop_motion()
        axis.set_acceleration(30)
        self.assertEqual(axis.c.acceleration_rpm_s, 30)
        for invalid in (0, -1, float('nan'), float('inf'), True, 100001):
            with self.assertRaises(ValueError): axis.set_acceleration(invalid)
        self.assertEqual(axis.c.acceleration_rpm_s, 30)
        axis = self.ready_axis()
        axis.jog(30)
        axis.calculate(0.005)
        velocity = axis.reference_velocity
        axis.set_acceleration(60)
        axis.calculate(0.005)
        self.assertAlmostEqual(axis.reference_velocity - velocity, 0.005)

    def test_virtual_feedback_keeps_real_encoder_and_manual_error(self):
        axis = Axis(AxisConfig())
        axis.feedback(0, 0.005)
        axis.set_output_test(True)
        axis.enable()
        for _ in range(25): axis.calculate(0.005)
        axis.jog(60)
        for _ in range(100):
            axis.feedback(0, 0.005)
            axis.calculate(0.005)
        telemetry = axis.telemetry()
        self.assertAlmostEqual(telemetry['position'], axis.virtual_position)
        self.assertAlmostEqual(telemetry['error'], telemetry['position'])
        self.assertEqual(telemetry['encoder_position'], 0)
        simulated = axis.virtual_position
        axis.feedback(1000, 0.005)
        self.assertAlmostEqual(axis.telemetry()['error'], simulated - 0.1)
        self.assertAlmostEqual(axis.telemetry()['encoder_position'], 0.1)
        self.assertEqual(axis.virtual_position, simulated)
        axis.feedback(round(simulated * 10000), 0.005)
        self.assertLessEqual(abs(axis.telemetry()['error']), 0.5 / 10000)
        axis.jog(9999.9)
        for _ in range(100):
            axis.feedback(round(axis.virtual_position * 10000) & 65535, 0.005)
            axis.calculate(0.005)
        self.assertLessEqual(abs(axis.volts), 0.2 + 1e-10)
        axis.stop_motion()
        for _ in range(120): axis.calculate(0.005)
        simulated = axis.virtual_position
        for raw in range(axis.encoder.previous, -1, -500):
            axis.feedback(raw, 0.005)
            axis.calculate(0.005)
        axis.feedback(0, 0.005)
        axis.calculate(0.005)
        self.assertEqual(axis.virtual_position, simulated)
        self.assertAlmostEqual(axis.error, simulated)

    def test_output_test_holds_voltage_without_encoder_and_stops_with_enable(self):
        axis = Axis(AxisConfig())
        axis.feedback(0, 0.005)
        axis.set_output_test(True)
        axis.enable()
        for _ in range(25): axis.calculate(0.005)
        axis.jog(60)
        for _ in range(400):
            axis.feedback(0, 0.005)
            axis.calculate(0.005)
        self.assertAlmostEqual(axis.volts, 0.2)
        self.assertTrue(axis.enabled)
        self.assertAlmostEqual(axis.error, axis.virtual_position)
        self.assertGreater(axis.error, 1)
        axis.set_acceleration(60)
        axis.stop_motion()
        previous = axis.volts
        for _ in range(240):
            axis.feedback(0, 0.005)
            axis.calculate(0.005)
            self.assertLessEqual(abs(axis.volts - previous), 0.001 + 1e-10)
            previous = axis.volts
        self.assertEqual(axis.volts, 0)
        self.assertTrue(axis.enabled)
        self.assertEqual(axis.mode, 'hold')
        axis.move(0.1)
        for _ in range(1000): axis.calculate(0.005)
        self.assertAlmostEqual(axis.virtual_position, 0.1)
        self.assertTrue(axis.enabled)
        with self.assertRaises(ValueError): axis.set_output_test(False)
        axis.jog(-60)
        for _ in range(240): axis.calculate(0.005)
        self.assertAlmostEqual(axis.volts, -0.2)
        axis.disable()
        self.assertEqual(axis.calculate(0.005), 0)
        axis.set_output_test(False)
        self.assertFalse(axis.output_test)

    def test_position_converges_clockwise_and_counterclockwise(self):
        self.exercise_move(0.3)
        self.exercise_move(-0.3)

    def test_following_error_stalled_motor_and_travel(self):
        axis = Axis(AxisConfig(verified=True))
        axis.feedback(0, 0.005)
        axis.enable()
        for _ in range(60): axis.calculate(0.005)
        axis.move(1)
        with self.assertRaises(ServoFault):
            for _ in range(400): axis.calculate(0.005)
        axis.disable()
        with self.assertRaises(ValueError): axis.move(11)

    def test_saturation_does_not_integrate_windup(self):
        axis = Axis(AxisConfig(verified=True, ki=20, kp=100, no_response_timeout_s=10))
        axis.feedback(0, 0.005)
        axis.enable()
        for _ in range(60): axis.calculate(0.005)
        axis.reference = 0.05
        for _ in range(100): axis.calculate(0.005)
        self.assertEqual(axis.integral, 0)
        self.assertLessEqual(abs(axis.volts), 0.2)

    def ready_axis(self, **config):
        axis = Axis(AxisConfig(verified=True, **config))
        axis.feedback(0, 0.005)
        axis.enable()
        for _ in range(60):
            axis.feedback(0, 0.005)
            axis.calculate(0.005)
        return axis

    def test_no_encoder_response_small_move_and_jog_both_directions(self):
        for command, value in (('move', 0.005), ('move', -0.005), ('jog', 1), ('jog', -1)):
            with self.subTest(command=command, value=value):
                axis = self.ready_axis()
                getattr(axis, command)(value)
                with self.assertRaisesRegex(ServoFault, 'sem resposta do encoder'):
                    for _ in range(200):
                        axis.feedback(0, 0.005)
                        axis.calculate(0.005)
                self.assertFalse(axis.enabled)
                self.assertEqual(axis.volts, 0)
                self.assertEqual(axis.mode, 'disabled')

    def test_no_response_monitor_ignores_idle_enable_and_subresolution_commands(self):
        axis = self.ready_axis()
        for _ in range(400):
            axis.feedback(0, 0.005)
            self.assertEqual(axis.calculate(0.005), 0)
        axis.jog(0.0001)
        for _ in range(120):
            axis.feedback(0, 0.005)
            axis.calculate(0.005)
        self.assertTrue(axis.enabled)

    def test_response_after_start_delay_and_then_stall(self):
        axis = self.ready_axis()
        axis.jog(1)
        position = 0.0
        for n in range(200):
            axis.feedback(round(position * 10000) & 65535, 0.005)
            volts = axis.calculate(0.005)
            if n >= 40:  # Simulate 200ms mechanical/drive startup delay.
                position += volts * 5 * 0.005
        self.assertTrue(axis.enabled)
        with self.assertRaisesRegex(ServoFault, 'sem resposta do encoder'):
            for _ in range(150):
                axis.feedback(round(position * 10000) & 65535, 0.005)
                axis.calculate(0.005)

    def test_slow_motion_waits_for_resolvable_expected_counts(self):
        axis = self.ready_axis(counts_per_rev=100, kp=0.02, ff1=0,
                               tolerance_counts=0.5, following_error_rev=1)
        axis.reference = 0.5  # About 1 count/s, with voltage above half a PDM step.
        for _ in range(125):
            axis.feedback(0, 0.005)
            axis.calculate(0.005)
        self.assertTrue(axis.enabled)  # Timeout passed but <4 expected counts.
        with self.assertRaisesRegex(ServoFault, 'sem resposta do encoder'):
            for _ in range(1000):
                axis.feedback(0, 0.005)
                axis.calculate(0.005)

    def test_jog_brakes_and_holds_within_soft_limits(self):
        axis = Axis(AxisConfig(verified=True, min_rev=-0.15, max_rev=0.15))
        axis.feedback(0, 0.005)
        axis.enable()
        for _ in range(60): axis.calculate(0.005)
        axis.jog(30)
        position = 0
        for _ in range(700):
            axis.feedback(round(position * 10000) & 65535, 0.005)
            position += axis.calculate(0.005) * 5 * 0.005
        self.assertEqual(axis.mode, 'hold')
        self.assertLessEqual(axis.reference, 0.15)
        self.assertLessEqual(position, 0.15)
        axis.disable()
        axis.zero()
        self.assertEqual(axis.position, 0)

    def test_invalid_config_values(self):
        for changes in (dict(counts_per_rev=0), dict(kp=float('nan')), dict(verified='yes'),
                        dict(max_rpm=4000), dict(voltage_limit=11), dict(min_rev=10, max_rev=0),
                        dict(no_response_timeout_s=0), dict(no_response_timeout_s=11)):
            with self.assertRaises(ValueError): AxisConfig(**changes)

    def test_deadline_and_gui_heartbeat_fail_before_output(self):
        class FakeBoard:
            writes = 0
            def read_encoders(self): return [0] * 4
            def write_servo(self, *_): self.writes += 1
        now = [10.0]
        board = FakeBoard()
        session = Session(board, [Axis(AxisConfig()) for _ in range(4)], queue.Queue(),
                          output=lambda *a, **kw: None, clock=lambda: now[0])
        now[0] += 0.03
        with self.assertRaises(ServoFault): session.step()
        self.assertEqual(board.writes, 0)
        session.previous = now[0]
        now[0] += 0.005
        session.last_client -= 1
        with self.assertRaises(ServoFault): session.step()
        self.assertEqual(board.writes, 0)


class BackendTests(unittest.TestCase):
    def setUp(self):
        self.sim = ServoSimulator(connector=2, first_encoder=8, plant=True)
        self.addCleanup(self.sim.stop)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        config = dict(schema=1, ip='127.0.0.1', connector='P3',
                      axes=[asdict(AxisConfig()) for _ in range(4)])
        path = Path(self.temp.name) / 'config.json'
        path.write_text(json.dumps(config))
        backend = Path(__file__).resolve().parents[1] / 'driver/backend.py'
        self.process = subprocess.Popen([sys.executable, '-u', str(backend), '--config', str(path),
                                         '--port', str(self.sim.port)], stdin=subprocess.PIPE,
                                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.addCleanup(self.cleanup_process)
        self.messages = queue.Queue()
        def receive():
            for line in self.process.stdout:
                self.messages.put(json.loads(line))
        threading.Thread(target=receive, daemon=True).start()
        self.ready = self.wait_for(lambda m: m['type'] == 'ready')
        # P1/P2: lower 12 inputs, upper 12 generic outputs initially low.
        for port in (0, 1):
            self.assertEqual(self.sim.memory[self.sim.GPIO + self.sim.STRIDE + port * 4] & 0xFFFFFF, 0xFFF000)
            self.assertEqual(self.sim.memory[self.sim.GPIO + port * 4], 0)
            for register in (2, 3, 4):
                self.assertEqual(self.sim.memory[self.sim.GPIO + register * self.sim.STRIDE + port * 4] & 0xFFFFFF, 0)

    def cleanup_process(self):
        if self.process.poll() is None:
            self.process.kill()
        self.process.wait(timeout=2)
        for stream in (self.process.stdin, self.process.stdout, self.process.stderr):
            stream.close()

    def send(self, operation, **data):
        self.process.stdin.write(json.dumps(dict(op=operation, **data)) + '\n')
        self.process.stdin.flush()

    def wait_for(self, predicate, timeout=2, heartbeat=False):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            if heartbeat and self.process.poll() is None: self.send('heartbeat')
            try:
                message = self.messages.get(timeout=0.05)
            except queue.Empty:
                continue
            if message['type'] == 'fault' and not predicate(message):
                self.fail(str(message))
            if predicate(message): return message
        self.fail('Backend message timeout')

    def test_diagnostics_identification_and_acknowledged_cycle(self):
        info = self.ready['identification']
        self.assertEqual(info['model'], '7I80HDT')
        self.assertEqual(info['ip'], '127.0.0.1')
        self.assertEqual(info['io_width'], 72)
        self.assertEqual(self.ready['encoder_channels'], [8, 9, 10, 11])
        self.assertEqual(self.ready['watchdog_ms'], 100)
        self.assertGreater(self.ready['pdm_hz'], 0)
        self.assertIn(4, [module['tag'] for module in info['modules']])
        message = self.wait_for(lambda m: m['type'] == 'status', heartbeat=True)
        diagnostic = message['diagnostics']
        self.assertEqual(diagnostic['raw_counts'], [0] * 4)
        self.assertTrue(diagnostic['watchdog_ok'])
        self.assertGreaterEqual(diagnostic['cycles'], 1)
        self.assertGreaterEqual(diagnostic['max_cycle_ms'], message['cycle_ms'])
        self.assertTrue(all(not axis['enabled'] for axis in message['axes']))
        self.send('quit')
        self.assertEqual(self.process.wait(timeout=2), 0)

    def test_pipe_enable_move_stop_and_eof_shutdown(self):
        message = self.wait_for(lambda m: m['type'] == 'status', heartbeat=True)
        self.assertTrue(all(not a['enabled'] and a['volts'] == 0 for a in message['axes']))
        self.send('enable', axis=0)
        self.wait_for(lambda m: m['type'] == 'status' and m['axes'][0]['in_position'], heartbeat=True)
        self.send('move', axis=0, value=0.03)
        message = self.wait_for(lambda m: m['type'] == 'status' and m['axes'][0]['in_position']
                                and abs(m['axes'][0]['position'] - 0.03) < 0.0003, heartbeat=True)
        self.assertTrue(all(not a['enabled'] for a in message['axes'][1:]))
        self.send('stop_all')
        self.wait_for(lambda m: m['type'] == 'status' and not m['axes'][0]['enabled'], heartbeat=True)
        self.process.stdin.close()
        self.assertEqual(self.process.wait(timeout=2), 0)
        self.assertEqual(self.sim.memory[self.sim.PWM + 4 * self.sim.STRIDE], 0)
        self.assertEqual(self.sim.memory[self.sim.GPIO + self.sim.STRIDE] & 0xFFFFFF, 0)

    def test_stop_keeps_hardware_enable_and_live_acceleration_is_acknowledged(self):
        self.send('enable', axis=0)
        self.wait_for(lambda m: m['type'] == 'status' and m['axes'][0]['in_position'], heartbeat=True)
        self.send('move', axis=0, value=1)
        self.wait_for(lambda m: m['type'] == 'status' and m['axes'][0]['mode'] == 'move', heartbeat=True)
        self.send('acceleration', axis=0, value=60)
        message = self.wait_for(lambda m: m['type'] == 'axis_config', heartbeat=True)
        self.assertEqual(message['acceleration_rpm_s'], 60)
        self.send('stop', axis=0)
        message = self.wait_for(lambda m: m['type'] == 'status' and m['axes'][0]['in_position'], heartbeat=True)
        self.assertTrue(message['axes'][0]['enabled'])
        self.assertLess(message['axes'][0]['position'], 0.2)
        self.assertEqual(self.sim.memory[self.sim.PWM + 4 * self.sim.STRIDE], 1)
        self.send('disable', axis=0)
        self.wait_for(lambda m: m['type'] == 'status' and not m['axes'][0]['enabled'], heartbeat=True)
        self.assertEqual(self.sim.memory[self.sim.PWM + 4 * self.sim.STRIDE], 0)
        self.assertEqual(self.sim.memory[self.sim.PWM], 0)

    def test_live_jog_rpm_changes_output_in_both_directions_and_reports_limit(self):
        self.sim.plant = False
        self.send('output_test', axis=0, value=True)
        self.send('enable', axis=0)
        self.wait_for(lambda m: m['type'] == 'status' and m['axes'][0]['in_position'], heartbeat=True)
        for rpm in (10, 30, -20, -50, 9999.9):
            self.send('jog', axis=0, value=rpm)
            command = self.wait_for(lambda m: m['type'] == 'jog_command', heartbeat=True)
            effective = max(-60, min(60, rpm))
            self.assertEqual(command['requested_rpm'], rpm)
            self.assertEqual(command['effective_rpm'], effective)
            self.wait_for(lambda m: m['type'] == 'status' and abs(m['axes'][0]['rpm'] - effective) < 0.01,
                          heartbeat=True)
            word = self.sim.memory[self.sim.PWM]
            volts = (word >> 16 & 4095) * 10 / 4095 * (1 if word & (1 << 31) else -1)
            self.assertAlmostEqual(volts, effective / 300, delta=10 / 4095)
        self.send('quit')
        self.assertEqual(self.process.wait(timeout=2), 0)

    def test_instrument_test_keeps_output_with_frozen_encoder_then_disables(self):
        self.sim.plant = False
        self.send('output_test', axis=0, value=True)
        self.wait_for(lambda m: m['type'] == 'status' and m['axes'][0]['output_test'], heartbeat=True)
        self.send('enable', axis=0)
        self.wait_for(lambda m: m['type'] == 'status' and m['axes'][0]['in_position'], heartbeat=True)
        self.send('jog', axis=0, value=60)
        end = time.monotonic() + 0.9
        while time.monotonic() < end:
            message = self.wait_for(lambda m: m['type'] == 'status', heartbeat=True)
        self.assertTrue(message['axes'][0]['enabled'])
        self.assertAlmostEqual(message['axes'][0]['volts'], 0.2)
        word = self.sim.memory[self.sim.PWM]
        self.assertAlmostEqual((word >> 16 & 4095) * 10 / 4095, 0.2, delta=10 / 4095)
        self.send('stop', axis=0)
        message = self.wait_for(lambda m: m['type'] == 'status' and m['axes'][0]['mode'] == 'hold', heartbeat=True)
        self.assertEqual(message['axes'][0]['volts'], 0)
        self.assertEqual(self.sim.memory[self.sim.PWM + 4 * self.sim.STRIDE], 1)
        self.send('disable', axis=0)
        self.wait_for(lambda m: m['type'] == 'status' and not m['axes'][0]['enabled'], heartbeat=True)
        self.assertEqual(self.sim.memory[self.sim.PWM + 4 * self.sim.STRIDE], 0)

    def test_gui_loss_faults_and_requires_new_session(self):
        self.send('io_output', connector='P1', channel=0, value=True)
        self.wait_for(lambda m: m['type'] == 'status' and m['io']['P1']['outputs'] == 1, heartbeat=True)
        message = self.wait_for(lambda m: m['type'] == 'fault', timeout=2)
        self.assertIn('heartbeat', message['message'])
        self.assertEqual(self.process.wait(timeout=2), 1)
        self.assertEqual(self.sim.memory[self.sim.PWM + 4 * self.sim.STRIDE], 0)
        self.assertEqual(self.sim.memory[self.sim.GPIO], 0)
        self.assertEqual(self.sim.memory[self.sim.GPIO + self.sim.STRIDE] & 0xFFFFFF, 0)

    def test_frozen_encoder_fault_preserves_read_only_diagnostics(self):
        self.sim.plant = False
        self.send('enable', axis=0)
        self.wait_for(lambda m: m['type'] == 'status' and m['axes'][0]['in_position'], heartbeat=True)
        self.send('move', axis=0, value=0.005)
        message = self.wait_for(lambda m: m['type'] == 'fault', heartbeat=True)
        self.assertIn('Motor 1', message['message'])
        self.assertIn('sem resposta do encoder', message['message'])
        self.assertTrue(message['diagnostic_mode'])
        self.assertIsNone(self.process.poll())
        diagnostic = self.wait_for(lambda m: m['type'] == 'diagnostic_status', heartbeat=True)
        self.assertEqual(diagnostic['enable_mask'], 0)
        self.assertEqual(self.sim.memory[self.sim.PWM + 4 * self.sim.STRIDE], 0)
        self.assertTrue(all(self.sim.memory.get(self.sim.PWM + axis * 4, 0) == 0 for axis in range(4)))
        writes = len(self.sim.writes)
        self.send('jog', axis=0, value=10)
        self.wait_for(lambda m: m['type'] == 'rejected', heartbeat=True)
        self.sim.memory[self.sim.ENC + 8 * 4] = 123
        self.sim.memory[self.sim.ENC + self.sim.STRIDE + 8 * 4] = 0x8000
        diagnostic = self.wait_for(lambda m: m['type'] == 'diagnostic_status'
                                   and m['raw_counts'][0] == 123, heartbeat=True)
        self.assertTrue(diagnostic['quadrature_errors'][0])
        self.wait_for(lambda m: m['type'] == 'diagnostic_status' and m['watchdog_expired'], heartbeat=True)
        self.assertEqual(len(self.sim.writes), writes)
        self.send('quit')
        self.assertEqual(self.process.wait(timeout=2), 0)

    def test_enable_rearms_after_encoder_fault_without_disconnect(self):
        self.sim.plant = False
        self.send('enable', axis=0)
        self.wait_for(lambda m: m['type'] == 'status' and m['axes'][0]['in_position'], heartbeat=True)
        self.send('jog', axis=0, value=10)
        self.wait_for(lambda m: m['type'] == 'fault', heartbeat=True)
        self.wait_for(lambda m: m['type'] == 'diagnostic_status' and m['watchdog_expired'], heartbeat=True)
        self.send('output_test', axis=0, value=True)
        self.send('enable', axis=0)
        self.wait_for(lambda m: m['type'] == 'rearmed', heartbeat=True)
        message = self.wait_for(lambda m: m['type'] == 'status' and m['axes'][0]['in_position'], heartbeat=True)
        self.assertTrue(message['axes'][0]['output_test'])
        self.assertTrue(message['axes'][0]['enabled'])
        self.assertEqual(message['axes'][0]['volts'], 0)
        self.assertTrue(all(not axis['enabled'] for axis in message['axes'][1:]))
        self.assertTrue(all(port['outputs'] == 0 for port in message['io'].values()))
        self.send('jog', axis=0, value=60)
        self.wait_for(lambda m: m['type'] == 'status' and m['axes'][0]['volts'] >= 0.199, heartbeat=True)
        self.send('quit')
        self.assertEqual(self.process.wait(timeout=2), 0)
        self.assertEqual(self.sim.memory[self.sim.PWM + 4 * self.sim.STRIDE], 0)
        self.assertEqual(self.sim.memory[self.sim.PWM], 0)

    def test_network_failure_retains_diagnosis_and_readings_recover_without_writes(self):
        self.sim.truncate = True
        message = self.wait_for(lambda m: m['type'] == 'fault', heartbeat=True)
        self.assertTrue(message['diagnostic_mode'])
        self.wait_for(lambda m: m['type'] == 'diagnostic_error', heartbeat=True)
        self.assertIsNone(self.process.poll())
        writes = len(self.sim.writes)
        self.sim.truncate = False
        self.wait_for(lambda m: m['type'] == 'diagnostic_status', heartbeat=True)
        self.assertEqual(len(self.sim.writes), writes)
        self.send('quit')
        self.assertEqual(self.process.wait(timeout=2), 0)

    def test_generic_outputs_acknowledged_stop_all_and_reject_invalid_commands(self):
        for connector in ('P1', 'P2'):
            self.send('io_output', connector=connector, channel=11, value=True)
        self.wait_for(lambda m: m['type'] == 'status'
                      and all(m['io'][p]['outputs'] == 0x800 for p in ('P1', 'P2')), heartbeat=True)
        self.assertEqual(self.sim.memory[self.sim.GPIO], 0x800000)
        self.assertEqual(self.sim.memory[self.sim.GPIO + 4], 0x800000)
        for changes in (dict(connector='P3', channel=0, value=True),
                        dict(connector='P1', channel=12, value=True),
                        dict(connector='P1', channel=0, value=1)):
            self.send('io_output', **changes)
            self.wait_for(lambda m: m['type'] == 'rejected', heartbeat=True)
        self.send('stop_all')
        self.wait_for(lambda m: m['type'] == 'status'
                      and all(m['io'][p]['outputs'] == 0 for p in ('P1', 'P2')), heartbeat=True)
        self.assertEqual(self.sim.memory[self.sim.GPIO], 0)
        self.assertEqual(self.sim.memory[self.sim.GPIO + 4], 0)
        self.send('io_output', connector='P1', channel=0, value=True)
        self.wait_for(lambda m: m['type'] == 'status' and m['io']['P1']['outputs'] == 1, heartbeat=True)
        self.send('quit')
        self.assertEqual(self.process.wait(timeout=2), 0)
        for port in (0, 1):
            self.assertEqual(self.sim.memory[self.sim.GPIO + port * 4], 0)
            self.assertEqual(self.sim.memory[self.sim.GPIO + self.sim.STRIDE + port * 4] & 0xFFFFFF, 0)

    def test_process_kill_expires_hardware_watchdog(self):
        self.send('io_output', connector='P2', channel=11, value=True)
        self.send('enable', axis=0)
        self.wait_for(lambda m: m['type'] == 'status' and m['axes'][0]['enabled'], heartbeat=True)
        self.process.kill()
        self.process.wait(timeout=2)
        time.sleep(0.16)
        self.assertEqual(self.sim.memory[self.sim.WD + self.sim.STRIDE] & 1, 1)
        self.assertEqual(self.sim.memory[self.sim.GPIO + self.sim.STRIDE], 0)
        self.assertEqual(self.sim.memory[self.sim.GPIO + self.sim.STRIDE + 4], 0)


if __name__ == '__main__':
    unittest.main()
