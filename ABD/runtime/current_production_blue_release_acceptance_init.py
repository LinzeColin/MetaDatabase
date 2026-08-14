"""Minimal package namespace for ABD's frozen infrastructure-only entrypoint.

This release-local initializer deliberately avoids importing the source tree's
full acceptance-oracle aggregator. The associated systemd unit invokes only
``python -m abd_acceptance.infrastructure_iac``; that direct module imports
its own verified dependencies explicitly.
"""
