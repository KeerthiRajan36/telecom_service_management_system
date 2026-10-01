"""
Bootstrap script: creates tables (if missing), the first Super Admin, and a default
matrix of SLA rules. Safe to run multiple times.

    python -m scripts.seed
"""
import os

from app.core.config import settings
from app.db.base_class import Base
from app.db.session import engine, SessionLocal
from app.core.security import hash_password
from app.models.user import User
from app.models.sla import SLARule
from app.models.enums import UserRole, TicketCategory, TicketPriority, CustomerType
import app.models  # noqa: F401

# minutes to resolve, by priority
RESOLUTION_MINUTES = {
    TicketPriority.CRITICAL: 4 * 60,
    TicketPriority.HIGH: 8 * 60,
    TicketPriority.MEDIUM: 24 * 60,
    TicketPriority.LOW: 72 * 60,
}
# enterprise customers get tighter SLAs, prepaid slightly looser
CUSTOMER_TYPE_FACTOR = {
    CustomerType.ENTERPRISE: 0.5,
    CustomerType.POSTPAID: 1.0,
    CustomerType.PREPAID: 1.5,
}


def seed_admin(db):
    email = os.getenv("ADMIN_EMAIL", "admin@example.com")
    password = os.getenv("ADMIN_PASSWORD", "Admin@12345")
    if settings.ENV.lower() == "production" and password == "Admin@12345":
        raise SystemExit("Refusing to create the admin with the default password in production: set ADMIN_PASSWORD")
    if db.query(User).filter(User.email == email).first():
        print(f"Admin {email} already exists")
        return
    db.add(User(email=email, full_name="Super Admin", hashed_password=hash_password(password), role=UserRole.SUPER_ADMIN))
    db.commit()
    print(f"Created Super Admin: {email}")


def seed_sla_rules(db):
    created = 0
    for category in TicketCategory:
        for priority, minutes in RESOLUTION_MINUTES.items():
            for ctype, factor in CUSTOMER_TYPE_FACTOR.items():
                exists = db.query(SLARule).filter_by(ticket_category=category, priority=priority, customer_type=ctype).first()
                if exists:
                    continue
                resolution = int(minutes * factor)
                db.add(SLARule(
                    ticket_category=category, priority=priority, customer_type=ctype,
                    response_time_minutes=max(15, resolution // 8), resolution_time_minutes=resolution,
                ))
                created += 1
    db.commit()
    print(f"Seeded {created} SLA rules")


def main():
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        seed_admin(db)
        seed_sla_rules(db)


if __name__ == "__main__":
    main()
