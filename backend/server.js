import app from "./app.js";
import dotenv from "dotenv";
import cron from "node-cron";
import { autoAnalyzeMarket } from "./services/analysis.service.js";

dotenv.config();

const PORT = process.env.PORT || 5000;

// ======================================================
// START SERVER
// ======================================================
app.listen(PORT, () => {
  console.log(`🚀 Server running on port ${PORT}`);
});

// ======================================================
// RUN ON STARTUP
// ======================================================
(async () => {
  console.log("📊 Initial market scan started...");
  await autoAnalyzeMarket();
})();

// ======================================================
// DAY TRADING SCHEDULE
// Every 15 Minutes
// ======================================================
cron.schedule("*/15 * * * *", async () => {
  console.log("📈 Running 15min market scan...");
  await autoAnalyzeMarket();
});

// ======================================================
// OPTIONAL H1 TREND REFRESH
// Every Hour
// ======================================================
cron.schedule("0 * * * *", async () => {
  console.log("🕐 Hourly trend synchronization...");
});
