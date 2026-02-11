from app.rf_propagation import profile_diffraction


def test_profile_diffraction_clear_path_has_no_loss():
    res = profile_diffraction(
        distances_km=[0.0, 5.0, 10.0],
        terrain_profile_m=[100.0, 95.0, 100.0],
        start_total_height_m=120.0,
        end_total_height_m=120.0,
        freq_ghz=5.8,
        use_fresnel=True,
        obstruction_grace_m=20.0,
    )
    assert res.blocked is False
    assert res.diffraction_loss_db == 0.0


def test_profile_diffraction_multi_edge_gives_positive_loss():
    res = profile_diffraction(
        distances_km=[0.0, 3.0, 6.0, 9.0, 12.0],
        terrain_profile_m=[100.0, 118.0, 111.0, 119.0, 100.0],
        start_total_height_m=115.0,
        end_total_height_m=115.0,
        freq_ghz=5.8,
        use_fresnel=True,
        obstruction_grace_m=20.0,
    )
    assert res.blocked is False
    assert res.diffraction_loss_db > 0.0


def test_profile_diffraction_blocks_when_obstruction_exceeds_grace():
    res = profile_diffraction(
        distances_km=[0.0, 4.0, 8.0],
        terrain_profile_m=[100.0, 145.0, 100.0],
        start_total_height_m=110.0,
        end_total_height_m=110.0,
        freq_ghz=5.8,
        use_fresnel=True,
        obstruction_grace_m=20.0,
    )
    assert res.blocked is True
