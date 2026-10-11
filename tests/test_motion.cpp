#include "motion.hpp"
#include <cstdio>
#include <cstdlib>
#include <limits>

void near(double value, double expected) {
    if (std::abs(value - expected) > 1e-9) {
        std::fprintf(stderr, "actual %.15g expected %.15g\n", value, expected);
        std::exit(1);
    }
}
void endpoint(const t3d::Plan &plan, double target) {
    double p = plan.segments[0].position, v = plan.segments[0].velocity;
    double duration = 0;
    for (std::size_t i = 0; i < plan.count; ++i) {
        const auto &s = plan.segments[i];
        near(s.position, p); near(s.velocity, v);
        p += v * s.duration + .5 * s.acceleration * s.duration * s.duration;
        v += s.acceleration * s.duration;
        duration += s.duration;
    }
    near(p, target); near(v, 0); near(duration, plan.duration);
}
int main() {
    // 1000 RPM -> stop at 600 RPM/s: 1.6667 seconds and 13.8889 turns.
    const auto stop = t3d::ramp_velocity(1000./60, 0, 350./60, 600./60, 2);
    near(stop.velocity, 0); near(stop.travel, 1000.*1000/(2*600*60));
    const auto up = t3d::ramp_velocity(0, 1000./60, 350./60, 600./60, 1);
    near(up.velocity, 350./60); near(up.travel, 350./120);
    const auto reverse = t3d::ramp_velocity(10, -10, 2, 10, 2);
    near(reverse.velocity, -2); near(reverse.travel, 4);
    const auto down = t3d::ramp_velocity(-10, -2, 2, 10, 1);
    near(down.velocity, -2); near(down.travel, -5.2);
    // Analytic asymmetric triangle: peak sqrt(8/3), time peak/2 + peak/4.
    auto triangle = t3d::plan_trajectory(0, 1, 10, 2, 0, 4);
    near(triangle.duration, std::sqrt(8./3)*.75); endpoint(triangle, 1);
    auto trapezoid = t3d::plan_trajectory(0, 100, 10, 2, 0, 4);
    near(trapezoid.duration, 13.75); endpoint(trapezoid, 100);
    for (double target : {-1., .01, 1., 100.})
        for (double velocity : {-20., -2., 0., 2., 20.})
            endpoint(t3d::plan_trajectory(0, target, 5, 2, velocity, 4), target);
    // Overshoot is included in the position envelope used by soft limits.
    auto overshoot = t3d::plan_trajectory(0, .01, 5, 2, 2, 4);
    near(overshoot.maximum, .5);
    bool rejected = false;
    try { t3d::ramp_velocity(0, 1, 1, 0, .002); }
    catch (const std::invalid_argument &) { rejected = true; }
    if (!rejected) return 1;
    std::puts("Native motion: asymmetric ramps, reversal, endpoints and limits OK");
}
