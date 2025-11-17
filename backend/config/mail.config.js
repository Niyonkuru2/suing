import { Resend } from "resend";
import dotenv from "dotenv";

dotenv.config();

export const resend = new Resend(process.env.RESEND_API_KEY);

export const sendAlertEmail = async (subject, htmlContent) => {
  try {
    const { data, error } = await resend.emails.send({
      from: "Forex Analysis With 50 EMA <onboarding@resend.dev>",
      to: process.env.ALERT_RECEIVER,
      subject,
      html: htmlContent,
    });

    if (error) throw error;
    console.log("Email alert sent successfully:", data?.id || "no-id");
  } catch (err) {
    console.error("Failed to send email:", err.message);
  }
};
