#pragma once
#include <QPixmap>
#include <QWidget>

// Static reference photo, fitted to the available width without upscaling.
class PinoutImage final : public QWidget
{
public:
    explicit PinoutImage(QWidget *parent = nullptr);
    QSize sizeHint() const override;
protected:
    void resizeEvent(QResizeEvent *event) override;
    void paintEvent(QPaintEvent *event) override;
private:
    QPixmap m_photo;
};
