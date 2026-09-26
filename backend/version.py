"""Single source of truth for the app version.

Bump __version__ before running `build.py --release`. Releases are published
to GitHub as tag v<__version__>, and installed copies of the app update
themselves from the latest release (see updater.py).
"""
__version__ = "2.1.0"

GITHUB_REPO = "knightmare04-boop/BirdStamp"
