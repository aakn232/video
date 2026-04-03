"""
HomeCam Player - Main Window
메인 윈도우 - 비디오 영역, 컨트롤 바, 파일 정보 바를 포함
"""
import sys
from pathlib import Path

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QFrame, QLabel, QPushButton, QFileDialog, QStatusBar,
    QSizePolicy, QApplication, QDialog, QListWidget
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QKeyEvent, QDragEnterEvent, QDropEvent, QFont

from player_engine import PlayerEngine
from timeline_manager import TimelineManager, format_time
from ui.control_bar import ControlBar


class MainWindow(QMainWindow):
    """HomeCam Player 메인 윈도우"""

    def __init__(self, initial_folder: str = None):
        super().__init__()
        self.setWindowTitle("🏠 HomeCam Player")
        self.setMinimumSize(900, 600)
        self.resize(1280, 720)

        self._timeline_mgr = TimelineManager()
        self._player: PlayerEngine = None
        self._is_loaded = False
        self._mpv_total_duration = 0.0  # mpv가 보고하는 전체 재생 길이

        self._setup_ui()
        self._load_stylesheet()
        self._setup_shortcuts()

        # 초기 폴더가 있으면 바로 로드
        if initial_folder:
            self._load_folder(initial_folder)

    def _setup_ui(self):
        """UI 구성"""
        # 중앙 위젯
        central = QWidget()
        central.setObjectName("centralWidget")
        self.setCentralWidget(central)
        self._main_layout = QVBoxLayout(central)
        self._main_layout.setContentsMargins(0, 0, 0, 0)
        self._main_layout.setSpacing(0)

        # 비디오 프레임
        self._video_frame = QFrame()
        self._video_frame.setObjectName("videoFrame")
        self._video_frame.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding
        )
        self._video_frame.setMinimumHeight(300)
        self._main_layout.addWidget(self._video_frame, 1)

        # 초기 화면: 폴더 열기 안내
        self._setup_welcome_screen()

        # 정보 바
        self._info_bar = QWidget()
        self._info_bar.setObjectName("infoBar")
        info_layout = QHBoxLayout(self._info_bar)
        info_layout.setContentsMargins(16, 4, 16, 4)

        self._file_info_label = QLabel("")
        self._file_info_label.setObjectName("fileInfoLabel")

        self._stats_label = QLabel("")
        self._stats_label.setObjectName("infoLabel")
        self._stats_label.setAlignment(Qt.AlignmentFlag.AlignRight)

        info_layout.addWidget(self._file_info_label)
        info_layout.addStretch()
        info_layout.addWidget(self._stats_label)

        self._main_layout.addWidget(self._info_bar)
        self._info_bar.hide()

        # 컨트롤 바
        self._control_bar = ControlBar()
        self._control_bar.play_pause_clicked.connect(self._on_play_pause)
        self._control_bar.seek_requested.connect(self._on_seek)
        self._control_bar.speed_changed.connect(self._on_speed_changed)
        self._control_bar.skip_forward_clicked.connect(self._on_skip_forward)
        self._control_bar.skip_backward_clicked.connect(self._on_skip_backward)
        self._control_bar.volume_changed.connect(self._on_volume_changed)
        self._control_bar.show_corrupted_clicked.connect(self._show_corrupted_files_dialog)
        self._main_layout.addWidget(self._control_bar)
        self._control_bar.hide()

        # 상태바
        self._status_bar = QStatusBar()
        self.setStatusBar(self._status_bar)
        self._status_bar.showMessage("폴더를 열거나 드래그 앤 드롭하세요")

        # 드래그 앤 드롭 활성화
        self.setAcceptDrops(True)

        # UI 업데이트 타이머 (100ms 간격)
        self._update_timer = QTimer(self)
        self._update_timer.setInterval(100)
        self._update_timer.timeout.connect(self._update_ui)

    def _setup_welcome_screen(self):
        """초기 환영 화면 설정"""
        self._welcome_widget = QWidget(self._video_frame)
        self._welcome_widget.setObjectName("dropZone")
        welcome_layout = QVBoxLayout(self._welcome_widget)
        welcome_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        welcome_layout.setSpacing(20)

        # 아이콘
        icon_label = QLabel("📹")
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_label.setFont(QFont("Segoe UI", 48))
        welcome_layout.addWidget(icon_label)

        # 타이틀
        title_label = QLabel("HomeCam Player")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_label.setStyleSheet("color: #c9d1d9; font-size: 28px; font-weight: bold; font-family: 'Segoe UI';")
        welcome_layout.addWidget(title_label)

        # 설명
        desc_label = QLabel("홈캠 녹화 파일을 연속으로 재생합니다")
        desc_label.setObjectName("dropLabel")
        desc_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        welcome_layout.addWidget(desc_label)

        # 폴더 열기 버튼
        open_btn = QPushButton("📂  폴더 열기")
        open_btn.setObjectName("openFolderBtn")
        open_btn.clicked.connect(self._on_open_folder)
        welcome_layout.addWidget(open_btn, alignment=Qt.AlignmentFlag.AlignCenter)

        # 드래그 앤 드롭 안내
        drop_label = QLabel("또는 폴더를 여기로 드래그 앤 드롭")
        drop_label.setObjectName("dropLabel")
        drop_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        welcome_layout.addWidget(drop_label)

    def _load_stylesheet(self):
        """QSS 스타일시트 로드"""
        qss_path = Path(__file__).parent / "styles.qss"
        if qss_path.exists():
            with open(qss_path, 'r', encoding='utf-8') as f:
                self.setStyleSheet(f.read())

    def _setup_shortcuts(self):
        """키보드 단축키는 keyPressEvent에서 처리"""
        pass

    # ========== 폴더 로드 ==========

    def _on_open_folder(self):
        """폴더 열기 다이얼로그"""
        folder = QFileDialog.getExistingDirectory(
            self, "홈캠 녹화 폴더 선택", "",
            QFileDialog.Option.ShowDirsOnly
        )
        if folder:
            self._load_folder(folder)

    def _load_folder(self, folder_path: str):
        """폴더 로드 및 재생 시작"""
        try:
            self._status_bar.showMessage(f"폴더 스캔 중: {folder_path}")
            QApplication.processEvents()

            def on_progress(current, total):
                self._status_bar.showMessage(
                    f"파일 검증 중: {current}/{total}"
                )
                QApplication.processEvents()

            files = self._timeline_mgr.scan_directory(
                folder_path, progress_callback=on_progress
            )
            file_count = self._timeline_mgr.get_file_count()
            est_duration = self._timeline_mgr.get_estimated_duration_str()
            skipped = self._timeline_mgr.get_skipped_files()

            skip_msg = f" (손상 {len(skipped)}개 제외)" if skipped else ""
            self._status_bar.showMessage(
                f"{file_count}개 파일 로드됨{skip_msg} | 예상 길이: {est_duration}"
            )

            # 컨트롤 바에 손상된 파일 수 전달
            self._control_bar.set_corrupted_count(len(skipped))

            # 환영 화면 숨기고 UI 전환
            self._welcome_widget.hide()
            self._info_bar.show()
            self._control_bar.show()

            # mpv 플레이어 초기화
            if self._player:
                self._player.cleanup()

            wid = int(self._video_frame.winId())
            self._player = PlayerEngine(wid, self)

            # 시그널 연결
            self._player.position_changed.connect(self._on_position_changed)
            self._player.duration_changed.connect(self._on_duration_changed)
            self._player.file_changed.connect(self._on_file_changed)
            self._player.speed_changed.connect(self._on_speed_updated)

            # 플레이리스트 로드
            self._player.load_playlist(files)
            self._is_loaded = True

            # 시간 매핑 구성 (갭 감지)
            if self._timeline_mgr.build_time_map(gap_threshold=20.0):
                self._setup_real_time_mode()

            # UI 업데이트 타이머 시작
            self._update_timer.start()

            # 재생 버튼 상태 업데이트
            self._control_bar.update_play_button(True)
            self._stats_label.setText(
                f"파일: {file_count}개{skip_msg} | 예상: {est_duration}"
            )

        except Exception as e:
            self._status_bar.showMessage(f"오류: {str(e)}")

    def _setup_real_time_mode(self):
        """실제 시간 기반 타임라인 모드 설정"""
        tmgr = self._timeline_mgr
        real_dur = tmgr.get_real_total_duration()
        gap_count = tmgr.get_gap_count()
        total_gap = tmgr.get_total_gap_duration()

        # 컨트롤 바를 실제 시간 모드로 전환
        self._control_bar.set_real_time_mode(True)

        # 시크바에 갭 영역 전달
        seek_bar = self._control_bar.get_seek_bar()
        seek_bar.set_gap_regions(tmgr.get_gap_ratios())
        seek_bar.set_clock_time_callback(tmgr.offset_to_clock_time_str)

        # 시크바 duration을 실제 시간으로 설정
        start_clock = tmgr.offset_to_clock_time_str(0)
        end_clock = tmgr.offset_to_clock_time_str(real_dur)
        self._control_bar.update_duration(real_dur, end_clock)
        self._control_bar.update_position(0, start_clock)

        # 상태바에 갭 정보 표시
        if gap_count > 0:
            gap_min = int(total_gap // 60)
            gap_sec = int(total_gap % 60)
            gap_msg = f" | ⚠ 녹화 갭 {gap_count}개 ({gap_min}분 {gap_sec}초)"
        else:
            gap_msg = ""

        file_count = tmgr.get_file_count()
        self._status_bar.showMessage(
            f"{file_count}개 파일 | {start_clock} ~ {end_clock}{gap_msg}"
        )

    # ========== 플레이어 이벤트 핸들러 ==========

    def _on_position_changed(self, position: float):
        """재생 위치 변경 (mpv 시간 → 실제 시간 변환)"""
        tmgr = self._timeline_mgr
        if tmgr.has_time_map() and self._mpv_total_duration > 0:
            real_offset = tmgr.mpv_to_real_offset(position, self._mpv_total_duration)
            clock_str = tmgr.offset_to_clock_time_str(real_offset)
            self._control_bar.update_position(real_offset, clock_str)
        else:
            self._control_bar.update_position(position)

    def _on_duration_changed(self, duration: float):
        """전체 시간 변경 (mpv 보고)"""
        self._mpv_total_duration = duration
        tmgr = self._timeline_mgr
        if tmgr.has_time_map():
            # 실제 시간 기반 duration 사용
            real_dur = tmgr.get_real_total_duration()
            end_clock = tmgr.offset_to_clock_time_str(real_dur)
            self._control_bar.update_duration(real_dur, end_clock)
        else:
            self._control_bar.update_duration(duration)

    def _on_file_changed(self, filename: str):
        """현재 재생 파일 변경"""
        self._file_info_label.setText(f"📹 {filename}")

    def _on_speed_updated(self, speed: float):
        """배속 변경됨"""
        self._control_bar.update_speed_display(speed)
        self._status_bar.showMessage(f"배속: {speed}x", 2000)

    # ========== 컨트롤 이벤트 핸들러 ==========

    def _on_play_pause(self):
        """재생/일시정지"""
        if self._player and self._is_loaded:
            self._player.toggle_pause()
            self._control_bar.update_play_button(not self._player.is_paused())

    def _on_seek(self, position: float):
        """시크 요청 (실제 시간 → mpv 시간 변환)"""
        if self._player and self._is_loaded:
            tmgr = self._timeline_mgr
            if tmgr.has_time_map() and self._mpv_total_duration > 0:
                mpv_pos = tmgr.real_offset_to_mpv(position, self._mpv_total_duration)
                self._player.seek(mpv_pos)
            else:
                self._player.seek(position)

    def _on_speed_changed(self, speed: float):
        """배속 변경"""
        if self._player and self._is_loaded:
            self._player.set_speed(speed)

    def _on_skip_forward(self, seconds: float):
        """앞으로 건너뛰기"""
        if self._player and self._is_loaded:
            self._player.seek_relative(seconds)

    def _on_skip_backward(self, seconds: float):
        """뒤로 건너뛰기"""
        if self._player and self._is_loaded:
            self._player.seek_relative(-seconds)

    def _on_volume_changed(self, volume: int):
        """볼륨 변경"""
        if self._player:
            self._player.set_volume(volume)

    def _show_corrupted_files_dialog(self):
        """손상된 파일 목록을 보여주는 다이얼로그"""
        skipped = self._timeline_mgr.get_skipped_files()
        if not skipped:
            return
            
        dialog = QDialog(self)
        dialog.setWindowTitle("손상된 파일 목록")
        dialog.setMinimumSize(400, 300)
        
        layout = QVBoxLayout(dialog)
        
        label = QLabel(f"제외된 손상 파일: {len(skipped)}개")
        label.setStyleSheet("font-weight: bold; font-size: 14px; color: #ff8888;")
        layout.addWidget(label)
        
        list_widget = QListWidget()
        list_widget.setStyleSheet(
            "QListWidget { background-color: #1e1e1e; color: #cccccc; border: 1px solid #333333; padding: 4px; }"
            "QListWidget::item { padding: 4px; border-bottom: 1px solid #2a2a2a; }"
        )
        for f in skipped:
            folder_name = Path(f).parent.name
            file_name = Path(f).name
            list_widget.addItem(f"{folder_name}/{file_name}")
        layout.addWidget(list_widget)
        
        close_btn = QPushButton("닫기")
        close_btn.setFixedHeight(32)
        close_btn.setStyleSheet("""
            QPushButton {
                background-color: #333333;
                color: white;
                border: none;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #444444;
            }
        """)
        close_btn.clicked.connect(dialog.accept)
        layout.addWidget(close_btn)
        
        dialog.exec()

    def _update_ui(self):
        """주기적 UI 업데이트"""
        pass  # 현재 position_changed 시그널로 처리

    # ========== 키보드 이벤트 ==========

    def keyPressEvent(self, event: QKeyEvent):
        """키보드 단축키 처리"""
        if not self._player or not self._is_loaded:
            super().keyPressEvent(event)
            return

        key = event.key()

        if key == Qt.Key.Key_Space:
            self._on_play_pause()
        elif key == Qt.Key.Key_Left:
            self._on_skip_backward(10)
        elif key == Qt.Key.Key_Right:
            self._on_skip_forward(10)
        elif key == Qt.Key.Key_Up:
            self._player.cycle_speed_up()
        elif key == Qt.Key.Key_Down:
            self._player.cycle_speed_down()
        elif key == Qt.Key.Key_Home:
            self._on_seek(0)
        elif key == Qt.Key.Key_End:
            duration = self._player.get_duration()
            if duration > 0:
                self._on_seek(duration - 1)
        elif key == Qt.Key.Key_F:
            # 전체화면 토글
            if self.isFullScreen():
                self.showNormal()
            else:
                self.showFullScreen()
        elif key == Qt.Key.Key_Escape:
            if self.isFullScreen():
                self.showNormal()
        elif key == Qt.Key.Key_O:
            self._on_open_folder()
        else:
            super().keyPressEvent(event)

    # ========== 드래그 앤 드롭 ==========

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        urls = event.mimeData().urls()
        if urls:
            path = urls[0].toLocalFile()
            if Path(path).is_dir():
                self._load_folder(path)
            elif Path(path).is_file() and path.lower().endswith('.mp4'):
                # 파일의 상위 폴더를 로드
                self._load_folder(str(Path(path).parent))

    # ========== 리사이즈 ==========

    def resizeEvent(self, event):
        """리사이즈 시 환영 화면 크기 조정"""
        super().resizeEvent(event)
        if hasattr(self, '_welcome_widget') and self._welcome_widget.isVisible():
            self._welcome_widget.setGeometry(self._video_frame.rect())

    # ========== 종료 ==========

    def closeEvent(self, event):
        """종료 시 리소스 정리"""
        self._update_timer.stop()
        if self._player:
            self._player.cleanup()
        super().closeEvent(event)
