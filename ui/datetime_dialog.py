from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
    QPushButton, QCalendarWidget, QFrame, QTimeEdit, QGroupBox, QToolTip,
    QMenu
)
from PyQt6.QtCore import Qt, QSize, QRect, QTime, QDate, pyqtSignal, QPointF
from PyQt6.QtGui import QPainter, QColor, QBrush, QPen, QTextCharFormat, QFont, QAction
from datetime import datetime, time, date, timedelta

class ScrollingRangeTimeline(QFrame):
    """다중 날짜 무한 스크롤 및 시작/종료 범위 선택 타임라인"""
    # (start_dt, end_dt) 발생 시그널
    range_changed = pyqtSignal(datetime, datetime)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(120)
        self._segments = []
        self._merged_segments = []  # [(start_ts, duration), ...]
        self._current_view_dt = datetime.now() # 화면 중심 시점
        
        # 범위 설정 (초기값: 현재 시각 ~ 1시간 뒤)
        self._start_dt = datetime.now()
        self._end_dt = datetime.now() + timedelta(hours=1)
        
        self._pixels_per_second = 0.2    # 줌 레벨
        
        self._is_dragging_view = False
        self._dragging_handle = None   # 'start', 'end' or None
        self._last_mouse_pos = None
        
        self.setMouseTracking(True)
        self.setStyleSheet("background-color: #0d0f14; border: 1px solid #222; border-radius: 8px;")

    def set_data(self, all_segments, merged_segments, start_dt, end_dt):
        self._segments = all_segments
        self._merged_segments = merged_segments
        self._start_dt = start_dt
        self._end_dt = end_dt
        self._current_view_dt = start_dt
        self.update()

    def set_view_dt(self, target_dt):
        self._current_view_dt = target_dt
        self.update()

    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        zoom_factor = 1.2 if delta > 0 else 0.8
        new_pps = self._pixels_per_second * zoom_factor
        self._pixels_per_second = max(0.001, min(20.0, new_pps))
        self.update()

    def _dt_to_x(self, target_dt):
        center_x = self.width() // 2
        diff_sec = (target_dt - self._current_view_dt).total_seconds()
        return center_x + int(diff_sec * self._pixels_per_second)

    def _x_to_dt(self, x):
        center_x = self.width() // 2
        diff_sec = (x - center_x) / self._pixels_per_second
        return self._current_view_dt + timedelta(seconds=diff_sec)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            x = event.position().x()
            start_x = self._dt_to_x(self._start_dt)
            end_x = self._dt_to_x(self._end_dt)
            
            # 핸들 드래그 우선순위
            if abs(x - start_x) < 20:
                self._dragging_handle = 'start'
            elif abs(x - end_x) < 20:
                self._dragging_handle = 'end'
            else:
                self._is_dragging_view = True
            
            self._last_mouse_pos = event.position()
            self.update()

    def mouseMoveEvent(self, event):
        curr_x = event.position().x()
        
        if self._dragging_handle:
            new_dt = self._x_to_dt(curr_x)
            if self._dragging_handle == 'start':
                self._start_dt = min(new_dt, self._end_dt - timedelta(seconds=1))
            else:
                self._end_dt = max(new_dt, self._start_dt + timedelta(seconds=1))
            self.range_changed.emit(self._start_dt, self._end_dt)
            
        elif self._is_dragging_view:
            delta_px = curr_x - self._last_mouse_pos.x()
            delta_sec = delta_px / self._pixels_per_second
            self._current_view_dt -= timedelta(seconds=delta_sec)
            self._last_mouse_pos = event.position()
            
        else:
            # 커서 아이콘 변경
            start_x = self._dt_to_x(self._start_dt)
            end_x = self._dt_to_x(self._end_dt)
            if abs(curr_x - start_x) < 20 or abs(curr_x - end_x) < 20:
                self.setCursor(Qt.CursorShape.SizeHorCursor)
            else:
                self.setCursor(Qt.CursorShape.ArrowCursor)
        
        self.update()

    def mouseReleaseEvent(self, event):
        self._is_dragging_view = False
        self._dragging_handle = None
        self.setCursor(Qt.CursorShape.ArrowCursor)

    def contextMenuEvent(self, event):
        """우클릭 컨텍스트 메뉴: 시작/종료 지점 지정"""
        menu = QMenu(self)
        menu.setStyleSheet("QMenu { background-color: #222; color: #eee; border: 1px solid #444; } QMenu::item:selected { background-color: #0078d7; }")
        
        click_dt = self._x_to_dt(event.pos().x())
        time_str = click_dt.strftime("%H:%M:%S")
        
        action_start = menu.addAction(f"🚩 여기를 시작점으로 설정 ({time_str})")
        action_end = menu.addAction(f"🏁 여기를 종료점으로 설정 ({time_str})")
        
        selected = menu.exec(event.globalPos())
        
        if selected == action_start:
            self._start_dt = min(click_dt, self._end_dt - timedelta(seconds=1))
            self.range_changed.emit(self._start_dt, self._end_dt)
        elif selected == action_end:
            self._end_dt = max(click_dt, self._start_dt + timedelta(seconds=1))
            self.range_changed.emit(self._start_dt, self._end_dt)
        
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        w = self.width()
        h = self.height()
        center_x = w // 2
        
        # 가시 범위 계산
        visible_sec_half = center_x / self._pixels_per_second
        v_start_dt = self._current_view_dt - timedelta(seconds=visible_sec_half)
        v_end_dt = self._current_view_dt + timedelta(seconds=visible_sec_half)
        v_start_ts = int(v_start_dt.timestamp())
        v_end_ts = int(v_end_dt.timestamp())

        # 1. 날짜별 배경 (Alternate Background) - 축소 시 날짜 구분을 도움
        curr_d = v_start_dt.date()
        while curr_d <= v_end_dt.date():
            d_start = datetime.combine(curr_d, time.min)
            d_end = datetime.combine(curr_d, time.max)
            x_start = self._dt_to_x(d_start)
            x_end = self._dt_to_x(d_end)
            
            # 날짜별로 미세하게 다른 배경색 (홀수/짝수 날짜)
            if curr_d.day % 2 == 0:
                painter.fillRect(QRect(x_start, 0, x_end - x_start, h), QColor(20, 22, 30))
            else:
                painter.fillRect(QRect(x_start, 0, x_end - x_start, h), QColor(13, 15, 20))
            curr_d += timedelta(days=1)

        # 2. 선택 영역 하이라이트 (파란색 오버레이)
        start_x = self._dt_to_x(self._start_dt)
        end_x = self._dt_to_x(self._end_dt)
        selection_rect = QRect(start_x, 0, end_x - start_x, h)
        painter.fillRect(selection_rect, QColor(0, 120, 215, 60))
        
        # 3. 데이터 유무 표시
        painter.setBrush(QBrush(QColor(46, 160, 67, 200)))
        painter.setPen(Qt.PenStyle.NoPen)
        for start_ts, duration in self._merged_segments:
            if start_ts + duration < v_start_ts or start_ts > v_end_ts: continue
            seg_dt = datetime.fromtimestamp(start_ts)
            seg_x = self._dt_to_x(seg_dt)
            seg_w = max(int(duration * self._pixels_per_second), 2)
            if seg_x + seg_w > 0 and seg_x < w:
                painter.drawRect(seg_x, 45, seg_w, h - 90)

        # 4. 가변형 눈금 및 텍스트 (Adaptive Ticking)
        pps = self._pixels_per_second
        if pps > 8.0: intervals = (1, 5, 30)
        elif pps > 2.0: intervals = (5, 10, 60)
        elif pps > 0.5: intervals = (10, 60, 300)
        elif pps > 0.1: intervals = (60, 300, 1800)
        elif pps > 0.02: intervals = (300, 1800, 3600)
        elif pps > 0.005: intervals = (1800, 3600, 14400)
        else: intervals = (3600, 14400, 86400)
        
        small, mid, large = intervals
        start_ts = (v_start_ts // small) * small
        
        for ts in range(start_ts, v_end_ts + small, small):
            dt = datetime.fromtimestamp(ts)
            lx = self._dt_to_x(dt)
            if lx < 0 or lx > w: continue
            
            if dt.hour == 0 and dt.minute == 0 and dt.second == 0:
                painter.setPen(QPen(QColor(255, 255, 100, 180), 2))
                painter.drawLine(lx, 0, lx, h)
                date_str = dt.strftime("%Y-%m-%d")
                painter.setBrush(QBrush(QColor(255, 180, 0, 180)))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawRoundedRect(lx + 5, 5, 90, 20, 4, 4)
                painter.setPen(QColor(0, 0, 0))
                painter.drawText(lx + 10, 20, date_str)
                continue

            if ts % large == 0:
                painter.setPen(QPen(QColor(220, 220, 220), 1))
                painter.drawLine(lx, 20, lx, 60)
                time_str = dt.strftime("%H:%M")
                painter.drawText(lx - 15, h - 5, time_str)
            elif ts % mid == 0:
                painter.setPen(QPen(QColor(120, 120, 120), 1))
                painter.drawLine(lx, 30, lx, 55)
            else:
                painter.setPen(QPen(QColor(60, 60, 60), 1))
                painter.drawLine(lx, 35, lx, 48)

        # 5. 범위 핸들 디자인
        painter.setPen(QPen(QColor(0, 120, 215), 3))
        painter.drawLine(start_x, 0, start_x, h)
        painter.drawLine(end_x, 0, end_x, h)
        
        painter.setBrush(QBrush(QColor(0, 120, 215)))
        painter.drawText(end_x + 3, h // 2 + 5, "]")

        # 5. 중앙 포인터 (미홈 스타일 지침)
        painter.setPen(QPen(QColor(255, 255, 255, 120), 1, Qt.PenStyle.DashLine))
        painter.drawLine(center_x, 0, center_x, h)
        
        painter.end()

class DateTimeSelectorDialog(QDialog):
    def __init__(self, timeline_mgr, available_dates, parent=None):
        super().__init__(parent)
        self._mgr = timeline_mgr
        self._available_dates = available_dates
        self.setWindowTitle("🎬 다중 날짜 범위 선택 (미홈 스타일)")
        self.setMinimumSize(950, 650)
        
        # 초기 범위 설정 (기본값: 가장 최근 날짜 전체)
        if available_dates:
            last_date = max(available_dates)
            self._start_dt = datetime.combine(last_date, time(0, 0))
            self._end_dt = datetime.combine(last_date, time(23, 59, 59))
        else:
            self._start_dt = datetime.now()
            self._end_dt = datetime.now()

        self._setup_ui()
        self._load_dates()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(25, 25, 25, 25)
        layout.setSpacing(20)

        # 상단 통합 요약 바
        header = QGroupBox("선택된 재생 범위")
        header.setStyleSheet("QGroupBox { font-size: 16px; font-weight: bold; color: #aaa; border: 1px solid #333; margin-top: 10px; padding-top: 15px; }")
        header_layout = QHBoxLayout(header)
        
        self._range_label = QLabel("불러오는 중...")
        self._range_label.setStyleSheet("font-size: 20px; font-weight: bold; color: #0078d7;")
        header_layout.addWidget(self._range_label)
        header_layout.addStretch()
        
        help_info = QLabel("🖱 휠: 줌(Zoom) | ↔ 드래그: 이동 | ▯ 핸들: 범위 조절")
        help_info.setStyleSheet("color: #777; font-size: 13px;")
        header_layout.addWidget(help_info)
        layout.addWidget(header)

        # 중앙: 달력 및 범위 타임라인
        content_layout = QHBoxLayout()
        
        # 달력 (날짜 워프용)
        self._calendar = QCalendarWidget()
        self._calendar.setGridVisible(True)
        self._calendar.setVerticalHeaderFormat(QCalendarWidget.VerticalHeaderFormat.NoVerticalHeader)
        self._calendar.selectionChanged.connect(self._on_calendar_date_changed)
        self._calendar.setStyleSheet("""
            QCalendarWidget QAbstractItemView { background-color: #1a1a1a; color: #ccc; selection-background-color: #0078d7; }
            QCalendarWidget QWidget#qt_calendar_navigationbar { background-color: #222; }
        """)
        content_layout.addWidget(self._calendar, 3)

        # 타임라인 패널
        self._timeline = ScrollingRangeTimeline(self)
        self._timeline.range_changed.connect(self._on_timeline_range_changed)
        content_layout.addWidget(self._timeline, 7)
        layout.addLayout(content_layout)

        # 하단 미세 조정 (선택 사항 - 여기선 라벨로 대체하거나 간략화)
        status_footer = QHBoxLayout()
        self._status_info = QLabel("ℹ 녹화 기록(초록색)이 있는 구간을 파란색 범위 안으로 설정하세요.")
        self._status_info.setStyleSheet("color: #888; font-style: italic;")
        status_footer.addWidget(self._status_info)
        status_footer.addStretch()
        
        btn_cancel = QPushButton("취소")
        btn_cancel.setFixedSize(110, 45)
        btn_cancel.clicked.connect(self.reject)
        
        btn_ok = QPushButton("범위 로드 및 재생")
        btn_ok.setFixedSize(180, 45)
        btn_ok.setStyleSheet("background-color: #0078d7; color: white; font-weight: bold; font-size: 15px; border-radius: 6px;")
        btn_ok.clicked.connect(self.accept)
        
        status_footer.addWidget(btn_cancel)
        status_footer.addWidget(btn_ok)
        layout.addLayout(status_footer)

    def _load_dates(self):
        # 1. 캘린더 데이터 표시
        fmt = QTextCharFormat()
        fmt.setBackground(QColor(46, 160, 67, 50))
        fmt.setForeground(QColor(100, 255, 100))
        fmt.setFontWeight(QFont.Weight.Bold)
        for d in self._available_dates:
            qd = QDate(d.year, d.month, d.day)
            self._calendar.setDateTextFormat(qd, fmt)

        # 2. 타임라인 데이터 초기화
        all_segs = self._mgr.get_all_segments()
        merged_segs = self._mgr.get_merged_segments(threshold_sec=3.0)
        self._timeline.set_data(all_segs, merged_segs, self._start_dt, self._end_dt)
        self._update_range_label()

    def _on_calendar_date_changed(self):
        """달력에서 날짜를 고르면 타임라인을 해당 시점으로 워프(Warp)"""
        qd = self._calendar.selectedDate()
        target_dt = datetime(qd.year(), qd.month(), qd.day(), 12, 0, 0) # 해당 날짜 정오로 이동
        self._timeline.set_view_dt(target_dt)

    def _on_timeline_range_changed(self, start, end):
        self._start_dt = start
        self._end_dt = end
        self._update_range_label()

    def _update_range_label(self):
        start_str = self._start_dt.strftime("%Y-%m-%d %H:%M")
        end_str = self._end_dt.strftime("%H:%M") if self._start_dt.date() == self._end_dt.date() else self._end_dt.strftime("%Y-%m-%d %H:%M")
        
        diff = self._end_dt - self._start_dt
        hours = diff.total_seconds() / 3600
        
        self._range_label.setText(f"{start_str} ~ {end_str} ({hours:.1f} 시간)")

    def get_selected_range(self):
        return self._start_dt, self._end_dt
