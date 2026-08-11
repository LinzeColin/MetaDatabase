from __future__ import annotations

import logging
import time

from .config import get_settings
from .db import Base, make_engine, make_session_factory
from .discovery import enqueue_due_profiles
from .models import *  # noqa: F401,F403

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def main() -> None:
    settings = get_settings()
    engine = make_engine(settings.database_url)
    if settings.app_env != "production":
        Base.metadata.create_all(engine)
    factory = make_session_factory(engine)
    while True:
        with factory() as db:
            count = enqueue_due_profiles(db)
            if count:
                logging.info("enqueued %s due discovery run(s)", count)
        time.sleep(60)


if __name__ == "__main__":
    main()
