// Grant bounded resource limits, drop all capabilities, then exec the user backend.
// Installed root-owned with only cap_sys_resource=ep; never setuid root.
#include <cerrno>
#include <cstdio>
#include <cstring>
#include <linux/capability.h>
#include <sys/prctl.h>
#include <sys/resource.h>
#include <sys/syscall.h>
#include <unistd.h>
#include <vector>

static int fail(const char *operation)
{
    std::fprintf(stderr, "T3D runtime: %s: %s\n", operation, std::strerror(errno));
    return 1;
}

int main(int argc, char **argv)
{
    if (getuid() != T3D_ALLOWED_UID || geteuid() != getuid()) {
        std::fprintf(stderr, "T3D runtime: usuário não autorizado\n");
        return 1;
    }
    // Priority 10 requested by default; maximum granted is 20. Only this
    // process and descendants inherit these limits, not the desktop session.
    const rlimit priority{20, 20};
    const rlimit memory{256UL * 1024 * 1024, 256UL * 1024 * 1024};
    const rlimit realtime_cpu{200000, 200000}; // 200 ms of RT CPU without blocking.
    if (setrlimit(RLIMIT_RTPRIO, &priority)) return fail("RLIMIT_RTPRIO");
    if (setrlimit(RLIMIT_MEMLOCK, &memory)) return fail("RLIMIT_MEMLOCK");
    if (setrlimit(RLIMIT_RTTIME, &realtime_cpu)) return fail("RLIMIT_RTTIME");

    __user_cap_header_struct header{};
    header.version = _LINUX_CAPABILITY_VERSION_3;
    __user_cap_data_struct capabilities[2]{};
    if (syscall(SYS_capset, &header, capabilities)) return fail("drop capabilities");
    if (prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0)) return fail("no_new_privs");

    const bool check = argc == 2 && std::strcmp(argv[1], "--check") == 0;
    std::vector<char *> args{
        const_cast<char *>(T3D_PYTHON), const_cast<char *>("-u"),
        const_cast<char *>(check ? T3D_RUNTIME_CHECK : T3D_BACKEND)
    };
    if (!check) {
        for (int i = 1; i < argc; ++i) args.push_back(argv[i]);
    }
    args.push_back(nullptr);
    execv(T3D_PYTHON, args.data());
    return fail("exec backend");
}
