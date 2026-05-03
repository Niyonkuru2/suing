import axios from "axios";
import { sendAlertEmail } from "../config/mail.config.js";
import { marketSignalEmailTemplate } from "../utils/sendAlertEmail.js";

// ==========================================
// CONFIG
// ==========================================
const API_KEY = process.env.TWELVE_DATA_API_KEY;
const PYTHON_API_URL = "https://five0ema.onrender.com/analyze-mtf";

// Prevent duplicate alerts
const lastSignals = new Map();

// ==========================================
// FETCH MARKET DATA (30m + 1H)
// ==========================================
const fetchMarketData = async (symbol) => {
  const url30m = `https://api.twelvedata.com/time_series?symbol=${symbol}&interval=30min&outputsize=200&apikey=${API_KEY}`;
  const url1h = `https://api.twelvedata.com/time_series?symbol=${symbol}&interval=1h&outputsize=200&apikey=${API_KEY}`;

  const [res30m, res1h] = await Promise.all([
    axios.get(url30m),
    axios.get(url1h),
  ]);

  if (res30m.data.status === "error") {
    throw new Error(res30m.data.message);
  }

  if (res1h.data.status === "error") {
    throw new Error(res1h.data.message);
  }

  return {
    values_30m: res30m.data.values,
    values_1h: res1h.data.values,
  };
};

// ==========================================
// CALL FASTAPI
// ==========================================
const runPythonAnalysis = async (values_30m, values_1h) => {
  const payload = { values_30m, values_1h };

  const response = await axios.post(PYTHON_API_URL, payload);
  return response.data;
};

// ==========================================
// HANDLE SIGNAL
// ==========================================
const handleSignal = async (symbol, result) => {
  const {
    signal,
    entry,
    stop_loss,
    take_profit,
    trend,
    volatility,
    structure,
  } = result;

  // No signal
  if (!["BUY", "SELL"].includes(signal)) {
    console.log(
      `${symbol} → No trade | Trend: ${trend} | Volatility: ${volatility}`
    );
    return;
  }

  // Prevent duplicate alerts
  const key = `${symbol}_${signal}`;
  if (lastSignals.get(symbol) === key) {
    console.log(`⚠️ Duplicate skipped → ${symbol}`);
    return;
  }

  lastSignals.set(symbol, key);

  // TradingView link
  const chartLink = `https://www.tradingview.com/chart/?symbol=${symbol.replace(
    "/",
    ""
  )}`;

  // Email template
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

  await sendAlertEmail(`${symbol} ${signal} Signal`, emailHTML);

  console.log(
    `${symbol} ${signal} | Entry: ${entry} | SL: ${stop_loss} | TP: ${take_profit}`
  );
};

// ==========================================
// MAIN ANALYSIS FUNCTION
// ==========================================
export const performAnalysis = async (symbol) => {
  try {
    console.log(`Analyzing ${symbol}...`);

    const { values_30m, values_1h } = await fetchMarketData(symbol);

    const result = await runPythonAnalysis(values_30m, values_1h);

    await handleSignal(symbol, result);

    return result;
  } catch (error) {
    console.error(`Error for ${symbol}:`, error.message);
  }
};

// ==========================================
// AUTO MARKET LOOP
// ==========================================
export const autoAnalyzeMarket = async () => {
  const pairs = [
    "EUR/USD",
     "GBP/USD",
      "USD/JPY",
      "USD/CHF",
      "USD/CAD",
      "AUD/USD",
      "NZD/USD",
      "GBP/JPY",
      "EUR/GBP",
      "XAU/USD"
  ];

  for (const symbol of pairs) {
    await performAnalysis(symbol);
  }
};
