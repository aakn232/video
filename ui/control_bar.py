"""
HomeCam Player - Control Bar
하단 재생 컨트롤 바 위젯
"""
from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QPushButton,
    QLabel, QSlider, QButtonGroup, QSizePolicy
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont

from ui.seek_bar import SeekBar


class ControlBar(QWidget):
    """하단 컨트롤 바 위젯"""

    # 시그널
    play_pause_clicked = pyqtSignal()
    seek_requested = pyqtSignal(float)
    speed_changed = pyqtSignal(float)
    skip_forward_clicked = pyqtSignal(float)
    skip_backward_clicked = pyqtSignal(float)
    volume_changed = pyqtSignal(int)
    show_corrupted_clicked = pyqtSignal()

    SPEED_OPTIONS = [1, 2, 4, 8, 16]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("controlBar")
        self._current_speed = 1.0
        self._is_playing = False
        self._is_real_time_mode = False
        self._setup_ui()

    def _setup_ui(self):
        """UI 구성"""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 8, 16, 12)
        main_layout.setSpacing(8)

        # --- 시크바 행 ---
        seek_layout = QHBoxLayout()
        seek_layout.setSpacing(12)

        # 시간 표시 (시계 시간)
        time_left = QVBoxLayout()
        time_left.setSpacing(0)
        self._time_current = QLabel("00:00:00")
        self._time_current.setObjectName("timeLabel")
        self._time_current.setFixedWidth(80)
        self._time_current.setAlignment(Qt.AlignmentFlag.AlignCenter)
        time_left.addWidget(self._time_current)

        self._seek_bar = SeekBar()
        self._seek_bar.seek_requested.connect(self.seek_requested.emit)

        time_right = QVBoxLayout()
        time_right.setSpacing(0)
        self._time_total = QLabel("00:00:00")
        self._time_total.setObjectName("timeLabel")
        self._time_total.setFixedWidth(80)
        self._time_total.setAlignment(Qt.AlignmentFlag.AlignCenter)
        time_right.addWidget(self._time_total)

        seek_layout.addLayout(time_left)
        seek_layout.addWidget(self._seek_bar, 1)
        seek_layout.addLayout(time_right)

        main_layout.addLayout(seek_layout)

        # --- 컨트롤 행 ---
        controls_layout = QHBoxLayout()
        controls_layout.setSpacing(8)

        # 좌측: 재생 컨트롤
        play_controls = QHBoxLayout()
        play_controls.setSpacing(4)

        self._btn_skip_back_60 = QPushButton("⏪ 60s")
        self._btn_skip_back_60.setObjectName("controlBtn")
        self._btn_skip_back_60.setFixedSize(70, 36)
        self._btn_skip_back_60.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._btn_skip_back_60.clicked.connect(lambda: self.skip_backward_clicked.emit(60))

        self._btn_skip_back = QPushButton("◀ 10s")
        self._btn_skip_back.setObjectName("controlBtn")
        self._btn_skip_back.setFixedSize(65, 36)
        self._btn_skip_back.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._btn_skip_back.clicked.connect(lambda: self.skip_backward_clicked.emit(10))

        self._btn_play_pause = QPushButton("▶")
        self._btn_play_pause.setObjectName("playBtn")
        self._btn_play_pause.setFixedSize(50, 50)
        self._btn_play_pause.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._btn_play_pause.clicked.connect(self.play_pause_clicked.emit)

        self._btn_skip_fwd = QPushButton("10s ▶")
        self._btn_skip_fwd.setObjectName("controlBtn")
        self._btn_skip_fwd.setFixedSize(65, 36)
        self._btn_skip_fwd.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._btn_skip_fwd.clicked.connect(lambda: self.skip_forward_clicked.emit(10))

        self._btn_skip_fwd_60 = QPushButton("60s ⏩")
        self._btn_skip_fwd_60.setObjectName("controlBtn")
        self._btn_skip_fwd_60.setFixedSize(70, 36)
        self._btn_skip_fwd_60.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._btn_skip_fwd_60.clicked.connect(lambda: self.skip_forward_clicked.emit(60))

        play_controls.addWidget(self._btn_skip_back_60)
        play_controls.addWidget(self._btn_skip_back)
        play_controls.addWidget(self._btn_play_pause)
        play_controls.addWidget(self._btn_skip_fwd)
        play_controls.addWidget(self._btn_skip_fwd_60)

        controls_layout.addLayout(play_controls)
        controls_layout.addStretch(1)

        # 중앙: 배속 버튼
        speed_layout = QHBoxLayout()
        speed_layout.setSpacing(4)

        speed_label = QLabel("배속:")
        speed_label.setObjectName("speedLabel")
        speed_layout.addWidget(speed_label)

        self._speed_buttons: list[QPushButton] = []
        for speed in self.SPEED_OPTIONS:
            btn = QPushButton(f"{speed}x")
            btn.setObjectName("speedBtn")
            btn.setFixedSize(48, 32)
            btn.setCheckable(True)
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            if speed == 1:
                btn.setChecked(True)
            btn.clicked.connect(lambda checked, s=speed: self._on_speed_clicked(s))
            self._speed_buttons.append(btn)
            speed_layout.addWidget(btn)

        speed_layout.addSpacing(16)
        
        self._btn_corrupted = QPushButton("⚠ 손상 파일")
        self._btn_corrupted.setObjectName("corruptedBtn")
        self._btn_corrupted.setFixedHeight(32)
        self._btn_corrupted.setStyleSheet("""
            QPushButton {
                background-color: #3d2222;
                color: #ff8888;
                border: 1px solid #553333;
                border-radius: 4px;
                padding: 0 8px;
            }
            QPushButton:hover {
                background-color: #4d2a2a;
            }
            QPushButton:pressed {
                background-color: #5d3333;
            }
        """)
        self._btn_corrupted.clicked.connect(self.show_corrupted_clicked.emit)
        self._btn_corrupted.hide()
        speed_layout.addWidget(self._btn_corrupted)

        controls_layout.addLayout(speed_layout)
        controls_layout.addStretch(1)

        # 우측: 볼륨
        volume_layout = QHBoxLayout()
        volume_layout.setSpacing(8)

        volume_label = QLabel("🔊")
        volume_label.setObjectName("volumeIcon")
        volume_layout.addWidget(volume_label)

        self._volume_slider = QSlider(Qt.Orientation.Horizontal)
        self._volume_slider.setObjectName("volumeSlider")
        self._volume_slider.setRange(0, 100)
        self._volume_slider.setValue(50)
        self._volume_slider.setFixedWidth(100)
        self._volume_slider.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._volume_slider.valueChanged.connect(self.volume_changed.emit)
        volume_layout.addWidget(self._volume_slider)

        controls_layout.addLayout(volume_layout)

        main_layout.addLayout(controls_layout)

    def set_volume(self, volume: int):
        """외부에서 볼륨 슬라이더 설정 (초기 로드 등)"""
        self._volume_slider.blockSignals(True)
        self._volume_slider.setValue(volume)
        self._volume_slider.blockSignals(False)

    def _on_speed_clicked(self, speed: float):
        """배속 버튼 클릭"""
        self._current_speed = speed
        for btn in self._speed_buttons:
            btn.setChecked(btn.text() == f"{int(speed)}x")
        self.speed_changed.emit(speed)

    def update_play_button(self, is_playing: bool):
        """재생/일시정지 버튼 상태 업데이트"""
        self._is_playing = is_playing
        self._btn_play_pause.setText("❚❚" if is_playing else "▶")

    def update_position(self, seconds: float, clock_time: str = None):
        """현재 위치 업데이트 (시계 시간 사용 가능)"""
        if clock_time and self._is_real_time_mode:
            self._time_current.setText(clock_time)
        else:
            self._time_current.setText(self._format_time(seconds))
        self._seek_bar.set_position(seconds)

    def update_duration(self, seconds: float, clock_time: str = None):
        """전체 시간 업데이트 (시계 시간 사용 가능)"""
        if clock_time and self._is_real_time_mode:
            self._time_total.setText(clock_time)
        else:
            self._time_total.setText(self._format_time(seconds))
        self._seek_bar.set_duration(seconds)

    def set_real_time_mode(self, enabled: bool):
        """실제 시계 시간 표시 모드 설정"""
        self._is_real_time_mode = enabled

    def update_speed_display(self, speed: float):
        """배속 표시 업데이트"""
        self._current_speed = speed
        speed_int = int(speed)
        for btn in self._speed_buttons:
            btn.setChecked(btn.text() == f"{speed_int}x")

    def set_corrupted_count(self, count: int):
        """손상된 파일 개수 설정 및 버튼 표시 여부 업데이트"""
        if count > 0:
            self._btn_corrupted.setText(f"⚠ 손상 ({count})")
            self._btn_corrupted.show()
        else:
            self._btn_corrupted.hide()

    def get_seek_bar(self) -> SeekBar:
        """시크바 위젯 반환"""
        return self._seek_bar

    @staticmethod
    def _format_time(seconds: float) -> str:
        """초를 HH:MM:SS 형식으로 변환"""
        if seconds is None or seconds < 0:
            seconds = 0
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
