"""
HomeCam Player - 홈캠 녹화본 연속 재생 플레이어

사용법:
  python main.py                    # GUI에서 폴더 선택
  python main.py <폴더경로>          # 지정 폴더 바로 로드
"""
import sys
import os
from pathlib import Path

# 프로젝트 루트를 sys.path에 추가
project_dir = Path(__file__).parent
sys.path.insert(0, str(project_dir))

# libmpv DLL 경로를 환경변수에 추가
mpv_dir = project_dir / "mpv"
if mpv_dir.exists():
    os.environ["PATH"] = str(mpv_dir) + os.pathsep + os.environ.get("PATH", "")

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont

from ui.main_window import MainWindow


def main():
    # High DPI 지원
    os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "1"

    app = QApplication(sys.argv)
    app.setApplicationName("HomeCam Player")
    app.setApplicationDisplayName("🏠 HomeCam Player")

    # 기본 폰트 설정
    font = QFont("Segoe UI", 10)
    app.setFont(font)

    # 커맨드라인 인자로 폴더 경로 전달
    initial_folder = None
    if len(sys.argv) > 1:
        folder_path = sys.argv[1]
        if Path(folder_path).is_dir():
            initial_folder = folder_path

    # 메인 윈도우 생성 및 표시
    window = MainWindow(initial_folder=initial_folder)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
