# Static C storage for the cyclic control state. Counts remain Python integers
# so long-running encoder accumulation keeps its original unlimited range.
cpdef double clamp(double value, double limit)

cdef class Encoder:
    cdef public object config, previous, count
    cpdef update(self, object raw, double dt)

cdef class Trajectory:
    cdef public double start, target, duration, minimum, maximum
    cdef public object segments
    cpdef sample(self, double t)

cdef class Axis:
    cdef public object c, encoder, trajectory, mode
    cdef public double position, velocity, offset, reference, reference_velocity
    cdef public double integral, output_velocity, volts, error, settled_time
    cdef public double virtual_position, elapsed, jog_velocity, enable_delay
    cdef public double response_time, response_expected_counts, response_anchor
    cdef public int response_direction
    cdef public bint enabled, in_position, output_test
    cpdef _check_response(self, double dt)
    cpdef feedback(self, object raw, double dt)
    cpdef calculate(self, double dt)
