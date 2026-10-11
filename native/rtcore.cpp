// Single-owner timing/statistics core. No board access and no global counters.
#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <algorithm>
#include <array>
#include <cerrno>
#include <cmath>
#include <cstdint>
#include <limits>
#include <new>
#include <time.h>
#include "motion.hpp"

namespace {
constexpr std::size_t capacity = 256;
struct Statistics {
    std::array<double, capacity> window{};
    std::uint64_t count = 0;
    std::size_t used = 0;
    std::size_t next = 0;
    double mean = 0;
    double m2 = 0;
    double minimum = std::numeric_limits<double>::infinity();
    double maximum = 0;

    void add(double value) noexcept {
        window[next] = value;
        next = (next + 1) % capacity;
        used = std::min(used + 1, capacity);
        ++count;
        // Keep Welford's original operation order; do not reorder this recurrence.
        const double delta = value - mean;
        mean += delta / static_cast<double>(count);
        m2 += delta * (value - mean);
        minimum = std::min(minimum, value);
        maximum = std::max(maximum, value);
    }
};
struct PySamples {
    PyObject_HEAD
    Statistics *state;
};

PyObject *samples_new(PyTypeObject *type, PyObject *args, PyObject *kwargs) {
    if (PyTuple_Size(args) || (kwargs && PyDict_Size(kwargs))) {
        PyErr_SetString(PyExc_TypeError, "Samples takes no arguments");
        return nullptr;
    }
    auto *self = reinterpret_cast<PySamples *>(type->tp_alloc(type, 0));
    if (!self) return nullptr;
    self->state = new (std::nothrow) Statistics{};
    if (!self->state) {
        Py_DECREF(reinterpret_cast<PyObject *>(self));
        return PyErr_NoMemory();
    }
    return reinterpret_cast<PyObject *>(self);
}
void samples_dealloc(PyObject *object) {
    auto *self = reinterpret_cast<PySamples *>(object);
    delete self->state;
    PyTypeObject *type = Py_TYPE(object);
    type->tp_free(object);
    Py_DECREF(type);
}
PyObject *samples_add(PyObject *object, PyObject *argument) {
    auto &state = *reinterpret_cast<PySamples *>(object)->state;
    const double nanoseconds = PyFloat_AsDouble(argument);
    if (PyErr_Occurred()) return nullptr;
    if (!std::isfinite(nanoseconds)) {
        PyErr_SetString(PyExc_ValueError, "Nonfinite statistics sample");
        return nullptr;
    }
    if (state.count == std::numeric_limits<std::uint64_t>::max()) {
        PyErr_SetString(PyExc_OverflowError, "Statistics counter exhausted");
        return nullptr;
    }
    state.add(nanoseconds / 1e6);
    Py_RETURN_NONE;
}
PyObject *samples_report(PyObject *object, PyObject *) {
    const auto &state = *reinterpret_cast<PySamples *>(object)->state;
    if (!state.count) Py_RETURN_NONE;
    // Fixed-size stack copy; sorting/report allocation occurs only on demand.
    auto ordered = state.window;
    std::sort(ordered.begin(), ordered.begin() + state.used);
    const auto rank = static_cast<std::size_t>(std::ceil(state.used * .95)) - 1;
    const auto last = (state.next + capacity - 1) % capacity;
    return Py_BuildValue("{s:K,s:d,s:d,s:d,s:d,s:d,s:d}",
        "count", static_cast<unsigned long long>(state.count),
        "last_ms", state.window[last], "mean_ms", state.mean,
        "min_ms", state.minimum, "max_ms", state.maximum,
        "stddev_ms", std::sqrt(std::max(0., state.m2 / state.count)),
        "p95_recent_ms", ordered[rank]);
}
PyObject *samples_window(PyObject *object, void *) {
    const auto &state = *reinterpret_cast<PySamples *>(object)->state;
    PyObject *result = PyTuple_New(static_cast<Py_ssize_t>(state.used));
    if (!result) return nullptr;
    const auto start = state.used == capacity ? state.next : 0;
    for (std::size_t i = 0; i < state.used; ++i) {
        PyObject *value = PyFloat_FromDouble(state.window[(start + i) % capacity]);
        if (!value) { Py_DECREF(result); return nullptr; }
        PyTuple_SET_ITEM(result, static_cast<Py_ssize_t>(i), value);
    }
    return result;
}
PyMethodDef samples_methods[] = {
    {"add", samples_add, METH_O, "Record one nanosecond sample."},
    {"report", samples_report, METH_NOARGS, "Lifetime stats and recent P95."},
    {nullptr, nullptr, 0, nullptr}
};
PyGetSetDef samples_properties[] = {
    {"window", samples_window, nullptr, "Recent samples, oldest first (read-only).", nullptr},
    {nullptr, nullptr, nullptr, nullptr, nullptr}
};
PyType_Slot samples_slots[] = {
    {Py_tp_new, reinterpret_cast<void *>(samples_new)},
    {Py_tp_dealloc, reinterpret_cast<void *>(samples_dealloc)},
    {Py_tp_methods, samples_methods},
    {Py_tp_getset, samples_properties},
    {0, nullptr}
};
PyType_Spec samples_spec = {
    "_rtcore.Samples", static_cast<int>(sizeof(PySamples)), 0,
    Py_TPFLAGS_DEFAULT, samples_slots
};
PyObject *sleep_until_ns(PyObject *, PyObject *argument) {
    const long long target_ns = PyLong_AsLongLong(argument);
    if (PyErr_Occurred()) return nullptr;
    if (target_ns < 0) {
        PyErr_SetString(PyExc_ValueError, "Negative absolute deadline");
        return nullptr;
    }
    const timespec target{static_cast<time_t>(target_ns / 1000000000LL),
                          static_cast<long>(target_ns % 1000000000LL)};
    int result;
    do {
        Py_BEGIN_ALLOW_THREADS
        result = clock_nanosleep(CLOCK_MONOTONIC, TIMER_ABSTIME, &target, nullptr);
        Py_END_ALLOW_THREADS
        if (PyErr_CheckSignals() < 0) return nullptr;
    } while (result == EINTR);
    if (result) {
        errno = result; // clock_nanosleep returns an errno value directly.
        return PyErr_SetFromErrno(PyExc_OSError);
    }
    Py_RETURN_NONE;
}
[[gnu::cold]] PyObject *motion_error(const std::exception &error) {
    PyErr_SetString(PyExc_ValueError, error.what());
    return nullptr;
}
PyObject *ramp_velocity(PyObject *, PyObject *args) {
    double velocity, target, accel, decel, dt;
    if (!PyArg_ParseTuple(args, "ddddd", &velocity, &target, &accel, &decel, &dt)) return nullptr;
    try {
        const auto result = t3d::ramp_velocity(velocity, target, accel, decel, dt);
        return Py_BuildValue("(dd)", result.velocity, result.travel);
    } catch (const std::exception &error) { return motion_error(error); }
}
PyObject *plan_trajectory(PyObject *, PyObject *args) {
    double start, target, vmax, accel, velocity, decel;
    if (!PyArg_ParseTuple(args, "dddddd", &start, &target, &vmax, &accel, &velocity, &decel)) return nullptr;
    try {
        const auto plan = t3d::plan_trajectory(start, target, vmax, accel, velocity, decel);
        PyObject *segments = PyList_New(static_cast<Py_ssize_t>(plan.count));
        if (!segments) return nullptr;
        for (std::size_t i = 0; i < plan.count; ++i) {
            const auto &segment = plan.segments[i];
            PyObject *item = Py_BuildValue("(dddd)", segment.duration, segment.position,
                                          segment.velocity, segment.acceleration);
            if (!item) { Py_DECREF(segments); return nullptr; }
            PyList_SET_ITEM(segments, static_cast<Py_ssize_t>(i), item);
        }
        return Py_BuildValue("(Nddd)", segments, plan.duration, plan.minimum, plan.maximum);
    } catch (const std::exception &error) { return motion_error(error); }
}
PyMethodDef methods[] = {
    {"ramp_velocity", ramp_velocity, METH_VARARGS, "Independent acceleration/braking with exact travel."},
    {"plan_trajectory", plan_trajectory, METH_VARARGS, "Asymmetric position trajectory."},
    {"sleep_until_ns", sleep_until_ns, METH_O, "Absolute monotonic wait, releases GIL."},
    {nullptr, nullptr, 0, nullptr}
};
PyModuleDef module = {
    PyModuleDef_HEAD_INIT, "_rtcore", "C++ fixed-memory timing/statistics.",
    -1, methods, nullptr, nullptr, nullptr, nullptr
};
} // namespace

PyMODINIT_FUNC PyInit__rtcore() {
    PyObject *result = PyModule_Create(&module);
    if (!result) return nullptr;
    if (PyModule_AddStringConstant(result, "__version__", T3D_VERSION) < 0) {
        Py_DECREF(result);
        return nullptr;
    }
    PyObject *type = PyType_FromSpec(&samples_spec);
    if (!type || PyModule_AddObject(result, "Samples", type) < 0) {
        Py_XDECREF(type);
        Py_DECREF(result);
        return nullptr;
    }
    return result;
}
