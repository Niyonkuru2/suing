import express from "express";
import cors from "cors";
import dotenv from "dotenv";
import analysisRouter from "./controllers/analysis.controller.js";

dotenv.config();

const app = express();
app.use(cors());
app.use(express.json());

app.use("/api/analysis", analysisRouter);

app.get("/", (req, res) => {
  res.send("Forex Analyzer backend is running...");
});

export default app;
