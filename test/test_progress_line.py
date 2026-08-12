"""Unit tests for the download progress line."""
import time

from quantmine.data_acquisition import PROGRESS_BAR_WIDTH, progress_line


def test_bar_and_percentage_track_completion():
    started = time.monotonic()
    line = progress_line("prices", 12, 39, started)

    assert "12/39" in line
    assert "31%" in line
    assert line.count("#") == round(12 / 39 * PROGRESS_BAR_WIDTH)


def test_no_eta_before_the_first_unit_completes():
    """Dividing by zero completed units would be a crash, or a lie."""
    line = progress_line("shares", 0, 771, time.monotonic())

    assert "eta" not in line
    assert "0/771" in line


def test_eta_is_extrapolated_from_elapsed_per_completed_unit():
    started = time.monotonic() - 100  # 100s for a quarter of the work
    line = progress_line("prices", 10, 40, started)

    # 30 units left at 10s each -> 5m00s, allowing a second of test overhead.
    assert "eta 5m0" in line


def test_a_total_of_zero_does_not_divide_by_zero():
    line = progress_line("prices", 0, 0, time.monotonic())

    assert "0/1" in line
