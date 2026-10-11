"""Software position loop; board driver only transfers encoder counts and volts.

Units: motor revolutions, rev/s, rev/s²; positive means clockwise as configured.
PID + FF1 structure follows LinuxCNC pid(9). This is not a hard realtime runtime.
"""
from dataclasses import dataclass, fields, replace
import math
from _rtcore import plan_trajectory, ramp_velocity


class ServoFault(Exception):
    pass


def clamp(value, limit):
    return max(-limit, min(limit, value))


@dataclass(frozen=True)
class AxisConfig:
    counts_per_rev: float = 10000
    rpm_at_10v: float = 3000
    encoder_sign: int = 1
    output_sign: int = 1
    max_rpm: float = 1000
    acceleration_rpm_s: float = 350
    deceleration_rpm_s: float = 600
    kp: float = 50
    ki: float = 0
    kd: float = 0
    ff1: float = 1
    following_error_rev: float = 0.1
    tolerance_counts: float = 2
    no_response_timeout_s: float = 0.5
    min_rev: float = -10
    max_rev: float = 10
    verified: bool = False

    def __post_init__(self):
        if type(self.verified) is not bool:
            raise ValueError('verified must be boolean')
        for field in fields(self):
            if field.name != 'verified':
                value = getattr(self, field.name)
                if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                    raise ValueError(f'Invalid {field.name}')
        if self.encoder_sign not in (-1, 1) or self.output_sign not in (-1, 1):
            raise ValueError('Directions must be -1 or +1')
        if not 1 <= self.counts_per_rev <= 10_000_000 or not 1 <= self.rpm_at_10v <= 30000:
            raise ValueError('Invalid encoder/analog scale')
        if not 0 < self.max_rpm <= self.rpm_at_10v or self.acceleration_rpm_s <= 0 or self.deceleration_rpm_s <= 0:
            raise ValueError('Invalid velocity/acceleration')
        if self.kp <= 0 or min(self.ki, self.kd, self.ff1) < 0:
            raise ValueError('Invalid PID limits')
        if self.following_error_rev <= 0 or self.tolerance_counts < 0.5 or self.min_rev >= self.max_rev:
            raise ValueError('Invalid following error/tolerance/travel')
        if not 0.05 <= self.no_response_timeout_s <= 10:
            raise ValueError('Encoder response timeout must be between 0.05 and 10 seconds')

    @property
    def vmax(self):
        return self.max_rpm / 60

    @property
    def accel(self):
        return self.acceleration_rpm_s / 60

    @property
    def decel(self):
        return self.deceleration_rpm_s / 60


class Encoder:
    """Extend 16-bit hardware count; never infer motion from timestamp bits."""
    def __init__(self, config):
        self.config = config
        self.previous = None
        self.count = 0

    def update(self, raw, dt):
        if type(raw) is not int or not 0 <= raw <= 65535 or dt <= 0:
            raise ServoFault('Invalid encoder sample')
        if self.previous is None:
            self.previous = raw
            return 0.0, 0.0
        # Sampling must resolve half a count-register wrap at full drive speed,
        # including a 25% overspeed margin. Otherwise no delta is trustworthy.
        bound = self.config.counts_per_rev * self.config.rpm_at_10v / 60 * 1.25 * dt
        if bound + 4 >= 32768:
            raise ServoFault('Sampling interval cannot resolve encoder wrap')
        delta = (raw - self.previous + 32768) % 65536 - 32768
        if abs(delta) > bound + 4:
            raise ServoFault('Encoder count jump exceeds physical speed bound')
        self.previous = raw
        self.count += delta * self.config.encoder_sign
        return self.count / self.config.counts_per_rev, delta * self.config.encoder_sign / self.config.counts_per_rev / dt


class Trajectory:
    """Constant-acceleration segments with continuous position and velocity."""
    def __init__(self, start, target, vmax, accel, initial_velocity=0.0, decel=None):
        self.start, self.target = start, target
        self.segments, self.duration, self.minimum, self.maximum = plan_trajectory(
            start, target, vmax, accel, initial_velocity, accel if decel is None else decel)

    def sample(self, t):
        t = max(0, t)
        if t >= self.duration:
            return self.target, 0.0, True
        for duration, position, velocity, acceleration in self.segments:
            if t < duration:
                return position + velocity * t + 0.5 * acceleration * t * t, velocity + acceleration * t, False
            t -= duration
        return self.target, 0.0, True


class Axis:
    def __init__(self, config):
        self.c = config
        self.encoder = Encoder(config)
        self.position = self.velocity = self.offset = 0.0
        self.reference = self.reference_velocity = self.integral = self.output_velocity = 0.0
        self.volts = self.error = self.settled_time = 0.0
        self.enabled = self.in_position = False
        self.mode = 'disabled'
        self.output_test = False
        self.virtual_position = 0.0
        self.trajectory = None
        self.elapsed = 0.0
        self.jog_velocity = 0.0
        self.enable_delay = 0.0
        self._reset_response_monitor()

    def _reset_response_monitor(self):
        self.response_time = self.response_expected_counts = 0.0
        self.response_anchor = self.position
        self.response_direction = 0

    def _check_response(self, dt):
        # Feedback belongs to the PREVIOUS output interval. Ignore sub-LSB
        # commands and corrections already inside the accepted position band.
        demanding_motion = (abs(self.reference_velocity) > 0 or
                            abs(self.error) > self.c.tolerance_counts / self.c.counts_per_rev)
        if not demanding_motion or abs(self.volts) < 0.5 * 10 / 4095:
            self._reset_response_monitor()
            return
        direction = 1 if self.output_velocity > 0 else -1
        if direction != self.response_direction:
            self._reset_response_monitor()
            self.response_direction = direction
        progress = (self.position - self.response_anchor) * direction * self.c.counts_per_rev
        if progress >= 2 - 1e-9:
            self._reset_response_monitor()
            self.response_direction = direction
            return
        self.response_time += dt
        self.response_expected_counts += abs(self.output_velocity) * dt * self.c.counts_per_rev
        # Four expected counts allow for quantization at very low speed. This
        # detects absent progress, not an electrical diagnosis of the encoder.
        if (self.response_time + 1e-12 >= self.c.no_response_timeout_s
                and self.response_expected_counts >= 4):
            self.disable()
            raise ServoFault('Comando de movimento sem resposta do encoder; motor desabilitado')

    def feedback(self, raw, dt):
        position, self.velocity = self.encoder.update(raw, dt)
        self.position = position - self.offset
        if self.output_test:
            self.error = self.virtual_position - self.position

    def enable(self):
        if self.encoder.previous is None or abs(self.velocity) > self.c.vmax * 0.01:
            raise ValueError('Enable requires stationary, valid feedback')
        if not self.c.min_rev <= self.position <= self.c.max_rev:
            raise ValueError('Position outside configured travel')
        self.disable()
        self.enabled, self.mode = True, 'enabling'
        self.reference = self.position
        self.enable_delay = 0.1  # Zero speed for 100ms after SON, before position hold.

    def disable(self):
        self.enabled = self.in_position = False
        self.mode = 'disabled'
        self.trajectory = None
        self.reference = self.position
        self.reference_velocity = self.integral = self.output_velocity = self.volts = self.error = 0.0
        self.settled_time = 0.0
        self._reset_response_monitor()

    def set_output_test(self, active):
        if type(active) is not bool:
            raise ValueError('Expected boolean output test mode')
        if self.output_test == active:
            return
        # Preserve the simulated position and real encoder origin across toggles.
        # Rebase the closed-loop trajectory on the real measurement to avoid
        # commanding a catch-up to a simulated position when leaving test mode.
        if self.enabled:
            if self.mode == 'move':
                self.mode = 'stopping'
                self.trajectory = None
                self.jog_velocity = 0.0
            self.reference = self.virtual_position if active else self.position
            self.reference_velocity = self.output_velocity if self.mode in ('jog', 'stopping') else 0.0
            if not active:
                self.jog_velocity = clamp(self.jog_velocity, self.c.vmax)
            self.integral = 0.0
            self.in_position, self.settled_time = False, 0.0
        self.output_test = active
        self.error = self.virtual_position - self.position if active else self.reference - self.position
        self._reset_response_monitor()

    def stop_motion(self):
        """Brake the reference with configured deceleration, retaining position hold."""
        if self.enabled and self.mode in ('move', 'jog', 'stopping'):
            self.trajectory = None
            self.mode, self.jog_velocity = 'stopping', 0.0
            self.in_position, self.settled_time = False, 0.0

    def set_acceleration(self, rpm_s, deceleration=False):
        if isinstance(rpm_s, bool) or not isinstance(rpm_s, (int, float)) or not math.isfinite(rpm_s) or not 0.1 <= rpm_s <= 100000:
            raise ValueError('Aceleração deve estar entre 0,1 e 100000 RPM/s')
        updated = replace(self.c, **{('deceleration_rpm_s' if deceleration else 'acceleration_rpm_s'): rpm_s})
        if self.mode == 'move':
            trajectory = Trajectory(self.reference, self.trajectory.target, updated.vmax,
                                    updated.accel, self.reference_velocity, updated.decel)
            if trajectory.minimum < updated.min_rev or trajectory.maximum > updated.max_rev:
                raise ValueError('A nova aceleração ultrapassaria os limites de posição durante a frenagem')
            self.trajectory = trajectory
            self.elapsed = 0.0
        self.c = updated
        self.encoder.config = self.c

    def configure(self, values):
        updated = AxisConfig(**values)
        if not updated.min_rev <= self.position <= updated.max_rev:
            raise ValueError('Posição atual fora dos novos limites')
        geometry_changed = any(getattr(updated, name) != getattr(self.c, name)
                               for name in ('counts_per_rev', 'encoder_sign', 'output_sign', 'rpm_at_10v'))
        trajectory = None
        if self.mode == 'move' and not geometry_changed:
            trajectory = Trajectory(self.reference, self.trajectory.target, updated.vmax,
                                    updated.accel, self.reference_velocity, updated.decel)
            if trajectory.minimum < updated.min_rev or trajectory.maximum > updated.max_rev:
                raise ValueError('Trajetória fora dos novos limites de posição')
        if geometry_changed:
            self.disable()
            self.encoder.count *= updated.encoder_sign * self.c.encoder_sign
            self.offset = self.encoder.count / updated.counts_per_rev - self.position
            self.velocity *= (updated.encoder_sign * self.c.encoder_sign
                              * self.c.counts_per_rev / updated.counts_per_rev)
        self.c = self.encoder.config = updated
        if not self.output_test:
            self.jog_velocity = clamp(self.jog_velocity, updated.vmax)
        self.integral = 0.0
        self._reset_response_monitor()
        if trajectory is not None:
            self.trajectory, self.elapsed = trajectory, 0.0
        return geometry_changed

    def zero(self):
        if self.enabled:
            raise ValueError('Disable before setting local zero')
        self.offset += self.position
        self.position = self.reference = self.virtual_position = 0.0
        self.error = 0.0

    def move(self, target):
        if not math.isfinite(target) or not self.c.min_rev <= target <= self.c.max_rev:
            raise ValueError('Target outside travel')
        if not self.enabled or self.mode != 'hold' or not self.in_position:
            raise ValueError('Wait for enabled, settled position hold before moving')
        start = self.virtual_position if self.output_test else self.reference
        self.trajectory = Trajectory(start, target, self.c.vmax, self.c.accel, decel=self.c.decel)
        self.elapsed, self.settled_time = 0.0, 0.0
        self.in_position, self.mode = False, 'move'

    def jog(self, rpm):
        limit = 9999.9 if self.output_test else self.c.vmax * 60
        if not math.isfinite(rpm) or abs(rpm) > limit:
            raise ValueError('Jog exceeds velocity limit')
        if not self.enabled or self.mode not in ('hold', 'jog'):
            raise ValueError('Enable and wait for hold before jogging')
        self.mode, self.jog_velocity, self.in_position = 'jog', rpm / 60, False

    def jog_stop(self):
        if self.mode == 'jog':
            self.mode, self.jog_velocity = 'stopping', 0.0

    def calculate(self, dt):
        if not 0 < dt <= 0.02:
            raise ServoFault('Servo deadline missed')
        if not self.enabled:
            if self.output_test:
                self.error = self.virtual_position - self.position
            self.volts = 0.0
            return 0.0
        if not self.c.min_rev <= self.position <= self.c.max_rev:
            raise ServoFault('Measured position outside travel')
        if self.mode == 'enabling':
            self.enable_delay -= dt
            self.reference = self.position
            if self.enable_delay <= 0:
                self.mode = 'hold'
            self.volts = 0.0
            return 0.0
        if self.output_test:
            # Explicit instrument test: command velocity directly without PID,
            # closed-loop corrections or absent-feedback fault. Encoder stays live.
            if self.mode == 'move':
                self.elapsed += dt
                self.virtual_position, self.output_velocity, done = self.trajectory.sample(self.elapsed)
                if done:
                    self.mode = 'hold'
            else:
                target = clamp(self.jog_velocity, self.c.vmax) if self.mode == 'jog' else 0.0
                old_velocity = self.output_velocity
                self.output_velocity, travel = ramp_velocity(old_velocity, target, self.c.accel, self.c.decel, dt)
                self.virtual_position += travel
            self.reference = self.virtual_position
            self.reference_velocity = self.output_velocity
            self.error = self.virtual_position - self.position
            self.volts = self.c.output_sign * self.output_velocity * 600 / self.c.rpm_at_10v
            if self.mode == 'stopping' and self.output_velocity == 0:
                self.mode = 'hold'
            self.in_position = self.mode == 'hold' and self.output_velocity == 0
            return self.volts
        self._check_response(dt)
        if self.mode == 'move':
            self.elapsed += dt
            self.reference, self.reference_velocity, done = self.trajectory.sample(self.elapsed)
            if done:
                self.mode = 'hold'
        elif self.mode in ('jog', 'stopping'):
            old_velocity = self.reference_velocity
            self.reference_velocity, travel = ramp_velocity(old_velocity, self.jog_velocity, self.c.accel, self.c.decel, dt)
            next_reference = self.reference + travel
            # Begin braking before a jog reaches a soft limit.
            stopping_distance = self.reference_velocity ** 2 / (2 * self.c.decel)
            margin = stopping_distance + abs(self.reference_velocity) * 2 * dt + 1 / self.c.counts_per_rev
            if ((self.reference_velocity > 0 and self.c.max_rev - next_reference <= margin)
                    or (self.reference_velocity < 0 and next_reference - self.c.min_rev <= margin)):
                self.jog_stop()
            if not self.c.min_rev <= next_reference <= self.c.max_rev:
                raise ServoFault('Jog reference outside travel')
            self.reference = next_reference
            if self.mode == 'stopping' and self.reference_velocity == 0:
                self.mode = 'hold'
        self.error = self.reference - self.position
        if abs(self.error) > self.c.following_error_rev:
            raise ServoFault('Position following error exceeded')
        deadband = 0.6 / self.c.counts_per_rev
        error = math.copysign(max(0, abs(self.error) - deadband), self.error)
        candidate_i = self.integral + error * dt
        derivative = self.reference_velocity - self.velocity
        base = self.c.kp * error + self.c.kd * derivative + self.c.ff1 * self.reference_velocity
        requested = base + self.c.ki * candidate_i
        limited = clamp(requested, self.c.vmax)
        # Acceleration limits belong to the reference trajectory. Limiting PID
        # correction to that same ramp removes its authority to catch up with
        # a lagging velocity amplifier and can destabilize the outer loop.
        if abs(requested - limited) < 1e-12 or (requested - limited) * error <= 0:
            self.integral = candidate_i if self.c.ki else 0.0
        else:
            limited = clamp(base + self.c.ki * self.integral, self.c.vmax)
        self.output_velocity = limited
        self.volts = self.c.output_sign * limited * 600 / self.c.rpm_at_10v
        settled = (self.mode == 'hold' and abs(self.error) <= self.c.tolerance_counts / self.c.counts_per_rev + 1e-12
                   and abs(self.velocity) <= max(1 / self.c.counts_per_rev / dt, 0.001))
        self.settled_time = self.settled_time + dt if settled else 0.0
        self.in_position = self.settled_time >= 0.1
        return self.volts

    def telemetry(self):
        return dict(position=self.virtual_position if self.output_test else self.position,
                    rpm=self.output_velocity * 60 if self.output_test else self.velocity * 60,
                    encoder_position=self.position, encoder_rpm=self.velocity * 60,
                    target=self.virtual_position if self.output_test else self.reference,
                    error=self.error, volts=self.volts, enabled=self.enabled,
                    in_position=self.in_position, mode=self.mode,
                    virtual_position=self.virtual_position,
                    jog_rpm=self.jog_velocity * 60, output_test=self.output_test)
