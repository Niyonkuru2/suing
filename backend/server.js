import app from "./app.js";
import dotenv from "dotenv";
import cron from "node-cron";
import { autoAnalyzeMarket } from "./services/analysis.service.js";

dotenv.config();
const PORT = process.env.PORT || 5000;

app.listen(PORT, () => {
  console.log(`Server running on port ${PORT}`);
});

// Run automatic analysis every 10 minutes
cron.schedule("*/10 * * * *", async () => {
  console.log("Running scheduled market analysis...");
  await autoAnalyzeMarket();
});
