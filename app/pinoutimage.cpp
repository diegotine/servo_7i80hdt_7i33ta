#include "pinoutimage.h"
#include <QPainter>
#include <QResizeEvent>
#include <algorithm>

PinoutImage::PinoutImage(QWidget *parent)
    : QWidget(parent), m_photo(":/pinout/7i33ta-pinout.png")
{
    setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Preferred);
}
QSize PinoutImage::sizeHint() const
{
    return m_photo.isNull() ? QSize(720, 840)
        : QSize(720, qRound(720.0 * m_photo.height() / m_photo.width()));
}
void PinoutImage::resizeEvent(QResizeEvent *event)
{
    QWidget::resizeEvent(event);
    if (m_photo.isNull()) return;
    const int imageWidth = std::min(width(), m_photo.width());
    setMinimumHeight(qRound(double(imageWidth) * m_photo.height() / m_photo.width()));
}
void PinoutImage::paintEvent(QPaintEvent *)
{
    if (m_photo.isNull()) return;
    const int imageWidth = std::min(width(), m_photo.width());
    const int imageHeight = qRound(double(imageWidth) * m_photo.height() / m_photo.width());
    QPainter painter(this);
    painter.setRenderHint(QPainter::SmoothPixmapTransform);
    painter.drawPixmap(QRect((width() - imageWidth) / 2, 0, imageWidth, imageHeight), m_photo);
}
