# Security Policy

## Sensitive Information

This project requires sensitive credentials to function. Please follow these guidelines:

### Configuration Files

- **NEVER** commit `config/settings.py` to version control
- This file is already listed in `.gitignore`
- Always use `config/settings.example.py` as a template

### Email Credentials

- Use App Passwords (Gmail) or service account credentials (Microsoft 365), not your main account password
- Never share your App Password publicly
- Generate unique App Passwords for each application
- Revoke App Passwords when no longer needed

### Setting Up Email Credentials

**For Gmail:**
1. Enable 2-Factor Authentication on your Google Account
2. Go to: [Google Account → Security → 2-Step Verification → App passwords](https://myaccount.google.com/apppasswords)
3. Generate a new app password for "Mail"
4. Copy the generated password to `config/settings.py`

**For Microsoft 365 / Office 365:**
1. Ensure your organization allows SMTP AUTH
2. Use your account credentials or an App Password if MFA is enabled
3. Set `SMTP_SERVER = "smtp.office365.com"` and `SMTP_PORT = 587`

## Cloud Deployment Security

When deploying to GCP Cloud Run, follow these additional best practices:

### Secret Manager
- **Always** store email passwords in GCP Secret Manager — never as plain-text environment variables
- Grant only the Cloud Run service account access to secrets (`roles/secretmanager.secretAccessor`)

### IAM — Principle of Least Privilege
- Create a dedicated service account for Cloud Scheduler with only `roles/run.invoker`
- Do not use overly broad roles like `roles/owner` or `roles/editor`
- Regularly audit IAM bindings using `gcloud projects get-iam-policy`

### Network Security
- Deploy Cloud Run with `--no-allow-unauthenticated` to prevent public access
- Only Cloud Scheduler (via authenticated OIDC token) should be able to trigger runs

### Container Security
- Keep the base Docker image (`python:3.11-slim`) updated
- Regularly rebuild and redeploy to pick up security patches for Chrome and system libraries

## Reporting Security Issues

If you discover a security vulnerability, please email the maintainer directly rather than opening a public issue.

## Best Practices

1. **Environment Variables**: Use environment variables for sensitive data in production (Cloud Run)
2. **Separate Credentials**: Use different credentials for development and production
3. **Regular Rotation**: Periodically rotate your App Passwords and service account keys
4. **Access Control**: Limit who has access to production credentials and GCP project
5. **Audit Logging**: Enable Cloud Audit Logs to track access to secrets and services

## What's Safe to Share

✅ Safe:
- `config/settings.example.py` (template with placeholder values)
- All code files (no secrets embedded)
- README and documentation
- `requirements.txt`
- `Dockerfile` and deployment scripts

❌ Never Share:
- `config/settings.py` (contains real credentials)
- Email passwords or App Passwords
- GCP service account key files (`.json`)
- API keys or tokens
- Any file containing real email addresses or URLs you want to keep private
