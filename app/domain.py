from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional
from uuid import uuid4


class SiteKind(str, Enum):
    CORE = "core"
    POP = "pop"
    CPE = "cpe"


class LinkKind(str, Enum):
    PTP = "ptp"
    PTMP = "ptmp"
    ETHERNET = "ethernet"


class StatusState(str, Enum):
    UP = "up"
    DOWN = "down"
    DEGRADED = "degraded"
    UNKNOWN = "unknown"


class DeviceType(str, Enum):
    ROUTER = "router"
    SWITCH = "switch"
    POE_SWITCH = "poe_switch"
    AP = "ap"
    REPEATER = "repeater"
    ANTENNA = "antenna"


class LinkType(str, Enum):
    FAST_ETH = "fast_eth"
    GIG_ETH = "gig_eth"
    OPTICAL = "optical"


class CableType(str, Enum):
    OUTDOOR = "outdoor"
    INDOOR = "indoor"


@dataclass(frozen=True)
class GeoPoint:
    lat: float
    lon: float
    altitude_m: Optional[float] = None


@dataclass
class ConfigNote:
    title: str
    body: str
    created_at: datetime = field(default_factory=datetime.utcnow)
    tags: List[str] = field(default_factory=list)


@dataclass
class Status:
    state: StatusState = StatusState.UNKNOWN
    last_seen: Optional[datetime] = None
    rtt_ms: Optional[float] = None
    loss_pct: Optional[float] = None


@dataclass
class Device:
    id: str
    name: str
    device_type: DeviceType
    ip_address: Optional[str] = None
    port: Optional[str] = None
    ports: Dict[str, int] = field(default_factory=dict)
    coordinates: Optional[GeoPoint] = None
    position: Optional[tuple[float, float]] = None
    notes_text: Optional[str] = None
    notes: List[ConfigNote] = field(default_factory=list)
    status: Status = field(default_factory=Status)
    is_uplink: bool = False
    metadata: Dict[str, str] = field(default_factory=dict)


@dataclass
class AntennaParams:
    id: str = field(default_factory=lambda: uuid4().hex[:8])
    name: Optional[str] = None
    applied: bool = False
    antenna_type: Optional[str] = None
    azimuth_deg: Optional[float] = None
    beamwidth_deg: Optional[float] = None
    altitude_m: Optional[float] = None
    height_m: Optional[float] = None
    gain_dbi: Optional[float] = None
    frequency_ghz: Optional[float] = None
    tx_power_dbm: Optional[float] = None
    rx_gain_dbi: Optional[float] = None
    rx_height_m: Optional[float] = None
    rx_sensitivity_dbm: Optional[float] = None
    misc_losses_db: Optional[float] = None
    link_margin_db: Optional[float] = None
    mcs: Optional[str] = None


@dataclass
class Site:
    id: str
    name: str
    kind: SiteKind
    location: GeoPoint
    devices: Dict[str, Device] = field(default_factory=dict)
    links: Dict[str, "DeviceLink"] = field(default_factory=dict)
    antennas: List[AntennaParams] = field(default_factory=list)
    notes: List[ConfigNote] = field(default_factory=list)
    metadata: Dict[str, str] = field(default_factory=dict)

    def add_device(self, device: Device) -> None:
        self.devices[device.id] = device

    def remove_device(self, device_id: str) -> None:
        self.devices.pop(device_id, None)

        links_to_remove = [
            link_id
            for link_id, link in self.links.items()
            if link.device_a_id == device_id or link.device_b_id == device_id
        ]
        for link_id in links_to_remove:
            self.links.pop(link_id, None)


@dataclass
class DeviceLink:
    id: str
    device_a_id: str
    device_b_id: str
    port_a: str
    port_b: str
    link_type: LinkType = LinkType.GIG_ETH
    cable_type: CableType = CableType.OUTDOOR
    metadata: Dict[str, str] = field(default_factory=dict)


@dataclass
class Link:
    id: str
    name: str
    kind: LinkKind
    site_a_id: str
    site_b_id: str
    notes_text: Optional[str] = None
    frequency_ghz: Optional[float] = None
    ssid: Optional[str] = None
    password: Optional[str] = None
    link_type: Optional[LinkType] = None
    cable_type: Optional[CableType] = None
    distance_km: Optional[float] = None
    channel_width_mhz: Optional[int] = None
    capacity_mbps: Optional[int] = None
    metadata: Dict[str, str] = field(default_factory=dict)


@dataclass
class PtPLink(Link):
    def __init__(self, **kwargs):
        super().__init__(kind=LinkKind.PTP, **kwargs)


@dataclass
class PtMPLink(Link):
    def __init__(self, **kwargs):
        super().__init__(kind=LinkKind.PTMP, **kwargs)


@dataclass
class EthernetLink(Link):
    def __init__(self, **kwargs):
        super().__init__(kind=LinkKind.ETHERNET, **kwargs)


@dataclass
class NetworkProject:
    id: str
    name: str
    sites: Dict[str, Site] = field(default_factory=dict)
    links: Dict[str, Link] = field(default_factory=dict)
    notes: List[ConfigNote] = field(default_factory=list)

    def add_site(self, site: Site) -> None:
        self.sites[site.id] = site

    def add_link(self, link: Link) -> None:
        self.links[link.id] = link

    def remove_site(self, site_id: str) -> None:
        self.sites.pop(site_id, None)
        links_to_remove = [
            link_id
            for link_id, link in self.links.items()
            if link.site_a_id == site_id or link.site_b_id == site_id
        ]
        for link_id in links_to_remove:
            self.links.pop(link_id, None)

    def remove_link(self, link_id: str) -> None:
        self.links.pop(link_id, None)
