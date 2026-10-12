import axios from "axios";
import { sendAlertEmail } from "../config/mail.config.js";
import { marketSignalEmailTemplate } from "../utils/sendAlertEmail.js";

// ------------------------------------------------------------------
// Configuration
// ------------------------------------------------------------------

const TWELVE_DATA_BASE_URL =
  "https://api.twelvedata.com/time_series";

const PYTHON_ANALYSIS_URL =
  "https://suing-s27n.onrender.com/analyze";

const CANDLE_COUNT = 200;
const MIN_CANDLES = 12;
const MS_BETWEEN_PAIRS = 8000;
const REQUEST_TIMEOUT_MS = 30000;

// ------------------------------------------------------------------
// Helpers
// ------------------------------------------------------------------

const sleep = (ms) =>
  new Promise((resolve) => setTimeout(resolve, ms));

const formatUtc = (date = new Date()) =>
  `${date.toISOString().replace("T", " ").slice(0, 19)} UTC`;

// ------------------------------------------------------------------
// Retry HTTP 429 and transient network/server errors
// ------------------------------------------------------------------

async function withRetry(
  fn,
  {
    retries = 3,
    baseDelayMs = 5000,
    label = "request",
  } = {}
) {
  let attempt = 0;

  while (true) {
    try {
      return await fn();
    } catch (error) {
      attempt += 1;

      const status = error.response?.status;

      const isRateLimited = status === 429;

      const isTransient =
        !error.response ||
        status === 408 ||
        status === 425 ||
        status >= 500;

      if (
        attempt > retries ||
        (!isRateLimited && !isTransient)
      ) {
        throw error;
      }

      const retryAfter =
        error.response?.headers?.["retry-after"];

      let retryAfterMs = 0;

      if (retryAfter !== undefined) {
        const seconds = Number(retryAfter);

        if (
          Number.isFinite(seconds) &&
          seconds >= 0
        ) {
          retryAfterMs = seconds * 1000;
        } else {
          const retryDate = Date.parse(retryAfter);

          if (Number.isFinite(retryDate)) {
            retryAfterMs = Math.max(
              0,
              retryDate - Date.now()
            );
          }
        }
      }

      const backoffMs = Math.max(
        retryAfterMs,
        baseDelayMs * 2 ** (attempt - 1)
      );

      console.warn(
        `Retrying ${label} (${attempt}/${retries}) in ` +
          `${Math.ceil(backoffMs / 1000)} seconds. ` +
          `HTTP status: ${status ?? "network error"}`
      );

      await sleep(backoffMs);
    }
  }
}

// ------------------------------------------------------------------
// Validate inputs and OHLC candles
// ------------------------------------------------------------------

function validateInputs(symbol, timeframe) {
  if (
    typeof symbol !== "string" ||
    !symbol.trim()
  ) {
    throw new Error(
      "A valid market symbol is required."
    );
  }

  if (
    typeof timeframe !== "string" ||
    !timeframe.trim()
  ) {
    throw new Error(
      "A valid timeframe is required."
    );
  }
}

function validateCandles(marketData) {
  if (!Array.isArray(marketData)) {
    throw new Error(
      "Twelve Data did not return a valid candle array."
    );
  }

  if (marketData.length < MIN_CANDLES) {
    throw new Error(
      `Insufficient OHLC candles: received ` +
        `${marketData.length}; at least ` +
        `${MIN_CANDLES} are required.`
    );
  }

  const invalidIndex = marketData.findIndex(
    (candle) => {
      if (
        !candle ||
        typeof candle !== "object"
      ) {
        return true;
      }

      const open = Number(candle.open);
      const high = Number(candle.high);
      const low = Number(candle.low);
      const close = Number(candle.close);

      return (
        !Number.isFinite(open) ||
        !Number.isFinite(high) ||
        !Number.isFinite(low) ||
        !Number.isFinite(close) ||
        high < low ||
        high < Math.max(open, close) ||
        low > Math.min(open, close)
      );
    }
  );

  if (invalidIndex !== -1) {
    throw new Error(
      `Invalid OHLC candle at array index ${invalidIndex}.`
    );
  }
}

// ------------------------------------------------------------------
// Fetch OHLC candles from Twelve Data
// ------------------------------------------------------------------

async function fetchMarketData(symbol, timeframe) {
  validateInputs(symbol, timeframe);

  const apiKey = process.env.TWELVE_DATA_API_KEY;

  if (!apiKey) {
    throw new Error(
      "TWELVE_DATA_API_KEY is missing from environment."
    );
  }

  console.log(
    `Fetching OHLC candles: ${symbol} (${timeframe})`
  );

  const response = await withRetry(
    () =>
      axios.get(TWELVE_DATA_BASE_URL, {
        params: {
          symbol,
          interval: timeframe,
          outputsize: CANDLE_COUNT,
          apikey: apiKey,
        },
        timeout: REQUEST_TIMEOUT_MS,
      }),
    {
      label: `Twelve Data ${symbol} ${timeframe}`,
      retries: 3,
      baseDelayMs: 5000,
    }
  );

  const data = response.data;

  if (
    data?.status === "error" ||
    data?.code
  ) {
    throw new Error(
      `Twelve Data error: ${
        data.message || "Unknown API error"
      }`
    );
  }

  const marketData = data?.values;

  validateCandles(marketData);

  console.log(
    `Received ${marketData.length} candles for ` +
      `${symbol} (${timeframe}).`
  );

  // Twelve Data normally returns newest candles first.
  return marketData;
}

// ------------------------------------------------------------------
// Run analysis through the Python FastAPI service
// ------------------------------------------------------------------

async function runPythonAnalysis(
  marketData,
  symbol,
  timeframe
) {
  validateInputs(symbol, timeframe);
  validateCandles(marketData);

  const payload = {
    values: marketData,
    symbol,
    timeframe,
    newest_first: true,
  };

  console.log(
    "Sending candles to price-action API:",
    {
      symbol,
      timeframe,
      candles: marketData.length,
    }
  );

  let response;

  try {
    response = await withRetry(
      () =>
        axios.post(
          PYTHON_ANALYSIS_URL,
          payload,
          {
            headers: {
              "Content-Type": "application/json",
            },
            timeout: REQUEST_TIMEOUT_MS,
          }
        ),
      {
        label: `Python analysis ${symbol} ${timeframe}`,
        retries: 3,
        baseDelayMs: 4000,
      }
    );
  } catch (error) {
    const detail =
      error.response?.data?.detail ||
      error.response?.data?.message ||
      error.message;

    console.error(
      "Price-action API request failed:",
      {
        symbol,
        timeframe,
        status: error.response?.status,
        detail,
      }
    );

    throw new Error(
      `Price-action analysis failed: ${detail}`
    );
  }

  const result = response.data;

  if (
    !result ||
    typeof result !== "object" ||
    !result.signal
  ) {
    throw new Error(
      "Price-action API returned an invalid response " +
        "or missing signal."
    );
  }

  console.log("Price-action result:", {
    symbol,
    timeframe,
    signal: result.signal,
    marketStructure: result.market_structure,
  });

  return result;
}

// ------------------------------------------------------------------
// Build email using the imported template
// ------------------------------------------------------------------

function buildZoneAlertEmail(result) {
  const timestamp = formatUtc();

  return marketSignalEmailTemplate(
    result.symbol,                       // symbol
    result.signal,                       // signal
    result.timeframe,                    // timeframe
    null,                                // entry_price
    null,                                // stopLoss
    null,                                // takeProfit
    timestamp,                           // timestamp
    "Market Structure + Pullback Zone",  // setupType
    null,                                // keyLevel
    null,                                // ema50
    null,                                // candlesSinceSignal
    null,                                // signalDatetime
    result                                // priceAction
  );
}

// ------------------------------------------------------------------
// Perform analysis for one symbol and timeframe
// Sends email only for BUY_ZONE or SELL_ZONE
// ------------------------------------------------------------------

export const performAnalysis = async (
  symbol,
  timeframe
) => {
  try {
    const marketData = await fetchMarketData(
      symbol,
      timeframe
    );

    const result = await runPythonAnalysis(
      marketData,
      symbol,
      timeframe
    );

    // Ensure symbol and timeframe are available to the template.
    const normalizedResult = {
      ...result,
      symbol: result.symbol || symbol,
      timeframe: result.timeframe || timeframe,
    };

    if (
      ["BUY_ZONE", "SELL_ZONE"].includes(
        normalizedResult.signal
      )
    ) {
      const direction =
        normalizedResult.signal === "BUY_ZONE"
          ? "BUY"
          : "SELL";

      const subject =
        `Price Action Zone: ` +
        `${normalizedResult.symbol} ${direction}`;

      // Use the imported reusable email template.
      const emailHTML =
        buildZoneAlertEmail(normalizedResult);

      await sendAlertEmail(
        subject,
        emailHTML
      );

      console.log(
        `Zone alert email sent: ` +
          `${normalizedResult.symbol} ` +
          `${normalizedResult.signal}`
      );
    } else {
      console.log(
        `No zone email for ${symbol} (${timeframe}). ` +
          `Signal: ${normalizedResult.signal}. ` +
          `Info: ${
            normalizedResult.info ||
            "No setup detected"
          }`
      );
    }

    return normalizedResult;
  } catch (error) {
    console.error(
      `Analysis failed for ${symbol} (${timeframe}):`,
      error.message
    );

    // Let the scheduler or calling controller handle failures.
    throw error;
  }
};

// ------------------------------------------------------------------
// Automatic market-analysis scheduler
// ------------------------------------------------------------------

export const autoAnalyzeMarket = async () => {
  const pairs = [
    { symbol: "EUR/USD", timeframe: "1h" },
    { symbol: "GBP/USD", timeframe: "1h" },
    { symbol: "USD/JPY", timeframe: "1h" },
    { symbol: "USD/CAD", timeframe: "1h" },
    { symbol: "USD/CHF", timeframe: "1h" },
    { symbol: "NZD/USD", timeframe: "1h" },
    { symbol: "XAU/USD", timeframe: "1h" },
    { symbol: "AUD/USD", timeframe: "1h" },
    { symbol: "EUR/GBP", timeframe: "1h" },
    { symbol: "GBP/JPY", timeframe: "1h" },
    { symbol: "AUD/CAD", timeframe: "1h" },
    { symbol: "AUD/CHF", timeframe: "1h" },
  ];

  console.log(
    `Starting automatic price-action analysis for ` +
      `${pairs.length} markets.`
  );

  console.log(
    `Started at: ${new Date().toISOString()}`
  );

  console.log(
    `Delay between markets: ` +
      `${MS_BETWEEN_PAIRS / 1000} seconds.`
  );

  const summary = {
    total: pairs.length,
    succeeded: 0,
    failed: 0,
    zoneAlerts: 0,
  };

  for (
    let index = 0;
    index < pairs.length;
    index += 1
  ) {
    const pair = pairs[index];

    console.log(
      `\nAnalyzing ${pair.symbol} ` +
        `(${pair.timeframe}) ` +
        `[${index + 1}/${pairs.length}]`
    );

    try {
      const result = await performAnalysis(
        pair.symbol,
        pair.timeframe
      );

      summary.succeeded += 1;

      if (
        ["BUY_ZONE", "SELL_ZONE"].includes(
          result.signal
        )
      ) {
        summary.zoneAlerts += 1;
      }
    } catch (error) {
      summary.failed += 1;

      console.error(
        `Failed: ${pair.symbol} ` +
          `(${pair.timeframe}): ${error.message}`
      );
    }

    if (index < pairs.length - 1) {
      await sleep(MS_BETWEEN_PAIRS);
    }
  }

  console.log(
    "Automatic analysis completed:",
    summary
  );

  return summary;
};

// ------------------------------------------------------------------
// Get analysis result without sending an email
// ------------------------------------------------------------------

export const getSignalsOnly = async (
  symbol,
  timeframe
) => {
  const marketData = await fetchMarketData(
    symbol,
    timeframe
  );

  const result = await runPythonAnalysis(
    marketData,
    symbol,
    timeframe
  );

  return {
    ...result,
    symbol: result.symbol || symbol,
    timeframe: result.timeframe || timeframe,
  };
};
