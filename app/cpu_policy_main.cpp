// Fixed sysfs operations owned by the Qt interface; never starts the driver.
#include "cpu_clock.h"
#include <charconv>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <unistd.h>

int main(int argc, char **argv)
{
    if (argc != 3) return 2;
    const bool inspect = std::strcmp(argv[1], "--cpu-check") == 0;
    const bool clockOnly = std::strcmp(argv[1], "--cpu-clock-session") == 0;
    if (!inspect && !clockOnly && std::strcmp(argv[1], "--cpu-session") != 0) return 2;
    if (!inspect) {
        const char *sudoUid = std::getenv("SUDO_UID");
        if (getuid() != 0 || geteuid() != 0 || !sudoUid
            || std::strcmp(sudoUid, T3D_ALLOWED_UID_TEXT) != 0) {
            std::fprintf(stderr, "T3D interface CPU: usuário não autorizado\n");
            return 1;
        }
    }
    int cpu = -1;
    const auto end = argv[2] + std::strlen(argv[2]);
    const auto parsed = std::from_chars(argv[2], end, cpu);
    if (parsed.ec != std::errc{} || parsed.ptr != end || cpu < 0 || cpu >= 1024) return 2;
    return cpuClockSession(cpu, inspect, clockOnly);
}
