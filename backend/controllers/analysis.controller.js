import express from "express";
import { performAnalysis } from "../services/analysis.service.js";

const router = express.Router();

// Manual trigger (POST)
router.post("/", async (req, res) => {
  try {
    const { symbol, timeframe } = req.body;
    if (!symbol || !timeframe) {
      return res.status(400).json({ message: "symbol and timeframe are required" });
    }

    const result = await performAnalysis(symbol, timeframe);
    res.status(200).json({ success: true, data: result });
  } catch (error) {
    res.status(500).json({ success: false, message: error.message });
  }
});

export default router;
