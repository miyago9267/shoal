"""Load the users table."""
import csv
import io

from .model import User


def load_users(text):
    """Parse ``id,name,plan`` CSV text into a list of User."""
    reader = csv.DictReader(io.StringIO(text))
    missing = {"id", "name", "plan"} - set(reader.fieldnames or [])
    if missing:
        raise ValueError(f"users file is missing column(s): {', '.join(sorted(missing))}")
    users = []
    for row in reader:
        users.append(User(id=int(row["id"]), name=row["name"].strip(),
                          plan=row["plan"].strip() or "none"))
    return users
