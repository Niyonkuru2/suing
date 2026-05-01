export const marketSignalEmailTemplate = (
  symbol,
  signal,
  probability,
  timeframe,
  price,
  ema50,
  volatility
) => {
  const isBuy = signal === "BUY";

  const mainColor = isBuy ? "#16a34a" : "#dc2626";
  const softColor = isBuy ? "#dcfce7" : "#fee2e2";
  const signalText = isBuy ? "Bullish Setup" : "Bearish Setup";

  return `
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>Trading Alert</title>

<style>
body{
  margin:0;
  padding:0;
  background:#f3f4f6;
  font-family:Arial, Helvetica, sans-serif;
}

.wrapper{
  max-width:640px;
  margin:30px auto;
  background:#ffffff;
  border-radius:14px;
  overflow:hidden;
  box-shadow:0 8px 24px rgba(0,0,0,0.08);
}

.header{
  background:${mainColor};
  color:#ffffff;
  text-align:center;
  padding:28px 20px;
}

.header h1{
  margin:0;
  font-size:28px;
  letter-spacing:1px;
}

.header p{
  margin-top:8px;
  opacity:0.95;
  font-size:15px;
}

.content{
  padding:32px;
  color:#111827;
}

.badge{
  display:inline-block;
  padding:8px 18px;
  border-radius:999px;
  background:${mainColor};
  color:#fff;
  font-weight:bold;
  font-size:14px;
}

.card{
  margin-top:24px;
  border:1px solid #e5e7eb;
  border-radius:12px;
  overflow:hidden;
}

.row{
  display:flex;
  justify-content:space-between;
  padding:14px 18px;
  border-bottom:1px solid #f1f5f9;
  font-size:15px;
}

.row:last-child{
  border-bottom:none;
}

.label{
  color:#6b7280;
}

.value{
  font-weight:700;
  color:#111827;
}

.score{
  margin-top:22px;
  background:${softColor};
  border-left:5px solid ${mainColor};
  padding:18px;
  border-radius:10px;
}

.score h3{
  margin:0 0 10px;
  font-size:18px;
}

.note{
  margin-top:22px;
  background:#f9fafb;
  padding:18px;
  border-radius:10px;
  font-size:14px;
  line-height:1.7;
  color:#374151;
}

.footer{
  text-align:center;
  padding:20px;
  background:#f9fafb;
  color:#6b7280;
  font-size:13px;
  border-top:1px solid #e5e7eb;
}
</style>
</head>

<body>
<div class="wrapper">

  <div class="header">
    <h1>${signal} ALERT</h1>
    <p>${signalText} detected by Smart Scanner</p>
  </div>

  <div class="content">

    <span class="badge">${signal}</span>

    <div class="card">
      <div class="row">
        <span class="label">Symbol</span>
        <span class="value">${symbol}</span>
      </div>

      <div class="row">
        <span class="label">Timeframe</span>
        <span class="value">${timeframe}</span>
      </div>

      <div class="row">
        <span class="label">Current Price</span>
        <span class="value">${price}</span>
      </div>

      <div class="row">
        <span class="label">EMA 50</span>
        <span class="value">${ema50}</span>
      </div>

      <div class="row">
        <span class="label">Volatility</span>
        <span class="value">${volatility}</span>
      </div>
    </div>

    <div class="score">
      <h3>Probability Score: ${probability}</h3>
      <p>
        Setup aligned with higher timeframe trend and lower timeframe trigger.
      </p>
    </div>

    <div class="note">
      <strong>Execution Checklist:</strong><br/>
      ✓ Confirm candle close<br/>
      ✓ Avoid entering before breakout confirmation<br/>
      ✓ Respect stop loss<br/>
      ✓ Risk only 1%–2% per trade<br/>
      ✓ Check major news events before entry
    </div>

  </div>

  <div class="footer">
    © ${new Date().getFullYear()} Smart Trading Bot<br/>
    Powered by FastAPI × Node.js × Twelve Data
  </div>

</div>
</body>
</html>
`;
};
