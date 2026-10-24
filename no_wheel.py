"""4.1.3 (owner, 19/10/2026): the mouse wheel must never change a number, a date/time,
a slider or a dropdown choice in NBL LIVE. Over such a box the wheel scrolls the page
it sits in instead. Lists, text boxes and open dropdown lists still scroll normally."""
from PySide6.QtCore import QObject, QEvent
from PySide6.QtWidgets import QAbstractScrollArea, QAbstractSlider, QAbstractSpinBox, QComboBox, QScrollBar, QWidget

GUARDED = (QAbstractSpinBox, QComboBox, QAbstractSlider)   # QDateTimeEdit is a QAbstractSpinBox


def guarded_box(widget):
    """The number/date/slider/dropdown box under the wheel, or None if the wheel should act normally."""
    while widget is not None:
        if isinstance(widget, QScrollBar):
            return None                      # a real scroll bar keeps scrolling
        if isinstance(widget, GUARDED):
            return widget
        if isinstance(widget, QAbstractScrollArea):
            return None                      # list, text box, open dropdown list, page
        widget = widget.parentWidget()
    return None


def scroll_page(box, event):
    area = box.parentWidget()
    while area is not None and not isinstance(area, QAbstractScrollArea):
        area = area.parentWidget()
    if area is None:
        return
    bar = area.verticalScrollBar()
    if bar is None or not bar.isVisible():
        return
    steps = event.angleDelta().y() / 120.0
    bar.setValue(int(bar.value() - steps * max(1, bar.singleStep()) * 3))


class WheelGuard(QObject):
    def eventFilter(self, obj, event):
        if event.type() != QEvent.Type.Wheel or not isinstance(obj, QWidget):
            return False
        box = guarded_box(obj)
        if box is None:
            return False
        try:
            scroll_page(box, event)
        except Exception:
            pass
        return True                          # the box never sees the wheel


def install(app):
    guard = WheelGuard(app)
    app.installEventFilter(guard)
    app._nbl_wheel_guard = guard             # keep a reference
    return guard
