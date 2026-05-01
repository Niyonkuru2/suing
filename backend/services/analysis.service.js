import axios from "axios";
import { sendAlertEmail } from "../config/mail.config.js";
import { marketSignalEmailTemplate } from "../utils/sendAlertEmail.js";

// =====================================================
// PROFESSIONAL SMART DAY-TRADING SCANNER
// Strategy:
// 1H   = Trend Direction
// 15m  = Entry Trigger
// EMA50 + Volatility + Session Filter
// Email Alerts
// Duplicate Protection
// =====================================================

// ---------------------------------------------
// MEMORY FOR DUPLICATE SIGNALS
// ---------------------------------------------
const sentSignals = new Map();

// expire old alerts after 2 hours
const ALERT_TTL = 1000 * 60 * 120;

// =====================================================
// UTILITIES
// =====================================================
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// Kigali timezone trading sessions
const isTradingSession = () => {
  const now = new Date();

  const kigaliHour = Number(
    now.toLocaleString("en-US", {
      timeZone: "Africa/Kigali",
      hour: "2-digit",
      hour12: false,
    })
  );

  // London + NY useful hours
  return kigaliHour >= 10 && kigaliHour <= 20;
};

const cleanOldSignals = () => {
  const now = Date.now();

  for (const [key, value] of sentSignals.entries()) {
    if (now - value > ALERT_TTL) {
      sentSignals.delete(key);
    }
  }
};

// =====================================================
// FETCH DATA FROM TWELVEDATA
// =====================================================
const fetchMarketData = async (symbol, timeframe) => {
  const apiKey = process.env.TWELVE_DATA_API_KEY;

  const url =
    `https://api.twelvedata.com/time_series` +
    `?symbol=${symbol}` +
    `&interval=${timeframe}` +
    `&outputsize=200` +
    `&apikey=${apiKey}`;

  const response = await axios.get(url);

  if (response.data.status === "error") {
    throw new Error(response.data.message);
  }

  return response.data.values;
};

// =====================================================
// CALL FASTAPI
// =====================================================
const runPythonAnalysis = async (
  values,
  symbol,
  timeframe
) => {
  const url =
    "https://suing-s27n.onrender.com/analyze";

  const response = await axios.post(url, {
    values,
    symbol,
    timeframe,
  });

  return response.data;
};

// =====================================================
// PROBABILITY SCORE
// =====================================================
const calculateScore = (
  trend,
  trigger,
  volatility
) => {
  let score = 0;

  if (trend === "PRICE_ABOVE_EMA50") score += 35;
  if (trend === "PRICE_BELOW_EMA50") score += 35;

  if (
    trigger === "PRICE_CROSSED_ABOVE_EMA50" ||
    trigger === "PRICE_CROSSED_BELOW_EMA50"
  ) {
    score += 40;
  }

  if (volatility === "HIGH") score += 25;
  if (volatility === "NORMAL") score += 15;
  if (volatility === "LOW") score -= 20;

  return Math.max(0, Math.min(100, score));
};

// =====================================================
// CORE ANALYSIS
// =====================================================
export const performAnalysis = async (
  symbol
) => {
  try {
    // ------------------------------
    // SESSION FILTER
    // ------------------------------
    if (!isTradingSession()) {
      console.log(
        `${symbol}: Outside active session`
      );
      return;
    }

    // ------------------------------
    // FETCH BOTH TIMEFRAMES
    // ------------------------------
    const h1Data = await fetchMarketData(
      symbol,
      "1h"
    );

    await sleep(500);

    const m15Data = await fetchMarketData(
      symbol,
      "15min"
    );

    // ------------------------------
    // ANALYZE BOTH
    // ------------------------------
    const trend = await runPythonAnalysis(
      h1Data,
      symbol,
      "1h"
    );

    const entry = await runPythonAnalysis(
      m15Data,
      symbol,
      "15min"
    );

    // ------------------------------
    // TREND LOGIC
    // ------------------------------
    const bullishTrend =
      trend.ema_signal ===
      "PRICE_ABOVE_EMA50";

    const bearishTrend =
      trend.ema_signal ===
      "PRICE_BELOW_EMA50";

    const bullishTrigger =
      entry.ema_signal ===
      "PRICE_CROSSED_ABOVE_EMA50";

    const bearishTrigger =
      entry.ema_signal ===
      "PRICE_CROSSED_BELOW_EMA50";

    let signal = "NO TRADE";

    if (bullishTrend && bullishTrigger) {
      signal = "BUY";
    }

    if (bearishTrend && bearishTrigger) {
      signal = "SELL";
    }

    if (signal === "NO TRADE") {
      console.log(
        `${symbol}: no aligned setup`
      );
      return;
    }

    // ------------------------------
    // VOLATILITY FILTER
    // ------------------------------
    if (entry.volatility === "LOW") {
      console.log(
        `${symbol}: low volatility skipped`
      );
      return;
    }

    // ------------------------------
    // DUPLICATE FILTER
    // ------------------------------
    cleanOldSignals();

    const key =
      `${symbol}_${signal}_${entry.timeframe}`;

    if (sentSignals.has(key)) {
      console.log(
        `${symbol}: duplicate skipped`
      );
      return;
    }

    sentSignals.set(key, Date.now());

    // ------------------------------
    // SCORE
    // ------------------------------
    const score = calculateScore(
      trend.ema_signal,
      entry.ema_signal,
      entry.volatility
    );

    // only strong setups
    if (score < 70) {
      console.log(
        `${symbol}: weak setup ${score}%`
      );
      return;
    }

    // ------------------------------
    // SEND ALERT
    // ------------------------------
    const html =
      marketSignalEmailTemplate(
        symbol,
        signal,
        `${score}% Probability`,
        entry.timeframe,
        entry.price,
        entry.ema50,
        entry.volatility
      );

    await sendAlertEmail(
      `${symbol} ${signal} Setup (${score}%)`,
      html
    );

    console.log(
      `ALERT => ${symbol} ${signal} ${score}%`
    );
  } catch (error) {
    console.error(
      `${symbol} failed:`,
      error.message
    );
  }
};

// =====================================================
// AUTO MARKET SCANNER
// =====================================================
export const autoAnalyzeMarket =
  async () => {
    const pairs = [
      "EUR/USD",
      "GBP/USD",
      "USD/JPY",
      "USD/CHF",
      "USD/CAD",
      "AUD/USD",
      "NZD/USD",
      "GBP/JPY",
      "EUR/JPY",
      "XAU/USD",
      "BTC/USD",
    ];

    for (const symbol of pairs) {
      console.log(
        `Scanning ${symbol}...`
      );

      await performAnalysis(symbol);

      await sleep(1000);
    }
  };
