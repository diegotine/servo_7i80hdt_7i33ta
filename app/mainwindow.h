#pragma once
#include <QMainWindow>
#include <QJsonObject>
#include <QProcess>
#include <QTimer>
#include <QElapsedTimer>
#include <array>

class QLineEdit;
class QComboBox;
class QCheckBox;
class QPushButton;
class QLabel;
class QDoubleSpinBox;
class QCloseEvent;
class QTableWidget;
class QPlainTextEdit;
class TelemetryPlot;

class MainWindow final : public QMainWindow
{
    Q_OBJECT
public:
    explicit MainWindow(QWidget *parent = nullptr);
protected:
    void closeEvent(QCloseEvent *event) override;
private:
    struct Panel {
        QLabel *position = nullptr, *rpm = nullptr, *error = nullptr, *volts = nullptr;
        std::array<QLabel *, 5> testLabels{};
        QLabel *reference = nullptr, *calibration = nullptr;
        QDoubleSpinBox *target = nullptr, *jogRpm = nullptr, *acceleration = nullptr;
        QPushButton *outputTest = nullptr;
        TelemetryPlot *plot = nullptr;
        QWidget *accelerationControl = nullptr;
        QPushButton *enable = nullptr, *move = nullptr, *zero = nullptr;
        QPushButton *cw = nullptr, *ccw = nullptr, *stop = nullptr, *settings = nullptr;
        bool enabled = false;
    };
    void setupInterface();
    void showIdentification(const QJsonObject &message);
    void logDiagnostic(const QString &message);
    void startConnection();
    void disconnectBoard();
    void send(const QJsonObject &message);
    void axisCommand(int index, const QString &operation, double value = 0);
    void receive();
    void updateStatus(const QJsonObject &message);
    void updateFaultDiagnostics(const QJsonObject &message);
    void setDisconnected();
    void configureAxis(int index);
    void applyAcceleration(int index, double value);
    void refreshConfig();
    void loadConfig();
    void saveConfig();
    void updateLoopback(const QJsonObject &message);
    void updateLoopbackControls();
    void showMessage(const QString &message, bool error = false);
    QLabel *m_diagState = nullptr, *m_diagIdentity = nullptr, *m_diagTiming = nullptr;
    QLabel *m_diagWatchdog = nullptr, *m_diagRuntime = nullptr;
    QTableWidget *m_diagModules = nullptr, *m_diagEncoders = nullptr;
    QPlainTextEdit *m_diagLog = nullptr;
    QElapsedTimer m_statusAge, m_plotClock;
    QProcess m_backend;
    QTimer m_heartbeat;
    QByteArray m_buffer;
    QJsonObject m_config;
    std::array<Panel, 4> m_panels;
    std::array<std::array<QLabel *, 12>, 2> m_inputs{};
    std::array<std::array<QPushButton *, 12>, 2> m_outputs{};
    QLineEdit *m_ip = nullptr;
    QComboBox *m_connector = nullptr;
    QLabel *m_message = nullptr, *m_link = nullptr;
    QPushButton *m_connect = nullptr, *m_disconnect = nullptr, *m_load = nullptr, *m_save = nullptr;
    QPushButton *m_loopbackButton = nullptr;
    QComboBox *m_loopbackChannel = nullptr, *m_loopbackMode = nullptr;
    QLineEdit *m_loopbackOn = nullptr, *m_loopbackOff = nullptr;
    QLabel *m_loopbackStatus = nullptr, *m_loopbackDetails = nullptr;
    QDoubleSpinBox *m_pwmPercent = nullptr;
    QPushButton *m_pwmApply = nullptr, *m_pwmStop = nullptr, *m_pwmPulse = nullptr;
    QLabel *m_pwmStatus = nullptr;
    bool m_pwmRunning = false;
    bool m_loopbackRunning = false;
    bool m_diagnosticMode = false;
    bool m_ready = false, m_stopping = false, m_closing = false;
};
