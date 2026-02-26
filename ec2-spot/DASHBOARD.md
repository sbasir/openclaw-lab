# CloudWatch Dashboard Documentation

## Overview

The `ec2-spot` stack creates CloudWatch dashboard `openclaw-lab-observability`.

The dashboard body is built in `ec2-spot/dashboard_builder.py` and passed to `aws.cloudwatch.Dashboard` in `ec2-spot/__main__.py`.

## Access

```bash
# Print stack outputs (includes dashboard_url)
make ec2-spot-output

# Open dashboard in browser
make openclaw-dashboard
```

## Current Widget Set

The current implementation contains 11 widgets:

1. **EC2 CPU Utilization** (`AWS/EC2: CPUUtilization`)
2. **OpenClaw Memory Used %** (`OpenClawLab/EC2: MEM_USED_PERCENT`)
3. **EC2 Status Checks** (`StatusCheckFailed*`)
4. **EC2 Network In/Out** (`AWS/EC2`)
5. **OpenClaw Container Logs (Filtered)** (CloudWatch Logs Insights)
6. **EBS Throughput (Bytes)** (`AWS/EBS: VolumeReadBytes/VolumeWriteBytes`)
7. **EBS Operations** (`AWS/EBS: VolumeReadOps/VolumeWriteOps/VolumeQueueLength`)
8. **Disk Used % (Root + Data)** (`OpenClawLab/EC2: DISK_USED_PERCENT` with `path=/` and `path=/opt/openclaw`)
9. **Disk I/O (CWAgent)** (`OpenClawLab/EC2: DISK_READ_BYTES/DISK_WRITE_BYTES`)
10. **SSM Command Status** (`AWS/SSM: CommandsSucceeded/Failed/TimedOut`)
11. **EBS Performance Indicators** (`VolumeThroughputPercentage`, `VolumeConsumedReadWriteOps`, `VolumeIdleTime`)

## Metric Namespaces and Dimensions

### OpenClaw custom metrics
- Namespace: `OpenClawLab/EC2`
- Emitted by CloudWatch Agent from `templates/cloudwatch-agent-config.json`
- Key metrics used by dashboard:
  - `MEM_USED_PERCENT`
  - `DISK_USED_PERCENT`
  - `DISK_READ_BYTES`
  - `DISK_WRITE_BYTES`

### AWS namespaces
- `AWS/EC2` for hypervisor metrics (CPU, network, status checks)
- `AWS/EBS` for volume-level metrics (throughput/ops/perf)
- `AWS/SSM` for command status

## Logs Integration

The dashboard log widget queries stable log group:

- Log group: `/aws/ec2/openclaw-lab`
- Stream model: `{instance_id}/...`
- Widget filters to this instance’s docker stream and OpenClaw-relevant patterns.

Current query shape:

```sql
SOURCE '/aws/ec2/openclaw-lab'
| filter @logStream like /{instance_id}\/docker/
| filter @message like /[Oo]pen[Cc]law|[Gg]ateway|[Dd]evice|[Pp]air|ERROR|Error|error|WARN|Warn|warn|FAIL|Fail|fail/
| fields @timestamp, @logStream, @message
| sort @timestamp desc
| limit 50
```

## CloudWatch Agent Prerequisites

CloudWatch Agent config (`templates/cloudwatch-agent-config.json`) provides:

- Custom metric namespace `OpenClawLab/EC2`
- Aggregation dimensions including `InstanceId` and `path`
- File log collection into `/aws/ec2/openclaw-lab`
  - `/var/log/cloud-init-output.log`
  - `/var/log/messages`
  - `/var/lib/docker/containers/*/*-json.log`

## Troubleshooting

### Memory or disk widgets show no data
- Verify agent is running:
  ```bash
  make openclaw-ec2-connect
  sudo systemctl status amazon-cloudwatch-agent
  ```
- Verify metric names in CloudWatch Metrics:
  - `OpenClawLab/EC2` namespace
  - `MEM_USED_PERCENT`, `DISK_USED_PERCENT`

### Logs widget shows no data
- Confirm log group exists:
  ```bash
  aws logs describe-log-groups --log-group-name-prefix /aws/ec2/openclaw-lab --region $AWS_REGION
  ```
- Confirm docker stream exists for current instance:
  ```bash
  aws logs describe-log-streams --log-group-name /aws/ec2/openclaw-lab --region $AWS_REGION
  ```

### Dashboard drift
- Re-apply stack:
  ```bash
  make ec2-spot-up AUTO_APPROVE=yes
  ```
