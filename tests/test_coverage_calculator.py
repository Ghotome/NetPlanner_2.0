import math

from app.coverage import CoverageCalculator
from app.domain import AntennaParams


def test_rx_sensitivity_from_nf_and_sinr():
    antenna = AntennaParams(
        frequency_ghz=5.8,
        channel_width_mhz=20.0,
        noise_figure_db=8.0,
        required_sinr_db=16.0,
    )
    value = CoverageCalculator.rx_sensitivity_dbm(antenna)
    expected = -174.0 + (10.0 * math.log10(20_000_000.0)) + 8.0 + 16.0
    assert value is not None
    assert abs(value - expected) < 1e-6


def test_rx_sensitivity_manual_with_wifi_channel_scaling():
    antenna = AntennaParams(
        frequency_ghz=5.8,
        rx_sensitivity_dbm=-90.0,
        channel_width_mhz=40.0,
    )
    value = CoverageCalculator.rx_sensitivity_dbm(antenna)
    assert value is not None
    assert abs(value - (-90.0 + 10.0 * math.log10(40.0 / 20.0))) < 1e-6


def test_rx_sensitivity_manual_uhf_reference_is_12_5khz():
    antenna = AntennaParams(
        frequency_ghz=0.45,
        rx_sensitivity_dbm=-120.0,
        channel_width_mhz=0.0125,
    )
    value = CoverageCalculator.rx_sensitivity_dbm(antenna)
    assert value == -120.0
