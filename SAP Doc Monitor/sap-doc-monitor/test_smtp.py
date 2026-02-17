"""
SMTP Configuration Helper
This script helps you test different SMTP configurations to find the right one.
"""

import smtplib
from email.mime.text import MIMEText

def test_smtp_connection(server, port, email, password):
    """Test SMTP connection with given credentials"""
    try:
        print(f"\nTesting: {server}:{port}")
        print(f"Email: {email}")
        print("-" * 50)
        
        # Create connection
        smtp = smtplib.SMTP(server, port)
        smtp.starttls()
        
        print("[+] Connection established")
        print("[+] TLS enabled")
        
        # Try to login
        smtp.login(email, password)
        print("[+] Login successful!")
        print(f"\n*** SUCCESS! Use these settings: ***")
        print(f"SMTP_SERVER = \"{server}\"")
        print(f"SMTP_PORT = {port}")
        
        smtp.quit()
        return True
        
    except smtplib.SMTPAuthenticationError:
        print("[X] Authentication failed - Check your email/password")
        return False
    except smtplib.SMTPException as e:
        print(f"[X] SMTP Error: {e}")
        return False
    except Exception as e:
        print(f"[X] Connection failed: {e}")
        return False

def main():
    print("="*70)
    print("SMTP Configuration Test")
    print("="*70)
    
    email = input("\nEnter your email (daxesh.prajapati@asint.net): ").strip()
    if not email:
        email = "daxesh.prajapati@asint.net"
    
    password = input("Enter your app password: ").strip()
    
    if not password:
        print("\n[!] Password is required!")
        return
    
    # Test common SMTP configurations
    configurations = [
        ("smtp.office365.com", 587),  # Microsoft 365
        ("smtp-mail.outlook.com", 587),  # Outlook
        ("smtp.gmail.com", 587),  # Google Workspace / Gmail
        ("mail.asint.net", 587),  # Custom (company domain)
        ("smtp.asint.net", 587),  # Custom (company domain)
    ]
    
    print("\nTesting different SMTP servers...\n")
    
    for server, port in configurations:
        if test_smtp_connection(server, port, email, password):
            print("\n" + "="*70)
            print("Configuration found! Update your settings.py with the above values.")
            print("="*70)
            break
    else:
        print("\n" + "="*70)
        print("No working configuration found.")
        print("Please contact your IT department for SMTP settings.")
        print("="*70)

if __name__ == "__main__":
    main()
