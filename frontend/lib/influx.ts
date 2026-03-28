import { InfluxDB, Point } from '@influxdata/influxdb-client';

const url = process.env.INFLUXDB_URL || 'http://localhost:8086';
const token = process.env.INFLUXDB_TOKEN;
const org = process.env.INFLUXDB_ORG || 'FiForesight';
const bucket = process.env.INFLUXDB_BUCKET || 'FiForesight';

const influxDB = new InfluxDB({ url, token });
const writeApi = influxDB.getWriteApi(org, bucket);
const queryApi = influxDB.getQueryApi(org);

function safeParseFloat(value: any): number | undefined {
  const parsed = parseFloat(value);
  return isNaN(parsed) ? undefined : parsed;
}

export async function cleanAndIngest(symbol: string, historicalData: any, earningsData: any) {
  try {
    const points: Point[] = [];
    const monthlySeries = historicalData['Monthly Adjusted Time Series'];
    if (monthlySeries) {
      Object.entries(monthlySeries).forEach(([date, data]: [string, any]) => {
        const point = new Point('market_data').tag('symbol', symbol);
        const fields = {
          open: safeParseFloat(data['1. open']),
          high: safeParseFloat(data['2. high']),
          low: safeParseFloat(data['3. low']),
          close: safeParseFloat(data['4. close']),
          volume: safeParseFloat(data['6. volume'])
        };
        Object.entries(fields).forEach(([k, v]) => { if (v !== undefined) point.floatField(k, v); });
        point.timestamp(new Date(date));
        points.push(point);
      });
    }

    const quarterlyEarnings = earningsData['quarterlyEarnings'];
    if (quarterlyEarnings) {
      quarterlyEarnings.forEach((earning: any) => {
        const point = new Point('earnings_data').tag('symbol', symbol);
        const fields = {
          actual_eps: safeParseFloat(earning['actualEPS']),
          estimated_eps: safeParseFloat(earning['estimatedEPS']),
          surprise: safeParseFloat(earning['surprise'])
        };
        Object.entries(fields).forEach(([k, v]) => { if (v !== undefined) point.floatField(k, v); });
        point.timestamp(new Date(earning['reportedDate']));
        points.push(point);
      });
    }

    writeApi.writePoints(points);
    await writeApi.flush();
    console.log(`Successfully ingested data for ${symbol} into InfluxDB.`);
  } catch (error) {
    console.error(`Error ingesting data for ${symbol}:`, error);
    throw error;
  }
}

export async function queryMarketData(symbol: string, range: string = '-1y') {
  const fluxQuery = `from(bucket: "${bucket}")
    |> range(start: ${range})
    |> filter(fn: (r) => r["_measurement"] == "market_data")
    |> filter(fn: (r) => r["symbol"] == "${symbol}")
    |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
    |> sort(columns: ["_time"], desc: false)`;
  return await queryApi.collectRows(fluxQuery);
}

export async function queryEarningsData(symbol: string, range: string = '-5y') {
  const fluxQuery = `from(bucket: "${bucket}")
    |> range(start: ${range})
    |> filter(fn: (r) => r["_measurement"] == "earnings_data")
    |> filter(fn: (r) => r["symbol"] == "${symbol}")
    |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
    |> sort(columns: ["_time"], desc: false)`;
  return await queryApi.collectRows(fluxQuery);
}
