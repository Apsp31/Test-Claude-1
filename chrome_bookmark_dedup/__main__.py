"""Allow running as: python -m chrome_bookmark_dedup [--gui]"""

import sys


def _main():
    if "--gui" in sys.argv:
        from .gui import run_gui
        run_gui()
    else:
        from .main import main
        sys.exit(main())


_main()
