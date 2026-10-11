#pragma once
#include <algorithm>
#include <array>
#include <cmath>
#include <cstddef>
#include <stdexcept>

namespace t3d {
struct Ramp { double velocity; double travel; };
// A reversal brakes to zero first, then accelerates with the remaining time.
inline Ramp ramp_velocity(double velocity, double target, double acceleration,
                          double deceleration, double dt) {
    if (!std::isfinite(velocity) || !std::isfinite(target) || !std::isfinite(dt)
        || !std::isfinite(acceleration) || !std::isfinite(deceleration)
        || acceleration <= 0 || deceleration <= 0 || dt <= 0)
        throw std::invalid_argument("Invalid velocity ramp");
    double travel = 0;
    if (velocity * target < 0) {
        const double to_zero = std::abs(velocity) / deceleration;
        const double braking = std::min(dt, to_zero);
        const double next = braking >= to_zero ? 0 : std::copysign(std::max(0., std::abs(velocity) - deceleration * braking), velocity);
        travel = .5 * (velocity + next) * braking;
        dt -= braking;
        velocity = next;
        if (dt <= 0) return {velocity, travel};
        velocity = 0;
    }
    const double rate = std::abs(target) > std::abs(velocity) ? acceleration : deceleration;
    const double difference = target - velocity;
    const double needed = std::abs(difference) / rate;
    const double used = std::min(dt, needed);
    const double next = needed <= dt ? target : velocity + std::copysign(rate * used, difference);
    travel += .5 * (velocity + next) * used + next * (dt - used);
    return {next, travel};
}
struct Segment { double duration, position, velocity, acceleration; };
struct Plan {
    std::array<Segment, 5> segments{};
    std::size_t count = 0;
    double duration = 0, minimum = 0, maximum = 0;
};
inline Plan plan_trajectory(double start, double target, double vmax,
                            double accel, double initial_velocity, double decel) {
    if (!std::isfinite(start) || !std::isfinite(target) || !std::isfinite(vmax)
        || !std::isfinite(accel) || !std::isfinite(decel) || !std::isfinite(initial_velocity)
        || vmax <= 0 || accel <= 0 || decel <= 0)
        throw std::invalid_argument("Invalid trajectory");
    Plan plan;
    plan.minimum = plan.maximum = start;
    double position = start, velocity = initial_velocity;
    const auto segment = [&](double duration, double acceleration) {
        if (duration <= 0) return;
        if (plan.count >= plan.segments.size()) throw std::invalid_argument("Too many trajectory segments");
        plan.segments[plan.count++] = {duration, position, velocity, acceleration};
        position += velocity * duration + .5 * acceleration * duration * duration;
        velocity += acceleration * duration;
        plan.duration += duration;
        plan.minimum = std::min(plan.minimum, position);
        plan.maximum = std::max(plan.maximum, position);
    };
    double distance = target - position;
    double direction = distance >= 0 ? 1 : -1;
    if (velocity * direction < 0 || velocity * velocity / (2 * decel) > std::abs(distance)) {
        if (velocity != 0) segment(std::abs(velocity) / decel, -std::copysign(decel, velocity));
        velocity = 0;
        distance = target - position;
        direction = distance >= 0 ? 1 : -1;
    }
    if (velocity * direction > vmax) {
        segment((velocity * direction - vmax) / decel, -direction * decel);
        velocity = direction * vmax;
        distance = target - position;
    }
    const double speed = velocity * direction;
    const double full_distance = (vmax * vmax - speed * speed) / (2 * accel) + vmax * vmax / (2 * decel);
    const double peak = std::abs(distance) >= full_distance ? vmax :
        std::sqrt(std::max(0., (2 * accel * decel * std::abs(distance) + decel * speed * speed) / (accel + decel)));
    const double ramp = std::max(0., (peak - speed) / accel);
    const double braking = peak / decel;
    const double cruise = std::max(0., std::abs(distance) - (peak * peak - speed * speed) / (2 * accel) - peak * peak / (2 * decel));
    segment(ramp, direction * accel);
    segment(peak != 0 ? cruise / peak : 0., 0);
    segment(braking, -direction * decel);
    if (!std::isfinite(plan.duration) || !std::isfinite(plan.minimum) || !std::isfinite(plan.maximum))
        throw std::invalid_argument("Trajectory exceeds numeric range");
    return plan;
}
} // namespace t3d
