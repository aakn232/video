"""
HomeCam Player - Player Engine
mpv 기반 비디오 재생 엔진 래퍼
"""
import os
import sys
import tempfile
from pathlib import Path
from PyQt6.QtCore import QObject, pyqtSignal, QTimer

# libmpv DLL 경로를 환경변수에 추가 (프로젝트 루트의 mpv 폴더)
_project_dir = Path(__file__).parent
_mpv_dir = _project_dir / "mpv"
if _mpv_dir.exists():
    os.environ["PATH"] = str(_mpv_dir) + os.pathsep + os.environ.get("PATH", "")

import mpv


class PlayerEngine(QObject):
    """mpv 기반 비디오 재생 엔진"""

    # Qt 시그널 (UI 업데이트용)
    position_changed = pyqtSignal(float)   # 현재 위치 (초)
    duration_changed = pyqtSignal(float)   # 전체 길이 (초)
    file_changed = pyqtSignal(str)         # 현재 재생 파일명
    eof_reached = pyqtSignal()             # 전체 재생 끝
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
        self._playlist_file = None
        self._last_media_title = ""
        self._init_player()
        self._init_poll_timer()

    def _init_player(self):
        """mpv 플레이어 초기화"""
        self._player = mpv.MPV(
            wid=str(self._wid),
            merge_files='yes',          # 핵심: 여러 파일을 하나의 타임라인으로
            keep_open='yes',            # 마지막 파일 끝에서 플레이어 유지
            hr_seek='yes',              # 정밀 시크
            demuxer_max_bytes='150MiB', # 디먹서 버퍼
            cache='yes',                # 캐시 활성화
            cache_secs='120',           # 120초 캐시
            osc='no',                   # mpv 자체 OSD 컨트롤러 비활성화
            osd_level='0',              # OSD 비활성화
            input_default_bindings='no', # 기본 키바인딩 비활성화
            input_vo_keyboard='no',     # 비디오 출력 키보드 비활성화
            vo='gpu',                   # GPU 렌더링
            hwdec='auto',              # 하드웨어 디코딩 자동
            audio_client_name='HomeCamPlayer',  # 오디오 세션 이름
            loglevel='error',           # 에러만 출력
        )

    def _init_poll_timer(self):
        """
        GUI 스레드에서 mpv 프로퍼티를 폴링하는 타이머.
        mpv의 property observer는 mpv 스레드에서 호출되어 Qt와 충돌하므로,
        대신 타이머로 주기적으로 값을 읽습니다.
        """
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(50)  # 50ms = 20fps UI 업데이트
        self._poll_timer.timeout.connect(self._poll_properties)

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

            # 전체 길이
            dur = self._player.duration
            if dur is not None and abs(dur - self._duration) > 0.1:
                self._duration = dur
                self.duration_changed.emit(dur)

            # 현재 파일명
            title = self._player.media_title
            if title is not None and title != self._last_media_title:
                self._last_media_title = title
                self.file_changed.emit(title)

        except (Exception, KeyboardInterrupt):
            pass

    def load_playlist(self, file_list: list[str]):
        """파일 목록을 플레이리스트로 로드하여 재생 시작"""
        if not file_list:
            return

        # 플레이리스트 파일 생성 (절대 경로 사용)
        self._playlist_file = tempfile.NamedTemporaryFile(
            mode='w', suffix='.txt', delete=False, encoding='utf-8'
        )
        for f in file_list:
            abs_path = os.path.abspath(f)
            self._playlist_file.write(abs_path + '\n')
        self._playlist_file.close()

        # 플레이리스트 로드
        self._player.loadlist(self._playlist_file.name)
        self._is_paused = False

        # 폴링 타이머 시작
        self._poll_timer.start()

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

    def seek(self, position_seconds: float):
        """특정 시간(초)으로 이동"""
        if self._player:
            self._player.seek(position_seconds, reference='absolute')

    def seek_relative(self, offset_seconds: float):
        """현재 위치에서 상대적으로 이동"""
        if self._player:
            self._player.seek(offset_seconds, reference='relative')

    def set_speed(self, multiplier: float):
        """배속 설정"""
        if self._player:
            self._speed = multiplier
            self._player.speed = multiplier
            # speed index 동기화
            if multiplier in self.SPEED_OPTIONS:
                self._current_speed_index = self.SPEED_OPTIONS.index(multiplier)
            self.speed_changed.emit(multiplier)

    def cycle_speed_up(self):
        """배속 올리기 (다음 단계)"""
        if self._current_speed_index < len(self.SPEED_OPTIONS) - 1:
            self._current_speed_index += 1
            self.set_speed(self.SPEED_OPTIONS[self._current_speed_index])

    def cycle_speed_down(self):
        """배속 내리기 (이전 단계)"""
        if self._current_speed_index > 0:
            self._current_speed_index -= 1
            self.set_speed(self.SPEED_OPTIONS[self._current_speed_index])

    def get_position(self) -> float:
        """현재 재생 위치 (초)"""
        return self._position

    def get_duration(self) -> float:
        """전체 타임라인 길이 (초)"""
        return self._duration

    def get_speed(self) -> float:
        """현재 배속"""
        return self._speed

    def is_paused(self) -> bool:
        """일시정지 상태인지"""
        return self._is_paused

    def set_volume(self, volume: int):
        """볼륨 설정 (0-100)"""
        if self._player:
            self._player.volume = volume

    def cleanup(self):
        """리소스 정리"""
        self._poll_timer.stop()
        if self._player:
            self._player.terminate()
            self._player = None
        if self._playlist_file and os.path.exists(self._playlist_file.name):
            try:
                os.unlink(self._playlist_file.name)
            except Exception:
                pass
