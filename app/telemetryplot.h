#pragma once
#include <QWidget>
#include <deque>

class TelemetryPlot final : public QWidget
{
    Q_OBJECT
public:
    explicit TelemetryPlot(QWidget *parent = nullptr);
    void append(double seconds, double command, double feedback);
    void breakTrace();
    QSize sizeHint() const override { return {650, 190}; }
protected:
    void paintEvent(QPaintEvent *) override;
private:
    struct Sample { double time, command, feedback; bool gap; };
    std::deque<Sample> m_samples;
    bool m_gap = true;
};
