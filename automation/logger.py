import smtplib
from datetime import datetime
from email.message import EmailMessage


class Logger:
    def __init__(self, log_file: str, email_recipient: str, email_host: str, email_user: str,
                 email_password: str) -> None:
        self._log_file: str = log_file
        self._email_recipient: str = email_recipient
        self._email_host: str = email_host
        self._email_user: str = email_user
        self._email_password: str = email_password

    def log(self, subject: str, message: str) -> None:
        time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        with open(self._log_file, 'a') as h:
            h.write(f'{time} {subject}\n{message}\n\n')

        msg = EmailMessage()
        msg['From'] = self._email_user
        msg['To'] = self._email_recipient
        msg['Subject'] = subject
        msg.set_content(message)

        with smtplib.SMTP_SSL(self._email_host, 465) as server:
            server.login(self._email_user, self._email_password)
            server.send_message(msg)
