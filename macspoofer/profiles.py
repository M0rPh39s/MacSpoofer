"""Static, data-driven device profile catalogue.

Profiles are plain data so the catalogue can be extended without touching the
generation or spoofing engines. Each :class:`DeviceProfile` names a device
class and carries one or more OUI prefixes registered to that vendor in the
public IEEE MA-L registry; a generated address copies one of those prefixes
verbatim and randomises the NIC-specific half (see :mod:`macspoofer.oui`).

The catalogue is curated by hand and is therefore the one part of this tool
that can drift from reality: vendors acquire each other and the registry grows.
``macspoofer verify-oui`` checks every prefix below against the official IEEE
registry and reports the real registrant for any that disagree -- treat that
command, not this file, as ground truth.

A note on what a MAC can and cannot do. Changing the address makes an
interface *look* like a NIC from the chosen vendor to anything doing OUI
lookups -- ARP tables, DHCP leases, switch MAC tables, Wi-Fi management
frames, inventory and NAC systems. It does not reproduce the rest of a device's
fingerprint: DHCP option ordering, hostname, TCP/IP stack quirks, mDNS/Bonjour
advertisements, TLS fingerprint and traffic patterns all still describe the
real machine. Profiles whose realism depends on something beyond the MAC say
so in ``notes``.
"""

from __future__ import annotations

from dataclasses import dataclass, field

__all__ = [
    "DeviceProfile",
    "Category",
    "CATEGORIES",
    "RANDOM_LOCAL_KEY",
    "RANDOM_VENDOR_KEY",
    "CUSTOM_KEY",
    "all_profiles",
    "profile_by_key",
    "category_by_key",
    "profiles_in_category",
    "search",
    "all_ouis",
]

RANDOM_LOCAL_KEY = "random-local"
RANDOM_VENDOR_KEY = "random-vendor"
CUSTOM_KEY = "custom"


@dataclass(frozen=True)
class DeviceProfile:
    """One impersonation target.

    ``ouis`` holds registered prefixes for ``vendor``; one is chosen at random
    per generation unless the caller pins it. A profile with an empty ``ouis``
    tuple is *synthetic* -- it is handled specially by the generator (random
    locally administered address, random registered vendor, or a MAC typed by
    the user) rather than mapping to a fixed vendor.
    """

    key: str
    label: str
    vendor: str
    ouis: tuple[str, ...] = ()
    notes: str = ""

    @property
    def synthetic(self) -> bool:
        return not self.ouis


@dataclass(frozen=True)
class Category:
    """A named group of profiles, as shown in the interactive menu."""

    key: str
    label: str
    description: str
    profiles: tuple[DeviceProfile, ...] = field(default_factory=tuple)


# ---------------------------------------------------------------------------
# Catalogue
# ---------------------------------------------------------------------------

CATEGORIES: tuple[Category, ...] = (
    Category(
        "phone",
        "Smartphones",
        "Handsets as they appear to a network's DHCP server and switch tables.",
        (
            DeviceProfile(
                "apple-iphone", "Apple iPhone", "Apple",
                ("00:1b:63", "00:25:00", "28:cf:da", "3c:07:54", "68:ab:1e",
                 "7c:d1:c3", "a4:5e:60", "d8:96:95", "f0:18:98", "04:0c:ce",
                 "54:26:96", "90:72:40", "b8:17:c2", "dc:a9:04", "f4:f1:5a"),
                "iOS 14+ uses a per-network randomised private MAC by default, so a "
                "locally administered address is often the more authentic iPhone.",
            ),
            DeviceProfile(
                "samsung-galaxy", "Samsung Galaxy", "Samsung",
                ("00:16:32", "00:1d:25", "00:21:19", "38:aa:3c", "5c:0a:5b", "78:1f:db",
                  "8c:77:12", "e8:50:8b", "94:51:03", "cc:07:ab", "f0:25:b7"),
            ),
            DeviceProfile(
                "google-pixel", "Google Pixel", "Google",
                ("00:1a:11", "3c:5a:b4", "54:60:09", "94:95:a0", "f4:f5:e8",
                 "20:df:b9", "30:fd:38"),
            ),
            DeviceProfile(
                "xiaomi-phone", "Xiaomi / Redmi / POCO", "Xiaomi",
                ("00:9e:c8", "28:6c:07", "50:8f:4c", "64:09:80", "78:11:dc",
                 "ac:c1:ee", "f8:a4:5f", "20:34:fb", "38:a4:ed", "64:b4:73",
                 "8c:be:be", "9c:99:a0"),
            ),
            DeviceProfile(
                "huawei-phone", "Huawei / Honor", "Huawei",
                ("00:e0:fc", "00:18:82", "00:25:9e", "28:31:52", "48:46:fb",
                 "78:d7:52", "f8:98:ef", "04:bd:70", "10:47:80", "20:f3:a3",
                 "34:6b:d3", "5c:7d:5e", "84:a8:e4", "9c:28:ef", "ac:4e:91"),
            ),
            DeviceProfile(
                "oneplus", "OnePlus", "OnePlus",
                ("94:65:2d", "c0:ee:fb", "64:a2:f9"),
            ),
            DeviceProfile(
                "motorola", "Motorola", "Motorola Mobility",
                ("00:0a:28", "00:24:37", "40:78:6a", "5c:51:88"),
            ),
            DeviceProfile(
                "nokia-phone", "Nokia", "Nokia",
                ("00:02:ee", "00:0b:e1", "00:1d:98", "9c:18:74", "78:2e:ef"),
            ),
            DeviceProfile(
                "lg-phone", "LG phone", "LG Electronics",
                ("00:1c:62", "00:1e:75", "10:68:3f", "58:a2:b5", "a8:16:b2",
                 "cc:fa:00", "2c:54:cf", "64:99:5d"),
            ),
        ),
    ),
    Category(
        "computer",
        "Laptops & desktops",
        "Workstations. On laptops the visible MAC usually belongs to the wireless "
        "card's chipset vendor, not the brand on the lid -- both are offered.",
        (
            DeviceProfile(
                "apple-macbook", "Apple MacBook / iMac / Mac mini", "Apple",
                ("00:03:93", "00:0a:27", "00:16:cb", "00:1e:c2", "3c:07:54",
                 "a4:5e:60", "f0:18:98", "68:ab:1e", "10:dd:b1", "b8:17:c2",
                 "dc:a9:04"),
            ),
            DeviceProfile(
                "dell-laptop", "Dell laptop / desktop", "Dell",
                ("00:11:43", "00:14:22", "00:21:9b", "18:03:73", "b8:2a:72",
                 "d0:67:e5", "f8:bc:12", "00:24:e8", "34:17:eb", "54:9f:35",
                 "84:2b:2b", "a4:ba:db", "f0:1f:af", "14:fe:b5"),
            ),
            DeviceProfile(
                "hp-laptop", "HP laptop / desktop", "HP",
                ("00:17:a4", "00:1b:78", "00:21:5a", "00:25:b3", "1c:c1:de",
                 "3c:d9:2b", "9c:b6:54", "2c:23:3a", "30:8d:99", "38:63:bb",
                 "6c:c2:17", "80:c1:6e", "b4:b5:2f", "fc:15:b4"),
            ),
            DeviceProfile(
                "lenovo-thinkpad", "Lenovo ThinkPad / IdeaPad", "Lenovo",
                ("00:59:07", "70:72:0d", "8c:16:45", "c8:5b:76", "50:7b:9d"),
            ),
            DeviceProfile(
                "microsoft-surface", "Microsoft Surface", "Microsoft",
                ("00:50:f2", "00:12:5a", "28:18:78", "7c:1e:52", "60:45:bd", "98:5f:d3",
                  "c0:33:5e", "48:50:73"),
            ),
            DeviceProfile(
                "intel-wifi", "Generic PC (Intel wireless card)", "Intel",
                ("00:13:02", "00:1b:21", "00:1e:67", "68:17:29", "7c:7a:91", "94:65:9c",
                  "a0:a8:cd", "00:21:6a", "34:13:e8", "5c:51:4f", "8c:a9:82", "b4:6b:fc",
                  "dc:53:60"),
                "The most common laptop MAC on a corporate network.",
            ),
            DeviceProfile(
                "realtek-nic", "Generic PC (Realtek NIC)", "Realtek",
                ("00:e0:4c",),
                "Ubiquitous on budget desktops, docks and USB Ethernet dongles.",
            ),
            DeviceProfile(
                "broadcom-nic", "Generic PC (Broadcom NIC)", "Broadcom",
                ("00:10:18", "00:1b:e9"),
            ),
            DeviceProfile(
                "atheros-nic", "Generic PC (Qualcomm Atheros wireless)", "Qualcomm Atheros",
                ("00:03:7f", "00:a0:c6"),
            ),
            DeviceProfile(
                "mediatek-nic", "Generic device (MediaTek chipset)", "MediaTek",
                ("00:0c:e7",),
            ),
            DeviceProfile(
                "foxconn-nic", "Generic PC (Foxconn / Hon Hai module)", "Hon Hai / Foxconn",
                ("00:01:6c", "00:16:ce", "90:4c:e5"),
            ),
        ),
    ),
    Category(
        "tablet",
        "Tablets & e-readers",
        "Tablets, often treated as trusted personal devices by guest networks.",
        (
            DeviceProfile(
                "apple-ipad", "Apple iPad", "Apple",
                ("00:1b:63", "28:cf:da", "7c:d1:c3", "a4:5e:60", "d8:96:95",
                 "f0:18:98", "54:26:96", "f4:f1:5a"),
            ),
            DeviceProfile(
                "samsung-tab", "Samsung Galaxy Tab", "Samsung",
                ("00:16:32", "38:aa:3c", "5c:0a:5b", "78:1f:db", "e8:50:8b", "cc:07:ab"),
            ),
            DeviceProfile(
                "amazon-fire-tablet", "Amazon Fire tablet / Kindle", "Amazon Technologies",
                ("44:65:0d", "74:c2:46", "f0:27:2d", "68:37:e9", "0c:47:c9",
                 "a0:02:dc", "50:dc:e7", "38:f7:3d", "40:b4:cd", "84:d6:d0",
                 "ac:63:be", "b4:7c:9c", "fc:65:de"),
            ),
        ),
    ),
    Category(
        "console",
        "Game consoles",
        "Consoles are frequently allow-listed on home and dorm networks and "
        "exempted from captive portals.",
        (
            DeviceProfile(
                "playstation-5", "Sony PlayStation 5", "Sony Interactive Entertainment",
                ("70:9e:29", "2c:cc:44", "78:84:3c", "a0:e4:53"),
            ),
            DeviceProfile(
                "playstation-4", "Sony PlayStation 4", "Sony Interactive Entertainment",
                ("fc:0f:e6", "00:d9:d1", "30:f9:ed", "00:04:1f", "00:13:a9",
                 "00:19:c5"),
            ),
            DeviceProfile(
                "xbox", "Microsoft Xbox Series X|S / One", "Microsoft",
                ("50:1a:c5", "7c:1e:52", "60:45:bd", "98:5f:d3", "c0:33:5e", "00:50:f2"),
            ),
            DeviceProfile(
                "nintendo-switch", "Nintendo Switch", "Nintendo",
                ("98:41:5c", "2c:10:c1", "7c:bb:8a", "98:b6:e9", "04:03:d6",
                 "58:bd:a3", "34:af:2c", "e8:4e:ce", "9c:e6:35"),
            ),
            DeviceProfile(
                "nintendo-legacy", "Nintendo Wii / Wii U / 3DS", "Nintendo",
                ("00:09:bf", "00:1a:e9", "00:1b:ea", "00:1f:32", "18:2a:7b"),
            ),
        ),
    ),
    Category(
        "tv",
        "Smart TVs & streaming",
        "Living-room devices. Commonly excluded from endpoint policy and left "
        "on a flat VLAN.",
        (
            DeviceProfile(
                "samsung-tv", "Samsung Smart TV", "Samsung",
                ("00:12:fb", "00:21:19", "8c:77:12", "e8:50:8b", "f0:25:b7", "cc:07:ab"),
            ),
            DeviceProfile(
                "lg-tv", "LG Smart TV (webOS)", "LG Electronics",
                ("00:34:da", "2c:54:cf", "3c:cd:93", "98:93:cc", "a8:16:b2", "c4:9a:02",
                  "e8:5b:5b", "f8:0c:f3", "cc:fa:00"),
            ),
            DeviceProfile(
                "sony-bravia", "Sony Bravia TV", "Sony",
                ("00:04:1f", "00:13:a9", "00:19:c5", "54:42:49", "30:f9:ed"),
            ),
            DeviceProfile(
                "vizio-tv", "Vizio Smart TV", "Vizio",
                ("00:19:9d", "2c:64:1f"),
            ),
            DeviceProfile(
                "panasonic-tv", "Panasonic TV / AV", "Panasonic",
                ("00:0b:97", "00:80:f0", "04:20:9a"),
            ),
            DeviceProfile(
                "roku", "Roku player / Roku TV", "Roku",
                ("b0:a7:37", "b8:3e:59", "cc:6d:a0", "dc:3a:5e", "88:de:a9", "ac:3a:7a"),
            ),
            DeviceProfile(
                "amazon-fire-tv", "Amazon Fire TV Stick", "Amazon Technologies",
                ("44:65:0d", "74:c2:46", "f0:27:2d", "68:37:e9", "0c:47:c9",
                 "50:dc:e7", "38:f7:3d", "ac:63:be", "fc:65:de"),
            ),
            DeviceProfile(
                "chromecast", "Google Chromecast / Google TV", "Google",
                ("3c:5a:b4", "54:60:09", "94:95:a0", "f4:f5:e8", "00:1a:11",
                 "20:df:b9", "30:fd:38"),
            ),
            DeviceProfile(
                "apple-tv", "Apple TV", "Apple",
                ("00:1b:63", "7c:d1:c3", "a4:5e:60", "d8:96:95", "f0:18:98",
                 "10:dd:b1", "dc:a9:04"),
            ),
            DeviceProfile(
                "nvidia-shield", "NVIDIA Shield TV", "NVIDIA",
                ("00:04:4b", "48:b0:2d"),
            ),
        ),
    ),
    Category(
        "iot",
        "Smart home & IoT",
        "Low-trust gadgets that are nonetheless usually permitted on the LAN.",
        (
            DeviceProfile(
                "amazon-echo", "Amazon Echo / Alexa", "Amazon Technologies",
                ("44:65:0d", "74:c2:46", "f0:27:2d", "68:37:e9", "a0:02:dc",
                 "50:dc:e7", "40:b4:cd", "84:d6:d0", "b4:7c:9c", "10:ae:60"),
            ),
            DeviceProfile(
                "google-nest", "Google Nest speaker / display / thermostat", "Google",
                ("f8:8f:ca", "3c:5a:b4", "54:60:09", "94:95:a0", "f4:f5:e8",
                 "20:df:b9", "30:fd:38"),
            ),
            DeviceProfile(
                "philips-hue", "Philips Hue bridge", "Signify (Philips)",
                ("00:17:88", "ec:b5:fa"),
            ),
            DeviceProfile(
                "sonos", "Sonos speaker", "Sonos",
                ("00:0e:58", "34:7e:5c", "48:a6:b8", "5c:aa:fd", "78:28:ca",
                 "94:9f:3e", "b8:e9:37", "f0:f6:c1"),
            ),
            DeviceProfile(
                "ring", "Ring doorbell / camera", "Ring",
                ("34:3e:a4", "9c:76:13"),
            ),
            DeviceProfile(
                "wyze", "Wyze camera / sensor", "Wyze Labs",
                ("2c:aa:8e", "7c:78:b2"),
            ),
            DeviceProfile(
                "esp32", "ESP32 / ESP8266 device (Shelly, Tasmota, DIY)", "Espressif",
                ("24:0a:c4", "30:ae:a4", "7c:9e:bd", "84:0d:8e", "a4:cf:12",
                 "c4:4f:33", "48:3f:da", "8c:aa:b5", "b4:e6:2d", "cc:50:e3",
                 "d8:a0:1d", "ec:fa:bc", "24:6f:28", "3c:61:05", "4c:11:ae",
                 "58:bf:25", "68:c6:3a", "7c:df:a1", "94:b9:7e", "ac:67:b2"),
                "The single most common OUI family in consumer smart-home gear.",
            ),
            DeviceProfile(
                "tplink-kasa", "TP-Link Kasa / Tapo smart plug", "TP-Link",
                ("00:1d:0f", "50:c7:bf", "a0:f3:c1", "ec:08:6b", "98:da:c4",
                 "b0:48:7a", "1c:3b:f3", "60:a4:b7"),
            ),
        ),
    ),
    Category(
        "network",
        "Network equipment",
        "Infrastructure. A switch or AP address is rarely questioned by "
        "inventory tooling -- and rarely overlooked by a vigilant one.",
        (
            DeviceProfile(
                "cisco", "Cisco switch / router", "Cisco Systems",
                ("00:00:0c", "00:0f:34", "00:1a:a1", "00:26:0b", "58:97:bd",
                 "6c:41:6a", "f4:cf:e2", "00:1b:d4", "00:24:97", "2c:3f:38",
                 "70:6b:b9", "a0:ec:f9", "e0:0e:da"),
            ),
            DeviceProfile(
                "ubiquiti", "Ubiquiti UniFi AP / switch", "Ubiquiti",
                ("00:15:6d", "24:a4:3c", "44:d9:e7", "68:d7:9a", "78:8a:20",
                 "fc:ec:da", "04:18:d6", "74:ac:b9", "b4:fb:e4", "dc:9f:db",
                 "e0:63:da", "f0:9f:c2", "18:e8:29"),
            ),
            DeviceProfile(
                "tplink-router", "TP-Link router / access point", "TP-Link",
                ("00:1d:0f", "14:cc:20", "50:c7:bf", "a0:f3:c1", "c0:4a:00",
                 "ec:08:6b", "98:da:c4", "00:27:19", "10:fe:ed", "30:b5:c2",
                 "54:a7:03", "64:70:02", "f4:f2:6d"),
            ),
            DeviceProfile(
                "netgear", "Netgear router / switch", "Netgear",
                ("00:09:5b", "00:1f:33", "20:4e:7f", "9c:3d:cf", "a0:40:a0",
                 "c0:3f:0e", "00:14:6c", "00:22:3f", "2c:30:33", "30:46:9a",
                 "4c:60:de", "6c:b0:ce", "b0:7f:b9", "08:bd:43"),
            ),
            DeviceProfile(
                "asus-router", "ASUS router", "ASUSTek",
                ("00:1b:fc", "00:24:8c", "08:60:6e", "1c:87:2c", "2c:56:dc",
                 "50:46:5d", "ac:22:0b", "00:0c:6e", "00:11:2f", "00:15:f2",
                 "04:d4:c4", "38:d5:47", "70:4d:7b", "d8:50:e6", "f8:32:e4",
                 "2c:fd:a1"),
            ),
            DeviceProfile(
                "dlink", "D-Link router / switch", "D-Link",
                ("00:05:5d", "00:1c:f0", "14:d6:4d", "1c:af:f7", "90:94:e4",
                 "c8:be:19", "00:0d:88", "00:13:46", "00:17:9a", "00:1b:11",
                 "00:21:91", "1c:7e:e5", "28:10:7b", "78:32:1b", "b8:a3:86",
                 "c4:a8:1d", "f0:7d:68"),
            ),
            DeviceProfile(
                "mikrotik", "MikroTik RouterBOARD", "MikroTik",
                ("00:0c:42", "4c:5e:0c", "48:8f:5a", "6c:3b:6b", "74:4d:28",
                 "b8:69:f4", "2c:c8:1b", "18:fd:74", "64:d1:54", "cc:2d:e0",
                 "dc:2c:6e"),
            ),
            DeviceProfile(
                "aruba", "Aruba / HPE access point", "Aruba Networks",
                ("00:0b:86", "00:1a:1e", "18:64:72", "24:de:c6", "6c:f3:7f",
                 "94:b4:0f", "ac:a3:1e", "d8:c7:c8", "20:4c:03", "40:e3:d6"),
            ),
            DeviceProfile(
                "juniper", "Juniper switch / router", "Juniper Networks",
                ("00:05:85", "00:12:1e", "00:19:e2", "28:8a:1c", "2c:21:31",
                 "3c:61:04", "54:e0:32", "78:19:f7", "84:18:88", "88:a2:5e",
                 "a8:d0:e5", "ec:13:db"),
            ),
            DeviceProfile(
                "fortinet", "Fortinet FortiGate / FortiAP", "Fortinet",
                ("00:09:0f", "08:5b:0e", "70:4c:a5", "90:6c:ac", "e8:1c:ba"),
            ),
            DeviceProfile(
                "zyxel", "Zyxel gateway / switch", "Zyxel",
                ("00:13:49", "00:19:cb", "00:a0:c5", "40:4a:03", "5c:f4:ab", "b0:b2:dc",
                  "ec:43:f6", "10:7b:ef"),
            ),
            DeviceProfile(
                "linksys", "Linksys router", "Linksys / Belkin",
                ("00:06:25", "00:0c:41", "00:12:17", "00:13:10", "00:14:bf",
                 "00:18:39", "00:18:f8", "00:1a:70", "00:1c:10", "00:1d:7e",
                 "00:21:29", "00:22:6b", "00:23:69", "00:25:9c", "20:aa:4b",
                 "48:f8:b3", "58:6d:8f", "c0:56:27", "c4:41:1e", "98:fc:11"),
            ),
        ),
    ),
    Category(
        "printer",
        "Printers & scanners",
        "Printers are the classic forgotten node: static leases, no endpoint "
        "agent, and broad allow-list entries.",
        (
            DeviceProfile(
                "hp-printer", "HP LaserJet / OfficeJet", "HP",
                ("00:01:e6", "00:01:e7", "00:02:a5", "00:04:ea", "00:08:02",
                 "00:0b:cd", "00:0e:7f", "00:0f:20", "00:11:0a", "00:11:85",
                 "00:12:79", "00:13:21", "00:14:38", "00:14:c2", "00:15:60",
                 "00:16:35", "00:17:08", "00:18:fe", "00:19:bb", "00:1a:4b"),
            ),
            DeviceProfile(
                "canon-printer", "Canon printer / MFP", "Canon",
                ("00:00:85", "00:1e:8f", "18:0c:ac", "2c:9e:fc", "88:87:17",
                 "f4:81:39"),
            ),
            DeviceProfile(
                "epson-printer", "Epson printer", "Seiko Epson",
                ("00:00:48", "00:26:ab", "38:9d:92", "44:d2:44", "64:eb:8c", "a4:ee:57"),
            ),
            DeviceProfile(
                "brother-printer", "Brother printer", "Brother Industries",
                ("00:1b:a9", "00:80:77", "30:05:5c", "3c:2a:f4", "b4:22:00"),
            ),
            DeviceProfile(
                "xerox-printer", "Xerox printer / MFP", "Xerox",
                ("00:00:aa", "9c:93:4e"),
            ),
            DeviceProfile(
                "lexmark-printer", "Lexmark printer", "Lexmark",
                ("00:04:00", "00:20:00", "00:21:b7"),
            ),
            DeviceProfile(
                "zebra-printer", "Zebra label printer / scanner", "Zebra Technologies",
                ("00:07:4d", "00:15:70", "00:23:68"),
            ),
        ),
    ),
    Category(
        "camera",
        "IP cameras & NVR",
        "Surveillance endpoints, usually on their own VLAN with permissive rules.",
        (
            DeviceProfile(
                "hikvision", "Hikvision camera / NVR", "Hikvision",
                ("44:19:b6", "bc:ad:28", "c0:56:e3", "4c:bd:8f", "58:03:fb",
                 "8c:e7:48", "e0:ba:ad", "28:57:be", "24:28:fd", "54:c4:15",
                 "a4:14:37", "f8:4d:fc"),
            ),
            DeviceProfile(
                "dahua", "Dahua camera / NVR", "Dahua Technology",
                ("3c:ef:8c", "90:02:a9", "4c:11:bf", "14:a7:8b", "38:af:29",
                 "e0:50:8b", "08:ed:ed", "bc:32:5f"),
            ),
            DeviceProfile(
                "axis", "Axis network camera", "Axis Communications",
                ("00:40:8c", "ac:cc:8e", "b8:a4:4f", "e8:27:25"),
            ),
            DeviceProfile(
                "reolink", "Reolink camera", "Reolink",
                ("ec:71:db",),
            ),
            DeviceProfile(
                "uniview", "Uniview camera / NVR", "Uniview",
                ("48:ea:63",),
            ),
        ),
    ),
    Category(
        "voip",
        "VoIP & conferencing",
        "Desk phones and room systems, normally pinned to a voice VLAN.",
        (
            DeviceProfile(
                "cisco-phone", "Cisco IP Phone", "Cisco Systems",
                ("00:00:0c", "00:0f:34", "00:1a:a1", "00:1b:d4", "00:26:0b",
                 "58:97:bd", "6c:41:6a", "f4:cf:e2"),
            ),
            DeviceProfile(
                "polycom", "Poly / Polycom phone", "Polycom",
                ("00:04:f2", "64:16:7f", "48:25:67"),
            ),
            DeviceProfile(
                "yealink", "Yealink phone", "Yealink",
                ("00:15:65", "80:5e:c0", "24:9a:d8"),
            ),
            DeviceProfile(
                "grandstream", "Grandstream phone / ATA", "Grandstream",
                ("00:0b:82", "c0:74:ad"),
            ),
            DeviceProfile(
                "avaya", "Avaya phone", "Avaya",
                ("00:04:0d", "00:1b:4f", "3c:3a:73", "b4:b0:17", "70:38:ee"),
            ),
            DeviceProfile(
                "snom", "Snom phone", "Snom",
                ("00:04:13",),
            ),
        ),
    ),
    Category(
        "ot",
        "Industrial & OT",
        "PLCs, HMIs and serial gateways. Only relevant on an ICS segment -- and "
        "a segment where an unexpected address is noticed quickly.",
        (
            DeviceProfile(
                "siemens", "Siemens SIMATIC PLC / HMI", "Siemens",
                ("00:0e:8c", "00:1b:1b", "08:00:06", "20:87:56", "00:1c:06",
                 "00:1f:f8", "28:63:36", "8c:f3:19"),
            ),
            DeviceProfile(
                "rockwell", "Rockwell / Allen-Bradley PLC", "Rockwell Automation",
                ("00:00:bc", "00:1d:9c", "5c:88:16", "34:c0:f9"),
            ),
            DeviceProfile(
                "schneider", "Schneider Electric / Modicon", "Schneider Electric",
                ("00:00:54", "00:80:f4"),
            ),
            DeviceProfile(
                "moxa", "Moxa serial / Ethernet gateway", "Moxa",
                ("00:90:e8",),
            ),
            DeviceProfile(
                "phoenix-contact", "Phoenix Contact controller", "Phoenix Contact",
                ("00:a0:45", "a8:74:1d"),
            ),
            DeviceProfile(
                "beckhoff", "Beckhoff industrial PC", "Beckhoff",
                ("00:01:05",),
            ),
            DeviceProfile(
                "omron", "Omron controller", "Omron",
                ("00:00:0a",),
            ),
        ),
    ),
    Category(
        "sbc",
        "Single-board & embedded",
        "Hobbyist and edge hardware -- the devices most often found plugged into "
        "a spare port.",
        (
            DeviceProfile(
                "raspberry-pi", "Raspberry Pi", "Raspberry Pi Foundation / Ltd",
                ("b8:27:eb", "dc:a6:32", "e4:5f:01", "28:cd:c1", "2c:cf:67",
                 "d8:3a:dd"),
                "b8:27:eb is Pi 1-3, dc:a6:32 and e4:5f:01 are Pi 4, "
                "2c:cf:67 and d8:3a:dd are Pi 5 / Pico W era.",
            ),
            DeviceProfile(
                "nvidia-jetson", "NVIDIA Jetson", "NVIDIA",
                ("00:04:4b", "48:b0:2d"),
            ),
            DeviceProfile(
                "beaglebone", "BeagleBone (TI)", "Texas Instruments",
                ("1c:ba:8c", "90:59:af", "c8:a0:30"),
            ),
            DeviceProfile(
                "arduino", "Arduino Ethernet / WiFi shield", "Arduino",
                ("90:a2:da", "a8:61:0a"),
            ),
            DeviceProfile(
                "espressif-dev", "Espressif ESP32 dev board", "Espressif",
                ("24:0a:c4", "30:ae:a4", "7c:9e:bd", "84:0d:8e", "a4:cf:12",
                 "c4:4f:33", "48:3f:da", "8c:aa:b5", "b4:e6:2d", "cc:50:e3"),
            ),
        ),
    ),
    Category(
        "wearable",
        "Wearables & accessories",
        "Watches, cameras and audio gear that join Wi-Fi in their own right.",
        (
            DeviceProfile(
                "apple-watch", "Apple Watch", "Apple",
                ("68:ab:1e", "7c:d1:c3", "a4:5e:60", "d8:96:95", "f4:f1:5a",
                 "dc:a9:04"),
            ),
            DeviceProfile(
                "gopro", "GoPro camera", "GoPro",
                ("d4:d9:19", "f4:dd:9e"),
            ),
            DeviceProfile(
                "bose", "Bose speaker / headphones", "Bose",
                ("00:0c:8a", "04:52:c7", "2c:41:a1", "60:ab:d2"),
            ),
        ),
    ),
    Category(
        "vm",
        "Virtual machines & hypervisors",
        "Reserved hypervisor ranges. Useful for blending into a virtualised "
        "estate -- and an instant tell on a network with no hypervisors.",
        (
            DeviceProfile(
                "vmware", "VMware virtual machine", "VMware",
                ("00:05:69", "00:0c:29", "00:1c:14", "00:50:56"),
                "00:50:56 is the vCenter-assigned range; 00:0c:29 is "
                "Workstation/ESXi auto-generated.",
            ),
            DeviceProfile(
                "virtualbox", "Oracle VirtualBox VM", "Oracle VirtualBox",
                ("08:00:27", "0a:00:27"),
            ),
            DeviceProfile(
                "hyper-v", "Microsoft Hyper-V VM", "Microsoft",
                ("00:15:5d",),
            ),
            DeviceProfile(
                "qemu-kvm", "QEMU / KVM guest", "QEMU",
                ("52:54:00",),
                "52:54:00 is locally administered -- QEMU's default, not an IEEE "
                "assignment.",
            ),
            DeviceProfile(
                "xen", "Xen guest", "Xen",
                ("00:16:3e",),
            ),
            DeviceProfile(
                "parallels", "Parallels Desktop VM", "Parallels",
                ("00:1c:42",),
            ),
            DeviceProfile(
                "docker", "Docker container interface", "Docker",
                ("02:42:ac",),
                "02:42:ac is locally administered, as Docker assigns it.",
            ),
        ),
    ),
    Category(
        "generic",
        "Generic & custom",
        "No vendor identity -- privacy rather than impersonation, or an address "
        "you supply yourself.",
        (
            DeviceProfile(
                RANDOM_LOCAL_KEY, "Random locally administered address", "none",
                (),
                "Impersonates nothing: the U/L bit marks it as unregistered. The "
                "correct choice for plain privacy on a public network, and what "
                "modern phones do by default.",
            ),
            DeviceProfile(
                RANDOM_VENDOR_KEY, "Random registered vendor from this catalogue", "random",
                (),
                "Picks any profile above at random.",
            ),
            DeviceProfile(
                CUSTOM_KEY, "Enter a specific MAC address", "custom",
                (),
                "Type the full address yourself; it is validated before use.",
            ),
        ),
    ),
)


# ---------------------------------------------------------------------------
# Lookup helpers
# ---------------------------------------------------------------------------

def all_profiles() -> tuple[DeviceProfile, ...]:
    """Every profile in catalogue order."""
    return tuple(p for c in CATEGORIES for p in c.profiles)


def vendor_profiles() -> tuple[DeviceProfile, ...]:
    """Every profile that maps to real registered OUIs."""
    return tuple(p for p in all_profiles() if not p.synthetic)


def profile_by_key(key: str) -> DeviceProfile | None:
    """Return the profile with *key*, or None."""
    wanted = (key or "").strip().lower()
    for profile in all_profiles():
        if profile.key == wanted:
            return profile
    return None


def category_by_key(key: str) -> Category | None:
    """Return the category with *key*, or None."""
    wanted = (key or "").strip().lower()
    for category in CATEGORIES:
        if category.key == wanted:
            return category
    return None


def profiles_in_category(key: str) -> tuple[DeviceProfile, ...]:
    """Return the profiles of category *key* (empty if unknown)."""
    category = category_by_key(key)
    return category.profiles if category else ()


def category_of(profile: DeviceProfile) -> Category | None:
    """Return the category holding *profile*."""
    for category in CATEGORIES:
        if profile in category.profiles:
            return category
    return None


def search(term: str) -> tuple[DeviceProfile, ...]:
    """Return profiles whose key, label or vendor contains *term*."""
    needle = (term or "").strip().lower()
    if not needle:
        return ()
    return tuple(
        p
        for p in all_profiles()
        if needle in p.key or needle in p.label.lower() or needle in p.vendor.lower()
    )


def all_ouis() -> tuple[tuple[str, DeviceProfile], ...]:
    """Return every (oui, profile) pair in the catalogue."""
    return tuple((o, p) for p in all_profiles() for o in p.ouis)
