# MacSpoofer

> Created by **M0rPh39s** · https://github.com/M0rPh39s/MacSpoofer

**MacSpoofer** changes a network interface's MAC address so the machine presents
itself as a different *class of device*. Start it with no arguments and it asks
which interface to change and what you want to look like — a Raspberry Pi, an
iPhone, a Hikvision camera, a Cisco switch, a PlayStation 5 — then builds an
address inside that vendor's registered OUI range and verifies the change
actually took effect.

```
sudo macspoofer
```

```
 __  __             _____                    __
|  \/  |           / ____|                  / _|
| \  / | __ _  ___| (___  _ __   ___   ___ | |_ ___ _ __
| |\/| |/ _` |/ __|\___ \| '_ \ / _ \ / _ \|  _/ _ \ '__|
| |  | | (_| | (__ ____) | |_) | (_) | (_) | ||  __/ |
|_|  |_|\__,_|\___|_____/| .__/ \___/ \___/|_| \___|_|
                         | |
                         |_|

MAC address spoofing with real device profiles
Created by M0rPh39s  •  https://github.com/M0rPh39s/MacSpoofer  •  v0.1.0
```

Use only on networks and devices you own or are authorised to test.

---

## Why a device profile rather than a random address

A MAC address is not opaque. Its first three octets are an **OUI** — a block
registered to a specific company in the public IEEE registry — so anything
looking at the address can tell an Apple NIC from an Espressif one. A random
address is immediately odd: it either belongs to no vendor at all, or to a
vendor that makes nothing like the device sending the traffic.

MacSpoofer keeps the registered prefix intact and randomises only the three
NIC-specific octets, so the result is indistinguishable in form from a real
address issued by that vendor:

```
b8:27:eb : d5:9f:86
└──────┘   └──────┘
 Raspberry  random
 Pi's OUI   per run
```

**What this does and does not achieve.** The address is what appears in ARP
tables, DHCP leases, switch MAC tables, Wi-Fi management frames and most
inventory and NAC systems — so to those, the device is a Raspberry Pi. It does
not reproduce the rest of a device's fingerprint: DHCP option ordering,
hostname, TCP/IP stack quirks, mDNS advertisements, TLS fingerprint and traffic
patterns all still describe the real machine. MacSpoofer changes one strong
signal, not every signal.

## Features

- **98 device profiles in 15 categories**, chosen from an interactive menu —
  phones, laptops, tablets, consoles, smart TVs, IoT, network gear, printers,
  IP cameras, VoIP phones, industrial controllers, single-board computers,
  wearables and hypervisors — plus random and custom addresses. 530 unique OUI
  prefixes in total.
- **Prefixes checked against the IEEE registry.** `macspoofer verify-oui`
  compares every bundled prefix against the official MA-L registry and names
  the real registrant for any that disagree. The catalogue ships clean: 633 of
  636 prefixes confirmed, the other 3 being locally administered hypervisor
  defaults that are absent from the registry by design.
- **Every change is verified by reading it back.** A command that exits 0 proves
  nothing — Wi-Fi drivers in particular accept the change and silently keep the
  old address. MacSpoofer re-reads the interface and reports `ok`, `unverified`
  or `failed` accordingly.
- **Restore to the true original.** The original address is recorded before the
  first change and never overwritten, so `restore` works even after several
  spoofs in a row.
- **Correct bit handling.** Multicast, broadcast and all-zero addresses are
  rejected before any privileged command runs, and the U/L bit is set correctly
  for random addresses.
- **macOS and Linux**, with the per-platform awkwardness handled rather than
  ignored (see [Platform notes](#platform-notes)).
- **Scriptable**: everything the wizard does is available as flags, with
  `--dry-run` and meaningful exit codes.

## Install

Requires Python 3.11+.

```bash
git clone https://github.com/M0rPh39s/MacSpoofer.git
cd MacSpoofer
pip install .
```

Or run it straight from a checkout without installing:

```bash
pip install rich
sudo python -m macspoofer
```

## Usage

### The wizard

```bash
sudo macspoofer
```

Three steps — interface, category, device — then a preview you can accept,
regenerate (`r`) or back out of (`b`):

```
╭─ Proposed change ────────────────────────────────────────────────────────────╮
│ Interface:   en0 (Wi-Fi)                                                     │
│ Current:     fc:b2:14:6e:3c:ea                                               │
│ New address: dc:a6:32:6d:75:2c                                               │
│ Appears as:  Raspberry Pi (Raspberry Pi Foundation / Ltd)                     │
│ Scope:       unicast, globally unique (registered OUI)                       │
│                                                                              │
│ dc:a6:32 is registered to Raspberry Pi Foundation / Ltd; the remaining three │
│ octets are random                                                            │
│                                                                              │
│ b8:27:eb is Pi 1-3, dc:a6:32 and e4:5f:01 are Pi 4, 2c:cf:67 and d8:3a:dd    │
│ are Pi 5 / Pico W era.                                                       │
╰──────────────────────────────────────────────────────────────────────────────╯
```

### Non-interactive

```bash
# Look like a specific device class
sudo macspoofer set -i en0 -d hikvision -y

# Pin the OUI instead of drawing one at random
sudo macspoofer set -i en0 -d raspberry-pi --oui b8:27:eb -y

# A random locally administered address: privacy, impersonating nothing
sudo macspoofer set -i en0 --random -y

# An exact address
sudo macspoofer set -i en0 -m aa:bb:cc:11:22:33 -y

# See what would happen, change nothing
macspoofer set -i en0 -d apple-iphone --dry-run

# Put it back
sudo macspoofer restore -i en0
sudo macspoofer restore --all
```

### Browsing and inspecting

```bash
macspoofer interfaces              # what can be changed
macspoofer interfaces --all        # include loopback, tunnels, virtual
macspoofer devices                 # the whole catalogue
macspoofer devices -c camera       # one category
macspoofer devices -s nintendo     # search by name or vendor
macspoofer status                  # interfaces plus recorded originals
```

### Commands

| Command | Purpose |
|---------|---------|
| *(none)* / `wizard` | Interactive device picker |
| `set` | Change an address from a profile, an explicit MAC, or at random |
| `restore` | Return an interface, or all of them, to the recorded original |
| `interfaces` | List interfaces with current and hardware addresses |
| `devices` | Browse or search the profile catalogue |
| `status` | Interfaces plus every recorded original |
| `verify-oui` | Check the catalogue against the IEEE registry |

Exit codes: `0` success, `1` error, `2` usage, `130` aborted.

## Device categories

| Category | Key | Examples |
|----------|-----|----------|
| Smartphones | `phone` | iPhone, Galaxy, Pixel, Xiaomi, Huawei, OnePlus, Motorola, Nokia, LG |
| Laptops & desktops | `computer` | MacBook, Dell, HP, ThinkPad, Surface, Intel/Realtek/Broadcom/Atheros NICs |
| Tablets & e-readers | `tablet` | iPad, Galaxy Tab, Fire tablet / Kindle |
| Game consoles | `console` | PlayStation 5, PlayStation 4, Xbox, Switch, Wii / 3DS |
| Smart TVs & streaming | `tv` | Samsung, LG webOS, Bravia, Vizio, Panasonic, Roku, Fire TV, Chromecast, Apple TV, Shield |
| Smart home & IoT | `iot` | Echo, Nest, Hue, Sonos, Ring, Wyze, ESP32/Shelly/Tasmota, Kasa |
| Network equipment | `network` | Cisco, UniFi, TP-Link, Netgear, ASUS, D-Link, MikroTik, Aruba, Juniper, FortiGate, Zyxel, Linksys |
| Printers & scanners | `printer` | HP, Canon, Epson, Brother, Xerox, Lexmark, Zebra |
| IP cameras & NVR | `camera` | Hikvision, Dahua, Axis, Reolink, Uniview |
| VoIP & conferencing | `voip` | Cisco IP Phone, Poly, Yealink, Grandstream, Avaya, Snom |
| Industrial & OT | `ot` | Siemens SIMATIC, Allen-Bradley, Schneider, Moxa, Phoenix Contact, Beckhoff, Omron |
| Single-board & embedded | `sbc` | Raspberry Pi, Jetson, BeagleBone, Arduino, ESP32 |
| Wearables & accessories | `wearable` | Apple Watch, GoPro, Bose |
| Virtual machines | `vm` | VMware, VirtualBox, Hyper-V, QEMU/KVM, Xen, Parallels, Docker |
| Generic & custom | `generic` | Random locally administered, random vendor, explicit MAC |

Profiles are plain data in `macspoofer/profiles.py` — adding one is a few lines,
no engine changes.

## Verifying the catalogue

The catalogue is curated by hand, which makes it the part of the tool most
likely to drift from reality. Rather than ask you to trust it, MacSpoofer can
check it:

```bash
# Using a local copy of the registry
macspoofer verify-oui --csv oui.csv

# Or fetch it (several MB, nothing is downloaded unless you ask)
macspoofer verify-oui --download
```

```
Checked 636 prefixes against 40497 IEEE assignments

  633 match the expected vendor
  3 locally administered, so absent from the registry by design
```

Building this tool, that command found 31 prefixes in the first draft of the
catalogue that the registry says belong to somebody else — a "Panasonic" prefix
registered to NEC, a "Vizio" one registered to Xiaomi — and they were removed.
A truncated registry download is detected and refused rather than reported as
hundreds of unregistered prefixes.

## Platform notes

### macOS

- **Reading addresses needs root.** Recent macOS versions hand unprivileged
  processes the placeholder `02:00:00:00:00:00` instead of the real address.
  MacSpoofer recognises that placeholder and says "unreadable (needs root)"
  rather than reporting a fake address. `networksetup` is exempt from the
  restriction, which is how the hardware address is still shown.
- **Wi-Fi changes often fail on Apple Silicon.** The driver accepts the command
  and keeps the old address. MacSpoofer detects this via the read-back and tells
  you, instead of claiming success. Wired and USB Ethernet adapters work
  normally.
- Wi-Fi changes are attempted directly first, then retried with the interface
  power-cycled, which drops the current network.
- Changes do not survive a reboot.

### Linux

- Uses `ip link` where available, falling back to `ifconfig`.
- `ethtool -P` gives the true permanent address when installed.
- NetworkManager may reassert its own address on a managed interface; set
  `wifi.mac-address-randomization`/`ethernet.cloned-mac-address` there instead
  if the change keeps reverting.

## How it works

```
profiles.py     the device catalogue (plain data)
     │
generator.py    pick a registered OUI, randomise the NIC half
     │
oui.py          parse, validate, enforce unicast / U-L bit rules
     │
interfaces.py   discover interfaces; current vs permanent address
     │
spoof.py        apply via ifconfig / ip, then READ BACK and compare
     │
state.py        remember the true original so restore works
```

`verify.py` checks `profiles.py` against the IEEE registry. `cli.py` is the
wizard and the subcommands.

## Development

```bash
pip install -e ".[dev]"
pytest
```

115 tests cover address bit semantics, catalogue integrity, generation,
interface parsing (including the macOS placeholder), the apply/restore state
machine against a simulated host, registry verification, and every CLI path
including the wizard.

## License

MIT — see [LICENSE](LICENSE).
