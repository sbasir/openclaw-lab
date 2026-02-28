"""Tests for S3 snapshot lifecycle management."""

from datetime import datetime, timezone, timedelta
import sys
from pathlib import Path

# Add templates directory to path to import the lifecycle script
templates_dir = Path(__file__).parent.parent / "templates"
sys.path.insert(0, str(templates_dir))

# Import functions from the lifecycle script
from s3_snapshot_lifecycle import (  # noqa: E402
    parse_snapshot_timestamp,
    is_daily_snapshot,
    is_friday_snapshot,
    calculate_snapshots_to_keep,
)


class TestParseSnapshotTimestamp:
    """Tests for parsing snapshot timestamps from S3 paths."""

    def test_valid_snapshot_path(self) -> None:
        """Test parsing a valid snapshot path."""
        path = "snapshots/2026-02-27-14-30/"
        result = parse_snapshot_timestamp(path)
        assert result == datetime(2026, 2, 27, 14, 30, tzinfo=timezone.utc)

    def test_valid_snapshot_path_without_trailing_slash(self) -> None:
        """Test parsing a valid snapshot path without trailing slash."""
        path = "snapshots/2026-02-27-14-30"
        result = parse_snapshot_timestamp(path)
        assert result == datetime(2026, 2, 27, 14, 30, tzinfo=timezone.utc)

    def test_invalid_format(self) -> None:
        """Test parsing an invalid snapshot path format."""
        path = "snapshots/invalid-format/"
        result = parse_snapshot_timestamp(path)
        assert result is None

    def test_non_snapshot_prefix(self) -> None:
        """Test parsing a path without snapshots/ prefix."""
        path = "latest/2026-02-27-14-30/"
        result = parse_snapshot_timestamp(path)
        assert result is None

    def test_midnight_snapshot(self) -> None:
        """Test parsing a midnight snapshot (00:00)."""
        path = "snapshots/2026-02-27-00-00/"
        result = parse_snapshot_timestamp(path)
        assert result == datetime(2026, 2, 27, 0, 0, tzinfo=timezone.utc)


class TestIsDailySnapshot:
    """Tests for identifying daily snapshots (00:00 UTC)."""

    def test_midnight_is_daily(self) -> None:
        """Test that 00:00 UTC is a daily snapshot."""
        dt = datetime(2026, 2, 27, 0, 0, tzinfo=timezone.utc)
        assert is_daily_snapshot(dt) is True

    def test_non_midnight_is_not_daily(self) -> None:
        """Test that non-midnight times are not daily snapshots."""
        dt = datetime(2026, 2, 27, 14, 30, tzinfo=timezone.utc)
        assert is_daily_snapshot(dt) is False

    def test_midnight_with_seconds_is_daily(self) -> None:
        """Test that 00:00:xx is still a daily snapshot."""
        dt = datetime(2026, 2, 27, 0, 0, 59, tzinfo=timezone.utc)
        assert is_daily_snapshot(dt) is True

    def test_midnight_with_minutes_is_daily(self) -> None:
        """Test that 00:xx:00 is still a daily snapshot."""
        dt = datetime(2026, 2, 27, 0, 15, 0, tzinfo=timezone.utc)
        assert is_daily_snapshot(dt) is True

    def test_midnight_plus_hour_is_not_daily(self) -> None:
        """Test that 01:00:00 is not a daily snapshot."""
        dt = datetime(2026, 2, 27, 1, 0, 0, tzinfo=timezone.utc)
        assert is_daily_snapshot(dt) is False

    def test_midnight_minus_minute_is_not_daily(self) -> None:
        """Test that 23:59:00 is not a daily snapshot."""
        dt = datetime(2026, 2, 26, 23, 59, 0, tzinfo=timezone.utc)
        assert is_daily_snapshot(dt) is False


class TestIsFridaySnapshot:
    """Tests for identifying Friday snapshots."""

    def test_friday_is_identified(self) -> None:
        """Test that a Friday is correctly identified."""
        # 2026-02-27 is a Friday
        dt = datetime(2026, 2, 27, 14, 30, tzinfo=timezone.utc)
        assert is_friday_snapshot(dt) is True

    def test_non_friday_is_not_identified(self) -> None:
        """Test that non-Friday days are not identified as Friday."""
        # 2026-02-28 is a Saturday
        dt = datetime(2026, 2, 28, 14, 30, tzinfo=timezone.utc)
        assert is_friday_snapshot(dt) is False

    def test_monday_is_not_friday(self) -> None:
        """Test that Monday is not identified as Friday."""
        # 2026-03-02 is a Monday
        dt = datetime(2026, 3, 2, 0, 0, tzinfo=timezone.utc)
        assert is_friday_snapshot(dt) is False


class TestCalculateSnapshotsToKeep:
    """Tests for the snapshot retention policy calculation."""

    def test_keep_all_recent_hourly_snapshots(self) -> None:
        """Test that hourly snapshots < 24 hours old are kept."""
        now = datetime(2026, 2, 27, 12, 0, tzinfo=timezone.utc)

        # Create snapshots from last 6 hours (hourly)
        snapshots = [
            f"snapshots/2026-02-27-{hour:02d}-{minute:02d}/"
            for hour in range(6, 12)  # 06:00 to 11:00
            for minute in [5, 25, 45]
        ]

        to_keep = calculate_snapshots_to_keep(snapshots, now)

        # Only one snapshot per hour should be kept (earliest minute)
        expected = [
            f"snapshots/2026-02-27-{hour:02d}-05/"
            for hour in range(6, 12)  # 06:00 to 11:00
        ]

        # Only one per hour should be kept (all < 24h old)
        assert len(to_keep) == len(expected)
        assert to_keep == set(expected)

    def test_daily_retention_24h_to_7d(self) -> None:
        """Test that only 00:00 UTC snapshots are kept in 24h-7d range."""
        now = datetime(2026, 2, 27, 12, 0, tzinfo=timezone.utc)

        # Create snapshots from 2-5 days ago (mix of hourly)
        snapshots = [
            "snapshots/2026-02-25-00-00/",  # 2 days ago, midnight (KEEP)
            "snapshots/2026-02-25-14-00/",  # 2 days ago, 14:00 (DELETE)
            "snapshots/2026-02-24-00-00/",  # 3 days ago, midnight (KEEP)
            "snapshots/2026-02-24-08-00/",  # 3 days ago, 08:00 (DELETE)
            "snapshots/2026-02-23-00-00/",  # 4 days ago, midnight (KEEP)
            "snapshots/2026-02-23-18-00/",  # 4 days ago, 18:00 (DELETE)
        ]

        to_keep = calculate_snapshots_to_keep(snapshots, now)

        # Only midnight snapshots should be kept
        expected = {
            "snapshots/2026-02-25-00-00/",
            "snapshots/2026-02-24-00-00/",
            "snapshots/2026-02-23-00-00/",
        }
        assert to_keep == expected

    def test_friday_retention_7d_to_30d(self) -> None:
        """Test that only Friday 00:00 snapshots are kept in 7d-30d range."""
        now = datetime(2026, 2, 27, 12, 0, tzinfo=timezone.utc)  # Friday

        # Create snapshots from 8-15 days ago
        snapshots = [
            "snapshots/2026-02-20-00-00/",  # 7 days ago, Friday midnight (KEEP)
            "snapshots/2026-02-19-00-00/",  # 8 days ago, Thursday midnight (DELETE)
            "snapshots/2026-02-18-00-00/",  # 9 days ago, Wednesday midnight (DELETE)
            "snapshots/2026-02-17-00-00/",  # 10 days ago, Tuesday midnight (DELETE)
            "snapshots/2026-02-16-00-00/",  # 11 days ago, Monday midnight (DELETE)
            "snapshots/2026-02-15-00-00/",  # 12 days ago, Sunday midnight (DELETE)
            "snapshots/2026-02-14-00-00/",  # 13 days ago, Saturday midnight (DELETE)
            "snapshots/2026-02-13-00-00/",  # 14 days ago, Friday midnight (KEEP)
        ]

        to_keep = calculate_snapshots_to_keep(snapshots, now)

        # Only Friday midnight snapshots should be kept
        expected = {
            "snapshots/2026-02-20-00-00/",
            "snapshots/2026-02-13-00-00/",
        }
        assert to_keep == expected

    def test_delete_all_over_30_days(self) -> None:
        """Test that all snapshots > 30 days old are deleted."""
        now = datetime(2026, 2, 27, 12, 0, tzinfo=timezone.utc)

        # Create snapshots from 31-35 days ago (all Fridays at midnight)
        snapshots = [
            "snapshots/2026-01-27-00-00/",  # 31 days ago, Friday midnight
            "snapshots/2026-01-24-00-00/",  # 34 days ago, Friday midnight
            "snapshots/2026-01-23-00-00/",  # 35 days ago, Friday midnight
        ]

        to_keep = calculate_snapshots_to_keep(snapshots, now)

        # None should be kept (all > 30 days)
        assert len(to_keep) == 0

    def test_comprehensive_retention_policy(self) -> None:
        """Test the entire retention policy with snapshots across all ranges."""
        now = datetime(2026, 2, 27, 12, 0, tzinfo=timezone.utc)  # Friday 12:00

        snapshots = [
            # < 24h: keep all
            "snapshots/2026-02-27-10-00/",  # 2h ago (KEEP)
            "snapshots/2026-02-27-08-00/",  # 4h ago (KEEP)
            "snapshots/2026-02-27-00-00/",  # 12h ago (KEEP - also daily)
            "snapshots/2026-02-26-18-00/",  # 18h ago (KEEP)
            "snapshots/2026-02-26-14-00/",  # 22h ago (KEEP - still < 24h)
            # 24h-7d: keep only 00:00 UTC
            "snapshots/2026-02-26-00-00/",  # 1d 12h ago, midnight (KEEP)
            "snapshots/2026-02-26-10-00/",  # 1d 2h ago, 10:00 (DELETE - not midnight)
            "snapshots/2026-02-25-00-00/",  # 2d 12h ago, midnight (KEEP)
            "snapshots/2026-02-24-00-00/",  # 3d 12h ago, midnight (KEEP)
            "snapshots/2026-02-23-00-00/",  # 4d 12h ago, midnight (KEEP)
            "snapshots/2026-02-22-00-00/",  # 5d 12h ago, midnight (KEEP)
            "snapshots/2026-02-21-00-00/",  # 6d 12h ago, midnight (KEEP)
            # 7d-30d: keep only Friday 00:00
            "snapshots/2026-02-20-00-00/",  # 7d 12h ago, Friday midnight (KEEP)
            "snapshots/2026-02-19-00-00/",  # 8d 12h ago, Thursday midnight (DELETE)
            "snapshots/2026-02-13-00-00/",  # 14d 12h ago, Friday midnight (KEEP)
            "snapshots/2026-02-06-00-00/",  # 21d 12h ago, Friday midnight (KEEP)
            "snapshots/2026-01-30-00-00/",  # 28d 12h ago, Friday midnight (KEEP)
            # > 30d: delete all
            "snapshots/2026-01-27-00-00/",  # 31d 12h ago, Friday midnight (DELETE)
            "snapshots/2026-01-20-00-00/",  # 38d 12h ago, Friday midnight (DELETE)
        ]

        to_keep = calculate_snapshots_to_keep(snapshots, now)

        expected = {
            # < 24h
            "snapshots/2026-02-27-10-00/",
            "snapshots/2026-02-27-08-00/",
            "snapshots/2026-02-27-00-00/",
            "snapshots/2026-02-26-18-00/",
            "snapshots/2026-02-26-14-00/",  # Fixed: < 24h
            # 24h-7d (daily)
            "snapshots/2026-02-26-00-00/",
            "snapshots/2026-02-25-00-00/",
            "snapshots/2026-02-24-00-00/",
            "snapshots/2026-02-23-00-00/",
            "snapshots/2026-02-22-00-00/",
            "snapshots/2026-02-21-00-00/",
            # 7d-30d (Friday only)
            "snapshots/2026-02-20-00-00/",
            "snapshots/2026-02-13-00-00/",
            "snapshots/2026-02-06-00-00/",
            "snapshots/2026-01-30-00-00/",
        }

        assert to_keep == expected

    def test_invalid_snapshot_paths_are_skipped(self) -> None:
        """Test that invalid snapshot paths are skipped."""
        now = datetime(2026, 2, 27, 12, 0, tzinfo=timezone.utc)

        snapshots = [
            "snapshots/2026-02-27-10-00/",  # Valid (KEEP)
            "snapshots/invalid-format/",  # Invalid format
            "latest/2026-02-27-10-00/",  # Wrong prefix
            "snapshots/2026-02-27-08-00/",  # Valid (KEEP)
        ]

        to_keep = calculate_snapshots_to_keep(snapshots, now)

        # Only valid snapshots should be in the result
        expected = {
            "snapshots/2026-02-27-10-00/",
            "snapshots/2026-02-27-08-00/",
        }
        assert to_keep == expected

    def test_empty_snapshot_list(self) -> None:
        """Test handling of empty snapshot list."""
        now = datetime(2026, 2, 27, 12, 0, tzinfo=timezone.utc)
        snapshots: list[str] = []

        to_keep = calculate_snapshots_to_keep(snapshots, now)

        assert len(to_keep) == 0

    def test_boundary_exactly_24_hours(self) -> None:
        """Test snapshot exactly at 24 hour boundary."""
        now = datetime(2026, 2, 27, 12, 0, tzinfo=timezone.utc)

        # Snapshot exactly 24 hours ago
        snapshots = ["snapshots/2026-02-26-12-00/"]

        to_keep = calculate_snapshots_to_keep(snapshots, now)

        # At exactly 24h, should transition to daily-only rule
        # Since it's not 00:00, it should NOT be kept
        assert len(to_keep) == 0

    def test_boundary_exactly_7_days(self) -> None:
        """Test snapshot exactly at 7 day boundary."""
        now = datetime(2026, 2, 27, 12, 0, tzinfo=timezone.utc)  # Friday

        # Snapshot exactly 7 days ago (Thursday midnight)
        snapshots = ["snapshots/2026-02-20-12-00/"]  # Thursday 12:00

        to_keep = calculate_snapshots_to_keep(snapshots, now)

        # At exactly 7d, should transition to Friday-only rule
        # Since it's not Friday, it should NOT be kept
        assert len(to_keep) == 0

    def test_hourly_run_idempotence(self) -> None:
        """Running the lifecycle policy an hour later should not add back
        snapshots that were already marked for deletion.

        This guards against bugs when the service is scheduled more frequently
        than once per day (the hourly timer).  As long as no snapshot ages out of
        the 24‑hour window between runs, the keep set should remain identical.
        """
        base_now = datetime(2026, 2, 27, 12, 0, tzinfo=timezone.utc)

        snapshots = [
            "snapshots/2026-02-27-10-15/",
            "snapshots/2026-02-27-11-45/",
        ]

        keep1 = calculate_snapshots_to_keep(snapshots, base_now)
        keep2 = calculate_snapshots_to_keep(snapshots, base_now + timedelta(hours=1))

        assert keep1 == keep2
