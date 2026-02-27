#!/usr/bin/env python3
"""S3 Snapshot Lifecycle Management for OpenClaw Lab.

Implements tiered retention policy:
  - < 24 hours: Keep all hourly snapshots
  - 24h - 7 days: Keep only 00:00 UTC daily snapshots
  - 7 days - 30 days: Keep only Friday snapshots
  - > 30 days: Delete all snapshots
  - Always preserve: latest/ (never deleted)

Snapshot path format: snapshots/YYYY-MM-DD-HH-MM/
"""

import sys
from datetime import datetime, timedelta, timezone
from typing import List, Set
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S%z",
)
logger = logging.getLogger(__name__)


def parse_snapshot_timestamp(snapshot_path: str) -> datetime | None:
    """Parse snapshot timestamp from path like 'snapshots/2026-02-27-14-30/'.

    Args:
        snapshot_path: S3 prefix path (e.g., 'snapshots/2026-02-27-14-30/')

    Returns:
        datetime object in UTC, or None if path doesn't match expected format
    """
    # Remove trailing slash and 'snapshots/' prefix
    path = snapshot_path.rstrip("/")
    if not path.startswith("snapshots/"):
        return None

    timestamp_str = path.replace("snapshots/", "")

    # Expected format: YYYY-MM-DD-HH-MM
    try:
        return datetime.strptime(timestamp_str, "%Y-%m-%d-%H-%M").replace(
            tzinfo=timezone.utc
        )
    except ValueError:
        return None


def is_daily_snapshot(snapshot_dt: datetime) -> bool:
    """Check if snapshot is a daily snapshot (00:00 UTC).

    Args:
        snapshot_dt: Snapshot datetime

    Returns:
        True if hour and minute are both 00
    """
    return snapshot_dt.hour == 0 and snapshot_dt.minute == 0


def is_friday_snapshot(snapshot_dt: datetime) -> bool:
    """Check if snapshot was taken on a Friday.

    Args:
        snapshot_dt: Snapshot datetime

    Returns:
        True if weekday is Friday (4)
    """
    return snapshot_dt.weekday() == 4  # Friday = 4


def calculate_snapshots_to_keep(
    snapshot_paths: List[str], now: datetime | None = None
) -> Set[str]:
    """Calculate which snapshots should be retained based on retention policy.

    Retention policy:
      - < 24 hours old: Keep all
      - 24h - 7 days old: Keep only 00:00 UTC daily snapshots
      - 7 days - 30 days old: Keep only Friday snapshots
      - > 30 days old: Delete all

    Args:
        snapshot_paths: List of S3 snapshot paths (e.g., ['snapshots/2026-02-27-14-00/'])
        now: Current time (for testing; defaults to datetime.now(UTC))

    Returns:
        Set of snapshot paths to keep
    """
    if now is None:
        now = datetime.now(timezone.utc)

    to_keep: Set[str] = set()

    for path in snapshot_paths:
        snapshot_dt = parse_snapshot_timestamp(path)
        if snapshot_dt is None:
            # Invalid format - log and skip
            logger.warning(f"Skipping invalid snapshot path: {path}")
            continue

        age = now - snapshot_dt

        # Rule 1: Keep all snapshots < 24 hours old
        if age < timedelta(hours=24):
            to_keep.add(path)
            continue

        # Rule 2: 24h - 7 days: Keep only 00:00 UTC daily snapshots
        if age < timedelta(days=7):
            if is_daily_snapshot(snapshot_dt):
                to_keep.add(path)
            continue

        # Rule 3: 7 days - 30 days: Keep only Friday snapshots
        if age < timedelta(days=30):
            if is_friday_snapshot(snapshot_dt) and is_daily_snapshot(snapshot_dt):
                to_keep.add(path)
            continue

        # Rule 4: > 30 days: Delete (not added to to_keep)

    return to_keep


def list_s3_snapshot_prefixes(bucket_name: str, region: str) -> List[str]:
    """List all snapshot prefixes in S3 bucket.

    Args:
        bucket_name: S3 bucket name
        region: AWS region

    Returns:
        List of snapshot prefix paths (e.g., ['snapshots/2026-02-27-14-00/'])
    """
    import boto3  # type: ignore[import-not-found]

    s3 = boto3.client("s3", region_name=region)
    paginator = s3.get_paginator("list_objects_v2")

    prefixes: Set[str] = set()

    # List all objects under snapshots/ prefix
    for page in paginator.paginate(
        Bucket=bucket_name, Prefix="snapshots/", Delimiter="/"
    ):
        # CommonPrefixes gives us the snapshot directories
        for prefix in page.get("CommonPrefixes", []):
            prefixes.add(prefix["Prefix"])

    return sorted(prefixes)


def delete_s3_prefix(
    bucket_name: str, prefix: str, region: str, dry_run: bool = False
) -> int:
    """Delete all objects under a given S3 prefix.

    Args:
        bucket_name: S3 bucket name
        prefix: S3 prefix to delete (e.g., 'snapshots/2026-02-27-14-00/')
        region: AWS region
        dry_run: If True, log what would be deleted without deleting

    Returns:
        Number of objects deleted (or would be deleted if dry_run=True)
    """
    import boto3

    s3 = boto3.client("s3", region_name=region)
    paginator = s3.get_paginator("list_objects_v2")

    deleted_count = 0

    for page in paginator.paginate(Bucket=bucket_name, Prefix=prefix):
        objects = page.get("Contents", [])
        if not objects:
            continue

        delete_keys = [{"Key": obj["Key"]} for obj in objects]

        if dry_run:
            logger.info(
                f"[DRY RUN] Would delete {len(delete_keys)} objects from {prefix}"
            )
            deleted_count += len(delete_keys)
        else:
            s3.delete_objects(Bucket=bucket_name, Delete={"Objects": delete_keys})
            logger.info(f"Deleted {len(delete_keys)} objects from {prefix}")
            deleted_count += len(delete_keys)

    return deleted_count


def apply_lifecycle_policy(
    bucket_name: str, region: str, dry_run: bool = False
) -> None:
    """Apply snapshot retention policy to S3 bucket.

    Args:
        bucket_name: S3 bucket name
        region: AWS region
        dry_run: If True, log actions without making changes
    """
    logger.info(f"Starting lifecycle policy for s3://{bucket_name} (dry_run={dry_run})")

    # List all snapshot prefixes
    all_snapshots = list_s3_snapshot_prefixes(bucket_name, region)
    logger.info(f"Found {len(all_snapshots)} total snapshots")

    # Calculate which to keep
    to_keep = calculate_snapshots_to_keep(all_snapshots)
    logger.info(f"Retention policy: keeping {len(to_keep)} snapshots")

    # Delete snapshots not in keep list
    to_delete = set(all_snapshots) - to_keep
    if to_delete:
        logger.info(f"Deleting {len(to_delete)} expired snapshots")
        for snapshot_path in sorted(to_delete):
            delete_s3_prefix(bucket_name, snapshot_path, region, dry_run=dry_run)
    else:
        logger.info("No snapshots to delete")

    logger.info("Lifecycle policy complete")


def main() -> int:
    """Main entry point for lifecycle script."""
    import argparse

    parser = argparse.ArgumentParser(description="Apply S3 snapshot lifecycle policy")
    parser.add_argument("--bucket", required=True, help="S3 bucket name")
    parser.add_argument("--region", required=True, help="AWS region")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Log actions without making changes",
    )
    args = parser.parse_args()

    try:
        apply_lifecycle_policy(args.bucket, args.region, dry_run=args.dry_run)
        return 0
    except Exception as e:
        logger.error(f"Lifecycle policy failed: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
