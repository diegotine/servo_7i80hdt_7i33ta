#include "timingfeed.h"
#include <QCoreApplication>
#include <QFile>
#include <QStandardPaths>
#include <cstring>
#include <sys/socket.h>
#include <sys/un.h>
#include <unistd.h>

QString timingSocketPath()
{
    return QStandardPaths::writableLocation(QStandardPaths::RuntimeLocation)
        + (QCoreApplication::arguments().contains("--smoke-test")
            ? QString("/t3d-timing-test-%1.sock").arg(QCoreApplication::applicationPid())
            : "/t3d-timing-monitor.sock");
}

TimingFeed::TimingFeed() : m_fd(socket(AF_UNIX, SOCK_DGRAM | SOCK_NONBLOCK | SOCK_CLOEXEC, 0)) {}
TimingFeed::~TimingFeed() { if (m_fd >= 0) ::close(m_fd); }

void TimingFeed::publish(const QByteArray &message, qint64 backendPid) const
{
    if (m_fd < 0) return;
    sockaddr_un address{};
    address.sun_family = AF_UNIX;
    const auto path = QFile::encodeName(timingSocketPath());
    if (path.size() >= static_cast<qsizetype>(sizeof(address.sun_path))) return;
    std::memcpy(address.sun_path, path.constData(), path.size() + 1);
    // Reuse the JSON already received from the backend; no extra board access.
    const QByteArray packet = "{\"gui_pid\":" + QByteArray::number(QCoreApplication::applicationPid())
        + ",\"backend_pid\":" + QByteArray::number(backendPid)
        + ",\"version\":\"" T3D_VERSION "\",\"payload\":" + message + "}";
    // No retry, wait, acknowledgment, or queue in the controlling application.
    (void)sendto(m_fd, packet.constData(), packet.size(), MSG_DONTWAIT | MSG_NOSIGNAL,
                 reinterpret_cast<const sockaddr *>(&address), sizeof(address));
}
