"""Enable ``python -m flowbio.cli`` to run the CLI."""
from __future__ import annotations

import sys

from flowbio.cli import main

if __name__ == "__main__":
    sys.exit(main())
