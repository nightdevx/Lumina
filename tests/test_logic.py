"""Pure-logic checks: no monitors, no Qt event loop, no registry."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from lumina.config import Config, ScheduleRule  # noqa: E402
from lumina.core.ddcci import VcpValue  # noqa: E402
from lumina.core.discovery import normalize_identity, parse_edid_name, parse_edid_vendor  # noqa: E402
from lumina.features.automation import active_rule, in_range, parse_hhmm  # noqa: E402


def m(h, mi=0):
    return h * 60 + mi


class TestTimeRange:
    def test_same_day(self):
        assert in_range(m(10), m(9), m(17))
        assert not in_range(m(8), m(9), m(17))
        assert not in_range(m(17), m(9), m(17)), "end is exclusive"
        assert in_range(m(9), m(9), m(17)), "start is inclusive"

    def test_overnight_wraps(self):
        # v1 compared strings, so this whole class of rule never fired.
        assert in_range(m(23), m(22), m(6))
        assert in_range(m(2), m(22), m(6))
        assert in_range(m(0), m(22), m(6))
        assert not in_range(m(12), m(22), m(6))
        assert not in_range(m(6), m(22), m(6))

    def test_equal_bounds_cover_whole_day(self):
        assert in_range(m(3), m(9), m(9))
        assert in_range(m(21), m(9), m(9))


class TestParseHhmm:
    def test_valid(self):
        assert parse_hhmm("00:00") == 0
        assert parse_hhmm("22:30") == 1350
        assert parse_hhmm("23:59") == 1439

    def test_garbage_does_not_raise(self):
        assert parse_hhmm("") == 0
        assert parse_hhmm("abc") == 0
        assert parse_hhmm("25:70") == 70   # wrapped, still a usable number


class TestActiveRule:
    def test_first_match_wins(self):
        rules = [ScheduleRule("09:00", "17:00", 80), ScheduleRule("10:00", "12:00", 40)]
        assert active_rule(rules, m(11)).value == 80

    def test_disabled_skipped(self):
        rules = [ScheduleRule("09:00", "17:00", 80, enabled=False),
                 ScheduleRule("10:00", "12:00", 40)]
        assert active_rule(rules, m(11)).value == 40

    def test_none_when_outside(self):
        assert active_rule([ScheduleRule("09:00", "17:00", 80)], m(20)) is None

    def test_empty(self):
        assert active_rule([], m(12)) is None


class TestVcpScaling:
    def test_percent_of_hundred_range(self):
        assert VcpValue(0, 50, 100).to_percent() == 50

    def test_non_hundred_max(self):
        # v1 hardcoded 0-100 and would have driven this monitor to 20% of its range.
        assert VcpValue(0, 128, 255).to_percent() == 50
        assert VcpValue(0, 0, 255).percent_to_raw(100) == 255
        assert VcpValue(0, 0, 255).percent_to_raw(50) == 128

    def test_nonzero_minimum(self):
        assert VcpValue(20, 20, 120).to_percent() == 0
        assert VcpValue(20, 120, 120).to_percent() == 100
        assert VcpValue(20, 20, 120).percent_to_raw(50) == 70

    def test_clamps_out_of_range_input(self):
        assert VcpValue(0, 0, 100).percent_to_raw(150) == 100
        assert VcpValue(0, 0, 100).percent_to_raw(-10) == 0

    def test_degenerate_range_does_not_divide_by_zero(self):
        assert VcpValue(50, 50, 50).to_percent() == 0


class TestIdentity:
    def test_interface_path(self):
        assert normalize_identity(
            r"\\?\DISPLAY#GSM7714#5&9063784&1&UID4352#{e6f07b5f-ee97-4a90-b076-33f57bf4eaa7}"
        ) == "DISPLAY#GSM7714#5&9063784&1&UID4352"

    def test_wmi_instance_name_matches_interface_path(self):
        # This equality is what tells the laptop panel apart from a monitor.
        wmi = normalize_identity(r"DISPLAY\BOE0A41\4&3a9f8b26&3&UID8388688_0")
        iface = normalize_identity(r"\\?\DISPLAY#BOE0A41#4&3a9f8b26&3&UID8388688#{guid}")
        assert wmi == iface == "DISPLAY#BOE0A41#4&3A9F8B26&3&UID8388688"

    def test_unknown_shape_survives(self):
        assert normalize_identity("weird") == "WEIRD"


def _edid_with_name(name: bytes) -> bytes:
    edid = bytearray(128)
    edid[8], edid[9] = 0x1E, 0x6D          # "GSM"
    edid[54:57] = b"\x00\x00\x00"
    edid[57] = 0xFC
    edid[58] = 0x00
    edid[59:59 + len(name)] = name
    return bytes(edid)


class TestEdid:
    def test_name_descriptor(self):
        assert parse_edid_name(_edid_with_name(b"LG HDR WFHD\x0a ")) == "LG HDR WFHD"

    def test_vendor_code(self):
        assert parse_edid_vendor(_edid_with_name(b"X\x0a")) == "GSM"

    def test_truncated_edid_returns_none(self):
        assert parse_edid_name(b"\x00" * 40) is None


class TestAutostart:
    def test_dev_entry_points_at_a_real_file(self):
        # Off-by-one in parents[] here writes a Run key to a path that does
        # not exist, and the failure only shows up at the next logon.
        from lumina.features.autostart import dev_entry
        assert dev_entry().is_file(), f"{dev_entry()} missing"


class TestConfig:
    def test_roundtrip(self):
        cfg = Config(sync=True, fade_duration_ms=1500,
                     schedules=[ScheduleRule("22:00", "06:00", 20)])
        import json
        restored = Config.from_dict(json.loads(cfg.to_json()))
        assert restored.sync is True
        assert restored.fade_duration_ms == 1500
        assert restored.schedules == [ScheduleRule("22:00", "06:00", 20, True)]

    def test_partial_dict_uses_defaults(self):
        cfg = Config.from_dict({"sync": True})
        assert cfg.sync is True
        assert cfg.schedules == []
        assert cfg.fade_enabled is True

    def test_bad_types_are_coerced_not_fatal(self):
        cfg = Config.from_dict({"schedules": ["not a dict", {"value": 500}]})
        assert len(cfg.schedules) == 1
        assert cfg.schedules[0].value == 100, "out-of-range percent clamped"
