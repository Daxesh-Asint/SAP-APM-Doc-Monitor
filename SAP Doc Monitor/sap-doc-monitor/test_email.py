"""
Test script to verify email configuration
"""
import smtplib
from email.message import EmailMessage
from config import settings

def test_email():
    print("Testing email configuration...")
    print(f"From: {settings.EMAIL_SENDER}")
    print(f"To: {settings.EMAIL_RECEIVER}")
    print(f"Server: {settings.SMTP_SERVER}:{settings.SMTP_PORT}")
    
    try:
        msg = EmailMessage()
        msg["From"] = settings.EMAIL_SENDER
        msg["To"] = settings.EMAIL_RECEIVER
        msg["Subject"] = "SAP Doc Monitor - Test Email"
        msg.set_content("""
        This is a test email from SAP Documentation Monitor.
        
        If you receive this email, your configuration is working correctly!
        
        Testing details:
        - Sender: learn.sapui5.frontend@gmail.com
        - Receiver: daxesh.prajapati@asint.net
        - Time: Test run
        
        Best regards,
        SAP Doc Monitor
        """)

        print("\nConnecting to SMTP server...")
        with smtplib.SMTP(settings.SMTP_SERVER, settings.SMTP_PORT, timeout=30) as server:
            print("Starting TLS...")
            server.starttls()
            
            print("Logging in...")
            server.login(settings.EMAIL_SENDER, settings.EMAIL_PASSWORD)
            
            print("Sending message...")
            server.send_message(msg)
            
        print("✅ Email sent successfully!")
        print(f"\nPlease check the inbox at: {settings.EMAIL_RECEIVER}")
        print("Also check the SPAM/Junk folder if not in inbox.")
        
    except smtplib.SMTPAuthenticationError as e:
        print(f"❌ Authentication failed: {e}")
        print("Please check your email and app password.")
    except smtplib.SMTPException as e:
        print(f"❌ SMTP error: {e}")
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_email()
