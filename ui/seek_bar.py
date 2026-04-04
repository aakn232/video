"""
HomeCam Player - Custom Seek Bar
전체 타임라인을 시각적으로 표현하는 커스텀 시크바 위젯
갭 영역을 시각적으로 표시합니다.
"""
from PyQt6.QtWidgets import QSlider, QToolTip
from PyQt6.QtCore import Qt, pyqtSignal, QPoint
from PyQt6.QtGui import QMouseEvent, QPainter, QColor, QPen


class SeekBar(QSlider):
    """
    커스텀 시크바.
    - 클릭한 위치로 즉시 시크
    - 마우스 호버 시 시간 툴팁 표시 (시계 시간 포함)
    - 갭 영역을 시각적으로 표시
    - 드래그 중 재생 위치 업데이트 제어
    """

    seek_requested = pyqtSignal(float)  # 시크 요청 (초 단위)
    drag_started = pyqtSignal()         # 드래그 시작
    drag_finished = pyqtSignal()        # 드래그 종료

    def __init__(self, parent=None):
        super().__init__(Qt.Orientation.Horizontal, parent)
        self.setMinimum(0)
        self.setMaximum(1000000)  # 0.001초 정밀도
        self._duration = 0.0
        self._is_dragging = False
        self._hover_enabled = True
        self._suppress_slider_signals = False

        # 갭 시각화 관련
        self._gap_regions: list[dict] = []  # [{'start': 0.25, 'end': 0.5, 'duration': 1800}, ...]
        self._clock_time_callback = None    # callback(seconds) -> str

        self.setMouseTracking(True)
        self.setObjectName("seekBar")

        # 시그널 연결
        self.sliderPressed.connect(self._on_slider_pressed)
        self.sliderReleased.connect(self._on_slider_released)
        self.sliderMoved.connect(self._on_slider_moved)

    def set_duration(self, duration: float):
        """전체 타임라인 길이 설정 (실제 시간 기준)"""
        self._duration = max(duration, 0.001)

    def set_position(self, position: float):
        """현재 재생 위치 업데이트 (드래그 중이 아닐 때만)"""
        if not self._is_dragging and self._duration > 0:
            value = int((position / self._duration) * self.maximum())
            self.setValue(value)

    def set_gap_regions(self, gap_ratios: list[dict]):
        """갭 영역 설정 (시크바에 시각적으로 표시)"""
        self._gap_regions = gap_ratios
        self.update()

    def set_clock_time_callback(self, callback):
        """시계 시간 변환 콜백 설정: callback(real_offset_seconds) -> str"""
        self._clock_time_callback = callback

    def _value_to_seconds(self, value: int) -> float:
        """슬라이더 값을 초 단위로 변환"""
        if self.maximum() == 0:
            return 0.0
        return (value / self.maximum()) * self._duration

    def _pos_to_value(self, pos_x: int) -> int:
        """마우스 X 좌표를 슬라이더 값으로 변환"""
        groove_width = self.width()
        if groove_width == 0:
            return 0
        ratio = max(0.0, min(1.0, pos_x / groove_width))
        return int(ratio * self.maximum())

    # ========== 마우스 이벤트 ==========

    def mousePressEvent(self, event: QMouseEvent):
        """클릭한 위치로 즉시 이동"""
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_started.emit()
            value = self._pos_to_value(int(event.position().x()))
            self.setValue(value)
            self._is_dragging = True
            seconds = self._value_to_seconds(value)
            self.seek_requested.emit(seconds)
            self._suppress_slider_signals = True
        super().mousePressEvent(event)
        self._suppress_slider_signals = False

    def mouseMoveEvent(self, event: QMouseEvent):
        """마우스 이동 시 시간 툴팁 표시 (갭 정보 포함)"""
        if self._hover_enabled and self._duration > 0:
            value = self._pos_to_value(int(event.position().x()))
            seconds = self._value_to_seconds(value)

            # 시계 시간 또는 상대 시간 표시
            if self._clock_time_callback:
                time_str = self._clock_time_callback(seconds)
            else:
                time_str = self._format_time(seconds)

            # 갭 영역 확인
            ratio = seconds / self._duration if self._duration > 0 else 0
            for gap in self._gap_regions:
                if gap['start'] <= ratio <= gap['end']:
                    gap_mins = int(gap['duration'] // 60)
                    gap_secs = int(gap['duration'] % 60)
                    if gap_mins > 0:
                        time_str += f"\n⚠ 녹화 없음 ({gap_mins}분 {gap_secs}초)"
                    else:
                        time_str += f"\n⚠ 녹화 없음 ({gap_secs}초)"
                    break

            QToolTip.showText(
                self.mapToGlobal(QPoint(int(event.position().x()), -40)),
                time_str,
                self
            )

        if self._is_dragging:
            value = self._pos_to_value(int(event.position().x()))
            self.setValue(value)
            seconds = self._value_to_seconds(value)
            self.seek_requested.emit(seconds)
            self._suppress_slider_signals = True

        super().mouseMoveEvent(event)
        self._suppress_slider_signals = False

    def mouseReleaseEvent(self, event: QMouseEvent):
        """드래그 끝 → 시크 실행"""
        if event.button() == Qt.MouseButton.LeftButton and self._is_dragging:
            self._is_dragging = False
            seconds = self._value_to_seconds(self.value())
            self.seek_requested.emit(seconds)
            self.drag_finished.emit()
            self._suppress_slider_signals = True
        super().mouseReleaseEvent(event)
        self._suppress_slider_signals = False

    def _on_slider_pressed(self):
        if self._suppress_slider_signals:
            return
        self._is_dragging = True
        self.drag_started.emit()

    def _on_slider_released(self):
        if self._suppress_slider_signals:
            return
        self._is_dragging = False
        seconds = self._value_to_seconds(self.value())
        self.seek_requested.emit(seconds)
        self.drag_finished.emit()

    def _on_slider_moved(self, value: int):
        """드래그 중 실시간 영상 탐색"""
        if self._suppress_slider_signals:
            return
        if self._is_dragging:
            seconds = self._value_to_seconds(value)
            self.seek_requested.emit(seconds)

    def is_dragging(self) -> bool:
        return self._is_dragging

    def get_current_seconds(self) -> float:
        """현재 슬라이더 값을 초 단위로 반환"""
        return self._value_to_seconds(self.value())

    # ========== 갭 시각화 ==========

    def paintEvent(self, event):
        """기본 슬라이더 그린 후 갭 영역 오버레이"""
        super().paintEvent(event)

        if not self._gap_regions:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        groove_height = 8
        groove_y = (self.height() - groove_height) // 2
        groove_width = self.width()

        # 갭 영역: 반투명 빨간색 + 빗금 패턴
        gap_fill = QColor(255, 69, 58, 100)
        hatch_pen = QPen(QColor(255, 120, 110, 120), 1)

        for gap in self._gap_regions:
            x_start = int(gap['start'] * groove_width)
            x_end = int(gap['end'] * groove_width)
            w = max(x_end - x_start, 2)

            # 배경 채우기
            painter.fillRect(x_start, groove_y - 2, w, groove_height + 4, gap_fill)

            # 빗금 패턴
            painter.setPen(hatch_pen)
            step = 6
            for lx in range(x_start, x_start + w, step):
                y1 = groove_y - 2
                y2 = groove_y + groove_height + 2
                x2 = min(lx + groove_height + 4, x_start + w)
                painter.drawLine(lx, y2, x2, y1)

        painter.end()

    @staticmethod
    def _format_time(seconds: float) -> str:
        """초를 HH:MM:SS 형식으로 변환"""
        if seconds < 0:
            seconds = 0
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
