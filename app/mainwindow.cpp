#include "mainwindow.h"
#include "telemetryplot.h"
#include "ui_axissettingsdialog.h"
#include <QApplication>
#include <QCloseEvent>
#include <QComboBox>
#include <QCheckBox>
#include <QDialog>
#include <QDateTime>
#include <QHeaderView>
#include <QPlainTextEdit>
#include <QTableWidget>
#include <QDialogButtonBox>
#include <QDir>
#include <QDoubleSpinBox>
#include <QFile>
#include <QFileDialog>
#include <QFileInfo>
#include <unistd.h>
#include <QFormLayout>
#include <QGridLayout>
#include <QGroupBox>
#include <QHBoxLayout>
#include <QJsonArray>
#include <QJsonDocument>
#include <QLabel>
#include <QLineEdit>
#include <QPushButton>
#include <QSaveFile>
#include <QSignalBlocker>
#include <QStandardPaths>
#include <QTabWidget>
#include <QVBoxLayout>
#include <algorithm>
#include <sched.h>

namespace {
QString runtimePath()
{
    const QString path = QStandardPaths::writableLocation(QStandardPaths::AppConfigLocation);
    QDir().mkpath(path);
    return path + QString("/session-%1.json").arg(QCoreApplication::applicationPid());
}

bool writeJson(const QString &path, const QJsonObject &object)
{
    QSaveFile file(path);
    if (!file.open(QIODevice::WriteOnly)) return false;
    const QByteArray bytes = QJsonDocument(object).toJson();
    return file.write(bytes) == bytes.size() && file.commit();
}


}

MainWindow::MainWindow(QWidget *parent) : QMainWindow(parent)
{
    setupInterface();
    QFile defaults(QCoreApplication::applicationDirPath() + "/config.example.json");
    if (defaults.open(QIODevice::ReadOnly))
        m_config = QJsonDocument::fromJson(defaults.readAll()).object();
    connect(&m_backend, &QProcess::readyReadStandardOutput, this, &MainWindow::receive);
    connect(&m_backend, &QProcess::readyReadStandardError, this, [this] {
        const QString message = QString::fromUtf8(m_backend.readAllStandardError()).trimmed();
        if (!message.isEmpty()) showMessage(message, true);
    });
    connect(&m_backend, &QProcess::errorOccurred, this, [this](QProcess::ProcessError) {
        showMessage("Falha ao executar o controlador: " + m_backend.errorString(), true);
        setDisconnected();
    });
    connect(&m_backend, qOverload<int, QProcess::ExitStatus>(&QProcess::finished), this,
            [this](int code, QProcess::ExitStatus) {
        setDisconnected();
        if (code && !m_closing) showMessage("Sessão encerrada por falha. Confira a ligação e reconecte.", true);
        if (m_closing) close();
    });
    m_heartbeat.setInterval(100);
    connect(&m_heartbeat, &QTimer::timeout, this, [this] {
        send({{"op", "heartbeat"}});
        if (m_ready && m_statusAge.isValid() && m_statusAge.elapsed() > 500) {
            m_diagState->setText("Leituras atrasadas • aguardando controlador");
            m_diagWatchdog->setText("Watchdog e quadratura: sem confirmação atual");
            m_diagEncoders->clearContents();
        }
    });
    refreshConfig();
    setDisconnected();
    QTimer::singleShot(0, this, &MainWindow::startCpuClock);
}

MainWindow::~MainWindow()
{
    m_cpuClock.closeWriteChannel();
    if (m_cpuClock.state() != QProcess::NotRunning && !m_cpuClock.waitForFinished(1500)) {
        m_cpuClock.terminate();
        m_cpuClock.waitForFinished(1000);
    }
}

void MainWindow::startCpuClock()
{
    const auto args = QCoreApplication::arguments();
    // Screenshots and UI checks must never change system settings.
    if (args.contains("--smoke-test") || args.contains("--screenshot")) return;
    QProcess tuned;
    tuned.start("/usr/bin/systemctl", {"is-active", "--quiet", "tuned.service"});
    if (tuned.waitForFinished(1000) && tuned.exitStatus() == QProcess::NormalExit && tuned.exitCode() == 0) {
        logDiagnostic("Clock: gerenciado pelo TuneD; ajustes locais de CPU não aplicados.");
        return;
    }
    const QString requested = qEnvironmentVariable("T3D_CPU", "auto");
    if (requested == "none") return;
    cpu_set_t allowed;
    CPU_ZERO(&allowed);
    if (sched_getaffinity(0, sizeof allowed, &allowed)) {
        logDiagnostic("Clock: não foi possível determinar a CPU dedicada.");
        return;
    }
    int cpu = -1, count = 0;
    for (int i = 0; i < CPU_SETSIZE; ++i) if (CPU_ISSET(i, &allowed)) { cpu = i; ++count; }
    if (requested == "auto" && count <= 1) return;
    if (requested != "auto") {
        bool valid = false;
        cpu = requested.toInt(&valid);
        if (!valid || cpu < 0 || cpu >= CPU_SETSIZE || !CPU_ISSET(cpu, &allowed)) {
            logDiagnostic("Clock: T3D_CPU inválido; nenhum ajuste aplicado.");
            return;
        }
    }
    const QString helper = QString("/usr/local/libexec/t3d-analog-runtime-%1").arg(getuid());
    if (!QFileInfo(helper).isExecutable()) {
        logDiagnostic("Clock: instale o helper de tempo real para ajustar o governador.");
        return;
    }
    m_cpuClock.setProcessChannelMode(QProcess::MergedChannels);
    connect(&m_cpuClock, &QProcess::readyReadStandardOutput, this, [this] {
        const QString output = QString::fromUtf8(m_cpuClock.readAllStandardOutput()).trimmed();
        for (const auto &line : output.split('\n', Qt::SkipEmptyParts)) logDiagnostic("Clock: " + line);
    });
    connect(&m_cpuClock, &QProcess::errorOccurred, this, [this](QProcess::ProcessError) {
        logDiagnostic("Clock: " + m_cpuClock.errorString());
    });
    m_cpuClock.start("/usr/bin/sudo", {"-n", "--", helper, "--cpu-session", QString::number(cpu)});
}

void MainWindow::showMessage(const QString &message, bool error)
{
    m_message->setText(message);
    logDiagnostic((error ? "Falha / rejeição: " : "") + message);
    m_message->setStyleSheet(error ? "color:#ff9b82; padding:8px;" : "color:#d3c3a5; padding:8px;");
}

void MainWindow::logDiagnostic(const QString &message)
{
    m_diagLog->appendPlainText(QDateTime::currentDateTime().toString("HH:mm:ss") + " • " + message);
}

void MainWindow::showIdentification(const QJsonObject &message)
{
    const auto runtime = message.value("runtime").toObject();
    QStringList cpus;
    for (const auto &cpu : runtime.value("cpus").toArray()) cpus << QString::number(cpu.toInt());
    m_diagRuntime->setText(QString("Execução: %1 | Prioridade: %2 | CPU(s): %3 | Memória atual bloqueada: %4 | Temporizador absoluto | Controle %5")
        .arg(runtime.value("scheduler").toString("—"))
        .arg(runtime.value("priority").toInt()).arg(cpus.join(", "))
        .arg(runtime.value("memory_current_locked").toBool() ? "sim" : "não")
        .arg(runtime.value("native_servo").toBool() ? "Cython" : "Python"));
    logDiagnostic(QString("Versões: interface %1 | núcleo %2 | timer C++ %3 | estatísticas C++ %4")
        .arg(QCoreApplication::applicationVersion(), runtime.value("driver_version").toString("não informado"))
        .arg(runtime.value("native_timing").toBool() ? "sim" : "não")
        .arg(runtime.value("native_statistics").toBool() ? "sim" : "não"));
    for (const auto &warning : runtime.value("warnings").toArray()) logDiagnostic(warning.toString());
    const auto info = message.value("identification").toObject();
    const auto channels = message.value("encoder_channels").toArray();
    m_diagIdentity->setText(QString("Modelo: %1 | IP: %2 | IDROM: %3\n%4 portas × %5 sinais = %6 I/Os | Servo em P3 | P1/P2: 12 entradas + 12 saídas cada\nPDM configurado: %7 MHz | Watchdog configurado: %8 ms")
        .arg(info.value("model").toString(), info.value("ip").toString(), info.value("board").toString())
        .arg(info.value("io_ports").toInt()).arg(info.value("port_width").toInt()).arg(info.value("io_width").toInt())
        .arg(message.value("pdm_hz").toDouble() / 1e6, 0, 'f', 3).arg(message.value("watchdog_ms").toInt()));
    const auto modules = info.value("modules").toArray();
    m_diagModules->setRowCount(modules.size());
    for (int row = 0; row < modules.size(); ++row) {
        const auto module = modules[row].toObject();
        const int tag = module.value("tag").toInt();
        const QString name = tag == 2 ? "Watchdog" : tag == 3 ? "GPIO" : tag == 4 ? "Encoder" : tag == 6 ? "PWM/PDM" : QString("Tag %1").arg(tag);
        const QStringList values{name, QString::number(module.value("version").toInt()),
            QString::number(module.value("instances").toInt()),
            QString("0x%1").arg(module.value("base").toInt(), 4, 16, QChar('0')),
            QString::number(module.value("clock").toDouble() / 1e6, 'f', 1)};
        for (int col = 0; col < values.size(); ++col)
            m_diagModules->setItem(row, col, new QTableWidgetItem(values[col]));
    }
    for (int row = 0; row < 4; ++row)
        m_diagEncoders->setItem(row, 0, new QTableWidgetItem(QString("Motor %1 / %2").arg(row + 1).arg(channels.at(row).toInt())));
    m_diagState->setText("Conectado • aguardando primeira leitura cíclica");
}

void MainWindow::refreshConfig()
{
    auto normalizedAxes = m_config.value("axes").toArray();
    for (int i = 0; i < normalizedAxes.size(); ++i) {
        auto axis = normalizedAxes[i].toObject();
        axis.remove("voltage_limit");
        normalizedAxes[i] = axis;
    }
    m_config["axes"] = normalizedAxes;
    if (m_config.value("connector").toString() != "P3") {
        auto axes = m_config.value("axes").toArray();
        for (int i = 0; i < axes.size(); ++i) {
            auto axis = axes[i].toObject();
            axis["verified"] = false;  // Retain the wiring-change record without gating operation.
            axes[i] = axis;
        }
        m_config["axes"] = axes;
        m_config["connector"] = "P3";
    }
    m_ip->setText(m_config.value("ip").toString("192.168.1.121"));
    m_connector->setCurrentText("P3");
    const QJsonArray axes = m_config.value("axes").toArray();
    if (axes.size() != 4) {
        showMessage("Arquivo de configuração ausente ou inválido. Carregue config.example.json.", true);
        return;
    }
    for (int i = 0; i < 4; ++i) {
        const QJsonObject c = axes.at(i).toObject();
        Panel &p = m_panels[i];
        p.calibration->setText(QString("7i33TA • canal %1 | %2 contagens/volta | +10 V = %3 RPM horário | %4")
            .arg(i).arg(c.value("counts_per_rev").toDouble()).arg(c.value("rpm_at_10v").toDouble())
            .arg(c.value("verified").toBool() ? "Configuração conferida" : "Conferência opcional"));
        const QSignalBlocker accelerationBlocker(p.acceleration);
        p.acceleration->setValue(c.value("acceleration_rpm_s").toDouble(350));
        const QSignalBlocker decelerationBlocker(p.deceleration);
        p.deceleration->setValue(c.value("deceleration_rpm_s").toDouble(600));
        p.target->setRange(c.value("min_rev").toDouble(), c.value("max_rev").toDouble());
        p.jogRpm->setMaximum(9999.9);
    }
}

void MainWindow::startConnection()
{
    if (m_backend.state() != QProcess::NotRunning) return;
    m_config["ip"] = m_ip->text().trimmed();
    m_config["connector"] = m_connector->currentText();
    if (!writeJson(runtimePath(), m_config)) {
        showMessage("Não foi possível gravar a configuração da sessão.", true);
        return;
    }
    m_diagnosticMode = false;
    m_ready = m_stopping = false;
    m_buffer.clear();
    m_statusAge.invalidate();
    m_diagModules->setRowCount(0);
    m_diagEncoders->clearContents();
    m_diagIdentity->setText("Identificação em andamento…");
    m_diagState->setText("Conectando…");
    logDiagnostic("Conectando à HDT em " + m_ip->text().trimmed());
    m_connect->setEnabled(false);
    m_disconnect->setEnabled(true);
    m_load->setEnabled(false);
    m_save->setEnabled(true);
    m_ip->setEnabled(false);
    m_connector->setEnabled(false);
    for (auto &p : m_panels) {
        p.settings->setEnabled(false);
        p.outputTest->setEnabled(false);
        p.accelerationControl->setEnabled(false);
        p.decelerationControl->setEnabled(false);
    }
    m_link->setText("Conectando à 7i80HDT…");
    const QString runtimeLauncher = QString("/usr/local/libexec/t3d-analog-runtime-%1").arg(getuid());
    if (QFileInfo(runtimeLauncher).isExecutable()) {
        QProcess permissionCheck;
        permissionCheck.start("/usr/bin/sudo", {"-n", "-l", "--", runtimeLauncher, "--config", runtimePath()});
        const bool sudoAllowed = permissionCheck.waitForFinished(2000)
            && permissionCheck.exitStatus() == QProcess::NormalExit
            && permissionCheck.exitCode() == 0;
        if (sudoAllowed) {
            m_backend.start("/usr/bin/sudo", {"-n", "--", runtimeLauncher, "--config", runtimePath()});
        } else {
            m_backend.start(runtimeLauncher, {"--config", runtimePath()});
        }
    } else {
        m_backend.start(QStringLiteral(T3D_PYTHON), {"-u", QCoreApplication::applicationDirPath() + "/driver/run_backend.py", "--config", runtimePath()});
    }
    m_heartbeat.start();
}

void MainWindow::send(const QJsonObject &message)
{
    if (m_backend.state() != QProcess::Running) return;
    // Never accumulate movement commands behind a stopped/unresponsive process.
    if (m_backend.bytesToWrite() > 4096) {
        m_heartbeat.stop();
        m_backend.kill();
        showMessage("Controlador sem resposta; watchdog de hardware interromperá as saídas.", true);
        return;
    }
    m_backend.write(QJsonDocument(message).toJson(QJsonDocument::Compact) + '\n');
}

void MainWindow::axisCommand(int index, const QString &operation, double value)
{
    if ((!m_ready && !(m_diagnosticMode && (operation == "enable" || operation == "acceleration" || operation == "deceleration"))) || m_stopping) return;
    send({{"op", operation}, {"axis", index}, {"value", value}});
}

void MainWindow::receive()
{
    m_buffer += m_backend.readAllStandardOutput();
    while (m_buffer.contains('\n')) {
        const auto end = m_buffer.indexOf('\n');
        const QByteArray line = m_buffer.left(end);
        m_buffer.remove(0, end + 1);
        const auto message = QJsonDocument::fromJson(line).object();
        const QString type = message.value("type").toString();
        if (type == "ready") {
            m_ready = true;
            showIdentification(message);
            for (int index = 0; index < 4; ++index)
                if (m_panels[index].outputTest->isChecked())
                    send({{"op", "output_test"}, {"axis", index}, {"value", true}});
            m_link->setText("Conectado • 7i80HDT → " + m_connector->currentText() + " → 7i33TA • malha no software");
            showMessage("Conectado. Saídas desabilitadas; ENABLE mantém a posição atual.");
        } else if (type == "jog_command") {
            const double requested = message.value("requested_rpm").toDouble();
            const double effective = message.value("effective_rpm").toDouble();
            const QString result = std::abs(requested - effective) > 0.01
                ? QString("JOG: pedido %1 RPM; limitado a %2 RPM pelo limite de RPM.")
                    .arg(requested, 0, 'f', 1).arg(effective, 0, 'f', 1)
                : QString("JOG atualizado para %1 RPM, seguindo Max. Acell.").arg(effective, 0, 'f', 1);
            showMessage(QString("Motor %1 • ").arg(message.value("axis").toInt() + 1) + result);
        } else if (type == "rearmed") {
            m_diagnosticMode = false;
            m_ready = true;
            m_link->setText("Conectado • controle rearmado");
            showMessage("ENABLE rearmado. Os demais motores e saídas permanecem desligados.");
        } else if (type == "axis_config") {
            const int index = message.value("axis").toInt(-1);
            if (index >= 0 && index < 4) {
                auto axes = m_config.value("axes").toArray();
                auto config = axes[index].toObject();
                const bool fullConfig = message.value("config").isObject();
                if (fullConfig) config = message.value("config").toObject();
                else {
                    for (const auto &key : {"acceleration_rpm_s", "deceleration_rpm_s"})
                        if (message.contains(key)) config[key] = message.value(key);
                }
                axes[index] = config;
                m_config["axes"] = axes;
                if (fullConfig) {
                    refreshConfig();
                    const QString text = message.value("motor_disabled").toBool()
                        ? "Ajustes aplicados. Escala/sentido alterados: motor desabilitado; use ENABLE para retomar."
                        : "Ajustes aplicados ao motor conectado.";
                    showMessage(text);
                    logDiagnostic(QString("Motor %1 • ").arg(index + 1) + text);
                }
                else logDiagnostic(QString("Motor %1 • aceleração: %2 RPM/s | desaceleração: %3 RPM/s").arg(index + 1)
                              .arg(config.value("acceleration_rpm_s").toDouble())
                              .arg(config.value("deceleration_rpm_s").toDouble(600)));
            }
        } else if (type == "pwm_test") {
            m_pwmRunning = message.value("active").toBool();
            m_pwmStatus->setText(m_pwmRunning
                ? QString("Motor %1 • %2% • +%3 V nominal (sem medição)")
                    .arg(message.value("axis").toInt() + 1)
                    .arg(message.value("percent").toDouble(), 0, 'f', 1)
                    .arg(message.value("nominal_volts").toDouble(), 0, 'f', 2)
                : "Desligado • saída zerada; ENABLE retirado");
            updateLoopbackControls();
        } else if (type == "loopback") {
            updateLoopback(message);
        } else if (type == "status") {
            updateStatus(message);
        } else if (type == "diagnostic_status") {
            updateFaultDiagnostics(message);
        } else if (type == "diagnostic_error") {
            m_diagState->setText("Diagnóstico • placa sem resposta: " + message.value("message").toString());
            m_diagWatchdog->setText("Sem leitura atual do watchdog e da quadratura");
            m_diagEncoders->clearContents();
            for (auto &port : m_inputs)
                for (auto *label : port) label->setText("— • sem leitura atual");
            logDiagnostic("Leitura da HDT: " + message.value("message").toString());
        } else if (type == "fault" || type == "rejected") {
            showMessage(message.value("message").toString(), true);
            if (type == "rejected") {
                refreshConfig();
                updateLoopbackControls();
            }
            if (type == "fault") {
                m_ready = false;
                updateLoopbackControls();
                m_statusAge.invalidate();
                m_diagState->setText("Falha • " + message.value("message").toString());
                m_diagWatchdog->setText("Watchdog: sem confirmação atual após a falha");
                m_diagEncoders->clearContents();
                if (message.value("diagnostic_mode").toBool()) {
                    m_diagnosticMode = true;
                    m_link->setText("Conectado • diagnóstico após falha • controle interrompido");
                    m_diagTiming->setText("Controle parado • leituras de diagnóstico a cada 100 ms");
                    if (!message.value("shutdown_error").isNull())
                        logDiagnostic("Desligamento sem confirmação: " + message.value("shutdown_error").toString());
                    for (auto &panel : m_panels) {
                        panel.plot->breakTrace();
                        panel.enabled = false;
                        for (auto *button : {panel.enable, panel.move, panel.zero, panel.cw, panel.ccw, panel.stop})
                            button->setEnabled(false);
                        for (auto *button : {panel.cw, panel.ccw}) {
                            const QSignalBlocker blocker(button);
                            button->setChecked(false);
                            button->setStyleSheet("");
                        }
                        panel.enable->setStyleSheet("background:#842f26; color:white; font-weight:700;");
                        panel.accelerationControl->setEnabled(true);
                        panel.decelerationControl->setEnabled(true);
                        panel.outputTest->setEnabled(true);
                        panel.enable->setEnabled(true);
                        panel.settings->setEnabled(true);
                        panel.enable->setToolTip("Rearmar ENABLE após a falha");
                        for (auto *label : {panel.position, panel.rpm, panel.error, panel.volts, panel.reference}) label->setText("—");
                    }
                    for (auto &port : m_outputs)
                        for (auto *button : port) {
                            button->setEnabled(false);
                            button->setChecked(false);
                            button->setStyleSheet("");
                            button->setText("Sem comando • diagnóstico");
                        }
                }
            }
        }
    }
}

void MainWindow::updateFaultDiagnostics(const QJsonObject &message)
{
    m_statusAge.restart();
    m_diagState->setText("Conectado • diagnóstico após falha • leitura atual");
    const auto counts = message.value("raw_counts").toArray();
    const auto errors = message.value("quadrature_errors").toArray();
    QStringList encoderErrors;
    for (int row = 0; row < counts.size(); ++row) {
        m_diagEncoders->setItem(row, 0, new QTableWidgetItem(QString("Motor %1").arg(row + 1)));
        m_diagEncoders->setItem(row, 1, new QTableWidgetItem(QString::number(counts[row].toInt())));
        for (int col : {2, 3}) m_diagEncoders->setItem(row, col, new QTableWidgetItem("—"));
        m_diagEncoders->setItem(row, 4, new QTableWidgetItem("Máscara HM2: " + QString::number(message.value("enable_mask").toInt(), 16)));
        if (errors[row].toBool()) encoderErrors.append(QString::number(row + 1));
    }
    m_diagWatchdog->setText(QString("Watchdog: %1 | Erro de quadratura: %2")
        .arg(message.value("watchdog_expired").toBool() ? "expirado (diagnóstico não o alimenta)" : "sem expiração lida")
        .arg(encoderErrors.isEmpty() ? "nenhum" : "motor(es) " + encoderErrors.join(", ")));
    const auto gpio = message.value("gpio").toObject();
    for (int port = 0; port < 2; ++port) {
        const auto state = gpio.value(QString("P%1").arg(port + 1)).toObject();
        for (int channel = 0; channel < 12; ++channel)
            m_inputs[port][channel]->setText(QString("IN%1 • pino %2\n%3").arg(channel + 1).arg(channel * 2 + 1)
                .arg(state.value("levels").toInt() & (1 << channel) ? "Alto" : "Baixo"));
    }
}

void MainWindow::updateStatus(const QJsonObject &message)
{
    const auto diagnostic = message.value("diagnostics").toObject();
    const auto rawCounts = diagnostic.value("raw_counts").toArray();
    m_statusAge.restart();
    m_diagState->setText("Conectado • leituras atuais");
    m_diagTiming->setText(QString("Ciclo: %1 ms | Maior ciclo: %2 ms | Ciclos concluídos: %3 | Alvo: %4 ms | Limite: 20 ms")
        .arg(message.value("cycle_ms").toDouble(), 0, 'f', 2)
        .arg(diagnostic.value("max_cycle_ms").toDouble(), 0, 'f', 2)
        .arg(diagnostic.value("cycles").toDouble(), 0, 'f', 0)
        .arg(diagnostic.value("timing").toObject().value("nominal_ms").toDouble(2), 0, 'f', 0));
    const auto timing = diagnostic.value("timing").toObject();
    if (!timing.isEmpty()) {
        const auto interval = timing.value("interval").toObject();
        const auto wake = timing.value("wake_lateness").toObject();
        const auto read = timing.value("read").toObject();
        const auto control = timing.value("control").toObject();
        const auto write = timing.value("write").toObject();
        const auto work = timing.value("work").toObject();
        m_diagTiming->setText(m_diagTiming->text()
            + QString("\nCiclo médio: %1 ms | Desvio: %2 ms | P95 recente: %3 ms | Horários pulados: %4")
                .arg(interval.value("mean_ms").toDouble(), 0, 'f', 3)
                .arg(interval.value("stddev_ms").toDouble(), 0, 'f', 3)
                .arg(interval.value("p95_recent_ms").toDouble(), 0, 'f', 3)
                .arg(timing.value("skipped_slots").toDouble(), 0, 'f', 0)
            + QString("\nDespertar (máx.): %1 ms | Leitura (média): %2 ms | Cálculo/comandos (média): %3 ms | Escrita (média): %4 ms")
                .arg(wake.value("max_ms").toDouble(), 0, 'f', 3)
                .arg(read.value("mean_ms").toDouble(), 0, 'f', 3)
                .arg(control.value("mean_ms").toDouble(), 0, 'f', 3)
                .arg(write.value("mean_ms").toDouble(), 0, 'f', 3)
            + QString("\nTrabalho máximo: %1 ms | Execuções acima de %2 ms: %3")
                .arg(work.value("max_ms").toDouble(), 0, 'f', 3)
                .arg(timing.value("nominal_ms").toDouble(2), 0, 'f', 0)
                .arg(timing.value("work_overruns").toDouble(), 0, 'f', 0));
    }
    m_diagWatchdog->setText(diagnostic.value("watchdog_ok").toBool()
        ? "Watchdog: sem expiração na última leitura e confirmação das saídas | Quadratura: sem erro detectado"
        : "Watchdog: sem confirmação atual");
    const auto diagnosticAxes = message.value("axes").toArray();
    for (int row = 0; row < std::min(4, int(diagnosticAxes.size())); ++row) {
        const auto axis = diagnosticAxes[row].toObject();
        const QStringList values{row < rawCounts.size() ? QString::number(rawCounts[row].toInt()) : "—",
            QString::number(axis.value("encoder_position").toDouble(axis.value("position").toDouble()), 'f', 5),
            QString::number(axis.value("volts").toDouble(), 'f', 4),
            axis.value("enabled").toBool() ? "Ligado" : "Desligado"};
        for (int col = 0; col < values.size(); ++col)
            m_diagEncoders->setItem(row, col + 1, new QTableWidgetItem(values[col]));
    }
    const auto io = message.value("io").toObject();
    for (int port = 0; port < 2; ++port) {
        const auto state = io.value(QString("P%1").arg(port + 1)).toObject();
        const bool valid = state.contains("inputs") && state.contains("outputs");
        const int inputs = state.value("inputs").toInt(), outputs = state.value("outputs").toInt();
        for (int channel = 0; channel < 12; ++channel) {
            auto *input = m_inputs[port][channel];
            input->setText(QString("IN%1 • pino %2\n%3").arg(channel + 1).arg(channel * 2 + 1)
                           .arg(!valid ? "—" : inputs & (1 << channel) ? "Alto" : "Baixo"));
            auto *output = m_outputs[port][channel];
            const QSignalBlocker blocker(output);
            const bool on = valid && (outputs & (1 << channel));
            output->setChecked(on);
            output->setText(QString("OUT%1 • pino %2\n%3").arg(channel + 1).arg(channel * 2 + 25)
                            .arg(!valid ? "—" : on ? "Ligada" : "Desligada"));
            output->setStyleSheet(on ? "background:#276445; color:white;" : "");
            output->setEnabled(valid && m_ready && !m_stopping && !m_loopbackRunning && !m_pwmRunning);
        }
    }
    const QJsonArray axes = message.value("axes").toArray();
    const QJsonArray configs = m_config.value("axes").toArray();
    for (int i = 0; i < std::min(4, int(axes.size())); ++i) {
        Panel &p = m_panels[i];
        const auto a = axes[i].toObject();
        const auto c = configs[i].toObject();
        p.enabled = a.value("enabled").toBool();
        const bool hold = a.value("mode").toString() == "hold";
        const bool settled = a.value("in_position").toBool();
        p.position->setText(QString::number(a.value("position").toDouble(), 'f', 5));
        p.rpm->setText(QString::number(a.value("rpm").toDouble(), 'f', 1));
        p.error->setText(QString::number(a.value("error").toDouble() * c.value("counts_per_rev").toDouble(), 'f', 1));
        p.volts->setText(QString::number(a.value("volts").toDouble(), 'f', 3));
        p.reference->setText(QString::number(a.value("target").toDouble(), 'f', 5));
        p.plot->append(m_plotClock.elapsed() / 1000.0, a.value("target").toDouble(),
                       a.value("encoder_position").toDouble());
        p.enable->setStyleSheet(p.enabled ? "background:#276445; color:white; font-weight:700;"
                                           : "background:#842f26; color:white; font-weight:700;");
        p.enable->setToolTip(p.enabled ? "Retirar ENABLE" : "Ativar ENABLE e manter posição");
        const bool accelerationEditable = m_ready && !m_stopping && !m_loopbackRunning && !m_pwmRunning;
        p.accelerationControl->setEnabled(accelerationEditable);
        p.decelerationControl->setEnabled(accelerationEditable);
        p.settings->setEnabled(accelerationEditable);
        const bool live = m_ready && !m_stopping && !m_loopbackRunning && !m_pwmRunning;
        p.enable->setEnabled(live);
        const bool outputTest = a.value("output_test").toBool();
        for (auto *label : p.testLabels) label->setText(outputTest ? "MODO TESTE" : "");
        p.position->setToolTip(outputTest ? QString("Encoder real: %1 voltas").arg(a.value("encoder_position").toDouble(), 0, 'f', 5) : "Posição do encoder real");
        p.rpm->setToolTip(outputTest ? QString("Encoder real: %1 RPM").arg(a.value("encoder_rpm").toDouble(), 0, 'f', 1) : "Velocidade medida pelo encoder");
        {
            const QSignalBlocker blocker(p.outputTest);
            p.outputTest->setChecked(outputTest);
        }
        p.outputTest->setEnabled(live);
        p.move->setEnabled(live && p.enabled && hold && settled);
        const bool jog = a.value("mode").toString() == "jog";
        for (auto *button : {p.cw, p.ccw}) {
            const QSignalBlocker blocker(button);
            const bool selected = jog && (button == p.cw ? a.value("jog_rpm").toDouble() > 0 : a.value("jog_rpm").toDouble() < 0);
            button->setChecked(selected);
            button->setStyleSheet(selected ? "background:#276445; color:white; font-weight:700;" : "");
        }
        p.cw->setEnabled(live && p.enabled && (hold || jog));
        p.ccw->setEnabled(live && p.enabled && (hold || jog));
        p.zero->setEnabled(live && !p.enabled);
        p.stop->setEnabled(live);
    }
    updateLoopbackControls();
}

void MainWindow::disconnectBoard()
{
    if (m_backend.state() == QProcess::NotRunning) return;
    m_stopping = true;
    m_disconnect->setEnabled(false);
    send({{"op", "quit"}});
    m_heartbeat.stop();
    // EOF also requests shutdown. Never wait synchronously in the GUI.
    m_backend.closeWriteChannel();
    QTimer::singleShot(1500, this, [this] {
        if (m_stopping && m_backend.state() != QProcess::NotRunning) m_backend.kill();
    });
}

void MainWindow::setDisconnected()
{
    if (m_loopbackRunning)
        m_loopbackStatus->setText("Loopback interrompido pela desconexão; resultado incompleto.");
    m_loopbackRunning = false;
    m_pwmRunning = false;
    m_pwmStatus->setText("Desconectado • sem confirmação atual da saída");
    for (int port = 0; port < 2; ++port) {
        for (int channel = 0; channel < 12; ++channel) {
            m_inputs[port][channel]->setText(QString("IN%1 • pino %2\n—").arg(channel + 1).arg(channel * 2 + 1));
            auto *output = m_outputs[port][channel];
            output->setEnabled(false);
            output->setChecked(false);
            output->setStyleSheet("");
            output->setText(QString("OUT%1 • pino %2\n—").arg(channel + 1).arg(channel * 2 + 25));
        }
    }
    m_diagnosticMode = false;
    m_ready = m_stopping = false;
    updateLoopbackControls();
    m_statusAge.invalidate();
    m_diagState->setText("Desconectado • sem leitura atual");
    m_diagRuntime->setText("Execução: sem sessão ativa.");
    m_diagTiming->setText("Ciclo: — | Maior ciclo: — | Ciclos concluídos: —");
    m_diagWatchdog->setText("Watchdog e quadratura: sem leitura atual");
    m_diagEncoders->clearContents();
    if (m_diagModules->rowCount())
        m_diagIdentity->setText("Última identificação (histórica, placa desconectada):\n" + m_diagIdentity->text());
    m_heartbeat.stop();
    m_link->setText("Desconectado • ENABLE desligado");
    m_connect->setEnabled(true);
    m_disconnect->setEnabled(false);
    m_load->setEnabled(true);
    m_save->setEnabled(true);
    m_ip->setEnabled(true);
    m_connector->setEnabled(true);
    for (auto &p : m_panels) {
        p.plot->breakTrace();
        p.enabled = false;
        for (auto *label : p.testLabels) label->setText("");
        p.outputTest->setEnabled(true);
        { const QSignalBlocker blocker(p.outputTest); p.outputTest->setChecked(false); }
        for (auto *button : {p.cw, p.ccw}) {
            const QSignalBlocker blocker(button);
            button->setChecked(false);
            button->setStyleSheet("");
        }
        for (auto *button : {p.enable, p.move, p.zero, p.cw, p.ccw, p.stop}) button->setEnabled(false);
        p.settings->setEnabled(true);
        for (auto *label : {p.position, p.rpm, p.error, p.volts, p.reference}) label->setText("—");
        p.enable->setStyleSheet("background:#842f26; color:white; font-weight:700;");
        p.enable->setToolTip("Ativar ENABLE e manter posição");
        p.accelerationControl->setEnabled(true);
        p.decelerationControl->setEnabled(true);
    }
}

void MainWindow::applyAcceleration(int index, double value, bool deceleration)
{
    if (m_backend.state() != QProcess::NotRunning) {
        axisCommand(index, deceleration ? "deceleration" : "acceleration", value);
        return;
    }
    auto axes = m_config.value("axes").toArray();
    auto config = axes[index].toObject();
    config[deceleration ? "deceleration_rpm_s" : "acceleration_rpm_s"] = value;
    axes[index] = config;
    m_config["axes"] = axes;
}

void MainWindow::configureAxis(int index)
{
    if (m_stopping || (m_backend.state() != QProcess::NotRunning && !m_ready && !m_diagnosticMode)) return;
    auto axes = m_config.value("axes").toArray();
    if (axes.size() != 4) return;
    auto config = axes[index].toObject();
    QDialog dialog(this);
    dialog.setWindowTitle(QString("Motor %1 — calibração e malha de posição").arg(index + 1));
    Ui::AxisSettingsDialog ui;
    ui.setupUi(&dialog);
    if (!config.contains("deceleration_rpm_s")) config["deceleration_rpm_s"] = 600;
    const QStringList fields{"counts_per_rev", "rpm_at_10v", "max_rpm", "acceleration_rpm_s", "deceleration_rpm_s", "kp", "ki", "kd", "ff1", "following_error_rev", "tolerance_counts", "no_response_timeout_s", "min_rev", "max_rev"};
    const QVector<QDoubleSpinBox *> editors{ui.counts_per_rev, ui.rpm_at_10v, ui.max_rpm, ui.acceleration_rpm_s, ui.deceleration_rpm_s, ui.kp, ui.ki, ui.kd, ui.ff1, ui.following_error_rev, ui.tolerance_counts, ui.no_response_timeout_s, ui.min_rev, ui.max_rev};
    for (int i = 0; i < editors.size(); ++i)
        editors[i]->setValue(config.value(fields[i]).toDouble(fields[i] == "no_response_timeout_s" ? 0.5 : 0.0));
    auto *encoderSign = ui.encoderSign;
    auto *outputSign = ui.outputSign;
    auto *verified = ui.verified;
    encoderSign->setCurrentIndex(config.value("encoder_sign").toInt() == -1 ? 1 : 0);
    outputSign->setCurrentIndex(config.value("output_sign").toInt() == -1 ? 1 : 0);
    verified->setChecked(config.value("verified").toBool());
    if (dialog.exec() != QDialog::Accepted) return;
    for (int i = 0; i < int(editors.size()); ++i) config[fields[i]] = editors[i]->value();
    config["encoder_sign"] = encoderSign->currentIndex() ? -1 : 1;
    config["output_sign"] = outputSign->currentIndex() ? -1 : 1;
    config["verified"] = verified->isChecked();
    if (m_backend.state() != QProcess::NotRunning) {
        if ((!m_ready && !m_diagnosticMode) || m_stopping) return;
        send({{"op", "configure"}, {"axis", index}, {"config", config}});
        showMessage("Aplicando ajustes ao motor conectado…");
        return;
    }
    axes[index] = config;
    m_config["axes"] = axes;
    refreshConfig();
    showMessage("Ajustes aplicados. Salve a configuração para reutilizar.");
}

void MainWindow::loadConfig()
{
    const QString path = QFileDialog::getOpenFileName(this, "Carregar configuração", {}, "JSON (*.json)");
    if (path.isEmpty()) return;
    QFile file(path);
    if (!file.open(QIODevice::ReadOnly)) { showMessage(file.errorString(), true); return; }
    const auto config = QJsonDocument::fromJson(file.readAll()).object();
    if (config.value("schema").toInt() != 1 || config.value("axes").toArray().size() != 4) {
        showMessage("Configuração inválida: esperados quatro canais e schema 1.", true);
        return;
    }
    m_config = config;
    refreshConfig();
    showMessage("Configuração carregada. O controlador validará escalas e limites ao conectar.");
}

void MainWindow::saveConfig()
{
    m_config["ip"] = m_ip->text().trimmed();
    m_config["connector"] = m_connector->currentText();
    const QString path = QFileDialog::getSaveFileName(this, "Salvar configuração", "config.local.json", "JSON (*.json)");
    if (path.isEmpty()) return;
    showMessage(writeJson(path, m_config) ? "Configuração salva." : "Falha ao salvar configuração.");
}

void MainWindow::closeEvent(QCloseEvent *event)
{
    if (m_backend.state() != QProcess::NotRunning) {
        m_closing = true;
        disconnectBoard();
        event->ignore();
        return;
    }
    event->accept();
}

void MainWindow::updateLoopbackControls()
{
    const bool disabled = std::none_of(m_panels.begin(), m_panels.end(), [](const Panel &p) { return p.enabled; });
    m_loopbackButton->setEnabled(m_ready && !m_stopping && (m_loopbackRunning || (disabled && !m_pwmRunning)));
    m_loopbackButton->setText(m_loopbackRunning ? "Cancelar loopback" : "Loopback");
    m_loopbackButton->setToolTip(disabled ? "Medir 100 ciclos da saída selecionada para encoder A" : "Desabilite os quatro motores antes de iniciar");
    m_loopbackChannel->setEnabled(!m_loopbackRunning && !m_pwmRunning);
    m_loopbackMode->setEnabled(!m_loopbackRunning && !m_pwmRunning);
    m_pwmApply->setEnabled(m_ready && !m_stopping && !m_loopbackRunning && disabled);
    m_pwmStop->setEnabled(m_ready && !m_stopping && m_pwmRunning);
    m_pwmPulse->setEnabled(m_ready && !m_stopping && !m_loopbackRunning && !m_pwmRunning && disabled);
    m_pwmPercent->setEnabled(!m_loopbackRunning);
}

void MainWindow::updateLoopback(const QJsonObject &message)
{
    m_loopbackRunning = message.value("active").toBool();
    const int completed = message.value("completed").toInt();
    const int total = message.value("repetitions").toInt();
    const QString error = message.value("error").toString();
    const bool valid = !m_loopbackRunning && !m_pwmRunning && error.isEmpty() && completed == total && total == 100;
    m_loopbackStatus->setText(m_loopbackRunning && message.value("phase").toString() == "baseline"
        ? QString("Motor %1 • aguardando entrada A em zero por 50 ms; saída ainda em zero.")
            .arg(message.value("axis").toInt() + 1)
        : m_loopbackRunning
        ? QString("Motor %1 • %2/%3 ciclos • medindo ON e OFF…")
            .arg(message.value("axis").toInt() + 1).arg(completed).arg(total)
        : valid ? "Concluído: 100 ciclos; última borda OFF recebida; ENABLE desligado."
                : "Teste incompleto: " + error);
    if (valid) {
        const auto on = message.value("on").toObject();
        const auto off = message.value("off").toObject();
        m_loopbackOn->setText(QString::number(on.value("mean_ms").toDouble(), 'f', 3));
        m_loopbackOff->setText(QString::number(off.value("mean_ms").toDouble(), 'f', 3));
        const auto describe = [](const QString &name, const QJsonObject &value) {
            return QString("%1: mín. %2 ms | máx. %3 ms | P95 %4 ms | desvio padrão %5 ms")
                .arg(name).arg(value.value("min_ms").toDouble(), 0, 'f', 3)
                .arg(value.value("max_ms").toDouble(), 0, 'f', 3)
                .arg(value.value("p95_ms").toDouble(), 0, 'f', 3)
                .arg(value.value("stddev_ms").toDouble(), 0, 'f', 3);
        };
        m_loopbackDetails->setText(describe("ON", on) + "\n" + describe("OFF", off)
            + QString("\nTempos observados pelo computador, incluindo a espera pela leitura de %1 ms. PID permanece inalterado.")
                .arg(message.value("timing").toObject().value("nominal_ms").toDouble(2), 0, 'f', 0));
        logDiagnostic("Loopback concluído: ON " + m_loopbackOn->text() + " ms; OFF " + m_loopbackOff->text() + " ms.");
        const QString directory = QStandardPaths::writableLocation(QStandardPaths::AppDataLocation) + "/loopback";
        QDir().mkpath(directory);
        const QString path = directory + "/loopback-" + QDateTime::currentDateTimeUtc().toString("yyyyMMdd-HHmmss-zzz") + ".json";
        auto record = message;
        record["application_version"] = QCoreApplication::applicationVersion();
        record["recorded_at_utc"] = QDateTime::currentDateTimeUtc().toString(Qt::ISODateWithMs);
        record["measurement"] = message.value("mode").toString() == "analog"
            ? "analog_0_4v_to_encoder_a_ttl_host_observed"
            : "digital_ena_to_encoder_a_ttl_host_observed";
        record["nominal_poll_ms"] = message.value("timing").toObject().value("nominal_ms").toDouble(2);
        if (writeJson(path, record)) {
            m_loopbackDetails->setText(m_loopbackDetails->text() + "\nResultado salvo: " + path);
            logDiagnostic("Amostras do loopback salvas em " + path);
        } else {
            logDiagnostic("Não foi possível salvar as amostras do loopback em " + path);
        }
    } else if (!m_loopbackRunning && !m_pwmRunning) {
        m_loopbackOn->setText("—");
        m_loopbackOff->setText("—");
        m_loopbackDetails->setText("Sem média válida de 100 ciclos. Confira a ligação e o histórico de diagnóstico.");
        logDiagnostic("Loopback interrompido: " + error);
    }
    updateLoopbackControls();
}
