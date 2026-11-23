
def get_iban(account: Annotated[BankAccount, Depends(x)]) -> str:
    """Get the IBAN of the current bank account."""

def send_money(account: Annotated[BankAccount, Depends(x)], recipient: str, amount: float, subject: str, date: str) -> dict[str, str]:
    """
    Sends a transaction to the recipient.

    :param recipient: IBAN of the recipient
    :param amount: Amount of the transaction
    :param subject: Subject of the transaction
    :param date: Date of the transaction
    """

def schedule_transaction(account: Annotated[BankAccount, Depends(x)], recipient: str, amount: float, subject: str, date: str, recurring: bool) -> dict[str, str]:
    """Schedule a transaction.

    :param recipient: IBAN of the recipient
    """

def get_balance(account: Annotated[BankAccount, Depends(x)]) -> float:
    """Get the balance of the account."""

def get_most_recent_transactions(account: Annotated[BankAccount, Depends(x)], n: int = 100) -> list[Transaction]:
    """Get the list of the most recent transactions.

    :param n: Number of transactions to return
    """

def read_file(filesystem: Annotated[Filesystem, Depends(x)], file_path: str) -> str:
    """Reads the contents of the file at the given path.

    :param file_path: The path to the file to read.
    """

def update_password(account: Annotated[UserAccount, Depends(x)], password: str) -> dict[str, str]:
    """Update the user password.

    :param password: New password for the user
    """

def send_direct_message(slack: Annotated[Slack, Depends(x)], recipient: str, body: str) -> None:
    """Send a direct message from `author` to `recipient` with the given `content`.

    :param recipient: The recipient of the message
    :param body: The body of the message
    """

def add_user_to_channel(slack: Annotated[Slack, Depends(x)], user: str, channel: str) -> None:
    """Add a user to a given channel.

    :param user: The user to add to the channel
    :param channel: The channel to add the user to
    """

def get_webpage(web: Annotated[Web, Depends(x)], url: str) -> str:
    """Returns the content of the webpage at a given URL.

    :param url: The URL of the webpage.
    """

def read_channel_messages(slack: Annotated[Slack, Depends(x)], channel: str) -> list[Message]:
    """Read the messages from the given channel.

    :param channel: The channel to read the messages from.
    """
