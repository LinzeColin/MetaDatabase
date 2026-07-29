"""Public S06/P01 Gmail OAuth entry point.

The implementation lives in ``abd_acceptance.gmail_oauth_core`` so the zero
cash dependency scanner can distinguish this repository-local module from a
third-party package.  This facade intentionally exports no network client and
performs no Gmail operation on import.
"""

from abd_acceptance.gmail_oauth_core import *  # noqa: F403
