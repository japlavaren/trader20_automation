import smtplib
from datetime import datetime
from email.message import EmailMessage
from typing import List, Optional


class Logger:
    def __init__(self, log_file: str, email_recipient: str, email_host: str, email_user: str,
                 email_password: str) -> None:
        self._log_file: str = log_file
        self._email_recipient: str = email_recipient
        self._email_host: str = email_host
        self._email_user: str = email_user
        self._email_password: str = email_password

    def log_message(self, symbol: str, content: str, parts: List[str]) -> None:
        spot_link = f'https://www.binance.com/en/trade/{symbol}'
        futures_link = f'https://www.binance.com/en/futures/{symbol}'
        info = '\n'.join(parts)
        self.log(subject=', '.join(parts), body=f'{content}\n\n{spot_link}\n{futures_link}\n\n{info}'.strip())

    def log(self, subject: str, body: str) -> None:
        time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        with open(self._log_file, 'a') as h:
            h.write(f'{time} {subject}\n{body}\n\n')

        msg = EmailMessage()
        msg['From'] = self._email_user
        msg['To'] = self._email_recipient
        msg['Subject'] = subject
        msg.set_content(body)

        with smtplib.SMTP_SSL(self._email_host, 465) as server:
            server.login(self._email_user, self._email_password)
            server.send_message(msg)

    @staticmethod
    def join_contents(content: str, parent_content: Optional[str]) -> str:
        return content + ('\n-----\n' + parent_content if parent_content is not None else '')
