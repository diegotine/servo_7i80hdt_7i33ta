#include "mainwindow.h"

#include <QApplication>
#include <QCheckBox>
#include <QDoubleSpinBox>
#include <QLabel>
#include <QTimer>

int main(int argc, char *argv[])
{
    QApplication application(argc, argv);
    application.setApplicationName("T3D Analog Velocity");
    application.setApplicationVersion(T3D_VERSION);
    application.setOrganizationName("HL-T3D-RABN");

    MainWindow window;
    window.show();
    if (application.arguments().contains("--preview-test"))
        window.findChild<QCheckBox *>("outputTest0")->setChecked(true);
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
            auto *test = window.findChild<QCheckBox *>("outputTest0");
            test->setChecked(!test->isChecked());
            application.processEvents();
            const bool stable = size == window.size() && hint == window.sizeHint()
                && valuePosition == window.findChild<QLabel *>("position0")->mapTo(&window, QPoint());
            const bool rpmRange = window.findChild<QDoubleSpinBox *>("jogRpm0")->maximum() == 9999.9;
            application.exit(stable && rpmRange ? 0 : 1);
        });
    return application.exec();
}
