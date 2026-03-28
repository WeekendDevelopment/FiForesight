import { InfluxDB, Point } from '@influxdata/influxdb-client';

const url = process.env.INFLUXDB_URL || 'http://localhost:8086';
const token = process.env.INFLUXDB_TOKEN;
const org = process.env.INFLUXDB_ORG || 'FiForesight';
const bucket = process.env.INFLUXDB_BUCKET || 'FiForesight';

// Log configuration on startup (for debugging)
console.log(`InfluxDB Config: URL=${url}, Org=${org}, Bucket=${bucket}`);

const influxDB = new InfluxDB({ url, token });
const writeApi = influxDB.getWriteApi(org, bucket);
const queryApi = influxDB.getQueryApi(org);

/**
 * Utility to safely parse a string as a float.
 */
function safeParseFloat(value: any): number | undefined {
  const parsed = parseFloat(value);
  return isNaN(parsed) ? undefined : parsed;
}

/**
 * Cleans and ingests financial data into InfluxDB.
 */
export async function cleanAndIngest(symbol: string, historicalData: any, earningsData: any) {
  try {
    const points: Point[] = [];

    // 1. Process Historical Price Data
    const monthlySeries = historicalData['Monthly Adjusted Time Series'];
    if (monthlySeries) {
      Object.entries(monthlySeries).forEach(([date, data]: [string, any]) => {
        const point = new Point('market_data').tag('symbol', symbol);
        
        const open = safeParseFloat(data['1. open']);
        const high = safeParseFloat(data['2. high']);
        const low = safeParseFloat(data['3. low']);
        const close = safeParseFloat(data['4. close']);
        const adjustedClose = safeParseFloat(data['5. adjusted close']);
        const volume = safeParseFloat(data['6. volume']);

        if (open !== undefined) point.floatField('open', open);
        if (high !== undefined) point.floatField('high', high);
        if (low !== undefined) point.floatField('low', low);
        if (close !== undefined) point.floatField('close', close);
        if (adjustedClose !== undefined) point.floatField('adjusted_close', adjustedClose);
        if (volume !== undefined) point.floatField('volume', volume);

        point.timestamp(new Date(date));
        points.push(point);
      });
    }

    // 2. Process Earnings Data
    const quarterlyEarnings = earningsData['quarterlyEarnings'];
    if (quarterlyEarnings) {
      quarterlyEarnings.forEach((earning: any) => {
        const point = new Point('earnings_data').tag('symbol', symbol);
        
        const actualEPS = safeParseFloat(earning['actualEPS']);
        const estimatedEPS = safeParseFloat(earning['estimatedEPS']);
        const surprise = safeParseFloat(earning['surprise']);
        const surprisePercentage = safeParseFloat(earning['surprisePercentage']);

        if (actualEPS !== undefined) point.floatField('actual_eps', actualEPS);
        if (estimatedEPS !== undefined) point.floatField('estimated_eps', estimatedEPS);
        if (surprise !== undefined) point.floatField('surprise', surprise);
        if (surprisePercentage !== undefined) point.floatField('surprise_percentage', surprisePercentage);

        point.timestamp(new Date(earning['reportedDate']));
        points.push(point);
      });
    }

    writeApi.writePoints(points);
    await writeApi.flush();
    console.log(`Successfully ingested data for ${symbol} into InfluxDB (Bucket: ${bucket})`);

  } catch (error) {
    console.error(`Error ingesting data for ${symbol} into InfluxDB:`, error);
    throw error;
  }
}

/**
 * Queries historical market data for a symbol from InfluxDB.
 * @param symbol The ticker symbol.
 * @param range The time range (e.g., '-1y' for one year).
 */
export async function queryMarketData(symbol: string, range: string = '-1y') {
  const fluxQuery = `from(bucket: "${bucket}")
    |> range(start: ${range})
    |> filter(fn: (r) => r["_measurement"] == "market_data")
    |> filter(fn: (r) => r["symbol"] == "${symbol}")
    |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
    |> sort(columns: ["_time"], desc: false)`;

  try {
    return await queryApi.collectRows(fluxQuery);
  } catch (error) {
    console.error(`Error querying market data for ${symbol}:`, error);
    throw error;
  }
}

/**
 * Queries earnings data for a symbol from InfluxDB.
 */
export async function queryEarningsData(symbol: string, range: string = '-5y') {
  const fluxQuery = `from(bucket: "${bucket}")
    |> range(start: ${range})
    |> filter(fn: (r) => r["_measurement"] == "earnings_data")
    |> filter(fn: (r) => r["symbol"] == "${symbol}")
    |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
    |> sort(columns: ["_time"], desc: false)`;

  try {
    return await queryApi.collectRows(fluxQuery);
  } catch (error) {
    console.error(`Error querying earnings data for ${symbol}:`, error);
    throw error;
  }
}
