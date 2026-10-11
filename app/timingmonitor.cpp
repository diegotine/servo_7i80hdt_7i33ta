#include "timingfeed.h"
#include <QApplication>
#include <QDateTime>
#include <QDesktopServices>
#include <QDir>
#include <QElapsedTimer>
#include <QFile>
#include <QJsonDocument>
#include <QJsonObject>
#include <QLabel>
#include <QLockFile>
#include <QMessageBox>
#include <QPushButton>
#include <QSocketNotifier>
#include <QStandardPaths>
#include <QTemporaryDir>
#include <QTimer>
#include <QUrl>
#include <QVBoxLayout>
#include <array>
#include <cerrno>
#include <cstring>
#include <sched.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/un.h>
#include <unistd.h>

namespace {
// Baselines belong to this observer, never reset the controller's counters.
struct Observation {
    qint64 source = -1, previousCycles = -1, previousWork = 0, previousSkipped = 0;
    qint64 cycles = 0, overruns = 0, skipped = 0, segments = 0;
    bool pendingBaseline = true;

    bool update(qint64 pid, const QJsonObject &timing) {
        const qint64 currentCycles = timing.value("work").toObject().value("count").toInteger();
        const qint64 work = timing.value("work_overruns").toInteger();
        const qint64 lost = timing.value("skipped_slots").toInteger();
        if (pendingBaseline || source != pid || currentCycles < previousCycles
            || work < previousWork || lost < previousSkipped) {
            ++segments;
            pendingBaseline = false;
        } else {
            cycles += currentCycles - previousCycles;
            overruns += work - previousWork;
            skipped += lost - previousSkipped;
        }
        const bool event = previousCycles >= 0 && source == pid
            && (work > previousWork || lost > previousSkipped);
        source = pid;
        previousCycles = currentCycles;
        previousWork = work;
        previousSkipped = lost;
        return event;
    }
    QJsonObject report() const {
        return {{"observed_cycles", cycles}, {"work_overruns", overruns},
                {"skipped_slots", skipped}, {"segments", segments}};
    }
};

QString pinObserver()
{
    cpu_set_t allowed;
    CPU_ZERO(&allowed);
    if (sched_getaffinity(0, sizeof(allowed), &allowed))
        return "Afinidade não aplicada: " + QString::fromLocal8Bit(std::strerror(errno));
    int controlCpu = -1;
    const QString setting = qEnvironmentVariable("T3D_CPU", "auto");
    for (int cpu = 0; cpu < CPU_SETSIZE; ++cpu)
        if (CPU_ISSET(cpu, &allowed)) controlCpu = cpu;
    if (setting != "auto" && setting != "none") {
        bool valid = false;
        const int requested = setting.toInt(&valid);
        if (valid) controlCpu = requested;
    }
    if (setting == "none") return "Sem CPU dedicada no controlador; isolamento não confirmado.";
    for (int cpu = 0; cpu < CPU_SETSIZE; ++cpu) {
        if (!CPU_ISSET(cpu, &allowed) || cpu == controlCpu) continue;
        cpu_set_t selected;
        CPU_ZERO(&selected);
        CPU_SET(cpu, &selected);
        if (!sched_setaffinity(0, sizeof(selected), &selected))
            return QString("Monitor na CPU %1 • controlador configurado para CPU %2 • prioridade normal")
                .arg(cpu).arg(controlCpu);
        break;
    }
    return "Não foi possível reservar outro núcleo; isolamento não confirmado.";
}

QString milliseconds(const QJsonObject &timing, const QString &field, const QString &stat)
{
    const auto value = timing.value(field).toObject().value(stat);
    return value.isDouble() ? QString::number(value.toDouble(), 'f', 4) : "—";
}
}

int main(int argc, char **argv)
{
    // Apply before QApplication starts any helper threads. No FIFO or root required.
    sched_param normal{};
    const bool ordinary = sched_setscheduler(0, SCHED_OTHER, &normal) == 0;
    const QString affinity = pinObserver();
    QApplication app(argc, argv);
    app.setOrganizationName("HL-T3D-RABN");
    app.setApplicationName("T3D Timing Monitor");
    const bool smoke = app.arguments().contains("--smoke-test");
    const QString socketPath = timingSocketPath();
    QLockFile lock(socketPath + ".lock");
    if (!lock.tryLock(0)) {
        QMessageBox::information(nullptr, "Monitor de períodos", "O monitor já está aberto.");
        return 0;
    }
    const int fd = socket(AF_UNIX, SOCK_DGRAM | SOCK_NONBLOCK | SOCK_CLOEXEC, 0);
    if (fd < 0) return 1;
    sockaddr_un address{};
    address.sun_family = AF_UNIX;
    const QByteArray encoded = QFile::encodeName(socketPath);
    if (encoded.size() >= static_cast<qsizetype>(sizeof(address.sun_path))) {
        ::close(fd);
        return 1;
    }
    std::memcpy(address.sun_path, encoded.constData(), encoded.size() + 1);
    QFile::remove(socketPath); // Only after acquiring our exclusive observer lock.
    if (bind(fd, reinterpret_cast<const sockaddr *>(&address), sizeof(address))) {
        QMessageBox::critical(nullptr, "Monitor de períodos", QString::fromLocal8Bit(std::strerror(errno)));
        ::close(fd);
        return 1;
    }
    chmod(encoded.constData(), S_IRUSR | S_IWUSR);

    QWidget window;
    window.setWindowTitle("T3D • Monitor de períodos • v" T3D_VERSION);
    window.resize(680, 420);
    auto *layout = new QVBoxLayout(&window);
    auto *state = new QLabel("Aguardando telemetria do T3D…", &window);
    auto *cpu = new QLabel(affinity + (ordinary ? "" : " • falha ao selecionar prioridade normal"), &window);
    auto *totals = new QLabel("Nenhum ciclo observado.", &window);
    auto *stages = new QLabel("", &window);
    auto *explanation = new QLabel(
        "Mede os timestamps do controlador; a chegada das mensagens não é o período da malha.\n"
        "Estouro = trabalho de leitura + controle + escrita acima do período. Ciclos perdidos = slots descartados pelo temporizador.\n"
        "Amostras de tela chegam a ~20 Hz. P95 usa os últimos 256 ciclos; máximos são desde o início da sessão.\n"
        "O tempo de trabalho informado não inclui a serialização da telemetria. O log não identifica o instante de cada estouro.", &window);
    auto *fileLabel = new QLabel(&window);
    for (auto *label : {state, cpu, totals, stages, explanation, fileLabel}) {
        label->setWordWrap(true);
        label->setTextInteractionFlags(Qt::TextSelectableByMouse);
        layout->addWidget(label);
    }
    auto *newTest = new QPushButton("Novo ensaio / novo log", &window);
    auto *folder = new QPushButton("Abrir pasta dos logs", &window);
    layout->addWidget(newTest);
    layout->addWidget(folder);

    QTemporaryDir temporary;
    const QString directory = smoke ? temporary.path()
        : QStandardPaths::writableLocation(QStandardPaths::GenericDataLocation)
            + "/HL-T3D-RABN/T3D Analog Velocity/timing";
    QDir().mkpath(directory);
    QFile log;
    Observation observation;
    QJsonObject latest, latestTiming;
    qint64 packets = 0;
    QElapsedTimer age;
    auto record = [&](const QString &kind, const QJsonObject &packet) {
        if (!log.isOpen()) return;
        const QJsonObject entry{{"event", kind}, {"observer_utc", QDateTime::currentDateTimeUtc().toString(Qt::ISODateWithMs)},
                                {"observer_totals", observation.report()}, {"telemetry", packet}};
        const QByteArray bytes = QJsonDocument(entry).toJson(QJsonDocument::Compact) + '\n';
        if (log.write(bytes) != bytes.size() || !log.flush()) {
            fileLabel->setText("ERRO ao gravar log: " + log.errorString());
            log.close();
        }
    };
    auto begin = [&] {
        record("end", latest);
        log.close();
        observation = Observation{};
        if (!latestTiming.isEmpty())
            observation.update(latest.value("backend_pid").toInteger(), latestTiming);
        const QString name = directory + "/timing-v" T3D_VERSION "-"
            + QDateTime::currentDateTimeUtc().toString("yyyyMMdd-HHmmss-zzz")
            + QString("-%1.jsonl").arg(QCoreApplication::applicationPid());
        log.setFileName(name);
        if (log.open(QIODevice::WriteOnly | QIODevice::NewOnly)) {
            fileLabel->setText("Log: " + name);
            record("begin", latest);
        } else fileLabel->setText("ERRO ao abrir log: " + log.errorString());
    };
    begin();
    QObject::connect(newTest, &QPushButton::clicked, &window, [&] { begin(); });
    QObject::connect(folder, &QPushButton::clicked, &window, [&] {
        QDesktopServices::openUrl(QUrl::fromLocalFile(directory));
    });

    QSocketNotifier receiver(fd, QSocketNotifier::Read, &window);
    QObject::connect(&receiver, &QSocketNotifier::activated, &window, [&] {
        // Bounded drain keeps this observer's UI responsive, independently of the servo.
        std::array<char, 65536> buffer{};
        for (int i = 0; i < 64; ++i) {
            const ssize_t size = recv(fd, buffer.data(), buffer.size(), MSG_DONTWAIT | MSG_TRUNC);
            if (size < 0) break;
            if (size >= static_cast<ssize_t>(buffer.size())) continue;
            const auto packet = QJsonDocument::fromJson(QByteArray(buffer.data(), size)).object();
            const auto payload = packet.value("payload").toObject();
            const QString type = payload.value("type").toString();
            if (type.isEmpty()) continue;
            ++packets;
            age.restart();
            latest = packet;
            if (type != "status") {
                if (type == "ready" || type == "rearmed") observation.pendingBaseline = true;
                state->setText(type == "fault" ? "FALHA: " + payload.value("message").toString()
                               : type == "disconnected" ? "Controlador desconectado; dados históricos."
                               : "Aguardando ciclos do controlador…");
                record(type, packet);
                continue;
            }
            const auto timing = payload.value("diagnostics").toObject().value("timing").toObject();
            if (!timing.value("work").isObject()) continue;
            const bool event = observation.update(packet.value("backend_pid").toInteger(), timing);
            latestTiming = timing;
            state->setText(QString("T3D v%1 • período alvo %2 ms • telemetria recebida")
                           .arg(packet.value("version").toString()).arg(timing.value("nominal_ms").toDouble()));
            totals->setText(QString("Neste ensaio: %1 ciclos • %2 estouros de trabalho • %3 ciclos perdidos\n"
                                   "Desde a conexão/rearme: %4 estouros • %5 ciclos perdidos")
                           .arg(observation.cycles).arg(observation.overruns).arg(observation.skipped)
                           .arg(timing.value("work_overruns").toInteger()).arg(timing.value("skipped_slots").toInteger()));
            totals->setStyleSheet(observation.overruns || observation.skipped ? "color: #b53c16" : "color: #16703c");
            QString table = "Último / P95 recente / máximo da sessão (ms):\n";
            for (const auto &[key, label] : std::array<std::pair<QString, QString>, 6>{{
                     {"interval", "Período observado"}, {"wake_lateness", "Atraso ao despertar"},
                     {"read", "Leitura / rede"}, {"control", "Controle / comandos"},
                     {"write", "Escrita / rede"}, {"work", "Trabalho total"}}})
                table += QString("%1: %2 / %3 / %4\n").arg(label,
                    milliseconds(timing, key, "last_ms"), milliseconds(timing, key, "p95_recent_ms"),
                    milliseconds(timing, key, "max_ms"));
            stages->setText(table.trimmed());
            if (event) record("overrun_or_skipped", packet);
        }
    });
    QTimer periodic;
    periodic.setInterval(1000);
    QObject::connect(&periodic, &QTimer::timeout, &window, [&] {
        if (age.isValid() && age.elapsed() < 1000) record("snapshot", latest);
        else state->setText("Sem telemetria atual; aguardando T3D. Valores históricos.");
    });
    periodic.start();
    window.show();
    // IPC smoke check only: no board, motor, CPU policy, or controller execution.
    TimingFeed testFeed;
    if (smoke) {
        QTimer::singleShot(0, &window, [&] {
            testFeed.publish(R"({"type":"status","diagnostics":{"timing":{"nominal_ms":1,"work":{"count":10},"work_overruns":0,"skipped_slots":0}}})", 123);
            testFeed.publish(R"({"type":"status","diagnostics":{"timing":{"nominal_ms":1,"work":{"count":12},"work_overruns":1,"skipped_slots":2}}})", 123);
        });
        QTimer::singleShot(300, &window, [&] {
            // A dropped telemetry packet must not lose accumulated overruns.
            Observation check;
            auto sample = [](qint64 cycles, qint64 work, qint64 skipped) {
                return QJsonObject{{"work", QJsonObject{{"count", cycles}}},
                                   {"work_overruns", work}, {"skipped_slots", skipped}};
            };
            check.update(1, sample(10, 2, 3));
            check.update(1, sample(30, 5, 8));
            const bool cumulative = check.cycles == 20 && check.overruns == 3 && check.skipped == 5;
            // Rearm resets counters; reconnect can change the source PID.
            check.update(1, sample(2, 0, 0));
            check.update(1, sample(5, 1, 2));
            check.update(2, sample(100, 10, 10));
            const bool reset = check.cycles == 23 && check.overruns == 4
                && check.skipped == 7 && check.segments == 3;
            log.flush();
            QFile verification(log.fileName());
            const bool recorded = verification.open(QIODevice::ReadOnly)
                && verification.readAll().contains("overrun_or_skipped");
            app.exit(packets == 2 && observation.cycles == 2 && observation.overruns == 1
                     && observation.skipped == 2 && log.isOpen() && cumulative && reset && recorded ? 0 : 1);
        });
    }
    const int result = app.exec();
    record("end", latest);
    log.close();
    ::close(fd);
    QFile::remove(socketPath);
    return result;
}
