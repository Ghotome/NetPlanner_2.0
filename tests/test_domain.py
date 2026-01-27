from app.domain import GeoPoint, NetworkProject, Site, SiteKind


def test_project_add_node():
    project = NetworkProject(id="p1", name="Test")
    site = Site(
        id="s1",
        name="Core",
        kind=SiteKind.CORE,
        location=GeoPoint(lat=50.0, lon=30.0),
    )
    project.add_site(site)
    assert "s1" in project.sites
