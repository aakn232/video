"""
HomeCam Player - Timeline Manager
MP4 파일 스캔, 정렬, 플레이리스트 생성, 시간 갭 감지를 담당하는 모듈
"""
import os
import re
import struct
from pathlib import Path
from dataclasses import dataclass
from datetime import datetime
from natsort import natsorted


def is_valid_mp4(filepath: str) -> bool:
    """
    MP4 파일의 유효성을 빠르게 검사.
    moov atom이 존재하는지 확인하여 손상된 파일을 걸러냄.
    """
    try:
        with open(filepath, 'rb') as f:
            file_size = os.path.getsize(filepath)
            if file_size < 8:
                return False

            pos = 0
            while pos < file_size:
                f.seek(pos)
                header = f.read(8)
                if len(header) < 8:
                    return False

                size = struct.unpack('>I', header[:4])[0]
                atom_type = header[4:8]

                if atom_type == b'moov':
                    return True

                if size == 0:
                    # atom이 파일 끝까지 확장
                    return False
                if size == 1:
                    # 64비트 확장 크기
                    ext_header = f.read(8)
                    if len(ext_header) < 8:
                        return False
                    size = struct.unpack('>Q', ext_header)[0]

                if size < 8:
                    return False

                pos += size

        return False
    except Exception:
        return False


@dataclass
class FileSegment:
    """하나의 녹화 파일 세그먼트 정보"""
    file_path: str
    unix_timestamp: int
    real_offset: float      # 첫 파일 타임스탬프 기준 경과 초
    file_index: int          # 정렬된 파일 목록 내 인덱스


@dataclass
class TimeGap:
    """녹화 갭(빈 시간 영역) 정보"""
    real_start: float       # 갭 시작 (첫 파일 기준 경과 초)
    real_end: float         # 갭 끝
    duration: float         # 갭 길이 (초)


class TimelineManager:
    """MP4 파일 스캔, 정렬, 플레이리스트 생성, 시간 갭 감지"""

    ESTIMATED_FILE_DURATION = 60.0  # 1분 파일 기준

    def __init__(self):
        self._files: list[str] = []
        self._skipped_files: list[str] = []
        self._folder_path: str = ""
        # 시간 매핑 관련
        self._segments: list[FileSegment] = []
        self._gaps: list[TimeGap] = []
        self._first_timestamp: int = 0
        self._real_total_duration: float = 0.0
        self._has_time_map: bool = False

    def scan_directory(self, folder_path: str, progress_callback=None) -> list[str]:
        """
        폴더 내 MP4 파일을 스캔하고 시간순으로 정렬하여 반환.
        손상된 파일(moov atom 누락)은 자동으로 제외됩니다.

        홈캠 파일 구조:
          폴더명: YYYYMMDDHH (예: 2026040212 = 2026년 4월 2일 12시)
          파일명: MMmSSs_유닉스타임스탬프.mp4 (예: 00M59S_1775098859.mp4)

        정렬 로직: 폴더명(시간) + 파일명(분초)으로 자연 정렬
        """
        self._folder_path = folder_path
        self._files = []
        self._skipped_files = []

        folder = Path(folder_path)
        if not folder.exists():
            raise FileNotFoundError(f"폴더를 찾을 수 없습니다: {folder_path}")

        # 하위 폴더 포함하여 MP4 파일 수집
        mp4_files = []
        for root, dirs, files in os.walk(folder):
            for f in files:
                if f.lower().endswith('.mp4'):
                    full_path = os.path.join(root, f)
                    mp4_files.append(full_path)

        if not mp4_files:
            raise ValueError(f"MP4 파일을 찾을 수 없습니다: {folder_path}")

        # 자연 정렬 (폴더명 + 파일명 기준으로 시간순 정렬)
        sorted_files = natsorted(mp4_files)

        # MP4 유효성 검사 (손상된 파일 필터링)
        valid_files = []
        total = len(sorted_files)
        for i, fpath in enumerate(sorted_files):
            if is_valid_mp4(fpath):
                valid_files.append(fpath)
            else:
                self._skipped_files.append(fpath)
            if progress_callback:
                progress_callback(i + 1, total)

        if not valid_files:
            raise ValueError(f"유효한 MP4 파일을 찾을 수 없습니다: {folder_path}")

        self._files = valid_files
        return self._files

    def get_skipped_files(self) -> list[str]:
        """건너뛴 (손상된) 파일 목록 반환"""
        return self._skipped_files

    def get_files(self) -> list[str]:
        """현재 로드된 파일 목록 반환"""
        return self._files

    def get_file_count(self) -> int:
        """로드된 파일 수 반환"""
        return len(self._files)

    def get_estimated_duration_seconds(self) -> float:
        """예상 총 재생 시간 (초) - 파일 수 × 60초 기준"""
        return len(self._files) * 60.0

    def get_estimated_duration_str(self) -> str:
        """예상 총 재생 시간 문자열 (HH:MM:SS)"""
        total_seconds = self.get_estimated_duration_seconds()
        return format_time(total_seconds)

    def get_folder_path(self) -> str:
        """현재 폴더 경로 반환"""
        return self._folder_path

    def get_file_info(self, file_path: str) -> dict:
        """
        파일 경로에서 시간 정보를 추출.
        반환: {'folder_hour': str, 'minute': str, 'second': str, 'timestamp': str, 'display_name': str}
        """
        path = Path(file_path)
        filename = path.stem  # 확장자 제외
        parent_name = path.parent.name

        info = {
            'folder_hour': parent_name,
            'minute': '',
            'second': '',
            'timestamp': '',
            'display_name': f"{parent_name}/{path.name}"
        }

        # 파일명에서 분, 초, 타임스탬프 추출
        match = re.match(r'(\d+)M(\d+)S_(\d+)', filename)
        if match:
            info['minute'] = match.group(1)
            info['second'] = match.group(2)
            info['timestamp'] = match.group(3)

        return info

    # ========== 시간 매핑 및 갭 감지 ==========

    def build_time_map(self, gap_threshold: float = 20.0) -> bool:
        """
        파일명의 유닉스 타임스탬프를 기반으로 시간 매핑 테이블을 생성하고 갭을 감지.

        Args:
            gap_threshold: 연속 파일 간 예상 간격(~60초)을 제외한 추가 갭이
                           이 값(초)을 초과하면 녹화 중단으로 판별.
        Returns:
            bool: 시간 매핑 테이블 생성 성공 여부
        """
        if not self._files:
            return False

        self._segments = []
        self._gaps = []
        self._has_time_map = False

        # 파일별 타임스탬프 추출
        file_timestamps: list[tuple[int, str, int]] = []
        for i, fpath in enumerate(self._files):
            info = self.get_file_info(fpath)
            ts_str = info.get('timestamp', '')
            if ts_str and ts_str.isdigit():
                file_timestamps.append((i, fpath, int(ts_str)))
            else:
                return False  # 타임스탬프 없는 파일 → 시간 매핑 불가

        if not file_timestamps:
            return False

        file_timestamps.sort(key=lambda x: x[2])
        self._first_timestamp = file_timestamps[0][2]

        # 세그먼트 생성
        for idx, (file_idx, fpath, ts) in enumerate(file_timestamps):
            self._segments.append(FileSegment(
                file_path=fpath,
                unix_timestamp=ts,
                real_offset=float(ts - self._first_timestamp),
                file_index=idx,
            ))

        # 갭 감지: (다음 파일 시작 - 현재 파일 시작 - 예상 파일 길이) > threshold
        for i in range(len(self._segments) - 1):
            curr = self._segments[i]
            next_seg = self._segments[i + 1]
            time_diff = next_seg.unix_timestamp - curr.unix_timestamp
            gap_extra = time_diff - self.ESTIMATED_FILE_DURATION

            if gap_extra > gap_threshold:
                gap_start = curr.real_offset + self.ESTIMATED_FILE_DURATION
                gap_end = next_seg.real_offset
                self._gaps.append(TimeGap(
                    real_start=gap_start,
                    real_end=gap_end,
                    duration=gap_end - gap_start,
                ))

        last_seg = self._segments[-1]
        self._real_total_duration = last_seg.real_offset + self.ESTIMATED_FILE_DURATION
        self._has_time_map = True
        return True

    def has_time_map(self) -> bool:
        return self._has_time_map

    def get_segments(self) -> list[FileSegment]:
        return self._segments

    def get_gaps(self) -> list[TimeGap]:
        return self._gaps

    def get_gap_count(self) -> int:
        return len(self._gaps)

    def get_total_gap_duration(self) -> float:
        """전체 갭 시간 합계 (초)"""
        return sum(g.duration for g in self._gaps)

    def get_real_total_duration(self) -> float:
        """갭 포함 전체 실제 시간 길이 (초)"""
        return self._real_total_duration

    def get_first_timestamp(self) -> int:
        return self._first_timestamp

    def get_gap_ratios(self) -> list[dict]:
        """시크바 시각화를 위한 갭 위치 비율 반환"""
        if not self._has_time_map or self._real_total_duration <= 0:
            return []
        return [
            {
                'start': gap.real_start / self._real_total_duration,
                'end': gap.real_end / self._real_total_duration,
                'duration': gap.duration,
            }
            for gap in self._gaps
        ]

    def mpv_to_real_offset(self, mpv_seconds: float, mpv_total_duration: float) -> float:
        """mpv 재생 위치 → 실제 시간 오프셋 변환"""
        if not self._has_time_map or not self._segments or mpv_total_duration <= 0:
            return mpv_seconds
        n = len(self._segments)
        avg = mpv_total_duration / n
        idx = max(0, min(int(mpv_seconds / avg), n - 1))
        offset_in_file = max(0.0, mpv_seconds - idx * avg)
        return self._segments[idx].real_offset + offset_in_file

    def real_offset_to_mpv(self, real_offset: float, mpv_total_duration: float) -> float:
        """실제 시간 오프셋 → mpv 재생 위치 변환 (갭이면 갭 다음 세그먼트로 스냅)"""
        if not self._has_time_map or not self._segments or mpv_total_duration <= 0:
            return real_offset

        n = len(self._segments)
        avg = mpv_total_duration / n

        # 갭 영역인지 확인 → 갭 이후 세그먼트로 스냅
        for gap in self._gaps:
            if gap.real_start <= real_offset < gap.real_end:
                for seg in self._segments:
                    if seg.real_offset >= gap.real_end:
                        real_offset = seg.real_offset
                        break
                break

        # 해당 real_offset에 가장 가까운 세그먼트 찾기
        target_idx = 0
        for i, seg in enumerate(self._segments):
            if seg.real_offset <= real_offset:
                target_idx = i
            else:
                break

        offset_in_file = max(0.0, real_offset - self._segments[target_idx].real_offset)
        return target_idx * avg + offset_in_file

    def offset_to_clock_time_str(self, real_offset: float) -> str:
        """실제 시간 오프셋 → 시계 시간 문자열 (HH:MM:SS, 24시간제)"""
        if not self._has_time_map or self._first_timestamp == 0:
            return format_time(real_offset)
        ts = self._first_timestamp + real_offset
        return datetime.fromtimestamp(ts).strftime("%H:%M:%S")


def format_time(seconds: float) -> str:
    """초를 HH:MM:SS 형식으로 변환"""
    if seconds is None or seconds < 0:
        return "00:00:00"
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"
