"""
HomeCam Player - Player Engine
mpv 기반 비디오 재생 엔진 래퍼
"""
import os
import sys
import tempfile
from pathlib import Path
from PyQt6.QtCore import QObject, pyqtSignal, QTimer

# libmpv DLL 경로를 환경변수에 추가 (프로젝트 루트의 libmpv 폴더)
_project_dir = Path(__file__).parent
_mpv_dir = _project_dir / "libmpv"
if _mpv_dir.exists():
    # PATH에 추가 (python-mpv 내부 체크용)
    os.environ["PATH"] = str(_mpv_dir) + os.pathsep + os.environ.get("PATH", "")
    
    # Python 3.8+ Windows용 DLL 로드 디렉토리 추가
    if sys.platform == 'win32' and hasattr(os, 'add_dll_directory'):
        os.add_dll_directory(str(_mpv_dir))

import mpv


class PlayerEngine(QObject):
    """mpv 기반 비디오 재생 엔진"""

    # Qt 시그널 (UI 업데이트용)
    position_changed = pyqtSignal(float)   # 현재 위치 (초)
    duration_changed = pyqtSignal(float)   # 전체 길이 (초)
    file_changed = pyqtSignal(str)         # 현재 재생 파일명
    segment_end_reached = pyqtSignal()     # 현재 파일 재생 끝
    speed_changed = pyqtSignal(float)      # 배속 변경됨

    SPEED_OPTIONS = [1.0, 2.0, 4.0, 8.0, 16.0]

    def __init__(self, wid: int, parent=None):
        super().__init__(parent)
        self._wid = wid
        self._player = None
        self._duration = 0.0
        self._position = 0.0
        self._is_paused = True
        self._speed = 1.0
        self._current_speed_index = 0
        self._file_list = []
        self._current_file_index = -1
        self._pending_file_index = -1
        self._last_media_title = ""
        self._expected_file_path = ""
        self._pending_seek_pos = -1.0
        self._pending_should_play = False
        self._pending_seek_precise = True
        self._init_player()
        self._init_poll_timer()

    def _on_mpv_event(self, event):
        """mpv 이벤트 핸들러"""
        if event.event_id == mpv.MpvEventID.END_FILE:
            self.segment_end_reached.emit()

    def _init_player(self):
        """mpv 플레이어 초기화"""
        self._player = mpv.MPV(
            wid=str(self._wid),
            # merge_files='yes',          # 제거: 수천 개 파일 로드 시 크래시 원인
            keep_open='yes',            # 파일 끝에서 플레이어 유지
            hr_seek='no',               # 빠른 시크 (스크러빙 성능 향상)
            demuxer_max_bytes='150MiB', # 디먹서 버퍼
            cache='yes',                # 캐시 활성화
            cache_secs='60',            # 60초 캐시
            osc='no',                   # mpv 자체 OSD 컨트롤러 비활성화
            osd_level='0',              # OSD 비활성화
            input_default_bindings='no', # 기본 키바인딩 비활성화
            input_vo_keyboard='no',     # 비디오 출력 키보드 비활성화
            vo='gpu',                   # GPU 렌더링
            hwdec='auto-safe',          # 보다 안전한 하드웨어 디코딩
            audio_client_name='HomeCamPlayer',
            loglevel='error',
        )

        # 이벤트 콜백 등록 (직접 등록 방식 사용으로 안정성 확보)
        self._player.register_event_callback(self._on_mpv_event)

    def _init_poll_timer(self):
        """GUI 스레드에서 mpv 프로퍼티를 폴링하는 타이머"""
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(20)  # 빠른 스크럽 반영을 위한 폴링 주기
        self._poll_timer.timeout.connect(self._poll_properties)

    def _seek_absolute(self, position_seconds: float, precise: bool) -> None:
        """절대 위치 시크 (드래그 중 keyframe, 최종 exact)"""
        if not self._player:
            return
        mode = "exact" if precise else "keyframes"
        self._player.command("seek", max(0.0, position_seconds), "absolute", mode)

    def _poll_properties(self):
        """mpv 프로퍼티를 주기적으로 폴링"""
        if not self._player:
            return

        try:
            # 현재 위치
            pos = self._player.time_pos
            if pos is not None and abs(pos - self._position) > 0.01:
                self._position = pos
                self.position_changed.emit(pos)

            # 전체 길이 (현재 파일 기준)
            dur = self._player.duration
            if dur is not None and abs(dur - self._duration) > 0.1:
                self._duration = dur
                self.duration_changed.emit(dur)

            # 현재 파일명
            title = self._player.media_title
            if title is not None and title != self._last_media_title:
                self._last_media_title = title
                self.file_changed.emit(title)

            # 지연된 시크 처리 (파일 로딩 완료 후 수행)
            self._handle_pending_seek()

        except Exception:
            pass

    def _handle_pending_seek(self):
        """파일이 실제로 로드된 후 예약된 시크 수행"""
        if self._pending_seek_pos < 0 or not self._player:
            return

        # 현재 로드된 파일 경로 확인
        try:
            current_path = self._player.path
            if not current_path or os.path.abspath(current_path) != self._expected_file_path:
                return  # 아직 파일이 바뀌지 않음

            if self._pending_file_index >= 0:
                self._current_file_index = self._pending_file_index
                self._pending_file_index = -1
            
            # 시크 수행
            target_pos = self._pending_seek_pos
            should_play = self._pending_should_play
            seek_precise = self._pending_seek_precise
            self._pending_seek_pos = -1.0
            
            self._seek_absolute(target_pos, precise=seek_precise)
            self._player.pause = not should_play
            self._is_paused = not should_play
        except Exception:
            pass

    def load_playlist(self, file_list: list[str]):
        """파일 목록 저장 (실제 로드는 load_file_index에서 수행)"""
        if not file_list:
            return
        self._file_list = file_list
        self._current_file_index = -1
        self._poll_timer.start()

    def load_file_index(
        self,
        index: int,
        start_pos: float = 0.0,
        should_play: bool = True,
        precise_seek: bool = True,
    ):
        """특정 인덱스의 파일을 로드하고 지정된 위치로 시크"""
        if not (0 <= index < len(self._file_list)):
            return

        file_path = os.path.abspath(self._file_list[index])

        # 같은 파일 로드 대기 중이면 최신 시크 값만 갱신
        if (
            self._pending_file_index == index
            and self._expected_file_path == file_path
            and self._pending_seek_pos >= 0
        ):
            self._pending_seek_pos = start_pos
            self._pending_should_play = should_play
            self._pending_seek_precise = precise_seek
            return

        self._pending_file_index = index
        self._expected_file_path = file_path
        
        # 파일 로드 예약
        self._pending_seek_pos = start_pos
        self._pending_should_play = should_play
        self._pending_seek_precise = precise_seek
        
        # 파일 로드 (replace 모드)
        try:
            self._player.loadfile(file_path, mode='replace')
        except Exception:
            self._pending_seek_pos = -1.0
            self._pending_file_index = -1

    def play(self):
        """재생"""
        if self._player:
            self._player.pause = False
            self._is_paused = False

    def pause(self):
        """일시정지"""
        if self._player:
            self._player.pause = True
            self._is_paused = True

    def toggle_pause(self):
        """재생/일시정지 토글"""
        if self._player:
            self._is_paused = not self._is_paused
            self._player.pause = self._is_paused

    def seek(self, position_seconds: float, precise: bool = True):
        """현재 재생 중인 파일 내에서 특정 시간(초)으로 이동"""
        if not self._player:
            return
            
        try:
            # mpv가 아이들 상태이거나 파일이 로드되지 않은 상태에서 시크 요청 시 크래시 방지
            if self._player.path:
                self._seek_absolute(position_seconds, precise=precise)
        except Exception:
            pass

    def seek_relative(self, offset_seconds: float):
        """현재 위치에서 상대적으로 이동"""
        if not self._player:
            return
            
        try:
            if self._player.path:
                self._player.seek(offset_seconds, reference='relative')
        except Exception:
            pass

    def set_speed(self, multiplier: float):
        """배속 설정"""
        if self._player:
            self._speed = multiplier
            self._player.speed = multiplier
            if multiplier in self.SPEED_OPTIONS:
                self._current_speed_index = self.SPEED_OPTIONS.index(multiplier)
            self.speed_changed.emit(multiplier)

    def cycle_speed_up(self):
        if self._current_speed_index < len(self.SPEED_OPTIONS) - 1:
            self._current_speed_index += 1
            self.set_speed(self.SPEED_OPTIONS[self._current_speed_index])

    def cycle_speed_down(self):
        if self._current_speed_index > 0:
            self._current_speed_index -= 1
            self.set_speed(self.SPEED_OPTIONS[self._current_speed_index])

    def get_position(self) -> float:
        return self._position

    def get_duration(self) -> float:
        return self._duration

    def get_current_index(self) -> int:
        return self._current_file_index

    def is_paused(self) -> bool:
        return self._is_paused

    def set_volume(self, volume: int):
        if self._player:
            self._player.volume = volume

    def cleanup(self):
        """리소스 정리"""
        self._poll_timer.stop()
        if self._player:
            self._player.terminate()
            self._player = None

