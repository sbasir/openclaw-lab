"""CloudWatch dashboard JSON builders for the EC2 Spot stack."""

from __future__ import annotations

import json
from typing import Any


def _build_cpu_widget(
    instance_id: str, aws_region: str, stack_name: str
) -> dict[str, Any]:
    return {
        "type": "metric",
        "x": 0,
        "y": 0,
        "width": 12,
        "height": 6,
        "properties": {
            "title": f"OpenClaw EC2 CPU Utilization ({stack_name})",
            "region": aws_region,
            "view": "timeSeries",
            "stacked": False,
            "period": 300,
            "metrics": [
                [
                    "AWS/EC2",
                    "CPUUtilization",
                    "InstanceId",
                    instance_id,
                    {"stat": "Average", "label": "CPUUtilization"},
                ]
            ],
            "yAxis": {"left": {"min": 0, "max": 100}},
        },
    }


def _build_memory_widget(
    instance_id: str, aws_region: str, stack_name: str
) -> dict[str, Any]:
    return {
        "type": "metric",
        "x": 12,
        "y": 0,
        "width": 12,
        "height": 6,
        "properties": {
            "title": f"OpenClaw Memory Used % ({stack_name})",
            "region": aws_region,
            "view": "timeSeries",
            "stacked": False,
            "period": 300,
            "metrics": [
                [
                    "OpenClawLab/EC2",
                    "MEM_USED_PERCENT",
                    "InstanceId",
                    instance_id,
                    {"stat": "Average", "label": "MEM_USED_PERCENT"},
                ]
            ],
            "yAxis": {"left": {"min": 0, "max": 100}},
        },
    }


def _build_status_widget(instance_id: str, aws_region: str) -> dict[str, Any]:
    return {
        "type": "metric",
        "x": 0,
        "y": 6,
        "width": 8,
        "height": 6,
        "properties": {
            "title": "EC2 Status Checks",
            "region": aws_region,
            "view": "timeSeries",
            "stacked": False,
            "period": 300,
            "metrics": [
                [
                    "AWS/EC2",
                    "StatusCheckFailed",
                    "InstanceId",
                    instance_id,
                    {"stat": "Maximum", "label": "StatusCheckFailed"},
                ],
                [
                    "AWS/EC2",
                    "StatusCheckFailed_Instance",
                    "InstanceId",
                    instance_id,
                    {"stat": "Maximum", "label": "Instance"},
                ],
                [
                    "AWS/EC2",
                    "StatusCheckFailed_System",
                    "InstanceId",
                    instance_id,
                    {"stat": "Maximum", "label": "System"},
                ],
            ],
            "yAxis": {"left": {"min": 0, "max": 1}},
        },
    }


def _build_network_widget(instance_id: str, aws_region: str) -> dict[str, Any]:
    return {
        "type": "metric",
        "x": 8,
        "y": 6,
        "width": 8,
        "height": 6,
        "properties": {
            "title": "EC2 Network (Bytes)",
            "region": aws_region,
            "view": "timeSeries",
            "stacked": False,
            "period": 300,
            "metrics": [
                [
                    "AWS/EC2",
                    "NetworkIn",
                    "InstanceId",
                    instance_id,
                    {"stat": "Sum", "label": "NetworkIn"},
                ],
                [
                    "AWS/EC2",
                    "NetworkOut",
                    "InstanceId",
                    instance_id,
                    {"stat": "Sum", "label": "NetworkOut"},
                ],
            ],
            "yAxis": {"left": {"min": 0}},
        },
    }


def _build_logs_widget(instance_id: str, aws_region: str) -> dict[str, Any]:
    return {
        "type": "log",
        "x": 16,
        "y": 6,
        "width": 8,
        "height": 6,
        "properties": {
            "query": (
                "SOURCE '/aws/ec2/openclaw-lab'\n"
                f"| filter @logStream like /{instance_id}\\/docker/\n"
                "| filter @message like /[Oo]pen[Cc]law|[Gg]ateway|[Dd]evice|[Pp]air|ERROR|Error|error|WARN|Warn|warn|FAIL|Fail|fail/\n"
                "| fields @timestamp, @logStream, @message\n"
                "| sort @timestamp desc\n"
                "| limit 50"
            ),
            "region": aws_region,
            "title": "OpenClaw Container Logs (Filtered)",
        },
    }


def _build_ebs_throughput_widget(volume_id: str, aws_region: str) -> dict[str, Any]:
    return {
        "type": "metric",
        "x": 0,
        "y": 12,
        "width": 12,
        "height": 6,
        "properties": {
            "title": "EBS Throughput (Bytes)",
            "region": aws_region,
            "view": "timeSeries",
            "stacked": False,
            "period": 300,
            "metrics": [
                [
                    "AWS/EBS",
                    "VolumeReadBytes",
                    "VolumeId",
                    volume_id,
                    {"stat": "Sum", "label": "VolumeReadBytes"},
                ],
                [
                    "AWS/EBS",
                    "VolumeWriteBytes",
                    "VolumeId",
                    volume_id,
                    {"stat": "Sum", "label": "VolumeWriteBytes"},
                ],
            ],
            "yAxis": {"left": {"min": 0}},
        },
    }


def _build_ebs_ops_widget(volume_id: str, aws_region: str) -> dict[str, Any]:
    return {
        "type": "metric",
        "x": 12,
        "y": 12,
        "width": 12,
        "height": 6,
        "properties": {
            "title": "EBS Operations",
            "region": aws_region,
            "view": "timeSeries",
            "stacked": False,
            "period": 300,
            "metrics": [
                [
                    "AWS/EBS",
                    "VolumeReadOps",
                    "VolumeId",
                    volume_id,
                    {"stat": "Sum", "label": "VolumeReadOps"},
                ],
                [
                    "AWS/EBS",
                    "VolumeWriteOps",
                    "VolumeId",
                    volume_id,
                    {"stat": "Sum", "label": "VolumeWriteOps"},
                ],
                [
                    "AWS/EBS",
                    "VolumeQueueLength",
                    "VolumeId",
                    volume_id,
                    {"stat": "Average", "label": "VolumeQueueLength"},
                ],
            ],
            "yAxis": {"left": {"min": 0}},
        },
    }


def _build_ec2_disk_widget(instance_id: str, aws_region: str) -> dict[str, Any]:
    return {
        "type": "metric",
        "x": 0,
        "y": 18,
        "width": 8,
        "height": 6,
        "properties": {
            "title": "Disk Used % (Root + Data)",
            "region": aws_region,
            "view": "timeSeries",
            "stacked": False,
            "period": 300,
            "metrics": [
                [
                    "OpenClawLab/EC2",
                    "DISK_USED_PERCENT",
                    "InstanceId",
                    instance_id,
                    "path",
                    "/",
                    {"stat": "Average", "label": "Root /"},
                ],
                [
                    "OpenClawLab/EC2",
                    "DISK_USED_PERCENT",
                    "InstanceId",
                    instance_id,
                    "path",
                    "/opt/openclaw",
                    {"stat": "Average", "label": "Data /opt/openclaw"},
                ],
            ],
            "yAxis": {"left": {"min": 0, "max": 100}},
        },
    }


def _build_ec2_disk_bytes_widget(instance_id: str, aws_region: str) -> dict[str, Any]:
    return {
        "type": "metric",
        "x": 8,
        "y": 18,
        "width": 8,
        "height": 6,
        "properties": {
            "title": "Disk I/O (CWAgent)",
            "region": aws_region,
            "view": "timeSeries",
            "stacked": False,
            "period": 300,
            "metrics": [
                [
                    "OpenClawLab/EC2",
                    "DISK_READ_BYTES",
                    "InstanceId",
                    instance_id,
                    {"stat": "Sum", "label": "DISK_READ_BYTES"},
                ],
                [
                    "OpenClawLab/EC2",
                    "DISK_WRITE_BYTES",
                    "InstanceId",
                    instance_id,
                    {"stat": "Sum", "label": "DISK_WRITE_BYTES"},
                ],
            ],
            "yAxis": {"left": {"min": 0}},
        },
    }


def _build_ssm_widget(aws_region: str) -> dict[str, Any]:
    return {
        "type": "metric",
        "x": 16,
        "y": 18,
        "width": 8,
        "height": 6,
        "properties": {
            "title": "SSM Command Status",
            "region": aws_region,
            "view": "timeSeries",
            "stacked": False,
            "period": 300,
            "metrics": [
                ["AWS/SSM", "CommandsSucceeded", {"stat": "Sum", "label": "Succeeded"}],
                ["AWS/SSM", "CommandsFailed", {"stat": "Sum", "label": "Failed"}],
                ["AWS/SSM", "CommandsTimedOut", {"stat": "Sum", "label": "TimedOut"}],
            ],
            "yAxis": {"left": {"min": 0}},
        },
    }


def _build_ebs_performance_widget(volume_id: str, aws_region: str) -> dict[str, Any]:
    return {
        "type": "metric",
        "x": 0,
        "y": 24,
        "width": 24,
        "height": 6,
        "properties": {
            "title": "EBS Performance Indicators",
            "region": aws_region,
            "view": "timeSeries",
            "stacked": False,
            "period": 300,
            "metrics": [
                [
                    "AWS/EBS",
                    "VolumeThroughputPercentage",
                    "VolumeId",
                    volume_id,
                    {"stat": "Average", "label": "Throughput%"},
                ],
                [
                    "AWS/EBS",
                    "VolumeConsumedReadWriteOps",
                    "VolumeId",
                    volume_id,
                    {"stat": "Average", "label": "ConsumedIOPS"},
                ],
                [
                    "AWS/EBS",
                    "VolumeIdleTime",
                    "VolumeId",
                    volume_id,
                    {"stat": "Average", "label": "IdleTime"},
                ],
            ],
            "yAxis": {"left": {"min": 0}},
        },
    }


def create_minimal_dashboard_body(
    *,
    instance_id: str,
    volume_id: str,
    aws_region: str,
    stack_name: str,
) -> str:
    """Create a minimal, known-good dashboard body with one metric widget.

    This is intentionally small to validate schema correctness before incrementally
    adding more widgets.
    """
    body = {
        "widgets": [
            _build_cpu_widget(instance_id, aws_region, stack_name),
            _build_memory_widget(instance_id, aws_region, stack_name),
            _build_status_widget(instance_id, aws_region),
            _build_network_widget(instance_id, aws_region),
            _build_logs_widget(instance_id, aws_region),
            _build_ebs_throughput_widget(volume_id, aws_region),
            _build_ebs_ops_widget(volume_id, aws_region),
            _build_ec2_disk_widget(instance_id, aws_region),
            _build_ec2_disk_bytes_widget(instance_id, aws_region),
            _build_ssm_widget(aws_region),
            _build_ebs_performance_widget(volume_id, aws_region),
        ]
    }
    return json.dumps(body)
