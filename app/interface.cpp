#include "mainwindow.h"
#include "ui_mainwindow.h"
#include "telemetryplot.h"
#include <QStackedWidget>
#include <QDialog>
#include <QDialogButtonBox>
#include <QFile>
#include <QTextBrowser>
#include <QVBoxLayout>
#include <QCheckBox>
#include <algorithm>
#include <QComboBox>
#include <QDoubleSpinBox>
#include <QGridLayout>
#include <QHeaderView>
#include <QJsonArray>
#include <QLabel>
#include <QLineEdit>
#include <QPlainTextEdit>
#include <QPushButton>
#include <QSignalBlocker>
#include <QTabWidget>
#include <QTableWidget>

void MainWindow::setupInterface()
{
    Ui::MainWindow ui;
    ui.setupUi(this);
    m_ip = ui.ip;
    m_connector = ui.connector;
    m_message = ui.message;
    m_link = ui.link;
    m_connect = ui.connect;
    m_disconnect = ui.disconnect;
    m_load = ui.load;
    m_save = ui.save;
    m_loopbackButton = ui.loopbackButton;
    m_loopbackChannel = ui.loopbackChannel;
    m_loopbackMode = ui.loopbackMode;
    m_pwmPercent = ui.pwmPercent;
    m_pwmApply = ui.pwmApply;
    m_pwmStop = ui.pwmStop;
    m_pwmPulse = ui.pwmPulse;
    connect(m_pwmPulse, &QPushButton::clicked, this, [this] {
        if (m_ready && !m_stopping && !m_loopbackRunning)
            send({{"op", "pwm_test_pulse"}, {"axis", m_loopbackChannel->currentIndex()}});
    });
    m_pwmStatus = ui.pwmStatus;
    connect(m_pwmApply, &QPushButton::clicked, this, [this] {
        if (m_ready && !m_stopping && !m_loopbackRunning)
            send({{"op", "pwm_test_set"}, {"axis", m_loopbackChannel->currentIndex()}, {"percent", m_pwmPercent->value()}});
    });
    connect(m_pwmStop, &QPushButton::clicked, this, [this] {
        if (m_ready) send({{"op", "pwm_test_stop"}});
    });
    m_loopbackOn = ui.loopbackOn;
    m_loopbackOff = ui.loopbackOff;
    m_loopbackStatus = ui.loopbackStatus;
    m_loopbackDetails = ui.loopbackDetails;
    connect(m_loopbackButton, &QPushButton::clicked, this, [this] {
        if (!m_ready || m_stopping) return;
        if (m_loopbackRunning) {
            send({{"op", "loopback_stop"}});
            m_loopbackStatus->setText("Cancelando; aguardando confirmação da saída desligada…");
        } else {
            m_loopbackOn->setText("—");
            m_loopbackOff->setText("—");
            m_loopbackDetails->setText("Aguardando retorno real da entrada A em modo TTL.");
            m_loopbackStatus->setText("Iniciando loopback…");
            send({{"op", "loopback_start"}, {"axis", m_loopbackChannel->currentIndex()},
                  {"mode", m_loopbackMode->currentIndex() == 1 ? "analog" : "digital"}});
        }
        m_loopbackButton->setEnabled(false);
    });
    connect(ui.loopbackHelp, &QPushButton::clicked, this, [this] {
        QDialog dialog(this);
        dialog.setWindowTitle("Loopback — ligação e medição de latência");
        dialog.resize(820, 650);
        auto *layout = new QVBoxLayout(&dialog);
        auto *text = new QTextBrowser(&dialog);
        QFile help(QCoreApplication::applicationDirPath() + "/TESTE_LOOPBACK.md");
        if (help.open(QIODevice::ReadOnly)) text->setMarkdown(QString::fromUtf8(help.readAll()));
        else text->setPlainText("Instruções não encontradas. Confira TESTE_LOOPBACK.md na pasta do projeto antes de ligar o fio.");
        layout->addWidget(text);
        auto *buttons = new QDialogButtonBox(QDialogButtonBox::Close, &dialog);
        connect(buttons, &QDialogButtonBox::rejected, &dialog, &QDialog::reject);
        layout->addWidget(buttons);
        dialog.exec();
    });
    m_plotClock.start();
    connect(ui.tabs, &QTabWidget::currentChanged, ui.motorTools, [tools = ui.motorTools](int index) {
        tools->setCurrentIndex(std::clamp(index, 0, 3));
        tools->setEnabled(index < 4);
    });
    m_diagState = ui.diagState;
    m_diagIdentity = ui.diagIdentity;
    m_diagTiming = ui.diagTiming;
    m_diagWatchdog = ui.diagWatchdog;
    m_diagModules = ui.diagModules;
    m_diagEncoders = ui.diagEncoders;
    m_diagLog = ui.diagLog;
    m_panels[0].position = ui.position0;
    m_panels[0].rpm = ui.rpm0;
    m_panels[0].error = ui.error0;
    m_panels[0].volts = ui.volts0;
    m_panels[0].reference = ui.reference0;
    m_panels[0].calibration = ui.calibration0;
    m_panels[0].target = ui.target0;
    m_panels[0].jogRpm = ui.jogRpm0;
    m_panels[0].acceleration = ui.acceleration0;
    m_panels[0].accelerationControl = ui.accelerationControl0;
    m_panels[0].outputTest = ui.outputTest0;
    m_panels[0].plot = ui.plot0;
    m_panels[0].enable = ui.enable0;
    m_panels[0].move = ui.move0;
    m_panels[0].zero = ui.zero0;
    m_panels[0].cw = ui.cw0;
    m_panels[0].ccw = ui.ccw0;
    m_panels[0].stop = ui.stop0;
    m_panels[0].settings = ui.settings0;
    m_panels[0].testLabels = {ui.testLabel0_0, ui.testLabel0_1, ui.testLabel0_2, ui.testLabel0_3, ui.testLabel0_4};
    connect(ui.target0Plus, &QPushButton::clicked, ui.target0, &QDoubleSpinBox::stepUp);
    connect(ui.target0Minus, &QPushButton::clicked, ui.target0, &QDoubleSpinBox::stepDown);
    connect(ui.jogRpm0Plus, &QPushButton::clicked, ui.jogRpm0, &QDoubleSpinBox::stepUp);
    connect(ui.jogRpm0Minus, &QPushButton::clicked, ui.jogRpm0, &QDoubleSpinBox::stepDown);
    connect(ui.acceleration0Plus, &QPushButton::clicked, ui.acceleration0, &QDoubleSpinBox::stepUp);
    connect(ui.acceleration0Minus, &QPushButton::clicked, ui.acceleration0, &QDoubleSpinBox::stepDown);
    m_panels[1].position = ui.position1;
    m_panels[1].rpm = ui.rpm1;
    m_panels[1].error = ui.error1;
    m_panels[1].volts = ui.volts1;
    m_panels[1].reference = ui.reference1;
    m_panels[1].calibration = ui.calibration1;
    m_panels[1].target = ui.target1;
    m_panels[1].jogRpm = ui.jogRpm1;
    m_panels[1].acceleration = ui.acceleration1;
    m_panels[1].accelerationControl = ui.accelerationControl1;
    m_panels[1].outputTest = ui.outputTest1;
    m_panels[1].plot = ui.plot1;
    m_panels[1].enable = ui.enable1;
    m_panels[1].move = ui.move1;
    m_panels[1].zero = ui.zero1;
    m_panels[1].cw = ui.cw1;
    m_panels[1].ccw = ui.ccw1;
    m_panels[1].stop = ui.stop1;
    m_panels[1].settings = ui.settings1;
    m_panels[1].testLabels = {ui.testLabel1_0, ui.testLabel1_1, ui.testLabel1_2, ui.testLabel1_3, ui.testLabel1_4};
    connect(ui.target1Plus, &QPushButton::clicked, ui.target1, &QDoubleSpinBox::stepUp);
    connect(ui.target1Minus, &QPushButton::clicked, ui.target1, &QDoubleSpinBox::stepDown);
    connect(ui.jogRpm1Plus, &QPushButton::clicked, ui.jogRpm1, &QDoubleSpinBox::stepUp);
    connect(ui.jogRpm1Minus, &QPushButton::clicked, ui.jogRpm1, &QDoubleSpinBox::stepDown);
    connect(ui.acceleration1Plus, &QPushButton::clicked, ui.acceleration1, &QDoubleSpinBox::stepUp);
    connect(ui.acceleration1Minus, &QPushButton::clicked, ui.acceleration1, &QDoubleSpinBox::stepDown);
    m_panels[2].position = ui.position2;
    m_panels[2].rpm = ui.rpm2;
    m_panels[2].error = ui.error2;
    m_panels[2].volts = ui.volts2;
    m_panels[2].reference = ui.reference2;
    m_panels[2].calibration = ui.calibration2;
    m_panels[2].target = ui.target2;
    m_panels[2].jogRpm = ui.jogRpm2;
    m_panels[2].acceleration = ui.acceleration2;
    m_panels[2].accelerationControl = ui.accelerationControl2;
    m_panels[2].outputTest = ui.outputTest2;
    m_panels[2].plot = ui.plot2;
    m_panels[2].enable = ui.enable2;
    m_panels[2].move = ui.move2;
    m_panels[2].zero = ui.zero2;
    m_panels[2].cw = ui.cw2;
    m_panels[2].ccw = ui.ccw2;
    m_panels[2].stop = ui.stop2;
    m_panels[2].settings = ui.settings2;
    m_panels[2].testLabels = {ui.testLabel2_0, ui.testLabel2_1, ui.testLabel2_2, ui.testLabel2_3, ui.testLabel2_4};
    connect(ui.target2Plus, &QPushButton::clicked, ui.target2, &QDoubleSpinBox::stepUp);
    connect(ui.target2Minus, &QPushButton::clicked, ui.target2, &QDoubleSpinBox::stepDown);
    connect(ui.jogRpm2Plus, &QPushButton::clicked, ui.jogRpm2, &QDoubleSpinBox::stepUp);
    connect(ui.jogRpm2Minus, &QPushButton::clicked, ui.jogRpm2, &QDoubleSpinBox::stepDown);
    connect(ui.acceleration2Plus, &QPushButton::clicked, ui.acceleration2, &QDoubleSpinBox::stepUp);
    connect(ui.acceleration2Minus, &QPushButton::clicked, ui.acceleration2, &QDoubleSpinBox::stepDown);
    m_panels[3].position = ui.position3;
    m_panels[3].rpm = ui.rpm3;
    m_panels[3].error = ui.error3;
    m_panels[3].volts = ui.volts3;
    m_panels[3].reference = ui.reference3;
    m_panels[3].calibration = ui.calibration3;
    m_panels[3].target = ui.target3;
    m_panels[3].jogRpm = ui.jogRpm3;
    m_panels[3].acceleration = ui.acceleration3;
    m_panels[3].accelerationControl = ui.accelerationControl3;
    m_panels[3].outputTest = ui.outputTest3;
    m_panels[3].plot = ui.plot3;
    m_panels[3].enable = ui.enable3;
    m_panels[3].move = ui.move3;
    m_panels[3].zero = ui.zero3;
    m_panels[3].cw = ui.cw3;
    m_panels[3].ccw = ui.ccw3;
    m_panels[3].stop = ui.stop3;
    m_panels[3].settings = ui.settings3;
    m_panels[3].testLabels = {ui.testLabel3_0, ui.testLabel3_1, ui.testLabel3_2, ui.testLabel3_3, ui.testLabel3_4};
    connect(ui.target3Plus, &QPushButton::clicked, ui.target3, &QDoubleSpinBox::stepUp);
    connect(ui.target3Minus, &QPushButton::clicked, ui.target3, &QDoubleSpinBox::stepDown);
    connect(ui.jogRpm3Plus, &QPushButton::clicked, ui.jogRpm3, &QDoubleSpinBox::stepUp);
    connect(ui.jogRpm3Minus, &QPushButton::clicked, ui.jogRpm3, &QDoubleSpinBox::stepDown);
    connect(ui.acceleration3Plus, &QPushButton::clicked, ui.acceleration3, &QDoubleSpinBox::stepUp);
    connect(ui.acceleration3Minus, &QPushButton::clicked, ui.acceleration3, &QDoubleSpinBox::stepDown);
    m_inputs[0][0] = ui.input0_0;
    m_outputs[0][0] = ui.output0_0;
    m_inputs[0][1] = ui.input0_1;
    m_outputs[0][1] = ui.output0_1;
    m_inputs[0][2] = ui.input0_2;
    m_outputs[0][2] = ui.output0_2;
    m_inputs[0][3] = ui.input0_3;
    m_outputs[0][3] = ui.output0_3;
    m_inputs[0][4] = ui.input0_4;
    m_outputs[0][4] = ui.output0_4;
    m_inputs[0][5] = ui.input0_5;
    m_outputs[0][5] = ui.output0_5;
    m_inputs[0][6] = ui.input0_6;
    m_outputs[0][6] = ui.output0_6;
    m_inputs[0][7] = ui.input0_7;
    m_outputs[0][7] = ui.output0_7;
    m_inputs[0][8] = ui.input0_8;
    m_outputs[0][8] = ui.output0_8;
    m_inputs[0][9] = ui.input0_9;
    m_outputs[0][9] = ui.output0_9;
    m_inputs[0][10] = ui.input0_10;
    m_outputs[0][10] = ui.output0_10;
    m_inputs[0][11] = ui.input0_11;
    m_outputs[0][11] = ui.output0_11;
    m_inputs[1][0] = ui.input1_0;
    m_outputs[1][0] = ui.output1_0;
    m_inputs[1][1] = ui.input1_1;
    m_outputs[1][1] = ui.output1_1;
    m_inputs[1][2] = ui.input1_2;
    m_outputs[1][2] = ui.output1_2;
    m_inputs[1][3] = ui.input1_3;
    m_outputs[1][3] = ui.output1_3;
    m_inputs[1][4] = ui.input1_4;
    m_outputs[1][4] = ui.output1_4;
    m_inputs[1][5] = ui.input1_5;
    m_outputs[1][5] = ui.output1_5;
    m_inputs[1][6] = ui.input1_6;
    m_outputs[1][6] = ui.output1_6;
    m_inputs[1][7] = ui.input1_7;
    m_outputs[1][7] = ui.output1_7;
    m_inputs[1][8] = ui.input1_8;
    m_outputs[1][8] = ui.output1_8;
    m_inputs[1][9] = ui.input1_9;
    m_outputs[1][9] = ui.output1_9;
    m_inputs[1][10] = ui.input1_10;
    m_outputs[1][10] = ui.output1_10;
    m_inputs[1][11] = ui.input1_11;
    m_outputs[1][11] = ui.output1_11;
    for (int index = 0; index < 4; ++index) {
        auto &p = m_panels[index];
        for (auto *label : p.testLabels) label->setText("");
        if (auto *grid = qobject_cast<QGridLayout *>(p.position->parentWidget()->layout()))
            for (int column = 0; column < 5; ++column) grid->setColumnStretch(column, 1);
        connect(p.acceleration, qOverload<double>(&QDoubleSpinBox::valueChanged), this,
                [this, index](double value) { applyAcceleration(index, value); });
        connect(p.outputTest, &QPushButton::toggled, this, [this, index](bool checked) {
            for (auto *label : m_panels[index].testLabels) label->setText(checked ? "MODO TESTE" : "");
            if ((m_ready || m_diagnosticMode) && !m_stopping)
                send({{"op", "output_test"}, {"axis", index}, {"value", checked}});
        });
        connect(p.enable, &QPushButton::clicked, this, [this, index] { axisCommand(index, m_panels[index].enabled ? "disable" : "enable"); });
        connect(p.stop, &QPushButton::clicked, this, [this, index] { axisCommand(index, "stop"); });
        connect(p.zero, &QPushButton::clicked, this, [this, index] { axisCommand(index, "zero"); });
        connect(p.move, &QPushButton::clicked, this, [this, index] {
            axisCommand(index, "move", m_panels[index].target->value());
        });
        for (auto *button : {p.cw, p.ccw}) {
            button->setCheckable(true);
            const double sign = button == p.cw ? 1 : -1;
            auto *other = button == p.cw ? p.ccw : p.cw;
            connect(button, &QPushButton::clicked, this, [this, index, sign, other](bool checked) {
                if (checked) {
                    const QSignalBlocker blocker(other);
                    other->setChecked(false);
                    axisCommand(index, "jog", sign * m_panels[index].jogRpm->value());
                } else {
                    axisCommand(index, "jog_stop");
                }
            });
        }
        p.jogRpm->setKeyboardTracking(true);
        auto *rpmUpdate = new QTimer(p.jogRpm);
        rpmUpdate->setSingleShot(true);
        rpmUpdate->setInterval(250);
        const auto applyJogRpm = [this, index] {
            const auto &panel = m_panels[index];
            if (panel.cw->isChecked() || panel.ccw->isChecked())
                axisCommand(index, "jog", panel.cw->isChecked() ? panel.jogRpm->value() : -panel.jogRpm->value());
        };
        connect(p.jogRpm, qOverload<double>(&QDoubleSpinBox::valueChanged), rpmUpdate,
                [rpmUpdate](double) { rpmUpdate->start(); });
        connect(rpmUpdate, &QTimer::timeout, this, applyJogRpm);
        connect(p.jogRpm, &QDoubleSpinBox::editingFinished, this, [rpmUpdate, applyJogRpm] {
            if (rpmUpdate->isActive()) {
                rpmUpdate->stop();
                applyJogRpm();
            }
        });
        connect(p.settings, &QPushButton::clicked, this, [this, index] { configureAxis(index); });
    }
    for (int port = 0; port < 2; ++port) {
        const QString connector = QString("P%1").arg(port + 1);
        for (int channel = 0; channel < 12; ++channel) {
            auto *output = m_outputs[port][channel];
            connect(output, &QPushButton::clicked, this, [this, connector, channel, output](bool checked) {
                if (!m_ready || m_stopping) return;
                output->setEnabled(false);
                send({{"op", "io_output"}, {"connector", connector}, {"channel", channel}, {"value", checked}});
            });
        }
    }
    for (auto *table : {m_diagModules, m_diagEncoders}) {
        table->horizontalHeader()->setSectionResizeMode(QHeaderView::Stretch);
        table->verticalHeader()->hide();
    }
    if (QCoreApplication::arguments().contains("--diagnostics")) ui.tabs->setCurrentWidget(ui.hdtDiagnostics);
    if (QCoreApplication::arguments().contains("--preview-tests")) ui.tabs->setCurrentWidget(ui.testsTab);
    connect(m_connect, &QPushButton::clicked, this, &MainWindow::startConnection);
    connect(m_disconnect, &QPushButton::clicked, this, &MainWindow::disconnectBoard);
    connect(m_load, &QPushButton::clicked, this, &MainWindow::loadConfig);
    connect(m_save, &QPushButton::clicked, this, &MainWindow::saveConfig);
}
