#include "telemetryplot.h"
#include <QPainter>
#include <QPainterPath>
#include <algorithm>
#include <cmath>

TelemetryPlot::TelemetryPlot(QWidget *parent) : QWidget(parent)
{
    setMinimumHeight(165);
    setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Expanding);
}

void TelemetryPlot::append(double seconds, double command, double feedback)
{
    if (!std::isfinite(seconds) || !std::isfinite(command) || !std::isfinite(feedback)) return;
    m_samples.push_back({seconds, command, feedback,
        m_gap || (!m_samples.empty() && seconds - m_samples.back().time > 0.3)});
    m_gap = false;
    while (m_samples.size() > 600 || (!m_samples.empty() && seconds - m_samples.front().time > 20))
        m_samples.pop_front();
    update();
}

void TelemetryPlot::breakTrace() { m_gap = true; }

void TelemetryPlot::paintEvent(QPaintEvent *)
{
    QPainter painter(this);
    painter.setRenderHint(QPainter::Antialiasing);
    painter.fillRect(rect(), QColor("#191611"));
    painter.setPen(QColor("#705638"));
    painter.drawRoundedRect(rect().adjusted(1, 1, -1, -1), 7, 7);
    painter.setFont(QFont("Noto Sans", 9));
    painter.setPen(QColor("#eadfc9"));
    painter.drawText(12, 20, "Posição (voltas) • últimos 20 s");
    painter.setPen(QColor("#edb84b"));
    painter.drawText(width() - 235, 20, "━ Comando");
    painter.setPen(QColor("#51cee2"));
    painter.drawText(width() - 120, 20, "━ Feedback");
    const QRectF area(76, 35, std::max(1, width() - 94), std::max(1, height() - 62));
    double low = 0, high = 0;
    for (const auto &s : m_samples) {
        low = std::min({low, s.command, s.feedback});
        high = std::max({high, s.command, s.feedback});
    }
    const double padding = std::max(0.01, (high - low) * 0.1);
    low -= padding; high += padding;
    for (int line = 0; line <= 4; ++line) {
        const double y = area.top() + area.height() * line / 4;
        painter.setPen(QColor("#3c3025"));
        painter.drawLine(QPointF(area.left(), y), QPointF(area.right(), y));
        painter.setPen(QColor("#b7a68e"));
        double value = high - (high - low) * line / 4;
        if (std::abs(value) < (high - low) * 0.00001) value = 0;
        painter.drawText(QRectF(2, y - 9, 68, 18), Qt::AlignRight | Qt::AlignVCenter,
                         QString::number(value, 'g', 4));
    }
    painter.drawText(QRectF(area.left(), area.bottom() + 4, area.width(), 18),
                     Qt::AlignRight, "−20 s                                      agora");
    if (m_samples.empty()) {
        painter.drawText(area, Qt::AlignCenter, "Aguardando leituras da placa");
        return;
    }
    const double end = m_samples.back().time;
    painter.save();
    painter.setClipRect(area.adjusted(-1, -1, 1, 1));
    for (bool feedback : {false, true}) {
        QPainterPath path;
        bool first = true;
        for (const auto &s : m_samples) {
            const QPointF point(area.right() - (end - s.time) * area.width() / 20,
                area.bottom() - ((feedback ? s.feedback : s.command) - low) * area.height() / (high - low));
            if (first || s.gap) path.moveTo(point); else path.lineTo(point);
            first = false;
        }
        painter.setPen(QPen(QColor(feedback ? "#51cee2" : "#edb84b"), 2));
        painter.drawPath(path);
    }
    painter.restore();
}
