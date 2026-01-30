from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from app.domain import (
    AntennaParams,
    CableType,
    ConfigNote,
    Device,
    DeviceLink,
    DeviceType,
    GeoPoint,
    Link,
    LinkKind,
    LinkType,
    NetworkProject,
    Site,
    SiteKind,
    Status,
    StatusState,
)

SCHEMA_VERSION = 1


def save_project(path: str | Path, project: NetworkProject) -> None:
    payload = {
        "schema_version": SCHEMA_VERSION,
        "saved_at": datetime.utcnow().isoformat(),
        "project": project_to_dict(project),
    }
    Path(path).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def load_project(path: str | Path) -> NetworkProject:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    project_data = data.get("project", {})
    return project_from_dict(project_data)


def project_to_dict(project: NetworkProject) -> dict[str, Any]:
    return {
        "id": project.id,
        "name": project.name,
        "notes": [note_to_dict(n) for n in project.notes],
        "sites": {sid: site_to_dict(site) for sid, site in project.sites.items()},
        "links": {lid: link_to_dict(link) for lid, link in project.links.items()},
    }


def project_from_dict(data: dict[str, Any]) -> NetworkProject:
    project = NetworkProject(id=data.get("id", "proj"), name=data.get("name", "Project"))
    project.notes = [note_from_dict(n) for n in data.get("notes", [])]
    for sid, sdata in data.get("sites", {}).items():
        project.sites[sid] = site_from_dict(sdata)
    for lid, ldata in data.get("links", {}).items():
        project.links[lid] = link_from_dict(ldata)
    return project


def site_to_dict(site: Site) -> dict[str, Any]:
    return {
        "id": site.id,
        "name": site.name,
        "kind": site.kind.value,
        "location": geopoint_to_dict(site.location),
        "antenna": antenna_to_dict(site.antenna),
        "devices": {did: device_to_dict(dev) for did, dev in site.devices.items()},
        "links": {lid: device_link_to_dict(link) for lid, link in site.links.items()},
        "notes": [note_to_dict(n) for n in site.notes],
        "metadata": site.metadata,
    }


def site_from_dict(data: dict[str, Any]) -> Site:
    site = Site(
        id=data.get("id", "site"),
        name=data.get("name", "Site"),
        kind=SiteKind(data.get("kind", "pop")),
        location=geopoint_from_dict(data.get("location", {})),
    )
    site.antenna = antenna_from_dict(data.get("antenna", {}))
    site.devices = {did: device_from_dict(ddata) for did, ddata in data.get("devices", {}).items()}
    site.links = {lid: device_link_from_dict(ldata) for lid, ldata in data.get("links", {}).items()}
    site.notes = [note_from_dict(n) for n in data.get("notes", [])]
    site.metadata = data.get("metadata", {})
    return site


def link_to_dict(link: Link) -> dict[str, Any]:
    return {
        "id": link.id,
        "name": link.name,
        "kind": link.kind.value if hasattr(link.kind, "value") else str(link.kind),
        "site_a_id": link.site_a_id,
        "site_b_id": link.site_b_id,
        "frequency_ghz": link.frequency_ghz,
        "ssid": link.ssid,
        "password": link.password,
        "link_type": link.link_type.value if link.link_type else None,
        "cable_type": link.cable_type.value if link.cable_type else None,
        "distance_km": link.distance_km,
        "channel_width_mhz": link.channel_width_mhz,
        "capacity_mbps": link.capacity_mbps,
        "metadata": link.metadata,
    }


def link_from_dict(data: dict[str, Any]) -> Link:
    link = Link(
        id=data.get("id", "link"),
        name=data.get("name", "Link"),
        kind=LinkKind(data.get("kind", "ptp")),
        site_a_id=data.get("site_a_id", ""),
        site_b_id=data.get("site_b_id", ""),
    )
    link.frequency_ghz = data.get("frequency_ghz")
    link.ssid = data.get("ssid")
    link.password = data.get("password")
    link.link_type = LinkType(data["link_type"]) if data.get("link_type") else None
    link.cable_type = CableType(data["cable_type"]) if data.get("cable_type") else None
    link.distance_km = data.get("distance_km")
    link.channel_width_mhz = data.get("channel_width_mhz")
    link.capacity_mbps = data.get("capacity_mbps")
    link.metadata = data.get("metadata", {})
    return link


def device_to_dict(device: Device) -> dict[str, Any]:
    return {
        "id": device.id,
        "name": device.name,
        "device_type": device.device_type.value,
        "ip_address": device.ip_address,
        "port": device.port,
        "coordinates": geopoint_to_dict(device.coordinates) if device.coordinates else None,
        "position": list(device.position) if device.position else None,
        "notes_text": device.notes_text,
        "notes": [note_to_dict(n) for n in device.notes],
        "status": status_to_dict(device.status),
        "is_uplink": device.is_uplink,
        "metadata": device.metadata,
    }


def device_from_dict(data: dict[str, Any]) -> Device:
    device = Device(
        id=data.get("id", "device"),
        name=data.get("name", "Device"),
        device_type=DeviceType(data.get("device_type", "router")),
    )
    device.ip_address = data.get("ip_address")
    device.port = data.get("port")
    coord = data.get("coordinates")
    if coord:
        device.coordinates = geopoint_from_dict(coord)
    pos = data.get("position")
    if pos:
        device.position = (pos[0], pos[1])
    device.notes_text = data.get("notes_text")
    device.notes = [note_from_dict(n) for n in data.get("notes", [])]
    status_data = data.get("status")
    if status_data:
        device.status = status_from_dict(status_data)
    device.is_uplink = bool(data.get("is_uplink", False))
    device.metadata = data.get("metadata", {})
    return device


def device_link_to_dict(link: DeviceLink) -> dict[str, Any]:
    return {
        "id": link.id,
        "device_a_id": link.device_a_id,
        "device_b_id": link.device_b_id,
        "port_a": link.port_a,
        "port_b": link.port_b,
        "link_type": link.link_type.value if link.link_type else None,
        "cable_type": link.cable_type.value if link.cable_type else None,
        "metadata": link.metadata,
    }


def device_link_from_dict(data: dict[str, Any]) -> DeviceLink:
    link = DeviceLink(
        id=data.get("id", "dlink"),
        device_a_id=data.get("device_a_id", ""),
        device_b_id=data.get("device_b_id", ""),
        port_a=data.get("port_a", ""),
        port_b=data.get("port_b", ""),
        link_type=LinkType(data["link_type"]) if data.get("link_type") else LinkType.GIG_ETH,
        cable_type=CableType(data["cable_type"]) if data.get("cable_type") else CableType.OUTDOOR,
    )
    link.metadata = data.get("metadata", {})
    return link


def antenna_to_dict(antenna: AntennaParams) -> dict[str, Any]:
    return {
        "antenna_type": antenna.antenna_type,
        "azimuth_deg": antenna.azimuth_deg,
        "beamwidth_deg": antenna.beamwidth_deg,
        "altitude_m": antenna.altitude_m,
        "height_m": antenna.height_m,
        "gain_dbi": antenna.gain_dbi,
        "frequency_ghz": antenna.frequency_ghz,
        "tx_power_dbm": antenna.tx_power_dbm,
        "rx_gain_dbi": antenna.rx_gain_dbi,
        "rx_height_m": antenna.rx_height_m,
        "rx_sensitivity_dbm": antenna.rx_sensitivity_dbm,
        "misc_losses_db": antenna.misc_losses_db,
        "link_margin_db": antenna.link_margin_db,
        "mcs": antenna.mcs,
    }


def antenna_from_dict(data: dict[str, Any]) -> AntennaParams:
    return AntennaParams(
        antenna_type=data.get("antenna_type"),
        azimuth_deg=data.get("azimuth_deg"),
        beamwidth_deg=data.get("beamwidth_deg"),
        altitude_m=data.get("altitude_m"),
        height_m=data.get("height_m"),
        gain_dbi=data.get("gain_dbi"),
        frequency_ghz=data.get("frequency_ghz"),
        tx_power_dbm=data.get("tx_power_dbm"),
        rx_gain_dbi=data.get("rx_gain_dbi"),
        rx_height_m=data.get("rx_height_m"),
        rx_sensitivity_dbm=data.get("rx_sensitivity_dbm"),
        misc_losses_db=data.get("misc_losses_db"),
        link_margin_db=data.get("link_margin_db"),
        mcs=data.get("mcs"),
    )


def note_to_dict(note: ConfigNote) -> dict[str, Any]:
    return {
        "title": note.title,
        "body": note.body,
        "created_at": note.created_at.isoformat(),
        "tags": note.tags,
    }


def note_from_dict(data: dict[str, Any]) -> ConfigNote:
    created = data.get("created_at")
    return ConfigNote(
        title=data.get("title", ""),
        body=data.get("body", ""),
        created_at=datetime.fromisoformat(created) if created else datetime.utcnow(),
        tags=data.get("tags", []),
    )


def status_to_dict(status: Status) -> dict[str, Any]:
    return {
        "state": status.state.value,
        "last_seen": status.last_seen.isoformat() if status.last_seen else None,
        "rtt_ms": status.rtt_ms,
        "loss_pct": status.loss_pct,
    }


def status_from_dict(data: dict[str, Any]) -> Status:
    return Status(
        state=StatusState(data.get("state", "unknown")),
        last_seen=datetime.fromisoformat(data["last_seen"]) if data.get("last_seen") else None,
        rtt_ms=data.get("rtt_ms"),
        loss_pct=data.get("loss_pct"),
    )


def geopoint_to_dict(point: GeoPoint) -> dict[str, Any]:
    return asdict(point)


def geopoint_from_dict(data: dict[str, Any]) -> GeoPoint:
    return GeoPoint(
        lat=data.get("lat", 0.0),
        lon=data.get("lon", 0.0),
        altitude_m=data.get("altitude_m"),
    )
