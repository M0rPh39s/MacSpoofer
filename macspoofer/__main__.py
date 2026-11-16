"""Allow ``python -m macspoofer`` to work identically to the ``macspoofer`` script."""

from macspoofer.cli import main

if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
