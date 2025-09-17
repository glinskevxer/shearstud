"""Persistence: the book of record and the repositories over it."""

from __future__ import annotations

from shearstud.store.db import connect, transaction

__all__ = ["connect", "transaction"]
