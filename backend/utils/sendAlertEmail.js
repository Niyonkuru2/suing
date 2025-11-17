export const marketSignalEmailTemplate = (
  symbol,
  signal,
  direction,
  timeframe,
  lastClose,
  timestamp
) => `
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>Market Signal Alert</title>
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
    .footer {
      text-align: center;
      font-size: 13px;
      color: #6b7280;
      padding: 20px;
      background-color: #f9fafb;
      border-top: 1px solid #e5e7eb;
    }
  </style>
</head>
<body>
  <div class="container">
    <div class="header">${signal} SIGNAL ALERT</div>
    <div class="content">
      <p>Dear Trader,</p>
      <p>
        A new <strong>${signal}</strong> signal has been detected by your automated EMA-50 system.
        Here are the details:
      </p>
      
      <div class="highlight">
        <p><strong>Symbol:</strong> ${symbol}</p>
        <p><strong>Timeframe:</strong> ${timeframe}</p>
        <p><strong>Trend Direction:</strong> ${direction}</p>
        <p><strong>Signal:</strong> <span class="signal-tag">${signal}</span></p>
        <p><strong>Last Close Price:</strong> ${lastClose}</p>
      </div>
      <p>
        Always confirm the signal with your trading strategy and risk management rules before entering a trade.
      </p>
    </div>

    <div class="footer">
      &copy; ${new Date().getFullYear()} Market Signal Bot. All rights reserved.<br/>
      Powered by FastAPI × Node.js × Twelve Data.
    </div>
  </div>
</body>
</html>
`;
