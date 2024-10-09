# run_workers.py

import dramatiq
from dramatiq.cli import main
import sys

if __name__ == "__main__":
    sys.argv = ["dramatiq", "dramatiq_tasks.image_tasks"]
    main()