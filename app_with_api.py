"""NBL LIVE launcher with Local API enabled."""
import sys
from pathlib import Path
from PySide6.QtWidgets import QApplication
import app as nbl


if __name__ == '__main__':
    if '--player' in sys.argv:
        from player import Output
        qapp = QApplication(sys.argv)
        window = Output(Path(sys.argv[-1]))
        window.show()
        sys.exit(qapp.exec())

    if '--alarm' in sys.argv:
        from NBL_CANH_BAO.alarm import Alarm
        qapp = QApplication(sys.argv)
        qapp.setStyleSheet(nbl.STYLE)
        window = Alarm()
        window.show()
        sys.exit(qapp.exec())

    qapp = QApplication(sys.argv)
    qapp.setStyle('Fusion')
    qapp.setStyleSheet(nbl.STYLE)
    from no_wheel import install as no_wheel
    no_wheel(qapp)

    # Install small runtime enhancements before Console creates ChromeBridge /
    # StudioPanel instances. Core start/stop behavior remains untouched.
    try:
        from chrome_reload_patch import install as install_chrome_reload
        install_chrome_reload()
        from cart_retry_patch import install as install_cart_retry
        install_cart_retry()
    except Exception as exc:
        print('NBL runtime patch không tải được:', str(exc)[:300])

    window = nbl.Console()
    local_api = None
    try:
        from local_api import LocalAPI
        local_api = LocalAPI(window)
        qapp.aboutToQuit.connect(local_api.close)
    except Exception as exc:
        window.log('Local API không mở được: ' + str(exc)[:500])

    window.show()
    sys.exit(qapp.exec())
