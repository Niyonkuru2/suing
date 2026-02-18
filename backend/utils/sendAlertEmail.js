export const marketSignalEmailTemplate = (
  symbol,
  signal,
  structure,
  timeframe,
  entry,
  stopLoss,
  takeProfit
) => `
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>Pullback Strategy Signal</title>
  <style>
    body {
      margin: 0;
      padding: 0;
      font-family: 'Segoe UI', Arial, sans-serif;
      background-color: #f4f4f7;
    }
    .container {
      max-width: 640px;
      margin: 40px auto;
      background: #ffffff;
      border-radius: 12px;
      overflow: hidden;
      box-shadow: 0 4px 14px rgba(0,0,0,0.1);
    }
    .header {
      background: ${signal === "BUY" ? "#28a745" : "#dc3545"};
      color: #ffffff;
      text-align: center;
      padding: 25px 20px;
      font-size: 26px;
      font-weight: 600;
      letter-spacing: 1px;
    }
    .content {
      padding: 30px 40px;
      color: #111827;
      font-size: 16px;
      line-height: 1.6;
    }
    .highlight {
      background-color: #f3f4f6;
      border-radius: 8px;
      padding: 20px;
      margin-top: 20px;
    }
    .signal-tag {
      display: inline-block;
      padding: 8px 18px;
      border-radius: 6px;
      color: #ffffff;
      font-weight: bold;
      background-color: ${signal === "BUY" ? "#28a745" : "#dc3545"};
      text-transform: uppercase;
    }
    .footer {
      text-align: center;
      font-size: 13px;
      color: #6b7280;
      padding: 20px;
      background-color: #f9fafb;
      border-top: 1px solid #e5e7eb;
    }
    .risk-box {
      margin-top: 20px;
      padding: 15px;
      border-left: 4px solid #111827;
      background: #fafafa;
      font-size: 14px;
    }
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      ${signal} SIGNAL – Pullback Trend Strategy
    </div>

    <div class="content">
      <p>Hello Trader,</p>

      <p>
        A new <strong>${signal}</strong> setup has been detected based on your 
        <strong>Market Structure + EMA50 Pullback Strategy</strong>.
      </p>

      <div class="highlight">
        <p><strong>Symbol:</strong> ${symbol}</p>
        <p><strong>Timeframe:</strong> ${timeframe}</p>
        <p><strong>Market Structure:</strong> ${structure}</p>
        <p><strong>Signal:</strong> <span class="signal-tag">${signal}</span></p>
        <p><strong>Entry Price:</strong> ${entry}</p>
        <p><strong>Stop Loss:</strong> ${stopLoss}</p>
        <p><strong>Take Profit:</strong> ${takeProfit}</p>
        <p><strong>Risk : Reward:</strong> 1 : 2</p>
      </div>

      <div class="risk-box">
        ⚠️ Trade only if all conditions align with your personal risk management rules.
        Risk no more than 1–2% per trade. Discipline over emotion.
      </div>

      <p style="margin-top:20px;">
        This signal was generated after:
        <br/>
        ✓ Confirmed market structure (HH/HL or LL/LH)
        <br/>
        ✓ EMA50 trend alignment
        <br/>
        ✓ Valid pullback
        <br/>
        ✓ Candle close confirmation
      </p>
    </div>

    <div class="footer">
      &copy; ${new Date().getFullYear()} Pullback Structure Bot<br/>
      Powered by FastAPI × Node.js × Twelve Data
    </div>
  </div>
</body>
</html>
`;
