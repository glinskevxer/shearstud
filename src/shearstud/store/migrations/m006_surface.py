"""The riding surface, which was a command line option and belongs on the deck.

The dynamic allowance a legal load rating uses depends on how rough the deck
is, and this package has always known that: the allowance table has three
entries and the rate command has a ``--surface`` option to pick between them.
What it did not have was anywhere to write the answer down, so every rating
started from the default and an engineer who knew the deck was rough had to
remember to say so, every time, or quietly rate a rough deck as an average one
and come out eleven per cent high on the live load.

It is a property of the structure, it is observed on an inspection, and it goes
in the structures table beside the condition rating for the same reason that
does.

Existing rows get ``minor``, which is what the option defaulted to, so no
rating that has already been worked changes because of this migration.
"""

from __future__ import annotations

from typing import Final

VERSION: Final[int] = 6
NAME: Final[str] = "surface"

UP: Final[str] = """
ALTER TABLE structures ADD COLUMN riding_surface TEXT NOT NULL DEFAULT 'minor';

CREATE INDEX structures_by_surface
    ON structures (riding_surface);
"""
