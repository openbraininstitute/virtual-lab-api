#!/usr/bin/env python3
"""
Script to send welcome emails and verification code emails from command line.

This script allows sending both types of emails:
1. Welcome emails - simple welcome message to single recipient or multiple recipients from file
2. Verification code emails - emails with verification codes for virtual labs (supports single recipient or multiple recipients from file)

Usage:
    poetry run send_emails welcome user@example.com
    poetry run send_emails welcome --email-list /path/to/emails.txt
    poetry run send_emails verification user@example.com --code 123456 --virtual-lab "My Lab" --expires "2025-12-31 23:59:59"
    poetry run send_emails verification --email-list /path/to/emails.txt --code ABC123 --virtual-lab "My Lab" --expires "2025-12-31 23:59:59"
"""

import argparse
import asyncio
import sys
from pathlib import Path
from typing import List

from pydantic import BaseModel, EmailStr, ValidationError
from virtual_labs.domain.email import VerificationCodeEmailDetails
from virtual_labs.infrastructure.email.send_welcome_email import send_welcome_email
from virtual_labs.infrastructure.email.verification_code_email import send_verification_code_email


class EmailModel(BaseModel):
    email: EmailStr


class EmailValidator:
    @staticmethod
    def validate_email(email: str) -> str:
        """Validate email using pydantic EmailStr."""
        try:
            EmailModel(email=email)
            return email
        except ValidationError as e:
            raise ValueError(f"invalid email format: {email}") from e


class EmailFileReader:
    @staticmethod
    def read_email_list(file_path: str) -> List[str]:
        path = Path(file_path)
        if not path.exists():
            raise ValueError(f"email list file not found: {file_path}")

        try:
            emails = []
            with open(path, 'r', encoding='utf-8') as f:
                for line_num, line in enumerate(f, 1):
                    email = line.strip()
                    if email:  
                        try:
                            emails.append(EmailValidator.validate_email(email))
                        except ValueError as e:
                            print(f"Warning: Line {line_num}: {e}")
            return emails
        except Exception as e:
            raise ValueError(f"Error reading email list file: {e}")


class EmailSender:
    def __init__(self):
        self.validator = EmailValidator()

    async def send_single_welcome(self, recipient: str) -> bool:
        print(f"Sending welcome email to: {recipient}")
        try:
            result = await send_welcome_email(recipient)
            print(f"✓ {result}")
            return True
        except Exception as e:
            print(f"✗ Failed to send welcome email: {str(e)}")
            self._print_traceback()
            return False

    async def send_bulk_welcome(self, recipients: List[str]) -> None:
        print(f"Sending welcome emails to {len(recipients)} recipient(s):")
        for email in recipients[:5]:  # Show first 5
            print(f"  - {email}")
        if len(recipients) > 5:
            print(f"  ... and {len(recipients) - 5} more")

        success_count = 0
        for i, recipient in enumerate(recipients, 1):
            print(f"\n[{i}/{len(recipients)}] Processing {recipient}...")
            if await self.send_single_welcome(recipient):
                success_count += 1

        print(f"\n✓ Completed: {success_count}/{len(recipients)} emails sent successfully")
        if success_count < len(recipients):
            sys.exit(1)

    async def send_single_verification(self, recipient: str, code: str, virtual_lab_name: str, expires_at: str) -> bool:
        print(f"Sending verification email to: {recipient}")
        print(f"  Code: {code}")
        print(f"  Virtual Lab: {virtual_lab_name}")
        print(f"  Expires: {expires_at}")

        try:
            details = VerificationCodeEmailDetails(
                recipient=recipient,
                code=code,
                virtual_lab_name=virtual_lab_name,
                expire_at=expires_at
            )
            result = await send_verification_code_email(details)
            print(f"✓ {result}")
            return True
        except Exception as e:
            print(f"✗ Failed to send verification email: {str(e)}")
            self._print_traceback()
            return False

    async def send_bulk_verification(self, recipients: List[str], code: str, virtual_lab_name: str, expires_at: str) -> None:
        """Send verification code emails to multiple recipients."""
        print(f"Sending verification emails to {len(recipients)} recipient(s) with code: {code}")
        for email in recipients[:5]: 
            print(f"  - {email}")
        if len(recipients) > 5:
            print(f"  ... and {len(recipients) - 5} more")

        success_count = 0
        for i, recipient in enumerate(recipients, 1):
            print(f"\n[{i}/{len(recipients)}] Processing {recipient}...")
            if await self.send_single_verification(recipient, code, virtual_lab_name, expires_at):
                success_count += 1

        print(f"\n✓ Completed: {success_count}/{len(recipients)} emails sent successfully")
        if success_count < len(recipients):
            sys.exit(1)

    def _print_traceback(self) -> None:
        """Print full traceback for debugging."""
        import traceback
        print("Full traceback:")
        traceback.print_exc()


def create_parser() -> argparse.ArgumentParser:
    """Create and configure the argument parser."""
    parser = argparse.ArgumentParser(
        description="Send welcome emails and verification code emails",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Send welcome email to single recipient
  poetry run send_emails welcome user@example.com

  # Send welcome emails to multiple recipients from file
  poetry run send_emails welcome --email-list /path/to/emails.txt

  # Send verification code email to single recipient
  python send_emails verification user@example.com --code 123456 --virtual-lab "My Lab" --expires "2025-12-31 23:59:59"

  # Send verification code emails to multiple recipients from file
  python send_emails verification --email-list /path/to/emails.txt --code ABC123 --virtual-lab "My Lab" --expires "2025-12-31 23:59:59"
        """
    )

    subparsers = parser.add_subparsers(dest="command", help="Email type to send")

    welcome_parser = subparsers.add_parser("welcome", help="Send welcome emails")
    group = welcome_parser.add_mutually_exclusive_group(required=True)
    group.add_argument("recipient", nargs='?', help="Single recipient email address")
    group.add_argument("--email-list", help="Path to file containing email addresses (one per line)")

    verification_parser = subparsers.add_parser("verification", help="Send verification code emails")
    group = verification_parser.add_mutually_exclusive_group(required=True)
    group.add_argument("recipient", nargs='?', help="Single recipient email address")
    group.add_argument("--email-list", help="Path to file containing email addresses (one per line)")
    verification_parser.add_argument("--code", required=True, help="Verification code (any format/length)")
    verification_parser.add_argument("--virtual-lab", required=True, help="Name of the virtual lab")
    verification_parser.add_argument("--expires", required=True, help="Expiration date/time (e.g., '2025-12-31 23:59:59')")

    return parser


async def main_async() -> None:
    parser = create_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    sender = EmailSender()
    validator = EmailValidator()

    try:
        if args.command == "welcome":
            if args.email_list:
                recipients = EmailFileReader.read_email_list(args.email_list)
                if not recipients:
                    print("Error: No valid email addresses found in the file")
                    sys.exit(1)
                await sender.send_bulk_welcome(recipients)
            else:
                recipient = validator.validate_email(args.recipient)
                success = await sender.send_single_welcome(recipient)
                if not success:
                    sys.exit(1)

        elif args.command == "verification":
            if args.email_list:
                recipients = EmailFileReader.read_email_list(args.email_list)
                if not recipients:
                    print("Error: No valid email addresses found in the file")
                    sys.exit(1)
                await sender.send_bulk_verification(
                    recipients=recipients,
                    code=args.code,  
                    virtual_lab_name=args.virtual_lab,
                    expires_at=args.expires
                )
            else:
                recipient = validator.validate_email(args.recipient)
                success = await sender.send_single_verification(
                    recipient=recipient,
                    code=args.code,  
                    virtual_lab_name=args.virtual_lab,
                    expires_at=args.expires
                )
                if not success:
                    sys.exit(1)

    except ValueError as e:
        print(f"Error: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nOperation cancelled")
        sys.exit(1)


def main() -> None: 
    asyncio.run(main_async())


def run_async() -> int:
    try:
        main()
        return 0
    except SystemExit as e:
        return e.code
    except Exception as e:
        print(f"Error: {e}")
        return 1


if __name__ == "__main__":
    run_async()
