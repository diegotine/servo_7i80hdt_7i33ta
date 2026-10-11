#include "cpu_clock.h"
#include <cerrno>
#include <csignal>
#include <cstdio>
#include <cstring>
#include <fstream>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>
#include <fcntl.h>
#include <poll.h>
#include <sys/file.h>
#include <unistd.h>

namespace {
volatile sig_atomic_t stopping = 0;
void stop(int) { stopping = 1; }
std::string read(const std::string &path)
{
    std::ifstream stream(path);
    std::string value;
    if (!stream || !std::getline(stream, value)) throw std::runtime_error("leitura: " + path);
    return value;
}
void write(const std::string &path, const std::string &value)
{
    const int fd = open(path.c_str(), O_WRONLY | O_CLOEXEC);
    if (fd < 0) throw std::runtime_error("abertura: " + path + ": " + std::strerror(errno));
    const std::string line = value + '\n';
    const auto count = ::write(fd, line.data(), line.size());
    const int saved = errno;
    close(fd);
    if (count != static_cast<ssize_t>(line.size()))
        throw std::runtime_error("gravação: " + path + ": " + std::strerror(saved));
}
bool contains(const std::string &values, const std::string &value)
{
    std::istringstream stream(values);
    std::string token;
    while (stream >> token) if (token == value) return true;
    return false;
}
}

int cpuClockSession(int cpu, bool inspectOnly)
{
    const std::string path = "/sys/devices/system/cpu/cpu" + std::to_string(cpu) + "/cpufreq/";
    int lock = -1;
    std::string governor, minimum, maximum;
    bool governorChanged = false, minimumChanged = false, maximumChanged = false;
    struct Extra { std::string path, previous, applied; };
    std::vector<Extra> extras;
    constexpr const char *target = "4200000";
    auto restore = [&] {
        for (auto it = extras.rbegin(); it != extras.rend(); ++it) {
            try { if (read(it->path) == it->applied) write(it->path, it->previous); }
            catch (const std::exception &e) { std::fprintf(stderr, "CPU: restauração falhou: %s\n", e.what()); }
        }
        // Restore only settings still owned by this session. Respect external changes.
        auto one = [&](const char *file, const std::string &saved, const char *ours, bool changed) {
            if (!changed) return;
            try { if (read(path + file) == ours) write(path + file, saved); }
            catch (const std::exception &e) { std::fprintf(stderr, "CPU: restauração falhou: %s\n", e.what()); }
        };
        // Saved maximum may be below our temporary minimum.
        if (!minimum.empty() && std::stoll(minimum) > 4200000) {
            one("scaling_max_freq", maximum, target, maximumChanged);
            one("scaling_min_freq", minimum, target, minimumChanged);
        } else {
            one("scaling_min_freq", minimum, target, minimumChanged);
            one("scaling_max_freq", maximum, target, maximumChanged);
        }
        one("scaling_governor", governor, "performance", governorChanged);
    };
    try {
        governor = read(path + "scaling_governor");
        minimum = read(path + "scaling_min_freq");
        maximum = read(path + "scaling_max_freq");
        const auto driver = read(path + "scaling_driver");
        const auto available = read(path + "scaling_available_governors");
        bool exact = false;
        std::ifstream discrete(path + "scaling_available_frequencies");
        if (discrete) {
            std::string values; std::getline(discrete, values);
            exact = contains(values, target);
        } else {
            exact = (driver == "intel_pstate" || driver == "intel_cpufreq" || driver == "amd-pstate" || driver == "amd-pstate-epp")
                && std::stoll(read(path + "cpuinfo_min_freq")) <= 4200000
                && std::stoll(read(path + "cpuinfo_max_freq")) >= 4200000;
        }
        std::printf("CPU %d | driver=%s | governador=%s | limites=%s..%s kHz | 4200 MHz selecionável=%s\n",
                    cpu, driver.c_str(), governor.c_str(), minimum.c_str(), maximum.c_str(), exact ? "sim" : "não");
        std::fflush(stdout);
        if (inspectOnly) return 0;
        if (geteuid() != 0) throw std::runtime_error("ajuste requer helper instalado via sudo");
        if (!contains(available, "performance")) throw std::runtime_error("governador performance indisponível");
        const std::string lockPath = "/run/t3d-cpu-clock-" + std::to_string(cpu) + ".lock";
        lock = open(lockPath.c_str(), O_CREAT | O_RDWR | O_CLOEXEC | O_NOFOLLOW, 0600);
        if (lock < 0 || flock(lock, LOCK_EX | LOCK_NB)) throw std::runtime_error("CPU já reservada por outra instância ou lock indisponível");
        std::signal(SIGPIPE, SIG_IGN);
        std::signal(SIGTERM, stop); std::signal(SIGINT, stop); std::signal(SIGHUP, stop);
        governorChanged = governor != "performance";
        write(path + "scaling_governor", "performance");
        if (exact) {
            // Widen first when the old minimum is above the requested maximum.
            if (std::stoll(minimum) > 4200000) {
                minimumChanged = minimum != target;
                write(path + "scaling_min_freq", target);
            }
            maximumChanged = maximum != target;
            write(path + "scaling_max_freq", target);
            minimumChanged = minimum != target;
            write(path + "scaling_min_freq", target);
            if (read(path + "scaling_min_freq") != target || read(path + "scaling_max_freq") != target)
                throw std::runtime_error("kernel não confirmou os limites de 4200 MHz");
        }
        // TuneD CPU plug-in: scoped EPB/EPP, boost and per-CPU PM QoS.
        const auto optional = [&](const std::string &file, const char *value) {
            if (access(file.c_str(), F_OK)) return;
            try {
                const auto previous = read(file);
                if (previous == value) return;
                extras.push_back({file, previous, value});
                write(file, value);
                if (read(file) != value) throw std::runtime_error("valor não confirmado");
                std::printf("CPU %d: %s=%s\n", cpu, file.c_str(), value);
            } catch (const std::exception &e) {
                std::fprintf(stderr, "CPU: ajuste opcional %s: %s\n", file.c_str(), e.what());
            }
        };
        const auto power = "/sys/devices/system/cpu/cpu" + std::to_string(cpu) + "/power/";
        optional(path + "boost", "1");
        optional(path + "energy_performance_preference", "performance");
        optional(power + "energy_perf_bias", "0");
        optional(power + "pm_qos_resume_latency_us", "n/a");
        if (read(path + "scaling_governor") != "performance") throw std::runtime_error("kernel não confirmou performance");
        std::printf("CPU %d: performance aplicado; %s. Restauração ao fechar o aplicativo.\n", cpu,
                    exact ? "limites solicitados e confirmados em 4200 MHz (sujeitos ao hardware)" : "4200 MHz exatos indisponíveis neste driver; turbo continua sob controle do hardware");
        std::fflush(stdout);
        // GUI owns stdin. EOF also restores after a GUI crash, without a timer in the control loop.
        while (!stopping) {
            pollfd input{STDIN_FILENO, POLLIN | POLLHUP, 0};
            const int result = poll(&input, 1, 250);
            if (result < 0 && errno != EINTR) throw std::runtime_error("poll da sessão falhou");
            if (result > 0 && (input.revents & (POLLIN | POLLHUP | POLLERR | POLLNVAL))) {
                char buffer[32];
                if (::read(STDIN_FILENO, buffer, sizeof buffer) <= 0) break;
            }
        }
        restore(); close(lock); return 0;
    } catch (const std::exception &e) {
        std::fprintf(stderr, "CPU: %s\n", e.what());
        restore(); if (lock >= 0) close(lock); return 1;
    }
}
