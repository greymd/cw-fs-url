# cw-fs-url

Generate a CloudWatch Metrics URL for EBS/EFS IOPS/Throughput/Latency calculation with metric math.

# Usage

```
$ python3 cw-fs-url.py --help
usage: cw-fs-url.py [-h] --from START_TIME --to END_TIME --ids RESOURCE_IDS --service {ebs,efs}
                    --metric {mibs,iops,latency} --region REGION [--period PERIOD]

Generate a CloudWatch Metrics URL for EBS/EFS IOPS/Throughput calculation.

options:
  -h, --help            show this help message and exit
  --from START_TIME     Start time in ISO8601 format.
  --to END_TIME         End time in ISO8601 format.
  --ids RESOURCE_IDS    Comma-separated list of EBS volume IDs or EFS filesystem IDs.
  --service {ebs,efs}   Set service type
  --metric {mibs,iops,latency}
                        Set metric type. mibs is Throughput in MiB/s, latency is ms/op
  --region REGION       AWS region.
  --period PERIOD       Set 60, 300, 3600 or any multiple of 60 [default: 300]
```

# Supported Metric Patterns

* EBS Throughput in MiB/s
* EBS IOPS
* EBS Latency
* EFS Throughput in MiB/s
* EFS IOPS

EBS metrics are calculated align with [1].
EFS metrics are calculated align with [2].

# Usage Examples

## EBS Throughput

```
$ python3 cw-fs-url.py \
--service ebs \
--metric mibs \
--region eu-west-1 \
--from 2023-01-01T00:00:00.000Z \
--to 2023-01-01T23:00:00.000Z \
--ids vol-aaa,vol-bbb,vol-ccc
```

## EFS Throughput

```
$ python3 cw-fs-url.py \
--service efs \
--metric mibs \
--region eu-west-1 \
--from 2023-01-01T00:00:00.000Z \
--to 2023-01-01T23:00:00.000Z \
--ids fs-aaa,fs-bbb,fs-ccc
```

# References

[1] Amazon CloudWatch metrics for Amazon EBS - Amazon Elastic Compute Cloud
https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/using_cloudwatch_ebs.html

[2] Using metric math with Amazon EFS - Amazon Elastic File System
https://docs.aws.amazon.com/efs/latest/ug/monitoring-metric-math.html
