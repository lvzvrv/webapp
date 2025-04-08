from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os

db_host = "db"
db_user = "postgres"
db_dbname = "postgres"
db_password = "BratkaIlya2015"

DATABASE_URL = f"postgresql://{db_user}:{db_password}@{db_host}:5432/{db_dbname}"

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

from sqlalchemy.orm import Session
from app import models

def init_db(db: Session):
    products_count = db.query(models.Product).count()
    if products_count == 0:

        # user that orders flag
        first_user = models.User(
            id = 0,
            username = "supermegauser",
            password_hash = "privet)))",
            balance = 0
        )

        # order with flag
        first_order = models.Order(
            id = 0, # подразумевается, что это самый первый заказ, а 0 это символичное начало
            user_id = 0,
            product_id = 2281337,
            quantity = 1,
            total_price = 9999,
            created_at = "2022-12-22 22:22:22.222222"
        )

        fake_users = [
            models.User(username="user1", password_hash="password1", balance=1000),
            models.User(username="user2", password_hash="password2", balance=500),
            models.User(username="user3", password_hash="password3", balance=1500),
            models.User(username="user4", password_hash="password4", balance=2000),
            models.User(username="user5", password_hash="password5", balance=300),
            models.User(username="user6", password_hash="password6", balance=800),
            models.User(username="user7", password_hash="password7", balance=1200),
            models.User(username="user8", password_hash="password8", balance=700),
            models.User(username="user9", password_hash="password9", balance=900),
            models.User(username="user10", password_hash="password10", balance=600),
        ]

        # base products
        initial_products = [
            models.Product(
                id = 2281337,
                name="Секретный товар",
                description=os.getenv('FLAG'),
                price=9999.0,
                is_hidden=True
            ),
            models.Product(name="Электронная книга", description="Лучший гид по программированию.", price=100.0),
            models.Product(name="Онлайн-курс", description="Изучите новые навыки.", price=200.0),
            models.Product(name="Музыкальный альбом", description="Сборник хитов.", price=150.0),
            models.Product(name="Графический планшет", description="Идеален для цифрового рисования и дизайна.",
                           price=300.0),
            models.Product(name="Умные часы",
                           description="Следите за здоровьем и получайте уведомления прямо на запястье.", price=250.0),
            models.Product(name="Наушники с шумоподавлением", description="Высококачественный звук без помех.",
                           price=180.0),
            models.Product(name="Игровая клавиатура",
                           description="Подсветка и быстрый отклик для профессиональных геймеров.", price=120.0),
            models.Product(name="Спортивная сумка", description="Просторная и удобная для занятий спортом.",
                           price=80.0),
            models.Product(name="Электросамокат", description="Экологичный транспорт для городских поездок.",
                           price=500.0),
            models.Product(name="Внешний жесткий диск", description="Надежное хранение данных объемом до 2 ТБ.",
                           price=90.0),
            models.Product(name="3D-принтер", description="Создавайте объекты прямо у себя дома.", price=600.0),
            models.Product(name="Очки виртуальной реальности",
                           description="Погружение в виртуальные миры с полным эффектом присутствия.", price=350.0),
            models.Product(name="Портативная колонка", description="Громкий и чистый звук в любом месте.", price=110.0)
        ]

        fake_orders = [
            models.Order(user_id=1, product_id=1, quantity=2, total_price=19998,
                         created_at="2023-01-10 10:10:10.000000"),
            models.Order(user_id=2, product_id=2, quantity=1, total_price=9999,
                         created_at="2023-01-11 11:11:11.000000"),
            models.Order(user_id=3, product_id=3, quantity=3, total_price=29997,
                         created_at="2023-01-12 12:12:12.000000"),
            models.Order(user_id=4, product_id=4, quantity=1, total_price=9999,
                         created_at="2023-01-13 13:13:13.000000"),
            models.Order(user_id=5, product_id=5, quantity=4, total_price=39996,
                         created_at="2023-01-14 14:14:14.000000"),
            models.Order(user_id=1, product_id=2, quantity=1, total_price=100,
                         created_at="2023-01-15 15:15:15.000000"),
            models.Order(user_id=2, product_id=3, quantity=2, total_price=400,
                         created_at="2023-01-16 16:16:16.000000"),
            models.Order(user_id=3, product_id=4, quantity=1, total_price=150,
                         created_at="2023-01-17 17:17:17.000000"),
            models.Order(user_id=4, product_id=5, quantity=3, total_price=900,
                         created_at="2023-01-18 18:18:18.000000"),
            models.Order(user_id=5, product_id=6, quantity=1, total_price=250,
                         created_at="2023-01-19 19:19:19.000000"),
            models.Order(user_id=6, product_id=7, quantity=1, total_price=180,
                         created_at="2023-01-20 20:20:20.000000"),
            models.Order(user_id=7, product_id=8, quantity=1, total_price=120,
                         created_at="2023-01-21 21:21:21.000000"),
            models.Order(user_id=8, product_id=9, quantity=2, total_price=160,
                         created_at="2023-01-22 22:22:22.000000"),
            models.Order(user_id=9, product_id=10, quantity=1, total_price=500,
                         created_at="2023-01-23 23:23:23.000000"),
            models.Order(user_id=10, product_id=11, quantity=1, total_price=90,
                         created_at="2023-01-24 00:00:00.000000"),
            models.Order(user_id=1, product_id=12, quantity=1, total_price=600,
                         created_at="2023-01-25 01:01:01.000000"),
            models.Order(user_id=2, product_id=13, quantity=1, total_price=350,
                         created_at="2023-01-26 02:02:02.000000"),
            models.Order(user_id=3, product_id=11, quantity=2, total_price=180,
                         created_at="2023-01-27 03:03:03.000000"),
            models.Order(user_id=4, product_id=5, quantity=2, total_price=600,
                         created_at="2023-01-28 04:04:04.000000"),
            models.Order(user_id=5, product_id=9, quantity=1, total_price=80,
                         created_at="2023-01-29 05:05:05.000000"),
            models.Order(user_id=6, product_id=6, quantity=3, total_price=750,
                         created_at="2023-01-30 06:06:06.000000"),
            models.Order(user_id=7, product_id=10, quantity=2, total_price=1000,
                         created_at="2023-01-31 07:07:07.000000"),
            models.Order(user_id=8, product_id=7, quantity=1, total_price=180,
                         created_at="2023-02-01 08:08:08.000000"),
            models.Order(user_id=9, product_id=8, quantity=2, total_price=240,
                         created_at="2023-02-02 09:09:09.000000"),
            models.Order(user_id=10, product_id=11, quantity=1, total_price=90,
                         created_at="2023-02-03 10:10:10.000000"),
        ]
        db.add_all(initial_products)
        db.add(first_user)
        db.add(first_order)
        db.add_all(fake_users)
        db.add_all(fake_orders)
        db.commit()
    else:
        print("База данных уже содержит товары.")
