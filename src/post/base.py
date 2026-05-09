"""Post-processor Protocol.

Every vendor post-processor (ABB RAPID, KUKA KRL, UR Script, ...) implements
this contract: take a vendor-neutral :class:`~src.motion.ir.Program` and emit
a string of source code in the target dialect. The vendor file extension is
exposed as a class attribute so callers can choose the right suffix when
writing to disk.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from src.motion.ir import Program


@runtime_checkable
class Post(Protocol):
    """Vendor post-processor contract."""

    name: str
    """Short identifier, e.g. ``"abb_rapid"``."""

    file_extension: str
    """Target source file extension, e.g. ``".mod"``."""

    def emit(self, program: Program) -> str:
        """Translate ``program`` into vendor source code as a single string."""
        ...

    def emit_to_file(self, program: Program, path: str) -> None:
        """Convenience helper: ``emit`` to a string and write to ``path``."""
        ...


__all__ = ["Post"]
