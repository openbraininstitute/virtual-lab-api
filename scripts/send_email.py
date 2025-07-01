# Utility script to send an email from command line and test our templates.
import asyncio
import sys
from pathlib import Path

from fastapi_mail import ConnectionConfig, FastMail, MessageSchema, MessageType

from virtual_labs.infrastructure.settings import settings


def read_command_line_arguments():
    if len(sys.argv) < 2:
        print()
        print("This script needs 3 arguments (only the first one is mandatory):")
        print("  * recipient (ex: \"obi.user.test.four@gmail.com\")")
        print("  * template (ex: \"welcome.html\")")
        print("  * subject (ex: \"Start your Simulation Journey!\")")
        print()
        sys.exit(1)
    recipient = sys.argv[1]
    template = "welcome.html"
    subject = "Start your Simulation Journey!"
    if len(sys.argv) > 2:
        template = sys.argv[2]
    if len(sys.argv) > 3:
        subject = sys.argv[3]
    return (recipient, template, subject)

async def main():
    (recipient, template, subject) = read_command_line_arguments()
    print()
    print("Sending email...")
    print("  To:       ", recipient)
    print("  Subject:  ", subject)
    print("  Template: ", template)
    print()
    email_config = ConnectionConfig(
        MAIL_FROM = settings.MAIL_FROM,
        MAIL_USERNAME = settings.MAIL_USERNAME,
        MAIL_PASSWORD = settings.MAIL_PASSWORD,
        MAIL_SERVER = settings.MAIL_SERVER,
        MAIL_PORT = settings.MAIL_PORT,
        MAIL_STARTTLS = True,
        MAIL_SSL_TLS = False,
        USE_CREDENTIALS = True,
        VALIDATE_CERTS = False,
        TEMPLATE_FOLDER = Path(__file__).parent.parent
        / "virtual_labs/infrastructure/email/templates",
    )
    try:
        message = MessageSchema(
            subject=subject,
            recipients=[recipient],
            body="",
            subtype=MessageType.html,
            template_body={},
        )
        fm = FastMail(email_config)
        await fm.send_message(message, template_name=template)
        print(f"An email has just been sent to {recipient}")
    except Exception as error:
        print(f"Unable to send an email to {recipient}!\n{error}")


def run_async() -> int:
    """
    Entrypoint for poetry script command.
    """
    asyncio.run(main())
    return 0


if __name__ == "__main__":
    run_async()
