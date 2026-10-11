#pragma once
#include <QByteArray>
#include <QString>

// GUI-only, best-effort telemetry. Never called by the controller thread.
QString timingSocketPath();
class TimingFeed final {
public:
    TimingFeed();
    ~TimingFeed();
    TimingFeed(const TimingFeed &) = delete;
    TimingFeed &operator=(const TimingFeed &) = delete;
    void publish(const QByteArray &message, qint64 backendPid) const;
private:
    int m_fd = -1;
};
