"""winutf8.py — on Windows, make sure Python reads and writes files as UTF-8.

Python on Windows uses an older character set unless "UTF-8 mode" is on, and the tools write characters like
the ¢, en dashes, × and ▲ arrows. setup_machine.py switches UTF-8 mode on for good (PYTHONUTF8=1); until then
ensure() quietly runs the script again in UTF-8 mode. On a Mac it does nothing.
"""

import os
import subprocess
import sys


def ensure():
    if os.name == "nt" and not sys.flags.utf8_mode:
        sys.exit(subprocess.run([sys.executable, "-X", "utf8", *sys.argv]).returncode)
