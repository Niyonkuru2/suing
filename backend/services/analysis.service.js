// ==========================================
// IMPORTS
// ==========================================
import axios from "axios";
import cron from "node-cron";
import { sendAlertEmail } from "../config/mail.config.js";
import { marketSignalEmailTemplate } from "../utils/sendAlertEmail.js";

// ==========================================
// CONFIG
// ==========================================
const TWELVE_API_KEY = process.env.TWELVE_DATA_API_KEY;
const PYTHON_API_URL = "https://five0ema.onrender.com/analyze-mtf";

// Prevent duplicate signals
const lastSignals = new Map();

// ==========================================
// FETCH MARKET DATA (30m + 1H)
// ==========================================
const fetchMarketData = async (symbol) => {
  const url30m = `https://api.twelvedata.com/time_series?symbol=${symbol}&interval=30min&outputsize=200&apikey=${TWELVE_API_KEY}`;
  const url1h = `https://api.twelvedata.com/time_series?symbol=${symbol}&interval=1h&outputsize=200&apikey=${TWELVE_API_KEY}`;

  try {
    const [res30m, res1h] = await Promise.all([
      axios.get(url30m),
      axios.get(url1h),
    ]);

    if (res30m.data.status === "error") throw new Error(res30m.data.message);
    if (res1h.data.status === "error") throw new Error(res1h.data.message);

    return {
      values_30m: res30m.data.values,
      values_1h: res1h.data.values,
    };
  } catch (error) {
    console.error(`Data fetch failed for ${symbol}:`, error.message);
    throw error;
  }
};

// ==========================================
// CALL PYTHON API (MTF STRATEGY)
// ==========================================
const runPythonAnalysis = async (values_30m, values_1h) => {
  try {
    const response = await axios.post(PYTHON_API_URL, {
      values_30m,
      values_1h,
    });

    return response.data;
  } catch (error) {
    console.error("FastAPI request failed:", error.message);
    throw new Error("Python API failed");
  }
};

// ==========================================
// PROCESS SIGNAL + EMAIL ALERT
// ==========================================
const handleSignal = async (symbol, result) => {
  const { signal, entry, stop_loss, take_profit, trend, volatility, structure } = result;

  // Skip if no signal
  if (!["BUY", "SELL"].includes(signal)) {
    console.log(
      `No trade → ${symbol} | Trend: ${trend} | Volatility: ${volatility}`
    );
    return;
  }

  // Prevent duplicate alerts
  const signalKey = `${symbol}_${signal}`;

  if (lastSignals.get(symbol) === signalKey) {
    console.log(`⚠️ Duplicate signal skipped → ${symbol}`);
    return;
  }

  lastSignals.set(symbol, signalKey);

  // TradingView chart link
  const chartLink = `https://www.tradingview.com/chart/?symbol=${symbol.replace("/", "")}`;

  // Generate email
  const emailHTML = marketSignalEmailTemplate(
    symbol,
    signal,
    structure,
    "30min (Entry) / 1H (Trend)",
    entry,
    stop_loss,
    take_profit,
    chartLink
  );

  // Send email
  await sendAlertEmail(`${symbol} ${signal} Signal`, emailHTML);

  console.log(
    `SIGNAL SENT → ${symbol} ${signal}\nEntry: ${entry} | SL: ${stop_loss} | TP: ${take_profit}`
  );
};

// ==========================================
// MAIN ANALYSIS FUNCTION
// ==========================================
export const performAnalysis = async (symbol) => {
  try {
    console.log(`🔍 Analyzing ${symbol}...`);

    // 1. Fetch data
    const { values_30m, values_1h } = await fetchMarketData(symbol);

    // 2. Run strategy
    const result = await runPythonAnalysis(values_30m, values_1h);

    // 3. Handle result
    await handleSignal(symbol, result);

    return result;
  } catch (err) {
    console.error(`Analysis failed for ${symbol}:`, err.message);
  }
};

// ==========================================
// AUTO MARKET SCAN
// ==========================================
export const autoAnalyzeMarket = async () => {
  const pairs = [
    "EUR/USD",
    "GBP/USD",
    "USD/JPY",
    "USD/CAD",
    "USD/CHF",
    "NZD/USD",
    "GBP/JPY",
    "EUR/GBP",
  ];

  for (const symbol of pairs) {
    await performAnalysis(symbol);
  }
};
})();
