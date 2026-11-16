"""Check the bundled OUI catalogue against the official IEEE registry.

The catalogue in :mod:`macspoofer.profiles` is curated by hand, so it is the
part of this tool most likely to be wrong: vendors are acquired, registries
grow, and a prefix typed from memory is a prefix that may belong to someone
else entirely. This module compares every bundled prefix against the IEEE MA-L
registry and reports the real registrant for any that disagree, so the
catalogue's accuracy is a thing you can measure rather than trust.

The registry is a public CSV published at
``https://standards-oui.ieee.org/oui/oui.csv``. It is only fetched when
``--download`` is passed; otherwise a local copy is read from ``--csv``.
"""

from __future__ import annotations

import csv
import io
import re
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

from macspoofer import oui, profiles

__all__ = ["VerifyError", "Finding", "Report", "load_registry", "verify_catalogue"]

IEEE_CSV_URL = "https://standards-oui.ieee.org/oui/oui.csv"
DOWNLOAD_TIMEOUT = 600.0

#: The MA-L registry held well over 30,000 assignments when this was written
#: and only ever grows. Far fewer than this means a partial file.
MIN_PLAUSIBLE_ROWS = 25_000

#: Long-standing assignments that any complete copy of the registry contains.
#: A truncated download is the common failure -- the file is several megabytes
#: fetched over a slow connection -- and it is indistinguishable from a real
#: result unless it is checked for: every prefix past the cut-off point simply
#: looks unregistered. Reporting that as "your catalogue is wrong" would be
#: worse than useless, so verification refuses to run on an incomplete file.
CANARY_PREFIXES: dict[str, str] = {
    "00:00:0c": "Cisco",
    "00:03:93": "Apple",
    "00:1b:63": "Apple",
    "08:00:27": "PCS Systemtechnik / Oracle VirtualBox",
    "00:0c:29": "VMware",
    "b8:27:eb": "Raspberry Pi",
    "00:15:5d": "Microsoft",
    "00:e0:4c": "Realtek",
}

# A deliberately generic client string: no user or machine detail is sent.
USER_AGENT = "macspoofer-oui-verify/1.0"

_WORD_RE = re.compile(r"[a-z0-9]+")

# Vendor names differ in form between the catalogue and the registry
# ("HP" vs "Hewlett Packard"); these let a match be recognised.
_ALIASES: dict[str, tuple[str, ...]] = {
    "hp": ("hewlett", "packard", "hp"),
    "apple": ("apple",),
    "google": ("google",),
    "amazon technologies": ("amazon",),
    "microsoft": ("microsoft",),
    "samsung": ("samsung",),
    "sony interactive entertainment": ("sony",),
    "lg electronics": ("lg",),
    "asustek": ("asustek", "asus"),
    "tp-link": ("tp", "link"),
    "d-link": ("d", "link"),
    "linksys / belkin": ("linksys", "belkin", "cisco"),
    "aruba networks": ("aruba", "hewlett", "packard"),
    "raspberry pi foundation / ltd": ("raspberry",),
    "signify (philips)": ("philips", "signify"),
    "hon hai / foxconn": ("hon", "hai", "foxconn"),
    "qualcomm atheros": ("qualcomm", "atheros"),
    "seiko epson": ("seiko", "epson"),
    # VirtualBox's 08:00:27 is registered to PCS Systemtechnik (via innotek/Sun).
    "oracle virtualbox": ("oracle", "virtualbox", "sun", "pcs", "systemtechnik"),
    "dahua technology": ("dahua",),
    "zebra technologies": ("zebra", "symbol"),
    "cisco systems": ("cisco",),
    "juniper networks": ("juniper",),
    "axis communications": ("axis",),
    "brother industries": ("brother",),
    "texas instruments": ("texas", "instruments"),
    "schneider electric": ("schneider", "telemecanique"),
    "rockwell automation": ("rockwell", "allen"),
    "phoenix contact": ("phoenix",),
    "motorola mobility": ("motorola",),
    # Registered under a parent, former or joint-venture name.
    "lg electronics": ("lg", "lge"),
    "lenovo": ("lenovo", "lenovoemc", "lcfc"),       # LCFC builds Lenovo laptops
    "panasonic": ("panasonic", "matsushita"),        # Matsushita was renamed Panasonic
    "mikrotik": ("mikrotik", "routerboard"),         # MikroTik registers as Routerboard.com
    "polycom": ("polycom", "poly"),                  # Polycom became Poly
    "xen": ("xen", "xensource"),
    "arduino": ("arduino", "gheo"),                  # Arduino shields: GHEO SA
    "bose": ("bose",),
}


class VerifyError(RuntimeError):
    """Raised when the IEEE registry cannot be loaded or looks incomplete."""


@dataclass(frozen=True)
class Finding:
    """One catalogue prefix that does not agree with the registry."""

    prefix: str
    profile_key: str
    expected: str
    actual: str


@dataclass
class Report:
    """Result of checking the whole catalogue."""

    checked: int = 0
    matched: int = 0
    mismatched: list[Finding] = field(default_factory=list)
    unknown: list[Finding] = field(default_factory=list)
    local: list[Finding] = field(default_factory=list)

    @property
    def clean(self) -> bool:
        return not self.mismatched and not self.unknown


def _tokens(name: str) -> set[str]:
    return set(_WORD_RE.findall(name.lower()))


def _fetch(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=DOWNLOAD_TIMEOUT) as response:  # noqa: S310
            return response.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        raise VerifyError(f"could not download {url}: {exc}") from exc


def load_registry(*, csv_path: str | None = None, download: bool = False) -> dict[str, str]:
    """Return a mapping of OUI prefix -> registered organisation name.

    Reads ``csv_path`` if given, otherwise downloads the registry when
    ``download`` is set. Nothing is fetched implicitly.
    """
    if csv_path:
        path = Path(csv_path).expanduser()
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            raise VerifyError(f"could not read {path}: {exc}") from exc
    elif download:
        text = _fetch(IEEE_CSV_URL)
    else:
        raise VerifyError(
            "give --csv with a local copy of the IEEE oui.csv, or --download to fetch it "
            f"from {IEEE_CSV_URL}"
        )

    registry: dict[str, str] = {}
    reader = csv.DictReader(io.StringIO(text))
    for row in reader:
        assignment = (row.get("Assignment") or "").strip()
        organisation = (row.get("Organization Name") or "").strip()
        if len(assignment) != 6 or not organisation:
            continue
        try:
            prefix = oui.normalise_oui(assignment)
        except oui.MacError:
            continue
        registry[prefix] = organisation
    if not registry:
        raise VerifyError("no usable rows found; is this the IEEE oui.csv?")
    check_complete(registry)
    return registry


def check_complete(registry: dict[str, str]) -> None:
    """Raise :class:`VerifyError` if *registry* is obviously partial.

    See :data:`CANARY_PREFIXES` for why this matters.
    """
    missing = [prefix for prefix in CANARY_PREFIXES if prefix not in registry]
    if len(registry) < MIN_PLAUSIBLE_ROWS or missing:
        detail = (
            f"only {len(registry)} assignments were parsed"
            if len(registry) < MIN_PLAUSIBLE_ROWS
            else f"{len(registry)} assignments were parsed"
        )
        if missing:
            named = ", ".join(f"{p} ({CANARY_PREFIXES[p]})" for p in missing[:4])
            detail += f", and these long-standing assignments are absent: {named}"
        raise VerifyError(
            f"the IEEE registry looks incomplete ({detail}). A truncated download is "
            "the usual cause -- every prefix past the cut-off would be misreported as "
            "unregistered, so no comparison was made. Re-download it and try again."
        )


def _agrees(expected_vendor: str, registered: str) -> bool:
    expected = expected_vendor.lower().strip()
    hints = _ALIASES.get(expected, tuple(_tokens(expected_vendor)))
    registered_tokens = _tokens(registered)
    return any(hint in registered_tokens for hint in hints)


def verify_catalogue(registry: dict[str, str]) -> Report:
    """Compare every catalogue prefix against *registry*."""
    report = Report()
    for prefix, profile in profiles.all_ouis():
        report.checked += 1
        normalised = oui.normalise_oui(prefix)

        # A locally administered prefix (U/L bit set) is not an IEEE assignment
        # and never appears in the registry. QEMU's 52:54:00 and Docker's
        # 02:42:ac are the real, documented defaults for those platforms, so
        # their absence is correct rather than a catalogue error.
        if int(normalised.split(":")[0], 16) & 0x02:
            report.local.append(
                Finding(normalised, profile.key, profile.vendor, "locally administered")
            )
            continue

        registered = registry.get(normalised)
        if registered is None:
            report.unknown.append(
                Finding(normalised, profile.key, profile.vendor, "not registered")
            )
            continue
        if _agrees(profile.vendor, registered):
            report.matched += 1
        else:
            report.mismatched.append(
                Finding(normalised, profile.key, profile.vendor, registered)
            )
    return report
