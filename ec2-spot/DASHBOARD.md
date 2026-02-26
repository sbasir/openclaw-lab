# CloudWatch Dashboard Documentation

## Overview

The OpenClaw Lab EC2 Spot stack automatically creates a comprehensive CloudWatch Dashboard (`openclaw-lab-observability`) with 20+ widgets providing complete observability across compute, memory, storage, network, and application layers.

The dashboard is production-ready and follows AWS Well-Architected Framework best practices with:
- **Multi-perspective metrics**: OS-level (CloudWatch Agent) + Hypervisor-level (AWS/EC2)
- **Threshold annotations**: Visual indicators for high resource consumption (80% threshold)
- **Log integration**: CloudWatch Logs Insights queries for errors and application logs
- **SSM connectivity**: Systems Manager command execution tracking
- **Time-series visualization**: Default 1-hour window with 60-300 second granularity by metric type

## Accessing the Dashboard

### Via Pulumi Stack Output

```bash
# Get the dashboard URL
cd ec2-spot
pulumi stack output dashboard_url

# Or open directly in browser (macOS/Linux)
open "$(pulumi stack output dashboard_url)"
```

### Via Makefile

```bash
# Quick command to open dashboard in default browser
make openclaw-dashboard
```

### Manual AWS Console Access

1. Go to CloudWatch → Dashboards
2. Search for `openclaw-lab-observability`
3. Click to open

## Dashboard Layout

The dashboard is organized in 8 logical sections, each with related metrics. Widgets are positioned to tell a story of system health from top to bottom.

### Section 1: Header & Status (Row 1)

**Purpose**: Quick overview of instance health and current resource consumption.

| Widget | Purpose | Key Metrics |
|--------|---------|-------------|
| Title & Metadata | Stack context | Instance ID, Region, Stack name |
| EC2 Status Checks | Instance health | StatusCheckFailed, StatusCheckFailed_Instance, StatusCheckFailed_System |
| CPU Single Value | Current CPU (glance) | CPU_USER, CPU_SYSTEM, CPU_IOWAIT |
| Memory Single Value | Current Memory (glance) | MEM_USED_PERCENT, MEM_AVAILABLE_PERCENT |
| Disk Single Value | Current Disk (glance) | DISK_USED_PERCENT (root and /opt/openclaw) |
| Recent Errors | Application issues | CloudWatch Logs with error/warn/fail regex |

**Use Case**: Check instance health before diving into detailed metrics.

---

### Section 2: CPU Performance (Row 2)

**Purpose**: Deep dive into CPU utilization and distribution of CPU time.

| Widget | Type | Details |
|--------|------|---------|
| CPU Usage Breakdown | Stacked time series | User%, System%, IOWait%, Idle% (80% threshold line) |
| EC2 CPU Utilization | Time series | Hypervisor-level min/avg/max CPU% (80% threshold line) |

**Key Insights**:
- High IOWait% indicates disk I/O bottlenecks
- System% spikes can indicate kernel/driver issues
- Compare CloudWatch Agent metrics (OS-level) with EC2 metrics (hypervisor-level) for sanity check

**Common Issues**:
- Sustained CPU > 80%: Consider larger instance type or workload optimization
- High IOWait: Check Disk I/O section for throughput issues
- System% > User%: Potential driver or kernel issue

---

### Section 3: Memory Performance (Row 3)

**Purpose**: Monitor RAM usage and availability to detect memory pressure.

| Widget | Type | Details |
|--------|------|---------|
| Memory Usage (%) | Time series | MEM_USED_PERCENT and MEM_AVAILABLE_PERCENT (80% threshold) |
| Memory Usage (Bytes) | Time series | Absolute MEM_USED_BYTES and MEM_AVAILABLE_BYTES |

**Key Insights**:
- Stable memory indicates predictable workload
- Gradual increase over time may indicate memory leak
- Available% < 20% is concerning for burst/spike protection

**Common Issues**:
- Memory used stuck at 90%+: Possible memory leak or undersized instance
- Periodic drops indicate garbage collection or process restarts

---

### Section 4: Disk Usage & Performance (Row 4)

**Purpose**: Monitor disk space and inode exhaustion on both root and data volumes.

| Widget | Type | Details |
|--------|------|---------|
| Disk Space Used (%) | Time series | Root (/) and /opt/openclaw (80% threshold) |
| Inode Usage | Time series | INODE_USED and INODE_FREE counts |
| EBS Throughput | Time series | VolumeReadBytes and VolumeWriteBytes |

**Key Insights**:
- `/opt/openclaw` is user data volume; `/` is root
- Inode exhaustion is rare but catastrophic (can't create files)
- EBS throughput should be smooth for good performance

**Common Issues**:
- / reaching 80%+: Cloud-init or system logs consuming disk space
- /opt/openclaw reaching 80%+: OpenClaw state/workspace growing (check snapshots)
- Inode free < 10%: Check for many small files or leftover temp files

---

### Section 5: Disk I/O Performance (Row 5)

**Purpose**: Analyze disk I/O patterns and latency.

| Widget | Type | Details |
|--------|------|---------|
| Disk I/O Operations | Time series | DISK_READ_OPS and DISK_WRITE_OPS |
| Disk I/O Throughput | Time series | DISK_READ_BYTES and DISK_WRITE_BYTES |
| Disk I/O Time | Time series | DISK_IO_TIME (milliseconds) |

**Key Insights**:
- Baseline I/O patterns establish normal workload
- Read/write asymmetry indicates specific workload bias
- High I/O time + low IOPS = latency issue

**Common Issues**:
- I/O time spikes with low throughput: Disk contention or saturation
- High read IOPS: Check if caching layer is effective
- Sustained IOPS near gp3 limits: Consider gp3 IOPS/throughput tuning

---

### Section 6: Network Performance (Rows 6-7)

**Purpose**: Monitor network traffic patterns and connection health.

| Widget | Type | Details |
|--------|------|---------|
| Network Throughput | Time series | NET_BYTES_SENT and NET_BYTES_RECV |
| Network Packets | Time series | NET_PACKETS_SENT and NET_PACKETS_RECV |
| EC2 Network (Hypervisor) | Time series | NetworkIn and NetworkOut (min/avg/max) |
| TCP Connections | Time series | TCP_ESTABLISHED and TCP_TIME_WAIT |

**Key Insights**:
- Compare packets/bytes ratio to detect small vs. large packets
- TCP_TIME_WAIT > 1000 on small instance: Potential connection leak
- Hypervisor view provides independent verification from OS-level metrics

**Common Issues**:
- Sustained high throughput: Verify it's expected (data transfer, backups)
- Many TIME_WAIT: Application not properly closing connections
- NetworkIn/Out asymmetry: One-directional data flow (downloads, uploads)

---

### Section 7: Systems Manager & Connectivity (Row 7)

**Purpose**: Monitor SSM Agent health and command execution.

| Widget | Type | Details |
|--------|------|---------|
| SSM Command Status | Time series | CommandsSucceeded, CommandsFailed, CommandsTimedOut |
| Application Logs | CloudWatch Logs Insights | Filters for cloud-init, docker, openclaw, cloudwatch-agent |

**Key Insights**:
- Successful commands = SSM Agent is responsive
- Failed commands may indicate permission or script issues
- Application logs show service startup and runtime issues

**Common Issues**:
- CommandsFailed increasing: Check script permissions and IAM roles
- CommandsTimedOut: Long-running operations or unreachable instance
- Missing application logs: Check CloudWatch Agent configuration

---

### Section 8: EBS & Spot Instance (Row 8)

**Purpose**: Monitor EBS data volume performance and spot instance stability.

| Widget | Type | Details |
|--------|------|---------|
| EBS Operations | Time series | VolumeReadOps and VolumeWriteOps |
| EBS Performance | Time series | VolumeQueueLength, VolumeThroughputPercentage, VolumeConsumedReadWriteOps |
| EBS Idle Time | Time series | VolumeIdleTime (seconds) |

**Key Insights**:
- VolumeQueueLength > 5: Volume may be experiencing throttling
- VolumeThroughputPercentage > 80%: Approaching gp3 limits
- VolumeIdleTime > 50%: Volume underutilized, cost optimization opportunity

**Common Issues**:
- Queue length spikes with timeouts: EBS saturation, scale up IOPS/throughput
- Consumed IOPS at gp3 max: Workload exceeds baseline, need instance/volume tuning
- Frequent idle time: Small workloads; consolidate or downsize

---

## Widget Details by Category

### CPU Metrics Category

**Namespace**: `OpenClawLab/EC2`

| Metric | Unit | Description |
|--------|------|-------------|
| CPU_USER | Percent | CPU time spent executing user-space code |
| CPU_SYSTEM | Percent | CPU time spent in kernel |
| CPU_IDLE | Percent | CPU idle time |
| CPU_IOWAIT | Percent | CPU idle waiting for disk I/O |

**Thresholds**:
- Alert if `CPU_USER + CPU_SYSTEM > 80%` for sustained period
- Alert if `CPU_IOWAIT > 30%` (potential disk bottleneck)

---

### Memory Metrics Category

**Namespace**: `OpenClawLab/EC2`

| Metric | Unit | Description |
|--------|------|-------------|
| MEM_USED_PERCENT | Percent | Memory used by applications and caches |
| MEM_AVAILABLE_PERCENT | Percent | Memory available for allocation |
| MEM_USED_BYTES | Bytes | Absolute memory used |
| MEM_AVAILABLE_BYTES | Bytes | Absolute memory available |

**Thresholds**:
- Alert if `MEM_USED_PERCENT > 85%` (limited headroom for spikes)
- Alert if `MEM_AVAILABLE_PERCENT < 15%` (risk of OOM)

---

### Disk Metrics Category

**Namespace**: `OpenClawLab/EC2`

| Metric | Unit | Paths | Description |
|--------|------|-------|-------------|
| DISK_USED_PERCENT | Percent | /, /opt/openclaw | Disk space used |
| INODE_USED | Count | / | Inodes allocated |
| INODE_FREE | Count | / | Inodes available |

**Thresholds**:
- Alert if `DISK_USED_PERCENT > 80%` for any mount
- Alert if `INODE_FREE < 10% of total` (exhaustion risk)

---

### Disk I/O Metrics Category

**Namespace**: `OpenClawLab/EC2`

| Metric | Unit | Description |
|--------|------|-------------|
| DISK_READ_OPS | Count/sec | Read operations per second |
| DISK_WRITE_OPS | Count/sec | Write operations per second |
| DISK_READ_BYTES | Bytes/sec | Read throughput |
| DISK_WRITE_BYTES | Bytes/sec | Write throughput |
| DISK_IO_TIME | Milliseconds | I/O operation latency |

**Baseline Values** (gp3, 3000 IOPS, 125 MB/s):
- Normal read IOPS: 100-500
- Normal write IOPS: 100-500
- Normal throughput: 5-50 MB/s (workload dependent)
- Normal I/O time: < 10ms

---

### Network Metrics Category

**Namespace**: `OpenClawLab/EC2`

| Metric | Unit | Description |
|--------|------|-------------|
| NET_BYTES_SENT | Bytes/sec | Outbound traffic |
| NET_BYTES_RECV | Bytes/sec | Inbound traffic |
| NET_PACKETS_SENT | Packets/sec | Outbound packets |
| NET_PACKETS_RECV | Packets/sec | Inbound packets |
| TCP_ESTABLISHED | Count | Active TCP connections |
| TCP_TIME_WAIT | Count | Connections in TIME_WAIT state |

**Interpretation**:
- Packets/Bytes ratio indicates packet size
- TCP_TIME_WAIT > 1000 (on t4g.small) = potential issue

---

### SSM & EBS Metrics

**SSM Namespace**: `AWS/SSM`
- CommandsSucceeded, CommandsFailed, CommandsTimedOut

**EBS Namespace**: `AWS/EBS`
- VolumeReadOps, VolumeWriteOps, VolumeReadBytes, VolumeWriteBytes
- VolumeQueueLength, VolumeThroughputPercentage, VolumeConsumedReadWriteOps
- VolumeIdleTime

---

## CloudWatch Logs Integration

The dashboard includes two CloudWatch Logs Insights queries:

### 1. Recent Errors & Warnings (Row 1)

```
SOURCE '/aws/ec2/openclaw-lab/{instance_id}'
| fields @timestamp, @message
| filter @message like /error|Error|ERROR|fail|Fail|FAIL|warn|Warn|WARN/
| sort @timestamp desc
| limit 20
```

**Purpose**: Quickly identify application and system errors.

### 2. Application & Service Logs (Row 7)

```
SOURCE '/aws/ec2/openclaw-lab/{instance_id}'
| fields @timestamp, @message
| filter @message like /cloud-init|cloudwatch-agent|docker|openclaw/
| sort @timestamp desc
| limit 50
```

**Purpose**: Follow startup and service health messages.

---

## Monitoring & Alerting Strategy

### Recommended CloudWatch Alarms

While alarms are not created by the dashboard automatically, consider adding:

```bash
# High CPU utilization
aws cloudwatch put-metric-alarm \
  --alarm-name openclaw-high-cpu \
  --metric-name CPUUtilization \
  --namespace AWS/EC2 \
  --statistic Average \
  --period 300 \
  --threshold 80 \
  --comparison-operator GreaterThanThreshold

# High disk usage on root
aws cloudwatch put-metric-alarm \
  --alarm-name openclaw-high-disk-root \
  --metric-name DISK_USED_PERCENT \
  --namespace OpenClawLab/EC2 \
  --dimensions Name=path,Value=/ \
  --statistic Average \
  --period 300 \
  --threshold 80 \
  --comparison-operator GreaterThanThreshold

# High disk usage on data volume
aws cloudwatch put-metric-alarm \
  --alarm-name openclaw-high-disk-data \
  --metric-name DISK_USED_PERCENT \
  --namespace OpenClawLab/EC2 \
  --dimensions Name=path,Value=/opt/openclaw \
  --statistic Average \
  --period 300 \
  --threshold 85 \
  --comparison-operator GreaterThanThreshold

# Memory pressure
aws cloudwatch put-metric-alarm \
  --alarm-name openclaw-high-memory \
  --metric-name MEM_USED_PERCENT \
  --namespace OpenClawLab/EC2 \
  --statistic Average \
  --period 300 \
  --threshold 85 \
  --comparison-operator GreaterThanThreshold
```

---

## Dashboard Refresh Rates

The dashboard auto-refreshes based on widget granularity:

- **High-frequency metrics** (CPU, Memory, Network): 60-second periods, 1-minute resolution
- **Medium-frequency metrics** (Disk I/O, EBS): 300-second periods, 5-minute resolution
- **Low-frequency metrics** (Status checks, SSM commands): 300-second periods, 5-minute resolution

Default viewing window: **Last 1 hour** (adjustable via AWS Console)

---

## Troubleshooting Dashboard Issues

### Dashboard URL not exported
- Ensure `pulumi up` completed successfully
- Verify dashboard was created: `aws cloudwatch describe-dashboards --dashboard-name-prefix openclaw`

### Metrics not appearing
- Verify CloudWatch Agent is running: `sudo systemctl status amazon-cloudwatch-agent`
- Check logs: `sudo cat /opt/aws/amazon-cloudwatch-agent/logs/amazon-cloudwatch-agent.log`
- Verify IAM permissions include `cloudwatch:PutMetricData`

### High latency in dashboard
- Reduce custom metrics if dashboard is slow to load
- Delete and recreate dashboard via `pulumi up` after removing unused widgets

### CloudWatch Logs Insights queries returning no results
- Check that cloud-init completed successfully
- Verify log group exists: `aws logs describe-log-groups --log-group-name-prefix openclaw`
- Check instance has `/var/log/cloud-init-output.log` written

---

## Cost Optimization

CloudWatch costs are incurred for:

1. **Custom Metrics**: `OpenClawLab/EC2` namespace (10 metrics × $0.30/month = ~$3)
2. **Dashboard**: Free (up to 3 dashboards per account)
3. **CloudWatch Logs**: Ingestion ($0.50/GB) + storage ($0.03/GB/month)

**Cost Tips**:
- Disable unused metrics in `cloudwatch-agent-config.json`
- Set appropriate log retention in cloud-init configuration
- Consider reducing metric collection interval if not needed

---

## Further Reading

- [AWS CloudWatch Agent Configuration Reference](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/Install-CloudWatch-Agent.html)
- [CloudWatch Dashboard Widgets](https://docs.aws.amazon.com/AmazonCloudWatch/latest/userguide/CloudWatch-Dashboards.html)
- [CloudWatch Logs Insights Query Syntax](https://docs.aws.amazon.com/AmazonCloudWatch/latest/logs/CWL_QuerySyntax.html)
- [AWS Well-Architected Framework - Operational Excellence](https://docs.aws.amazon.com/wellarchitected/latest/operational-excellence-pillar/welcome.html)
