from influxdb_client import InfluxDBClient
client = InfluxDBClient(url="http://localhost:8086", token="meu-token-supersecreto", org="myorg")
q = '''
from(bucket: "SoundDashHosp")
  |> range(start: -1y)
  |> filter(fn: (r) => r["_measurement"] == "Sensor100")
  |> count()
'''
print(client.query_api().query(q))