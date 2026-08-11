from __future__ import annotations

import logging
import time

from .config import get_settings
from .db import Base, make_engine, make_session_factory
from .discovery import claim_run, process_run
from .models import *  # noqa: F401,F403
from .security import CryptoBox

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def main() -> None:
    settings = get_settings()
    engine = make_engine(settings.database_url)
    if settings.app_env != "production":
        Base.metadata.create_all(engine)
    factory = make_session_factory(engine)
    crypto = CryptoBox(settings.data_encryption_key)
    while True:
        with factory() as db:
            run = claim_run(db)
            if run:
                logging.info("processing discovery run %s for user %s", run.id, run.user_id)
                process_run(db, run, settings, crypto)
                logging.info("completed discovery run %s with status %s", run.id, run.status)
            else:
                time.sleep(3)


if __name__ == "__main__":
    main()
