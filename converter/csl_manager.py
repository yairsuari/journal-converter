from pathlib import Path
import urllib.request
import urllib.error

_REGISTRY = "https://raw.githubusercontent.com/citation-style-language/styles/master/{style}.csl"
_CSL_DIR = Path(__file__).parent.parent / "csl"


def get_csl(style: str) -> Path:
    """Return path to a CSL file, fetching from registry if possible."""
    pinned = _CSL_DIR / f"{style}.csl"

    url = _REGISTRY.format(style=style)
    try:
        with urllib.request.urlopen(url, timeout=8) as resp:
            content = resp.read()
        _CSL_DIR.mkdir(exist_ok=True)
        pinned.write_bytes(content)
        return pinned
    except (urllib.error.URLError, OSError):
        pass

    if pinned.exists():
        print(f"[warning] Could not fetch '{style}' from CSL registry — using pinned version.")
        return pinned

    raise FileNotFoundError(
        f"CSL style '{style}' not found locally and could not be fetched.\n"
        f"Download it from https://github.com/citation-style-language/styles "
        f"and place it at: {pinned}"
    )
