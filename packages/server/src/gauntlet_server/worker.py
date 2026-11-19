"""Worker process. Stub until P1-9 adds the claim loop; keep `python -m gauntlet_server.worker`."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import signal

__all__ = ["main"]

log = logging.getLogger("gauntlet.worker")


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop.set)
    log.info("worker started")
    while not stop.is_set():
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=5)
    log.info("worker stopping")


if __name__ == "__main__":
    asyncio.run(main())
