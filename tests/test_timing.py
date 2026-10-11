"""Deterministic scheduling regressions, without a board or realtime privileges."""
import errno
import os
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from timing import AbsoluteSleeper, CycleTimer, Samples, configure_runtime


class TimingTests(unittest.TestCase):
    def test_wakeup_delay_does_not_accumulate_into_the_schedule(self):
        now, targets = [0], []

        def sleep(target):
            targets.append(target)
            now[0] = target + 100_000

        timer = CycleTimer(clock=lambda: now[0], sleeper=sleep)
        for _ in range(10):
            self.assertEqual(timer.wait(), 100_000)
            now[0] += 500_000  # Work performed after each wakeup.
        self.assertEqual(targets, list(range(5_000_000, 50_000_001, 5_000_000)))
        self.assertEqual(timer.skipped, 0)

    def test_expired_slots_are_skipped_without_a_catchup_burst(self):
        now, targets = [0], []

        def sleep(target):
            targets.append(target)
            now[0] = target

        timer = CycleTimer(clock=lambda: now[0], sleeper=sleep)
        timer.wait()
        now[0] = 18_000_000  # Work overran two scheduled starts.
        timer.wait()
        self.assertEqual(targets, [5_000_000, 20_000_000])
        self.assertEqual(timer.skipped, 2)

    def test_interrupted_absolute_sleep_reuses_the_same_deadline(self):
        sleeper = object.__new__(AbsoluteSleeper)
        sleeper.sleep = Mock(side_effect=[errno.EINTR, 0])
        sleeper(123_456_789)
        self.assertEqual(sleeper.sleep.call_count, 2)
        first, second = sleeper.sleep.call_args_list
        self.assertIs(first.args[2]._obj, second.args[2]._obj)
        sleeper.sleep = Mock(return_value=errno.EINVAL)
        with self.assertRaises(OSError):
            sleeper(123_456_789)

    def test_statistics_keep_lifetime_extrema_and_bounded_recent_percentile(self):
        samples = Samples()
        self.assertIsNone(samples.report())
        for value in range(1, 301):
            samples.add(value * 1_000_000)
        result = samples.report()
        self.assertEqual(len(samples.window), 256)
        self.assertEqual(result['count'], 300)
        self.assertEqual(result['mean_ms'], 150.5)
        self.assertEqual(result['min_ms'], 1)
        self.assertEqual(result['max_ms'], 300)
        self.assertEqual(result['p95_recent_ms'], 288)

    def test_denied_privileges_report_actual_normal_scheduler(self):
        libc = SimpleNamespace(mlockall=Mock(return_value=-1))
        with patch('timing.os.sched_getaffinity', return_value={0, 1}), \
                patch('timing.os.sched_setaffinity') as affinity, \
                patch('timing.os.sched_setscheduler', side_effect=PermissionError('denied')), \
                patch('timing.os.sched_getscheduler', return_value=os.SCHED_OTHER), \
                patch('timing.os.sched_getparam', return_value=os.sched_param(0)), \
                patch('timing.ctypes.CDLL', return_value=libc), \
                patch('timing.ctypes.get_errno', return_value=errno.ENOMEM):
            report = configure_runtime({})
        affinity.assert_called_once_with(0, {1})
        self.assertEqual(report['scheduler'], 'SCHED_OTHER')
        self.assertEqual(report['priority'], 0)
        self.assertFalse(report['memory_current_locked'])
        self.assertEqual(len(report['warnings']), 2)

    def test_runtime_options_reject_invalid_cpu_or_priority(self):
        with self.assertRaises(ValueError):
            configure_runtime({'T3D_RT_PRIORITY': '99'})
        with patch('timing.os.sched_getaffinity', return_value={0}):
            with self.assertRaises(ValueError):
                configure_runtime({'T3D_CPU': '4'})
