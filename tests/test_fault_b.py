from pathlib import Path

import pytest

from bike_demand.validate import load_data


pytestmark = pytest.mark.exercise

FIXTURES = Path(__file__).parent / "fixtures"


def test_fault_b_valid_control_passes():
    """The valid control CSV must be accepted."""
    frame = load_data(FIXTURES / "fault-b-valid.csv")
    assert len(frame) == 1


def test_fault_b_negative_count_is_rejected():
    """A negative rental count must be rejected."""
    with pytest.raises(ValueError):
        load_data(FIXTURES / "fault-b-invalid.csv")