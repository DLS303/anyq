from app.schemas import User

USERS: list[User] = [
    User(id="u-buyer", email="buyer@demo.superapp", full_name="Алия Нурланова", role="buyer", phone="+7 777 100 20 30"),
    User(id="u-owner", email="owner@demo.superapp", full_name="Ерлан Сатыбалды", role="owner", phone="+7 701 555 10 10"),
    User(id="u-mod", email="moderator@demo.superapp", full_name="Модератор", role="moderator"),
    User(id="u-admin", email="admin@demo.superapp", full_name="Администратор", role="admin"),
]

# The plots table stays in the database. Demo startup does not load listings.
PLOTS: list = []
