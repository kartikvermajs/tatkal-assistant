"""Local notification service for Tatkal opening events."""

import sys
from typing import Optional
from PySide6.QtWidgets import QApplication, QWidget


class NotificationService:
    """Manages audible and visual alerts for Tatkal opening without external dependencies."""

    def __init__(self) -> None:
        pass

    def play_sound(self) -> None:
        """Play native Windows system sound or Qt beep."""
        try:
            if sys.platform == "win32":
                import winsound
                # Standard system notification sound
                winsound.MessageBeep(winsound.MB_ICONASTERISK)
            else:
                QApplication.beep()
        except Exception:
            # Fallback to standard Qt beep if winsound fails
            QApplication.beep()

    def trigger_opening_alert(
        self,
        parent_widget: Optional[QWidget] = None,
        sound: bool = True,
        visual: bool = True,
    ) -> None:
        """Trigger configured alerts when Tatkal opens."""
        if sound:
            self.play_sound()

        if visual and parent_widget is not None:
            # Request OS taskbar window attention on Windows
            parent_widget.activateWindow()
            parent_widget.raise_()

    def trigger_checkpoint_alert(
        self,
        checkpoint_name: str,
        parent_widget: Optional[QWidget] = None,
        sound: bool = True,
        visual: bool = True,
    ) -> None:
        """Trigger configured alerts when a human checkpoint (CAPTCHA, OTP, Payment) is reached."""
        if sound:
            self.play_sound()

        if visual and parent_widget is not None:
            parent_widget.activateWindow()
            parent_widget.raise_()
