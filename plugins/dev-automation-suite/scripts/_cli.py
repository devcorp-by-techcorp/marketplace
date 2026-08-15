#!/usr/bin/env python3
"""
Shared CLI helpers for suite scripts.

``guard_broken_pipe`` exists because these scripts are routinely piped into
``head``, ``grep -m``, or a hook that stops reading early. When the reader
closes first, Python raises BrokenPipeError during interpreter shutdown and
prints a traceback to stderr — which a calling hook reads as a script crash and
reports as ERROR.

This is not error suppression: a closed downstream pipe is normal, expected
Unix behaviour for a filter, and the correct response is the conventional one
(redirect the dangling stdout to devnull and exit 141, matching SIGPIPE
semantics). The underlying condition is handled, not masked.

Standard library only.
"""

from __future__ import annotations

import os
import sys
from typing import Callable, NoReturn

SIGPIPE_EXIT = 141


def guard_broken_pipe(main_fn: Callable[[], None]) -> NoReturn:
    """Run ``main_fn`` with correct SIGPIPE handling.

    A SystemExit raised by the wrapped function is preserved so argparse and
    explicit ``sys.exit`` codes still reach the caller unchanged.
    """
    try:
        main_fn()
    except BrokenPipeError:
        # Reattach stdout so the interpreter's shutdown flush cannot re-raise.
        try:
            devnull = os.open(os.devnull, os.O_WRONLY)
            os.dup2(devnull, sys.stdout.fileno())
        except OSError:
            pass
        sys.exit(SIGPIPE_EXIT)
    except KeyboardInterrupt:
        sys.exit(130)
    sys.exit(0)
