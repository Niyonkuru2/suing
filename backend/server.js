import app from "./app.js";
import dotenv from "dotenv";
import cron from "node-cron";
import { autoAnalyzeMarket } from "./services/analysis.service.js";

dotenv.config();

const PORT = process.env.PORT || 5000;

app.listen(PORT, () => {
  console.log(`Server running on port ${PORT}`);
});

(async () => {
  console.log("Initial market scan started...");
  await autoAnalyzeMarket();
})();

cron.schedule("*/30 * * * *", async () => {
  console.log("Running 30min market scan...");
  await autoAnalyzeMarket();
});
