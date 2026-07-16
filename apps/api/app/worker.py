"""Outbox worker entrypoint: ``python -m app.worker``.

Importing :mod:`app.handlers` registers every domain's event handlers before the
delivery loop starts.
"""

from __future__ import annotations

import logging
import os
import socket

import app.handlers  # noqa: F401  (registers outbox handlers on import)
from app.platform.outbox.worker import run_forever


def main() -> None:  # pragma: no cover - process entrypoint
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    worker_id = f"{socket.gethostname()}-{os.getpid()}"
    run_forever(worker_id)


if __name__ == "__main__":  # pragma: no cover
    main()
