export const marketSignalEmailTemplate = (symbol, signal, timeframe, lastClose) => `
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
      font-family: Arial, sans-serif;
      background-color: #f4f4f7;
    }
    .container {
      max-width: 600px;
      margin: 40px auto;
      background: #ffffff;
      border-radius: 10px;
      overflow: hidden;
      box-shadow: 0 4px 12px rgba(0,0,0,0.1);
    }
    .header {
      background-color: #1a73e8; /* blue accent */
      color: #ffffff;
      text-align: center;
      padding: 20px;
      font-size: 24px;
      font-weight: bold;
    }
    .content {
      padding: 30px;
      color: #111827;
      font-size: 16px;
      line-height: 1.6;
    }
    .signal {
      display: inline-block;
      padding: 10px 20px;
      border-radius: 8px;
      color: #ffffff;
      font-weight: bold;
    }
    .buy {
      background-color: #28a745; /* green for BUY */
    }
    .sell {
      background-color: #dc3545; /* red for SELL */
    }
    .footer {
      text-align: center;
      font-size: 13px;
      color: #6b7280;
      padding: 20px;
      background-color: #f9fafb;
    }
  </style>
</head>
<body>
  <div class="container">
    <div class="header">Market Signal Alert</div>
    <div class="content">
      <p>Hello Trader,</p>
      <p>Our automated system has detected a market signal for the following instrument:</p>
      <p><strong>Symbol:</strong> ${symbol}</p>
      <p><strong>Timeframe:</strong> ${timeframe}</p>
      <p><strong>Signal:</strong> 
        <span class="signal ${signal === "BUY" ? "buy" : "sell"}">${signal}</span>
      </p>
      <p><strong>Last Close Price:</strong> ${lastClose}</p>
      <p>Please review this signal and make your trading decisions accordingly.</p>
    </div>
    <div class="footer">
      &copy; ${new Date().getFullYear()} Trading Signals. All rights reserved.
    </div>
  </div>
</body>
</html>
`
