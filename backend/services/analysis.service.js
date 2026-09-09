import axios from "axios";
import { sendAlertEmail } from "../config/mail.config.js";
import { marketSignalEmailTemplate } from "../utils/sendAlertEmail.js";

// Perform analysis for a given symbol and timeframe
export const performAnalysis = async (symbol, timeframe) => {
  try {
    const apiKey = process.env.TWELVE_DATA_API_KEY;

    if (!apiKey) {
      throw new Error("TWELVE_DATA_API_KEY is missing");
    }

    const url = `https://api.twelvedata.com/time_series?symbol=${encodeURIComponent(symbol)}&interval=${encodeURIComponent(timeframe)}&outputsize=200&apikey=${apiKey}`;

    console.log(`📡 Twelve Data request: ${symbol} ${timeframe}`);

    const response = await axios.get(url);

    console.log("📥 Twelve Data status:", response.status);
    console.log("📥 Twelve Data response:", response.data);

    if (response.data.status === "error") {
      throw new Error(
        `Twelve Data error: ${response.data.message || "Unknown error"}`
      );
    }

    const marketData = response.data.values;

    if (!marketData || !Array.isArray(marketData)) {
      throw new Error("Twelve Data returned no valid market data");
    }

    console.log(`📊 Received ${marketData.length} candles`);

    const result = await runPythonAnalysis(
      marketData,
      symbol,
      timeframe
    );

    console.log("🐍 Python analysis result:", result);

    if (["BUY", "SELL"].includes(result.signal)) {
      const timestamp =
        new Date().toISOString().replace("T", " ").slice(0, 19) + " UTC";

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
        result.ema50 || "N/A"
      );

      await sendAlertEmail(
        `🚨 ${result.symbol} ${result.signal} Signal Alert - ${
          result.setup_type || "Breakout + Pullback"
        }`,
        emailHTML
      );

      console.log(
        `✅ Signal sent: ${result.symbol} ${result.signal}`
      );
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

// Run analysis via FastAPI API
const runPythonAnalysis = async (marketData, symbol, timeframe) => {
  const url = "https://suing-s27n.onrender.com/analyze";

  const payload = {
    values: marketData,
    symbol,
    timeframe,
  };

  console.log("🐍 Sending data to FastAPI:", {
    url,
    symbol,
    timeframe,
    candles: marketData.length,
  });

  try {
    const response = await axios.post(url, payload, {
      headers: {
        "Content-Type": "application/json",
      },
      timeout: 30000,
    });

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
        error.response?.data?.detail ||
        error.response?.data?.message ||
        error.message
      }`
    );
  }
};

// Auto-analysis scheduler
export const autoAnalyzeMarket = async () => {
  // Timeframes optimized for pullback strategy
  const pairs = [
    { symbol: "EUR/USD", timeframe: "5min"},
    { symbol: "GBP/USD", timeframe: "5min"},
    { symbol: "USD/JPY", timeframe: "5min"},
    //{ symbol: "USD/CHF", timeframe: "1h" },
    //{ symbol: "NZD/USD", timeframe: "1h" },
    //{ symbol: "USD/CAD", timeframe: "1h" },
    //{ symbol: "AUD/USD", timeframe: "1h" },
    //{ symbol: "EUR/GBP", timeframe: "1h" },
    //{ symbol: "GBP/JPY", timeframe: "1h" },
    //{ symbol: "EUR/JPY", timeframe: "1h" },
    //{ symbol: "AUD/JPY", timeframe: "1h" },
    //{ symbol: "NZD/JPY", timeframe: "1h" },
  ];
  
  console.log(`🚀 Starting auto-analysis for ${pairs.length} pairs...`);
  console.log(`⏰ Time: ${new Date().toISOString()}`);
  
  for (const pair of pairs) {
    console.log(`\n📊 Analyzing ${pair.symbol} (${pair.timeframe})...`);
    try {
      await performAnalysis(pair.symbol, pair.timeframe);
    } catch (error) {
      console.error(`❌ Failed to analyze ${pair.symbol}:`, error.message);
    }
  }
  
  console.log(`\n✅ Auto-analysis complete for all pairs`);
};

// Function to get only signals (without sending email)
export const getSignalsOnly = async (symbol, timeframe) => {
  try {
    const apiKey = process.env.TWELVE_DATA_API_KEY;
    const url = `https://api.twelvedata.com/time_series?symbol=${symbol}&interval=${timeframe}&outputsize=200&apikey=${apiKey}`;
    
    const response = await axios.get(url);
    if (response.data.status === "error") throw new Error(response.data.message);

    const marketData = response.data.values;
    const result = await runPythonAnalysis(marketData, symbol, timeframe);
    
    return result;
  } catch (err) {
    console.error("❌ Analysis failed:", err.message);
    throw err;
  }
};
