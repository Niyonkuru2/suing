export const marketSignalEmailTemplate = (
  symbol,
  signal,
  timeframe,
  lastClose,
  stopLoss,
  takeProfit,
  timestamp,
  setupType,
  keyLevel,
  ema50
) => `
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>Market Signal Alert - ${signal}</title>
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
      padding: 15px 20px;
      margin-top: 15px;
      font-size: 15px;
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
    .setup-tag {
      display: inline-block;
      padding: 4px 12px;
      border-radius: 4px;
      background-color: #6c757d;
      color: #ffffff;
      font-size: 12px;
      font-weight: 600;
      text-transform: uppercase;
      margin-left: 8px;
    }
    .table {
      width: 100%;
      border-collapse: collapse;
      margin-top: 20px;
    }
    .table th, .table td {
      text-align: left;
      padding: 8px 0;
    }
    .table th {
      color: #6b7280;
      font-weight: 600;
      width: 40%;
    }
    .table tr {
      border-bottom: 1px solid #e5e7eb;
    }
    .table tr:last-child {
      border-bottom: none;
    }
    .strategy-box {
      background-color: #fff3cd;
      border-left: 4px solid #ffc107;
      padding: 12px 16px;
      margin: 20px 0;
      border-radius: 4px;
      font-size: 14px;
    }
    .strategy-box strong {
      color: #856404;
    }
    .footer {
      text-align: center;
      font-size: 13px;
      color: #6b7280;
      padding: 20px;
      background-color: #f9fafb;
      border-top: 1px solid #e5e7eb;
    }
    .risk-reward-badge {
      display: inline-block;
      background-color: #28a745;
      color: white;
      padding: 2px 10px;
      border-radius: 12px;
      font-size: 12px;
      font-weight: bold;
    }
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      ${signal} SIGNAL ALERT
      <span class="setup-tag">Breakout + Pullback</span>
    </div>
    <div class="content">
      <p>Dear Trader,</p>
      <p>A new <strong>${signal}</strong> signal has been detected by our automated system for:</p>
      
      <div class="highlight">
        <p><strong>Symbol:</strong> ${symbol}</p>
        <p><strong>Timeframe:</strong> ${timeframe}</p>
        <p><strong>Signal:</strong> <span class="signal-tag">${signal}</span></p>
        <p><strong>Setup Type:</strong> ${setupType || "Breakout + Pullback"}</p>
        <p><strong>Timestamp:</strong> ${timestamp}</p>
      </div>

      <div class="strategy-box">
        <strong>📊 Strategy Entry Conditions:</strong><br/>
        ${signal === "BUY" ? 
          `✅ Price was below EMA50 → broke above → made a high → pulled back → closed above that high` :
          `✅ Price was above EMA50 → broke below → made a low → pulled back → closed below that low`
        }
      </div>

      <table class="table">
        <tr><th>Entry Price:</th><td><strong>${lastClose}</strong></td></tr>
        <tr><th>Key Breakout Level:</th><td>${keyLevel || "N/A"}</td></tr>
        <tr><th>EMA50:</th><td>${ema50 || "N/A"}</td></tr>
        <tr><th>Stop Loss:</th><td><strong style="color: ${signal === "BUY" ? "#dc3545" : "#28a745"}">${stopLoss}</strong></td></tr>
        <tr><th>Take Profit:</th><td><strong style="color: ${signal === "BUY" ? "#28a745" : "#dc3545"}">${takeProfit}</strong></td></tr>
        <tr><th>Risk:Reward:</th><td><span class="risk-reward-badge">1 : 2</span></td></tr>
      </table>

      <p style="margin-top: 20px; font-size: 14px; color: #6b7280;">
        ⚠️ Please analyze this signal with your strategy before executing any trade.
        <br/>
        🎯 Recommended: Wait for confirmation before entry.
      </p>
    </div>
    <div class="footer">
      &copy; ${new Date().getFullYear()} Market Signal Bot. All rights reserved.<br/>
      Powered by FastAPI × Node.js × Twelve Data<br/>
      <span style="font-size: 11px; color: #9ca3af;">Strategy: EMA50 Breakout + Pullback with 1:2 RR</span>
    </div>
  </div>
</body>
</html>
`;

