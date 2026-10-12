
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
  signalDatetime = null,
  priceAction = null
) => {
  const isPriceAction = Boolean(priceAction);
  const isBuy = signal === "BUY" || signal === "BUY_ZONE";
  const isZone = ["BUY_ZONE", "SELL_ZONE"].includes(signal);

  const displaySignal = isZone
    ? signal.replace("_", " ")
    : signal;

  const accent = isBuy ? "#0f9d58" : "#d93025";
  const accentSoft = isBuy ? "#e6f4ea" : "#fce8e6";
  const navy = "#0b1f3a";

  const safe = (value, fallback = "N/A") => {
    if (value === null || value === undefined || value === "") {
      return fallback;
    }

    return String(value).replace(/[&<>"']/g, (char) => {
      const entities = {
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;",
      };

      return entities[char];
    });
  };

  const zone = priceAction?.zone ?? {};
  const pullback = priceAction?.pullback ?? {};

  const freshnessRow =
    candlesSinceSignal !== null && candlesSinceSignal !== undefined
      ? `
        <tr>
          <td style="padding:10px 0;color:#5f6368;font-size:13px;width:44%;border-bottom:1px solid #edf0f4;">
            Candles Since Trigger
          </td>
          <td style="padding:10px 0;color:#1a1a1a;font-size:13px;font-weight:600;border-bottom:1px solid #edf0f4;">
            ${safe(candlesSinceSignal)}
          </td>
        </tr>`
      : "";

  const signalTimeRow = signalDatetime
    ? `
      <tr>
        <td style="padding:10px 0;color:#5f6368;font-size:13px;width:44%;border-bottom:1px solid #edf0f4;">
          Trigger Candle
        </td>
        <td style="padding:10px 0;color:#1a1a1a;font-size:13px;font-weight:600;border-bottom:1px solid #edf0f4;">
          ${safe(signalDatetime)}
        </td>
      </tr>`
    : "";

  const strategyExplanation = isPriceAction
    ? isZone
      ? `A potential ${isBuy ? "bullish" : "bearish"} price-action zone was identified from OHLC market structure. This is a zone alert, not a confirmed entry. Check lower-timeframe price action for confirmation.`
      : "Price-action analysis was returned. Review the market structure and analysis details before making a decision."
    : isBuy
      ? "Price closed above the 50 EMA, pulled back with two red candles, then closed back above the pre-pullback swing high."
      : "Price closed below the 50 EMA, pulled back with two green candles, then closed back below the pre-pullback swing low.";

  const priceRows = isPriceAction
    ? `
      <tr>
        <td style="padding:10px 0;color:#5f6368;font-size:13px;width:44%;border-bottom:1px solid #edf0f4;">
          Market Structure
        </td>
        <td style="padding:10px 0;color:#1a1a1a;font-size:14px;font-weight:700;border-bottom:1px solid #edf0f4;">
          ${safe(priceAction?.market_structure)}
        </td>
      </tr>
      <tr>
        <td style="padding:10px 0;color:#5f6368;font-size:13px;border-bottom:1px solid #edf0f4;">
          Zone Type
        </td>
        <td style="padding:10px 0;color:#1a1a1a;font-size:14px;border-bottom:1px solid #edf0f4;">
          ${safe(zone.type)}
        </td>
      </tr>
      <tr>
        <td style="padding:10px 0;color:#5f6368;font-size:13px;border-bottom:1px solid #edf0f4;">
          Zone Low
        </td>
        <td style="padding:10px 0;color:#1a1a1a;font-size:14px;font-weight:700;border-bottom:1px solid #edf0f4;">
          ${safe(zone.low)}
        </td>
      </tr>
      <tr>
        <td style="padding:10px 0;color:#5f6368;font-size:13px;border-bottom:1px solid #edf0f4;">
          Zone High
        </td>
        <td style="padding:10px 0;color:#1a1a1a;font-size:14px;font-weight:700;border-bottom:1px solid #edf0f4;">
          ${safe(zone.high)}
        </td>
      </tr>
      <tr>
        <td style="padding:10px 0;color:#5f6368;font-size:13px;border-bottom:1px solid #edf0f4;">
          Pullback Detected
        </td>
        <td style="padding:10px 0;color:#1a1a1a;font-size:14px;border-bottom:1px solid #edf0f4;">
          ${pullback.detected === true ? "Yes" : "No"}
        </td>
      </tr>
      <tr>
        <td style="padding:10px 0;color:#5f6368;font-size:13px;border-bottom:1px solid #edf0f4;">
          Entry Price
        </td>
        <td style="padding:10px 0;color:#1a1a1a;font-size:14px;border-bottom:1px solid #edf0f4;">
          Not calculated — zone alert only
        </td>
      </tr>
      <tr>
        <td style="padding:10px 0;color:#5f6368;font-size:13px;border-bottom:1px solid #edf0f4;">
          Stop Loss
        </td>
        <td style="padding:10px 0;color:#1a1a1a;font-size:14px;border-bottom:1px solid #edf0f4;">
          Not calculated
        </td>
      </tr>
      <tr>
        <td style="padding:10px 0;color:#5f6368;font-size:13px;border-bottom:1px solid #edf0f4;">
          Take Profit
        </td>
        <td style="padding:10px 0;color:#1a1a1a;font-size:14px;border-bottom:1px solid #edf0f4;">
          Not calculated
        </td>
      </tr>
      <tr>
        <td style="padding:10px 0;color:#5f6368;font-size:13px;border-bottom:1px solid #edf0f4;">
          EMA50
        </td>
        <td style="padding:10px 0;color:#1a1a1a;font-size:14px;border-bottom:1px solid #edf0f4;">
          Not used
        </td>
      </tr>
      <tr>
        <td style="padding:10px 0;color:#5f6368;font-size:13px;">
          Risk : Reward
        </td>
        <td style="padding:10px 0;color:#1a1a1a;font-size:14px;">
          Not calculated
        </td>
      </tr>`
    : `
      <tr>
        <td style="padding:10px 0;color:#5f6368;font-size:13px;width:44%;border-bottom:1px solid #edf0f4;">
          Entry Price
        </td>
        <td style="padding:10px 0;color:#1a1a1a;font-size:14px;font-weight:700;border-bottom:1px solid #edf0f4;">
          ${safe(entry_price)}
        </td>
      </tr>
      <tr>
        <td style="padding:10px 0;color:#5f6368;font-size:13px;border-bottom:1px solid #edf0f4;">
          Key Level
        </td>
        <td style="padding:10px 0;color:#1a1a1a;font-size:14px;border-bottom:1px solid #edf0f4;">
          ${safe(keyLevel)}
        </td>
      </tr>
      <tr>
        <td style="padding:10px 0;color:#5f6368;font-size:13px;border-bottom:1px solid #edf0f4;">
          EMA50
        </td>
        <td style="padding:10px 0;color:#1a1a1a;font-size:14px;border-bottom:1px solid #edf0f4;">
          ${safe(ema50)}
        </td>
      </tr>
      <tr>
        <td style="padding:10px 0;color:#5f6368;font-size:13px;border-bottom:1px solid #edf0f4;">
          Stop Loss
        </td>
        <td style="padding:10px 0;color:#d93025;font-size:14px;font-weight:700;border-bottom:1px solid #edf0f4;">
          ${safe(stopLoss)}
        </td>
      </tr>
      <tr>
        <td style="padding:10px 0;color:#5f6368;font-size:13px;border-bottom:1px solid #edf0f4;">
          Take Profit
        </td>
        <td style="padding:10px 0;color:#0f9d58;font-size:14px;font-weight:700;border-bottom:1px solid #edf0f4;">
          ${safe(takeProfit)}
        </td>
      </tr>
      <tr>
        <td style="padding:10px 0;color:#5f6368;font-size:13px;">
          Risk : Reward
        </td>
        <td style="padding:10px 0;color:#1a1a1a;font-size:14px;">
          1 : 2
        </td>
      </tr>`;

  const nextSteps = isPriceAction
    ? `
      <ol style="padding-left:20px;margin-bottom:0;">
        <li style="margin-bottom:8px;">Open the 15M or 5M chart.</li>
        <li style="margin-bottom:8px;">Check how price reacts inside or near the zone.</li>
        <li style="margin-bottom:8px;">Wait for a local structure break or rejection in the expected direction.</li>
        <li>Determine your own entry and risk levels only after confirmation.</li>
      </ol>`
    : `
      Confirm the setup on your own chart and manage risk before entering any trade.`;

  const footerStrategy = isPriceAction
    ? "Pure OHLC Price Action Strategy"
    : "EMA50 Breakout + Pullback Strategy";

  return `
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<meta name="color-scheme" content="light" />
<title>${safe(symbol)} ${safe(displaySignal)} Alert</title>
</head>

<body style="margin:0;padding:0;background-color:#eef1f5;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;">

  <div style="display:none;max-height:0;overflow:hidden;opacity:0;">
    ${safe(symbol)} ${safe(displaySignal)} alert on ${safe(timeframe)}.
    ${isPriceAction ? "Potential price-action zone. Confirmation required." : "Review your trading setup."}
  </div>

  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background-color:#eef1f5;padding:32px 16px;">
    <tr>
      <td align="center">
        <table role="presentation" width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%;background-color:#ffffff;border-radius:14px;overflow:hidden;box-shadow:0 2px 10px rgba(15,23,42,0.08);">

          <tr>
            <td style="background-color:${navy};padding:28px 32px;">
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
                <tr>
                  <td style="color:#ffffff;font-size:13px;letter-spacing:1.5px;text-transform:uppercase;opacity:0.75;">
                    Market Signal Bot
                  </td>
                  <td align="right" style="color:#ffffff;font-size:12px;opacity:0.75;">
                    ${safe(timeframe)}
                  </td>
                </tr>
              </table>

              <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-top:14px;">
                <tr>
                  <td style="vertical-align:middle;">
                    <span style="display:inline-block;background-color:${accent};color:#ffffff;font-size:13px;font-weight:700;letter-spacing:0.5px;padding:6px 14px;border-radius:20px;text-transform:uppercase;">
                      ${safe(displaySignal)}
                    </span>
                    <span style="color:#ffffff;font-size:22px;font-weight:600;margin-left:12px;">
                      ${safe(symbol)}
                    </span>
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <tr>
            <td style="padding:28px 32px 8px 32px;">
              <p style="margin:0 0 4px 0;color:#5f6368;font-size:13px;">
                ${isPriceAction ? "Price-action analysis" : "Setup detected"}
              </p>

              <p style="margin:0 0 20px 0;color:#1a1a1a;font-size:15px;font-weight:600;">
                ${safe(setupType, isPriceAction ? "Market Structure + Pullback Zone" : "EMA50 Breakout + Pullback")}
              </p>

              <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background-color:${accentSoft};border-radius:8px;margin-bottom:24px;">
                <tr>
                  <td style="padding:14px 16px;color:#1a1a1a;font-size:13px;line-height:1.65;">
                    ${strategyExplanation}
                  </td>
                </tr>
              </table>

              <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="font-family:'SFMono-Regular',Consolas,'Liberation Mono',Menlo,monospace;">
                ${priceRows}
                ${freshnessRow}
                ${signalTimeRow}
                <tr>
                  <td style="padding:10px 0;color:#5f6368;font-size:13px;">
                    Detected At
                  </td>
                  <td style="padding:10px 0;color:#1a1a1a;font-size:13px;">
                    ${safe(timestamp)}
                  </td>
                </tr>
              </table>

              ${priceAction?.info ? `
                <p style="margin:18px 0;color:#5f6368;font-size:13px;line-height:1.6;">
                  <strong>Analysis details:</strong> ${safe(priceAction.info)}
                </p>` : ""}
            </td>
          </tr>

          <tr>
            <td style="padding:0 32px 28px 32px;">
              <h3 style="font-size:15px;color:#0b1f3a;margin-bottom:12px;">
                ${isPriceAction ? "Recommended next steps" : "Important"}
              </h3>

              ${nextSteps}

              <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background-color:#fff8e1;border-radius:8px;margin-top:22px;">
                <tr>
                  <td style="padding:12px 16px;color:#7a5c00;font-size:12.5px;line-height:1.6;">
                    &#9888; This is an automated technical alert, not financial advice.
                    ${isPriceAction
                      ? "A zone is not a confirmed entry. This analysis does not calculate entry, stop-loss, take-profit, or risk/reward levels."
                      : "Confirm the setup on your own chart and manage risk before entering any trade."}
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <tr>
            <td style="padding:18px 32px;background-color:#f7f8fa;border-top:1px solid #edf0f4;">
              <p style="margin:0;color:#9aa0a6;font-size:11.5px;text-align:center;line-height:1.6;">
                &copy; ${new Date().getFullYear()} Market Signal Bot
                &nbsp;&middot;&nbsp; ${footerStrategy}<br/>
                Powered by FastAPI &times; Node.js &times; Twelve Data
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
