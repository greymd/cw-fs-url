import argparse
import sys
from abc import abstractmethod

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

def generate_clause_metric(identifier: str, namespace: str, metric_name: str, dimension: str, visible=False) -> Clause:
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
    if visible:
        child.push(Attribute('true'))
    else:
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

def ec2_statuscheck(instance_ids) -> Clause:
    namespace = 'AWS/EC2'
    clause = Clause()
    metrics: list[Item] = []
    maths: list[Item] =[]
    idx = 0
    for instance_id in instance_ids:
        dimension = f"InstanceId={instance_id}"
        for metric_name in ['StatusCheckFailed_Instance', 'StatusCheckFailed_System']:
          idx += 1
          metrics.append(generate_clause_metric(f"m{idx}", namespace, metric_name, dimension, True))
    for item in metrics + maths:
        clause.push(item)
    return clause

def ec2_network_packets(instance_ids) -> Clause:
    namespace = 'AWS/EC2'
    clause = Clause()
    metrics: list[Item] = []
    maths: list[Item] =[]
    idx = 0
    for instance_id in instance_ids:
        dimension = f"InstanceId={instance_id}"
        for metric_name in ['NetworkPacketsIn', 'NetworkPacketsOut']:
          idx += 1
          maths.append(generate_clause_math(f"e{idx}", f'm{idx}/DIFF_TIME(m{idx})', f'{instance_id} {metric_name} in pps'))
          metrics.append(generate_clause_metric(f"m{idx}", namespace, metric_name, dimension))
    for item in metrics + maths:
        clause.push(item)
    return clause

def ec2_network(instance_ids) -> Clause:
    namespace = 'AWS/EC2'
    clause = Clause()
    metrics: list[Item] = []
    maths: list[Item] =[]
    idx = 0
    for instance_id in instance_ids:
        dimension = f"InstanceId={instance_id}"
        for metric_name in ['NetworkIn', 'NetworkOut']:
          idx += 1
          maths.append(generate_clause_math(f"e{idx}", f'(m{idx}/1048576)/PERIOD(m{idx})', f'{instance_id} {metric_name} in MiB/s'))
          # maths.append(generate_clause_math(f"e{idx}", f'm{idx}/DIFF_TIME(m{idx})', f'{instance_id} {metric_name} in MiB/s'))
          metrics.append(generate_clause_metric(f"m{idx}", namespace, metric_name, dimension))
    for item in metrics + maths:
        clause.push(item)
    return clause

def ec2_cpu(instance_ids) -> Clause:
    namespace = 'AWS/EC2'
    clause = Clause()
    metrics: list[Item] = []
    maths: list[Item] =[]
    idx = 0
    for instance_id in instance_ids:
        dimension = f"InstanceId={instance_id}"
        for metric_name in ['CPUUtilization']:
          idx += 1
          metrics.append(generate_clause_metric(f"m{idx}", namespace, metric_name, dimension, True))
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

def generate_url(region, metric_type, start_time, end_time, period, volume_ids) -> str:
    c = Clause()
    c.push(TypeStatement('metrics'))
    stat = 'Sum'
    if metric_type == 'network':
        c.push(ec2_network(volume_ids))
        stat = 'Sum'
    elif metric_type == 'packets':
        c.push(ec2_network_packets(volume_ids))
        stat = 'Maximum'
    elif metric_type == 'cpu':
        c.push(ec2_cpu(volume_ids))
        stat = 'Maximum'
    elif metric_type == 'statuscheck':
        c.push(ec2_statuscheck(volume_ids))
        stat = 'Average'
    else:
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
    parser = argparse.ArgumentParser(description="Generate a CloudWatch Metrics URL for EBS/EFS IOPS and Throughput calculation.")
    parser.add_argument("--from", dest="start_time", required=True, help="Start time in ISO8601 format.")
    parser.add_argument("--to", dest="end_time", required=True, help="End time in ISO8601 format.")
    parser.add_argument("--ids", dest="resource_ids", required=True, help="Comma-separated list of Instance IDs")
    parser.add_argument("--metric", dest="metric_type", required=True, choices=['network', 'cpu', 'statuscheck', 'packets'], help="Set metric type")
    parser.add_argument("--region", required=True, help="AWS region.")
    parser.add_argument("--period", required=False, default='300', help="Set 60, 300, 3600 or any multiple of 60 [default: 300]")
    args = parser.parse_args()

    cw_url = generate_url(args.region, args.metric_type, args.start_time, args.end_time, args.period, args.resource_ids.split(","))
    print(cw_url)

if __name__ == "__main__":
    main()
