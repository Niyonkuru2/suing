import nodemailer from "nodemailer";
import dotenv from "dotenv";

dotenv.config();

export const mailTransporter = nodemailer.createTransport({
  service: "gmail",
  auth: {
    user: process.env.EMAIL_USER,
    pass: process.env.EMAIL_PASS,
  },
});

//  HTML emails
export const sendAlertEmail = async (subject, htmlContent) => {
  const mailOptions = {
    from: process.env.EMAIL_USER,
    to: process.env.ALERT_RECEIVER,
    subject,
    html: htmlContent,
  };

  try {
    await mailTransporter.sendMail(mailOptions);
    console.log("Email alert sent successfully");
  } catch (err) {
    console.error("Failed to send email:", err.message);
  }
};