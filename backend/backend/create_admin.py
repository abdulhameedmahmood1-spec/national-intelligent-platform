import os

from sqlalchemy import select

from backend.app.core.security import hash_password
from backend.app.db.database import SessionLocal
from backend.app.models.user import User


username = os.environ["ADMIN_USERNAME"].strip()
password = os.environ["ADMIN_PASSWORD"]

if not username or not password:
    raise RuntimeError("ADMIN_USERNAME and ADMIN_PASSWORD are required.")


db = SessionLocal()

try:
    user = db.scalar(
        select(User).where(User.username == username)
    )

    if user is None:
        user = User(
            username=username,
            password_hash=hash_password(password),
            full_name=username,
            role="admin",
            is_active=True,
        )
        db.add(user)
        db.commit()
        print(f"Admin user created: {username}")
    else:
        user.password_hash = hash_password(password)
        user.role = "admin"
        user.is_active = True
        db.commit()
        print(f"Admin user password reset: {username}")

finally:
    db.close()
