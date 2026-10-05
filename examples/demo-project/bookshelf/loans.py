from datetime import date, timedelta

LOAN_DAYS = 14


def lend(loans, title, reader, today):
    if title in loans:
        raise ValueError(f"{title} is already lent")
    loans[title] = (reader, today + timedelta(days=LOAN_DAYS))


def give_back(loans, title):
    return loans.pop(title)[0]


def overdue(loans, today=None):
    today = today or date.today()
    return sorted(title for title, (_, due) in loans.items() if due < today)
