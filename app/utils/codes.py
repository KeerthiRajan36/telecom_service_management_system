"""Human-friendly, sequential-looking code generators (CUST-xxxx, TCK-xxxx, ...)."""
import random
import string


def _suffix(n: int = 8) -> str:
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=n))


def gen_customer_code() -> str:
    return f"CUST-{_suffix(8)}"


def gen_ticket_code() -> str:
    return f"TCK-{_suffix(8)}"


def gen_request_code() -> str:
    return f"SRQ-{_suffix(8)}"
