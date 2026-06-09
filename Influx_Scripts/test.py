from influxdb_client import InfluxDBClient
client = InfluxDBClient(url="http://10.64.137.6:8086/", token="LvrSeU4NaBeQN7c4S4LsJCmlflUIQDgwRJqm383tdMoQaoDkM6pHAB022sAURdkvsSG_SWGXp8FVKVciviD3iA==", org="ISEL")
q = '''
from(bucket: "SoundDashHosp")
  |> range(start: -1y)
  |> filter(fn: (r) => r["_measurement"] == "sensor2")
  |> count()
'''
print(client.query_api().query(q))