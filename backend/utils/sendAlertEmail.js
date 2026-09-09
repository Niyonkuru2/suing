export const marketSignalEmailTemplate = (
  symbol,
  signal,
  timeframe,
  entry_price,
  stopLoss,
  takeProfit,
  timestamp,
  setupType,
  keyLevel,
  ema50,
  candlesSinceSignal = null,
  signalDatetime = null
) => {
  const isBuy = signal === "BUY";
  const accent = isBuy ? "#0f9d58" : "#d93025";
  const accentSoft = isBuy ? "#e6f4ea" : "#fce8e6";
  const navy = "#0b1f3a";

  const freshnessRow =
    candlesSinceSignal !== null
      ? `<tr>
           <td style="padding:10px 0;color:#5f6368;font-size:13px;width:44%;border-bottom:1px solid #edf0f4;">Candles Since Trigger</td>
           <td style="padding:10px 0;color:#1a1a1a;font-size:13px;font-weight:600;border-bottom:1px solid #edf0f4;">${candlesSinceSignal}</td>
         </tr>`
      : "";

  const signalTimeRow = signalDatetime
    ? `<tr>
         <td style="padding:10px 0;color:#5f6368;font-size:13px;width:44%;border-bottom:1px solid #edf0f4;">Trigger Candle</td>
         <td style="padding:10px 0;color:#1a1a1a;font-size:13px;font-weight:600;border-bottom:1px solid #edf0f4;">${signalDatetime}</td>
       </tr>`
    : "";

  return `
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<meta name="color-scheme" content="light" />
<title>${symbol} ${signal} Signal</title>
</head>
<body style="margin:0;padding:0;background-color:#eef1f5;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;">
  <!-- preheader (hidden preview text) -->
  <div style="display:none;max-height:0;overflow:hidden;opacity:0;">
    ${symbol} ${signal} signal on ${timeframe} — entry ${entry_price}, SL ${stopLoss}, TP ${takeProfit}
  </div>

  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background-color:#eef1f5;padding:32px 16px;">
    <tr>
      <td align="center">
        <table role="presentation" width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%;background-color:#ffffff;border-radius:14px;overflow:hidden;box-shadow:0 2px 10px rgba(15,23,42,0.08);">

          <!-- Header -->
          <tr>
            <td style="background-color:${navy};padding:28px 32px;">
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
                <tr>
                  <td style="color:#ffffff;font-size:13px;letter-spacing:1.5px;text-transform:uppercase;opacity:0.65;">
                    Market Signal Bot
                  </td>
                  <td align="right" style="color:#ffffff;font-size:12px;opacity:0.65;">
                    ${timeframe}
                  </td>
                </tr>
              </table>
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-top:14px;">
                <tr>
                  <td style="vertical-align:middle;">
                    <span style="display:inline-block;background-color:${accent};color:#ffffff;font-size:13px;font-weight:700;letter-spacing:0.5px;padding:6px 14px;border-radius:20px;text-transform:uppercase;">
                      ${signal}
                    </span>
                    <span style="color:#ffffff;font-size:22px;font-weight:600;margin-left:12px;">
                      ${symbol}
                    </span>
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <!-- Body -->
          <tr>
            <td style="padding:28px 32px 8px 32px;">
              <p style="margin:0 0 4px 0;color:#5f6368;font-size:13px;">Setup detected</p>
              <p style="margin:0 0 20px 0;color:#1a1a1a;font-size:15px;font-weight:600;">
                ${setupType || "EMA50 Breakout + Pullback"}
              </p>

              <!-- Strategy explanation -->
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background-color:${accentSoft};border-radius:8px;margin-bottom:24px;">
                <tr>
                  <td style="padding:14px 16px;color:#1a1a1a;font-size:13px;line-height:1.55;">
                    ${
                      isBuy
                        ? "Price closed above the 50 EMA, pulled back with two red candles, then closed back above the pre-pullback swing high."
                        : "Price closed below the 50 EMA, pulled back with two green candles, then closed back below the pre-pullback swing low."
                    }
                  </td>
                </tr>
              </table>

              <!-- Key numbers -->
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="font-family:'SFMono-Regular',Consolas,'Liberation Mono',Menlo,monospace;">
                <tr>
                  <td style="padding:10px 0;color:#5f6368;font-size:13px;width:44%;border-bottom:1px solid #edf0f4;">Entry Price</td>
                  <td style="padding:10px 0;color:#1a1a1a;font-size:14px;font-weight:700;border-bottom:1px solid #edf0f4;">${entry_price}</td>
                </tr>
                <tr>
                  <td style="padding:10px 0;color:#5f6368;font-size:13px;border-bottom:1px solid #edf0f4;">Key Level</td>
                  <td style="padding:10px 0;color:#1a1a1a;font-size:14px;border-bottom:1px solid #edf0f4;">${keyLevel || "N/A"}</td>
                </tr>
                <tr>
                  <td style="padding:10px 0;color:#5f6368;font-size:13px;border-bottom:1px solid #edf0f4;">EMA50</td>
                  <td style="padding:10px 0;color:#1a1a1a;font-size:14px;border-bottom:1px solid #edf0f4;">${ema50 || "N/A"}</td>
                </tr>
                <tr>
                  <td style="padding:10px 0;color:#5f6368;font-size:13px;border-bottom:1px solid #edf0f4;">Stop Loss</td>
                  <td style="padding:10px 0;color:#d93025;font-size:14px;font-weight:700;border-bottom:1px solid #edf0f4;">${stopLoss}</td>
                </tr>
                <tr>
                  <td style="padding:10px 0;color:#5f6368;font-size:13px;border-bottom:1px solid #edf0f4;">Take Profit</td>
                  <td style="padding:10px 0;color:#0f9d58;font-size:14px;font-weight:700;border-bottom:1px solid #edf0f4;">${takeProfit}</td>
                </tr>
                <tr>
                  <td style="padding:10px 0;color:#5f6368;font-size:13px;border-bottom:1px solid #edf0f4;">Risk : Reward</td>
                  <td style="padding:10px 0;border-bottom:1px solid #edf0f4;">
                    <span style="display:inline-block;background-color:#eef1f5;color:#1a1a1a;font-size:12px;font-weight:700;padding:3px 10px;border-radius:10px;">1 : 2</span>
                  </td>
                </tr>
                ${freshnessRow}
                ${signalTimeRow}
                <tr>
                  <td style="padding:10px 0;color:#5f6368;font-size:13px;">Detected At</td>
                  <td style="padding:10px 0;color:#1a1a1a;font-size:13px;">${timestamp}</td>
                </tr>
              </table>
            </td>
          </tr>

          <!-- Disclaimer -->
          <tr>
            <td style="padding:0 32px 28px 32px;">
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background-color:#fff8e1;border-radius:8px;">
                <tr>
                  <td style="padding:12px 16px;color:#7a5c00;font-size:12.5px;line-height:1.5;">
                    ⚠️ This is an automated technical alert, not financial advice. Confirm the setup on your own chart and manage risk before entering any trade.
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <!-- Footer -->
          <tr>
            <td style="padding:18px 32px;background-color:#f7f8fa;border-top:1px solid #edf0f4;">
              <p style="margin:0;color:#9aa0a6;font-size:11.5px;text-align:center;line-height:1.6;">
                &copy; ${new Date().getFullYear()} Market Signal Bot &nbsp;·&nbsp; EMA50 Breakout + Pullback Strategy &nbsp;·&nbsp; 1:2 RR<br/>
                Powered by FastAPI × Node.js × Twelve Data
              </p>
            </td>
          </tr>

        </table>
      </td>
    </tr>
  </table>
</body>
</html>
`;
};
