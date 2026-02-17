import smtplib
from email.message import EmailMessage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

def send_email(subject, body, settings, html_body=None):
    """
    Send email to one or multiple recipients.
    EMAIL_RECEIVER can be a single email or comma-separated list.
    Supports both plain text and HTML emails.
    """
    # Handle multiple recipients - split by comma or semicolon
    receiver = settings.EMAIL_RECEIVER.replace(';', ',')
    recipients = [email.strip() for email in receiver.split(',') if email.strip()]
    
    if html_body:
        # Create multipart message with both plain text and HTML
        msg = MIMEMultipart('alternative')
        msg["From"] = settings.EMAIL_SENDER
        msg["To"] = ', '.join(recipients)
        msg["Subject"] = subject
        
        # Attach both plain text and HTML versions
        part1 = MIMEText(body, 'plain')
        part2 = MIMEText(html_body, 'html')
        msg.attach(part1)
        msg.attach(part2)
    else:
        # Use simple EmailMessage for plain text only
        msg = EmailMessage()
        msg["From"] = settings.EMAIL_SENDER
        msg["To"] = ', '.join(recipients)
        msg["Subject"] = subject
        msg.set_content(body)

    with smtplib.SMTP(settings.SMTP_SERVER, settings.SMTP_PORT) as server:
        server.starttls()
        server.login(settings.EMAIL_SENDER, settings.EMAIL_PASSWORD)
        server.send_message(msg)
    
    print(f"✅ Email sent to {len(recipients)} recipient(s): {', '.join(recipients)}")
