import axios from "axios";
import { sendAlertEmail } from "../config/mail.config.js";
import { marketSignalEmailTemplate } from "../utils/sendAlertEmail.js";

// ------------------------------------------------------------------
// Small helpers: delay + retry-with-backoff for 429s
// ------------------------------------------------------------------
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

/**
 * Runs `fn` and retries on HTTP 429 with exponential backoff.
 * Respects a `retry-after` header if the server sends one.
 */
async function withRetry(fn, { retries = 3, baseDelayMs = 5000, label = "request" } = {}) {
  let attempt = 0;
  while (true) {
    try {
      return await fn();
    } catch (err) {
      const status = err.response?.status;
      attempt += 1;
      if (status === 429 && attempt <= retries) {
        const retryAfterHeader = err.response?.headers?.["retry-after"];
        const retryAfterMs = retryAfterHeader ? Number(retryAfterHeader) * 1000 : null;
        const backoff = retryAfterMs || baseDelayMs * attempt; // 5s, 10s, 15s...
        console.warn(
          `⏳ ${label} hit 429. Retry ${attempt}/${retries} in ${Math.round(backoff / 1000)}s...`
        );
        await sleep(backoff);
        continue;
      }
      throw err;
    }
  }
}

// Twelve Data free tier: 8 credits/minute. outputsize=200 on a single
// symbol/interval is normally 1 credit, so spacing calls ~8s apart keeps
// you comfortably under the limit even with a handful of retries mixed in.
const MS_BETWEEN_PAIRS = 8000;

// ------------------------------------------------------------------
// Perform analysis for a given symbol and timeframe
// ------------------------------------------------------------------
export const performAnalysis = async (symbol, timeframe) => {
  try {
    const apiKey = process.env.TWELVE_DATA_API_KEY;

    if (!apiKey) {
      throw new Error("TWELVE_DATA_API_KEY is missing");
    }

    const url = `https://api.twelvedata.com/time_series?symbol=${encodeURIComponent(
      symbol
    )}&interval=${encodeURIComponent(timeframe)}&outputsize=200&apikey=${apiKey}`;

    console.log(`📡 Twelve Data request: ${symbol} ${timeframe}`);

    const response = await withRetry(() => axios.get(url), {
      label: `Twelve Data (${symbol})`,
    });

    console.log("📥 Twelve Data status:", response.status);

    if (response.data.status === "error") {
      throw new Error(`Twelve Data error: ${response.data.message || "Unknown error"}`);
    }

    const marketData = response.data.values;

    if (!marketData || !Array.isArray(marketData)) {
      throw new Error("Twelve Data returned no valid market data");
    }

    console.log(`📊 Received ${marketData.length} candles`);

    const result = await runPythonAnalysis(marketData, symbol, timeframe);

    console.log("🐍 Python analysis result:", result);

    if (["BUY", "SELL"].includes(result.signal)) {
      const timestamp = new Date().toISOString().replace("T", " ").slice(0, 19) + " UTC";

      const emailHTML = marketSignalEmailTemplate(
        result.symbol,
        result.signal,
        result.timeframe,
        result.entry_price,
        result.stop_loss,
        result.take_profit,
        timestamp,
        result.setup_type || "Breakout + Pullback",
        result.key_level || "N/A",
        result.ema50 || "N/A",
        result.candles_since_signal,
        result.signal_datetime
      );

      await sendAlertEmail(
        `🚨 ${result.symbol} ${result.signal} Signal Alert - ${
          result.setup_type || "Breakout + Pullback"
        }`,
        emailHTML
      );

      console.log(`✅ Signal sent: ${result.symbol} ${result.signal}`);
    } else {
      console.log(
        `⏸️ No valid signal for ${symbol} (${timeframe}). Info: ${
          result.info || "No setup detected"
        }`
      );
    }

    return result;
  } catch (err) {
    console.error("❌ Analysis failed");
    console.error("Message:", err.message);
    console.error("Status:", err.response?.status);
    console.error("Response:", err.response?.data);
    console.error("URL:", err.config?.url);

    throw err;
  }
};

// ------------------------------------------------------------------
// Run analysis via FastAPI (also wrapped with retry)
// ------------------------------------------------------------------
const runPythonAnalysis = async (marketData, symbol, timeframe) => {
  const url = "https://suing-s27n.onrender.com/analyze";

  const payload = { values: marketData, symbol, timeframe };

  console.log("🐍 Sending data to FastAPI:", {
    url,
    symbol,
    timeframe,
    candles: marketData.length,
  });

  try {
    const response = await withRetry(
      () =>
        axios.post(url, payload, {
          headers: { "Content-Type": "application/json" },
          timeout: 30000,
        }),
      { label: `FastAPI (${symbol})`, retries: 3, baseDelayMs: 4000 }
    );

    console.log("🐍 FastAPI status:", response.status);
    console.log("🐍 FastAPI response:", response.data);

    return response.data;
  } catch (error) {
    console.error("❌ FastAPI request failed");
    console.error("Message:", error.message);
    console.error("Status:", error.response?.status);
    console.error("Response:", error.response?.data);
    console.error("URL:", error.config?.url);

    throw new Error(
      `FastAPI analysis failed: ${
        error.response?.data?.detail || error.response?.data?.message || error.message
      }`
    );
  }
};

// ------------------------------------------------------------------
// Auto-analysis scheduler — now throttled between pairs
// ------------------------------------------------------------------
export const autoAnalyzeMarket = async () => {
  const pairs = [
    { symbol: "EUR/USD", timeframe: "1h" },
    { symbol: "GBP/USD", timeframe: "1h" },
    { symbol: "USD/JPY", timeframe: "1h" },
    { symbol: "USD/CAD", timeframe: "1h" },
    { symbol: "USD/CHF", timeframe: "1h" },
    { symbol: "NZD/USD", timeframe: "1h" },
    { symbol: "AUD/USD", timeframe: "1h" },
    { symbol: "EUR/GBP", timeframe: "1h" },
    { symbol: "GBP/JPY", timeframe: "1h" },
    { symbol: "XAUUSD", timeframe: "1h" },
    { symbol: "AUD/CAD", timeframe: "1h" },
    { symbol: "AUD/CHF", timeframe: "1h" },
  ];

  console.log(`🚀 Starting auto-analysis for ${pairs.length} pairs...`);
  console.log(`⏰ Time: ${new Date().toISOString()}`);
  console.log(
    `🐢 Throttling ${MS_BETWEEN_PAIRS / 1000}s between pairs to respect Twelve Data's per-minute credit limit`
  );

  for (let i = 0; i < pairs.length; i++) {
    const pair = pairs[i];
    console.log(`\n📊 Analyzing ${pair.symbol} (${pair.timeframe})...`);
    try {
      await performAnalysis(pair.symbol, pair.timeframe);
    } catch (error) {
      console.error(`❌ Failed to analyze ${pair.symbol}:`, error.message);
    }

    // Don't sleep after the very last pair
    if (i < pairs.length - 1) {
      await sleep(MS_BETWEEN_PAIRS);
    }
  }

  console.log(`\n✅ Auto-analysis complete for all pairs`);
};

// ------------------------------------------------------------------
// Get only signals (without sending email) — also throttled/retried
// ------------------------------------------------------------------
export const getSignalsOnly = async (symbol, timeframe) => {
  try {
    const apiKey = process.env.TWELVE_DATA_API_KEY;
    const url = `https://api.twelvedata.com/time_series?symbol=${encodeURIComponent(
      symbol
    )}&interval=${encodeURIComponent(timeframe)}&outputsize=200&apikey=${apiKey}`;

    const response = await withRetry(() => axios.get(url), {
      label: `Twelve Data (${symbol})`,
    });
    if (response.data.status === "error") throw new Error(response.data.message);

    const marketData = response.data.values;
    const result = await runPythonAnalysis(marketData, symbol, timeframe);

    return result;
  } catch (err) {
    console.error("❌ Analysis failed:", err.message);
    throw err;
  }
};
