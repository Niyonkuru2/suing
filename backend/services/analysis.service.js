import axios from "axios";
import { sendAlertEmail } from "../config/mail.config.js";
import { marketSignalEmailTemplate } from "../utils/sendAlertEmail.js";

export const performAnalysis = async (symbol, timeframe) => {
  try {
    const apiKey = process.env.TWELVE_DATA_API_KEY;
    const url = `https://api.twelvedata.com/time_series?symbol=${symbol}&interval=${timeframe}&outputsize=200&apikey=${apiKey}`;
    
    const response = await axios.get(url);
    if (response.data.status === "error") throw new Error(response.data.message);

    const marketData = response.data.values;
    const result = await runPythonAnalysis(marketData, symbol, timeframe);

    // If signal is BUY or SELL send professional HTML email
    if (["BUY", "SELL"].includes(result.signal)) {
      const emailHTML = marketSignalEmailTemplate(
        result.symbol,
        result.signal,
        result.confidence,
        result.timeframe,
        result.last_close,
        result.stop_loss,
        result.take_profit,
        result.timestamp
      );

      await sendAlertEmail(`${result.symbol} Signal Alert`, emailHTML);
    }

    return result;
  } catch (err) {
    console.error("Analysis failed:", err.message);
    throw err;
  }
};

// Run analysis via FastAPI API
const runPythonAnalysis = async (marketData, symbol, timeframe) => {
  const url = "https://suing.onrender.com/analyze";
  const payload = { values: marketData, symbol, timeframe };

  try {
    const response = await axios.post(url, payload);
    return response.data;
  } catch (error) {
    console.error("FastAPI request failed:", error.message);
    throw new Error("Failed to analyze market data via Python API");
  }
};


// Auto-analysis scheduler
export const autoAnalyzeMarket = async () => {
  const pairs = [
    { symbol: "EUR/USD", timeframe: "5min" },
    { symbol: "GBP/USD", timeframe: "5min" },
    { symbol: "USD/JPY", timeframe: "5min" },
    { symbol: "USD/CHF", timeframe: "5min" },
    { symbol: "NZD/USD", timeframe: "5min" },
    //{ symbol: "EUR/GBP", timeframe: "5min"},
    //{ symbol: "USD/CAD", timeframe: "5min"},

  ];

  for (const pair of pairs) {
    console.log(`Analyzing ${pair.symbol} (${pair.timeframe})...`);
    await performAnalysis(pair.symbol, pair.timeframe);
  }
};
