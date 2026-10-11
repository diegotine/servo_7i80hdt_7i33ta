"""Native/source arithmetic equivalence; no board, UDP or plant simulation."""
import importlib.util
from importlib.machinery import EXTENSION_SUFFIXES
from pathlib import Path
import math
import sys
import unittest

import servo
from run_backend import native_modules

source = Path(__file__).resolve().parents[1] / 'driver' / 'servo.py'
spec = importlib.util.spec_from_file_location('servo_reference', source)
reference = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = reference
spec.loader.exec_module(reference)


@unittest.skipUnless(servo.__file__.endswith(tuple(EXTENSION_SUFFIXES)), "requires native build")
class NativeCompatibilityTests(unittest.TestCase):
    def assert_values(self, left, right):
        self.assertEqual(left.keys(), right.keys())
        for key in left:
            if isinstance(left[key], float):
                self.assertTrue(math.isclose(left[key], right[key], rel_tol=1e-12, abs_tol=1e-12),
                                (key, left[key], right[key]))
            else:
                self.assertEqual(left[key], right[key], key)

    def test_all_runtime_modules_are_extensions(self):
        paths = native_modules()
        self.assertEqual(len(paths), 6)
        import _rtcore
        self.assertEqual(_rtcore.__version__, "0.2.5")
        self.assertTrue(all(path.endswith(tuple(EXTENSION_SUFFIXES)) for path in paths.values()))

    def test_lbp16_packet_bytes_and_validation_match(self):
        import mesa7i80hdt
        path = source.with_name('mesa7i80hdt.py')
        spec = importlib.util.spec_from_file_location('mesa_reference', path)
        python = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = python
        spec.loader.exec_module(python)
        for address, count in ((0, 1), (0x100, 127), (0xFFFC, 1)):
            for write in (False, True):
                for increment in (False, True):
                    self.assertEqual(mesa7i80hdt.command(address, count, write=write, increment=increment),
                                     python.command(address, count, write=write, increment=increment))
        values = (0, 0xFFFFFFFF, 123)
        self.assertEqual(mesa7i80hdt.write_command(0x100, values), python.write_command(0x100, values))
        for address, count in ((1, 1), (0, 0), (0, 128), (0xFFFC, 2)):
            for module in (mesa7i80hdt, python):
                with self.assertRaises(ValueError):
                    module.command(address, count)

    def test_encoder_wrap_and_unbounded_count(self):
        for previous, raw in ((65535, 2), (1, 65534), (200, 200)):
            results = []
            for module in (servo, reference):
                encoder = module.Encoder(module.AxisConfig())
                encoder.previous = previous
                encoder.count = 2**80
                results.append((encoder.update(raw, .002), encoder.count))
            self.assertEqual(results[0], results[1])

    def test_trajectory_samples_match(self):
        for target, velocity in ((1., 0.), (-1., 0.), (.01, 2.), (1., -2.)):
            native = servo.Trajectory(0., target, 5., 2., velocity)
            python = reference.Trajectory(0., target, 5., 2., velocity)
            self.assertAlmostEqual(native.duration, python.duration, places=12)
            for t in (0., .002, .125, native.duration / 2, native.duration, native.duration + 1):
                for actual, expected in zip(native.sample(t), python.sample(t)):
                    self.assertAlmostEqual(actual, expected, places=12)

    def test_control_outputs_match_for_each_mode(self):
        for mode in ('disabled', 'enabling', 'hold', 'jog', 'stopping', 'move'):
            for output_test in (False, True):
                for dt in (.0019, .002, .0021):
                    axes = []
                    for module in (servo, reference):
                        axis = module.Axis(module.AxisConfig(ki=2., kd=.2))
                        axis.encoder.update(0, dt)
                        axis.enabled = mode != 'disabled'
                        axis.mode = mode
                        axis.output_test = output_test
                        axis.reference = .001
                        axis.virtual_position = .001
                        axis.jog_velocity = .25 if mode == 'jog' else 0.
                        axis.reference_velocity = .1
                        axis.output_velocity = .1
                        if mode == 'move':
                            axis.trajectory = module.Trajectory(.001, .01, 5., 2.)
                        axis.calculate(dt)
                        axes.append(axis)
                    self.assert_values(axes[0].telemetry(), axes[1].telemetry())

    def test_deadline_faults_preserved(self):
        for dt in (0., -.001, .020001, float('nan')):
            for module in (servo, reference):
                with self.assertRaises(module.ServoFault):
                    module.Axis(module.AxisConfig()).calculate(dt)


if __name__ == '__main__':
    unittest.main()
