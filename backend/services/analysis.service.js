import axios from "axios";
import { sendAlertEmail } from "../config/mail.config.js";
import { marketSignalEmailTemplate } from "../utils/sendAlertEmail.js";

// Perform analysis for a given symbol and timeframe
export const performAnalysis = async (symbol, timeframe) => {
  try {
    const apiKey = process.env.TWELVE_DATA_API_KEY;
    const url = `https://api.twelvedata.com/time_series?symbol=${symbol}&interval=${timeframe}&outputsize=200&apikey=${apiKey}`;
    
    // Fetch market data
    const response = await axios.get(url);
    if (response.data.status === "error") throw new Error(response.data.message);

    const marketData = response.data.values;

    // Run Python analysis via FastAPI
    const result = await runPythonAnalysis(marketData, symbol, timeframe);

    // Only send email if full signal exists
    if (["BUY", "SELL"].includes(result.signal)) {
      // Get current timestamp
      const timestamp = new Date().toISOString().replace('T', ' ').slice(0, 19) + ' UTC';
      
      // Generate email HTML with all required parameters
      const emailHTML = marketSignalEmailTemplate(
        result.symbol,                    // symbol
        result.signal,                    // signal
        result.timeframe,                 // timeframe
        result.entry,                     // lastClose (entry price)
        result.stop_loss,                 // stopLoss
        result.take_profit,               // takeProfit
        timestamp,                        // timestamp
        result.setup_type || "Breakout + Pullback", // setupType
        result.key_level || "N/A",        // keyLevel
        result.ema50 || "N/A"            // ema50
      );

      await sendAlertEmail(
        `🚨 ${result.symbol} ${result.signal} Signal Alert - ${result.setup_type || "Breakout + Pullback"}`,
        emailHTML
      );

      console.log(
        `✅ Signal sent: ${result.symbol} ${result.signal} (${result.setup_type || "Breakout + Pullback"})`
      );
    } else {
      console.log(
        `⏸️ No valid signal for ${symbol} (${timeframe}). Info: ${result.info || "No setup detected"}`
      );
    }

    return result;
  } catch (err) {
    console.error("❌ Analysis failed:", err.message);
    throw err;
  }
};

// Run analysis via FastAPI API
const runPythonAnalysis = async (marketData, symbol, timeframe) => {
  //const url = "https://five0ema-1-7wri.onrender.com/analyze";
  const url = "https://suing-s27n.onrender.com/analyze";
  const payload = { values: marketData, symbol, timeframe };

  try {
    const response = await axios.post(url, payload);
    return response.data;
  } catch (error) {
    console.error("❌ FastAPI request failed:", error.message);
    throw new Error("Failed to analyze market data via Python API");
  }
};

// Auto-analysis scheduler
export const autoAnalyzeMarket = async () => {
  // Timeframes optimized for pullback strategy
  const pairs = [
    { symbol: "EUR/USD", timeframe: "1h" },
    { symbol: "GBP/USD", timeframe: "1h" },
    { symbol: "USD/JPY", timeframe: "1h" },
    { symbol: "USD/CHF", timeframe: "1h" },
    { symbol: "NZD/USD", timeframe: "1h" },
    { symbol: "USD/CAD", timeframe: "1h" },
    { symbol: "AUD/USD", timeframe: "1h" },
    { symbol: "EUR/GBP", timeframe: "1h" },
    { symbol: "GBP/JPY", timeframe: "1h" },
    { symbol: "EUR/JPY", timeframe: "1h" },
    { symbol: "AUD/JPY", timeframe: "1h" },
    { symbol: "NZD/JPY", timeframe: "1h" },
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
