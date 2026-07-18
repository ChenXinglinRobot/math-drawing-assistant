import sys

import PySide6
import PySide6.QtCore


def main() -> None:
    print("Python 版本：")
    print(sys.version)

    print("\nPython 可执行文件：")
    print(sys.executable)

    print("\nPySide6 版本：")
    print(PySide6.__version__)

    print("\nQt 版本：")
    print(PySide6.QtCore.__version__)


if __name__ == "__main__":
    main()