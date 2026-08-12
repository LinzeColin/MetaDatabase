"""CLI wrapper for the local S16/P02 frozen model evaluator."""

SOURCE_ARTIFACT_ID = "ART-S16-P02-01"

from abd_acceptance.model_eval_engine import main


if __name__ == "__main__":
    raise SystemExit(main())
