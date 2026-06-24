import base64
import os
import requests
from flask import current_app

class EmailService:
    """Service to handle all outgoing email communications using the Hermes API."""

    @staticmethod
    def send_email(to_emails, subject, body_html=None, body_text=None, from_name="ExpenseWise"):
        """Sends an email using the Hermes `/api/v1/send-email` API endpoint."""
        api_url = current_app.config.get('HERMES_BASE_URL')
        api_key = current_app.config.get('HERMES_API_KEY')
        bot_id = current_app.config.get('HERMES_EMAILBOT_ID')

        # Format recipient lists
        to_list = to_emails if isinstance(to_emails, list) else [to_emails]

        # Verify Hermes configurations are present; otherwise mock-log in developer mode
        if not api_url or not api_key:
            current_app.logger.warning(
                "Hermes Email Service is not configured. "
                "Simulating email dispatch to: %s | Subject: %s", to_list, subject
            )
            # Log raw mail contents to stdout/developer console
            print(f"\n--- [Hermes Email Bot Mock] To: {to_list} | Subject: {subject} ---")
            if body_text:
                print(f"Plaintext Body:\n{body_text}")
            if body_html:
                print(f"HTML Body:\n{body_html}")
            print("-------------------------------------------------------------\n")
            return {"success": True, "mocked": True}

        endpoint = f"{api_url.rstrip('/')}/api/v1/send-email"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "to": to_list,
            "subject": subject,
            "from_name": from_name
        }

        if bot_id:
            payload["bot_id"] = bot_id
        if body_html:
            payload["email_html_text"] = body_html
        if body_text:
            payload["email_plain_text"] = body_text

        try:
            response = requests.post(endpoint, headers=headers, json=payload, timeout=12)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            current_app.logger.error("Hermes Email API failed to dispatch message: %s", str(e))
            raise e

    @classmethod
    def send_otp_email(cls, email, otp):
        """Sends a verification OTP code during user registration."""
        subject = "Verify Your ExpenseWise Account - OTP"
        body_text = f"Your ExpenseWise registration verification OTP is: {otp}. It will expire in 5 minutes."
        body_html = f"""
        <html>
            <body style="font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; line-height: 1.6; color: #212529; padding: 20px;">
                <div style="max-width: 600px; margin: 0 auto; border: 1px solid #e9ecef; border-radius: 8px; overflow: hidden; box-shadow: 0 4px 6px rgba(0,0,0,0.05);">
                    <div style="background-color: #212529; color: #0d6efd; padding: 20px; text-align: center;">
                        <h1 style="margin: 0; font-size: 24px; font-weight: bold;">Expense<span style="color: #ffffff;">Wise</span></h1>
                    </div>
                    <div style="padding: 30px; background-color: #ffffff;">
                        <h2 style="color: #212529; margin-top: 0;">Confirm Your Email Address</h2>
                        <p>Thank you for registering an account on ExpenseWise. Please enter the following One-Time Password (OTP) to verify your account and activate your encrypted database vault:</p>
                        <div style="background-color: #f8f9fa; border: 1px solid #dee2e6; padding: 15px; text-align: center; margin: 25px 0; border-radius: 6px;">
                            <span style="font-size: 32px; font-weight: 800; letter-spacing: 4px; color: #0d6efd; font-family: monospace;">{otp}</span>
                        </div>
                        <p style="color: #6c757d; font-size: 14px;">This security code is strictly valid for <b>5 minutes</b>. If you did not register for this service, you can safely ignore this email.</p>
                    </div>
                    <div style="background-color: #f8f9fa; padding: 15px; text-align: center; font-size: 12px; color: #6c757d; border-top: 1px solid #e9ecef;">
                        Developed & Maintained by Indrajit Ghosh (Postdoc Researcher, IIT Kanpur)
                    </div>
                </div>
            </body>
        </html>
        """
        return cls.send_email(email, subject, body_html=body_html, body_text=body_text)

    @classmethod
    def send_password_reset_email(cls, email, reset_url):
        """Sends a secure password reset link to the user."""
        subject = "Reset Your ExpenseWise Password"
        body_text = f"We received a password reset request. Reset your password by opening the link: {reset_url}. This link expires in 1 hour."
        body_html = f"""
        <html>
            <body style="font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; line-height: 1.6; color: #212529; padding: 20px;">
                <div style="max-width: 600px; margin: 0 auto; border: 1px solid #e9ecef; border-radius: 8px; overflow: hidden; box-shadow: 0 4px 6px rgba(0,0,0,0.05);">
                    <div style="background-color: #212529; color: #0d6efd; padding: 20px; text-align: center;">
                        <h1 style="margin: 0; font-size: 24px; font-weight: bold;">Expense<span style="color: #ffffff;">Wise</span></h1>
                    </div>
                    <div style="padding: 30px; background-color: #ffffff;">
                        <h2 style="color: #dc3545; margin-top: 0;">Password Reset Request</h2>
                        <p>We received a request to reset the password for your ExpenseWise account. Click the button below to secure a new password:</p>
                        <div style="text-align: center; margin: 30px 0;">
                            <a href="{reset_url}" style="background-color: #0d6efd; color: #ffffff; padding: 12px 24px; text-decoration: none; border-radius: 5px; font-weight: bold; display: inline-block;">Reset Password</a>
                        </div>
                        <p style="color: #6c757d; font-size: 14px;">This reset button will expire in <b>1 hour</b>. If you did not request a password change, no action is needed.</p>
                    </div>
                    <div style="background-color: #f8f9fa; padding: 15px; text-align: center; font-size: 12px; color: #6c757d; border-top: 1px solid #e9ecef;">
                        Developed & Maintained by Indrajit Ghosh (Postdoc Researcher, IIT Kanpur)
                    </div>
                </div>
            </body>
        </html>
        """
        return cls.send_email(email, subject, body_html=body_html, body_text=body_text)
