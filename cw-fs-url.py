import argparse
import sys
from abc import abstractmethod

"""
== URL format of CloudWatch Metrics ==
~(
  metrics ........... (TypeStatement)
  ~(
    ~( .............. (Clause)
      ~'AWS/EBS ..... (Value)
      ~'VolumeWriteOps
      ~'VolumeId
      ~'vol-xxxxxxxxxxxxxxxx
      ~( ............ (Clause)
        id .......... (TypeStatement)
        ~'m3
        ~visible .... (Attribute)
        ~false ...... (Attribute)
      )
    )
    ~(
      ~(
        expression
        ~'(m3)/PERIOD(m3)
        ~label
        ~'Write IOPS
        ~id
        ~'e3
      )
    )
  )
  ~view
  ~'timeSeries
  ~stackec
  ~false
  ~region
  ~'eu-west-1
  ~start~'2023-10-10T00*3a40*3a00.000Z
  ~end~'2023-10-10T18*3a28*3a00.000Z
  ~stat
  ~'Sum
  ~period
  ~300
)

== Consideration ==
-- `*` is used as an meta character of URL encoding instead of '%'
-- Clause is the bracket area between `~(` and `)`
-- Metric Math requires nested Clauses
-- The string starts with `~` is Attribute
-- The string starts with `~'` is Value
-- The string starts just after `(` is TypeStatement
"""

class Item:
    @abstractmethod
    def generateQuery(self) -> str:
        pass

class Clause(Item):
    def __init__(self):
        self.items: list[Item] = []
    def push(self, item: Item):
        self.items.append(item)
    def generateQuery(self) -> str:
        query: list[str] = []
        query.append('~(')
        for item in self.items:
            query.append(item.generateQuery())
        query.append(')')
        return ''.join(query)

class TypeStatement(Item):
    def __init__(self, val):
        self.val: str = val
        return
    def generateQuery(self) -> str:
        return f'{self.val}'

class Value(Item):
    def __init__(self, val):
        self.val: str = val
        return
    def generateQuery(self) -> str:
        return "~'" + f'{self.val}'

class Attribute(Item):
    def __init__(self, val):
        self.val: str = val
        return
    def generateQuery(self) -> str:
        return "~" + f'{self.val}'

def error_exit(message):
    sys.stderr.write(f"Error: {message}\n")
    sys.exit(1)

def generate_clause_metric(identifier: str, namespace: str, metric_name: str, dimension: str) -> Clause:
    parent = Clause()
    parent.push(Value(namespace))
    parent.push(Value(metric_name))
    # TODO: It is technically possible to omit the dimension name with '.'
    if dimension == '.':
        parent.push(Value(dimension))
    else:
        key, val = dimension.split('=')
        parent.push(Value(key))
        parent.push(Value(val))
    ## Generate child clause
    child = Clause()
    child.push(TypeStatement('id'))
    child.push(Value(identifier))
    child.push(Attribute('visible'))
    child.push(Attribute('false'))
    parent.push(child)
    return parent

def generate_clause_math(identifier: str, expression: str, label: str) -> Clause:
    c = Clause()
    c.push(TypeStatement('expression'))
    c.push(Value(str_to_urlenc_aws(expression, True)))
    c.push(Attribute('label'))
    c.push(Value(str_to_urlenc_aws(label, True)))
    c.push(Attribute('id'))
    c.push(Value(identifier))
    parent = Clause()
    parent.push(c)
    return parent

def ebs_iops(volume_ids) -> Clause:
    namespace = 'AWS/EBS'
    clause = Clause()
    idx = 0
    for vol in volume_ids:
        idx += 1
        read_id = f"m{idx}"
        write_id = f"m{idx + 1}"
        read_iops_id = f"e{idx}"
        write_iops_id = f"e{idx + 1}"
        # generate Read IOPS Formula
        clause.push(generate_clause_math(read_iops_id, f'{read_id}/PERIOD({read_id})', f'{vol} read IOPS'))
        # generate Write IOPS Formula
        clause.push(generate_clause_math(write_iops_id, f'{write_id}/PERIOD({write_id})', f'{vol} write IOPS'))
        dimension = f"VolumeId={vol}"
        # generate VolumeReadOps Metrics
        clause.push(generate_clause_metric(read_id, namespace, 'VolumeReadOps', dimension))
        # generate VolumeWriteOps Metrics
        clause.push(generate_clause_metric(write_id, namespace, 'VolumeWriteOps', dimension))
    return clause

def ebs_mibs(volume_ids) -> Clause:
    namespace = 'AWS/EBS'
    clause = Clause()
    idx = 0
    for vol in volume_ids:
        idx += 1
        read_id = f"m{idx}"
        write_id = f"m{idx + 1}"
        read_iops_id = f"e{idx}"
        write_iops_id = f"e{idx + 1}"
        clause.push(generate_clause_math(read_iops_id, f'({read_id}/1048576)/PERIOD({read_id})', f'{vol} read MiB/s'))
        clause.push(generate_clause_math(write_iops_id, f'({write_id}/1048576)/PERIOD({write_id})', f'{vol} write MiB/s'))
        dimension = f"VolumeId={vol}"
        clause.push(generate_clause_metric(read_id, namespace, 'VolumeReadBytes', dimension))
        clause.push(generate_clause_metric(write_id, namespace, 'VolumeWriteBytes', dimension))
    return clause

def ebs_latency(volume_ids) -> Clause:
    namespace = 'AWS/EBS'
    clause = Clause()
    idx = 0
    for vol in volume_ids:
        idx += 1
        read_time_id = f"m{idx}"
        write_time_id = f"m{idx + 1}"
        read_op_id = f"m{idx + 2}"
        write_op_id = f"m{idx + 3}"
        read_latency_id = f"e{idx}"
        write_latency_id = f"e{idx + 1}"
        clause.push(generate_clause_math(read_latency_id, f'({read_time_id}/{read_op_id}) * 1000', f'{vol} avg read latency (ms/op)'))
        clause.push(generate_clause_math(write_latency_id, f'({write_time_id}/{write_op_id}) * 1000', f'{vol} avg write latency (ms/op)'))
        dimension = f"VolumeId={vol}"
        clause.push(generate_clause_metric(read_time_id, namespace, 'VolumeTotalReadTime', dimension))
        clause.push(generate_clause_metric(write_time_id, namespace, 'VolumeTotalWriteTime', dimension))
        clause.push(generate_clause_metric(read_op_id, namespace, 'VolumeReadOps', dimension))
        clause.push(generate_clause_metric(write_op_id, namespace, 'VolumeWriteOps', dimension))
    return clause

def efs_mibs(fs_ids) -> Clause:
    namespace = 'AWS/EFS'
    clause = Clause()
    metrics: list[Item] = []
    maths: list[Item] =[]
    idx = 0
    for fsid in fs_ids:
        dimension = f"FileSystemId={fsid}"
        for metric_name in ['TotalIOBytes', 'MeteredIOBytes', 'DataReadIOBytes', 'DataWriteIOBytes', 'MetadataWriteIOBytes', 'MetadataReadIOBytes', 'MetadataIOBytes']:
          idx += 1
          maths.append(generate_clause_math(f"e{idx}", f'(m{idx}/1048576)/PERIOD(m{idx})', f'{fsid} {metric_name} in MiB/s'))
          metrics.append(generate_clause_metric(f"m{idx}", namespace, metric_name, dimension))
    for item in metrics + maths:
        clause.push(item)
    return clause

def efs_iops(fs_ids) -> Clause:
    namespace = 'AWS/EFS'
    clause = Clause()
    metrics: list[Item] = []
    maths: list[Item] =[]
    idx = 0
    for fsid in fs_ids:
        dimension = f"FileSystemId={fsid}"
        for metric_name in ['TotalIOBytes', 'MeteredIOBytes', 'DataReadIOBytes', 'DataWriteIOBytes', 'MetadataWriteIOBytes', 'MetadataReadIOBytes', 'MetadataIOBytes']:
          idx += 1
          maths.append(generate_clause_math(f"e{idx}", f'(m{idx}/1048576)/PERIOD(m{idx})', f'{fsid} {metric_name} in IOPS'))
          metrics.append(generate_clause_metric(f"m{idx}", namespace, metric_name, dimension))
    for item in metrics + maths:
        clause.push(item)
    return clause


"""
Convert string to URL encoding used in AWS CloudWatch query. Use '*' instead of '%'.
Ignore some characters (, ), !, *, ' from encoding.
Encoded string is better to be lower case (it works with upper case, but try to align with Management console's behavior).
"""
def str_to_urlenc_aws(utf8_string: str, encode_formula=False) -> str:
    import urllib.parse
    import re
    if encode_formula:
        ignore_chars = ""
    else:
        ignore_chars = "'*()"
    encoded_string = urllib.parse.quote(utf8_string, safe=ignore_chars).replace('%', '*')
    # Function to convert matched object to lowercase
    def replacer(match):
        return match.group(0).lower()
    # Replace uppercase hex digits with lowercase using a regex
    lower_encoded_string = re.sub(r'\*[0-9A-F]{2}', replacer, encoded_string)
    return lower_encoded_string

def generate_url(region, service_type, metric_type, start_time, end_time, period, volume_ids) -> str:
    c = Clause()
    c.push(TypeStatement('metrics'))
    stat = 'Sum'
    if service_type == 'ebs' and metric_type == 'iops':
        c.push(ebs_iops(volume_ids))
        stat = 'Sum'
    elif service_type == 'ebs' and metric_type == 'mibs':
        c.push(ebs_mibs(volume_ids))
        stat = 'Sum'
    elif service_type == 'ebs' and metric_type == 'latency':
        c.push(ebs_latency(volume_ids))
        stat = 'Sum'
    elif service_type == 'efs' and metric_type == 'iops':
        c.push(efs_iops(volume_ids))
        stat = 'SampleCount'
    elif service_type == 'efs' and  metric_type == 'mibs':
        c.push(efs_mibs(volume_ids))
        stat = 'Sum'
    elif service_type == 'efs' and  metric_type == 'latency':
        error_exit('Latency of EFS cannot be calculated')
    c.push(Attribute('view'))
    c.push(Value('timeSeries'))
    c.push(Attribute('stackec'))
    c.push(Attribute('false'))
    c.push(Attribute('region'))
    c.push(Value(region))
    c.push(Attribute('start'))
    c.push(Value(start_time))
    c.push(Attribute('end'))
    c.push(Value(end_time))
    c.push(Attribute('stat'))
    c.push(Value(stat))
    c.push(Attribute('period'))
    c.push(Attribute(period))
    graph_query = str_to_urlenc_aws(c.generateQuery());
    return f'https://{region}.console.aws.amazon.com/cloudwatch/home?region={region}#metricsV2?graph={graph_query}'

def main():
    parser = argparse.ArgumentParser(description="Generate a CloudWatch Metrics URL for EBS/EFS IOPS/Throughput calculation.")
    parser.add_argument("--from", dest="start_time", required=True, help="Start time in ISO8601 format.")
    parser.add_argument("--to", dest="end_time", required=True, help="End time in ISO8601 format.")
    parser.add_argument("--ids", dest="resource_ids", required=True, help="Comma-separated list of EBS volume IDs or EFS filesystem IDs.")
    parser.add_argument("--service", dest="service_type", required=True, choices=['ebs', 'efs'], help="Set service type")
    parser.add_argument("--metric", dest="metric_type", required=True, choices=['mibs', 'iops', 'latency'], help="Set metric type. mibs is Throughput in MiB/s, latency is ms/op")
    parser.add_argument("--region", required=True, help="AWS region.")
    parser.add_argument("--period", required=False, default='300', help="Set 60, 300, 3600 or any multiple of 60 [default: 300]")
    args = parser.parse_args()

    cw_url = generate_url(args.region, args.service_type, args.metric_type, args.start_time, args.end_time, args.period, args.resource_ids.split(","))
    print(cw_url)

if __name__ == "__main__":
    main()
