#include "mainwindow.h"

#include <QApplication>
#include <QPushButton>
#include "telemetryplot.h"
#include <cmath>
#include <QDoubleSpinBox>
#include <QLabel>
#include <QTimer>
#include <QTabWidget>

int main(int argc, char *argv[])
{
    QApplication application(argc, argv);
    application.setApplicationName("T3D Analog Velocity");
    application.setApplicationVersion(T3D_VERSION);
    application.setOrganizationName("HL-T3D-RABN");

    MainWindow window;
    window.setWindowTitle(window.windowTitle() + QString(" • v%1").arg(application.applicationVersion()));
    window.show();
    if (application.arguments().contains("--preview-diagnostics")) {
        window.findChild<QTabWidget *>("tabs")->setCurrentWidget(window.findChild<QWidget *>("hdtDiagnostics"));
    }
    if (application.arguments().contains("--preview-tests")) {
        auto *tabs = window.findChild<QTabWidget *>("tabs");
        tabs->setCurrentWidget(window.findChild<QWidget *>("testsTab"));
    }
    if (application.arguments().contains("--preview-pinout"))
        window.findChild<QTabWidget *>("tabs")->setCurrentWidget(window.findChild<QWidget *>("pinoutTab"));
    if (application.arguments().contains("--preview-test"))
        window.findChild<QPushButton *>("outputTest0")->setChecked(true);
    if (application.arguments().contains("--preview-graph")) {
        for (int motor = 0; motor < 4; ++motor) {
            auto *plot = window.findChild<TelemetryPlot *>(QString("plot%1").arg(motor));
            for (int sample = 0; sample <= 400; ++sample) {
                const double t = sample * 0.05;
                plot->append(t, std::sin(t * 0.6), 0.98 * std::sin((t - 0.12) * 0.6));
            }
        }
    }
    const int capture = application.arguments().indexOf("--screenshot");
    if (capture >= 0 && capture + 1 < application.arguments().size()) {
        const QString path = application.arguments().at(capture + 1);
        QTimer::singleShot(200, &window, [&window, path] { window.grab().save(path); });
    }
    if (application.arguments().contains("--smoke-test"))
        QTimer::singleShot(300, &application, [&] {
            const auto size = window.size();
            const auto hint = window.sizeHint();
            const auto valuePosition = window.findChild<QLabel *>("position0")->mapTo(&window, QPoint());
            auto *test = window.findChild<QPushButton *>("outputTest0");
            test->setChecked(!test->isChecked());
            application.processEvents();
            const bool stable = size == window.size() && hint == window.sizeHint()
                && valuePosition == window.findChild<QLabel *>("position0")->mapTo(&window, QPoint());
            const bool rpmRange = window.findChild<QDoubleSpinBox *>("jogRpm0")->maximum() == 9999.9;
            application.exit(stable && rpmRange ? 0 : 1);
        });
    return application.exec();
}
