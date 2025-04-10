from sqlalchemy import Column, Integer, String, Float, Boolean, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from app.database import Base
from datetime import datetime

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    password_hash = Column(String)
    balance = Column(Float, default=1000.0)

    orders = relationship("Order", back_populates="owner")


class Product(Base):
    __tablename__ = "products"
    id = Column(Integer, primary_key=True, autoincrement=False)
    name = Column(String)
    small_description = Column(String)  # Новое поле для краткого описания
    description = Column(String)
    price = Column(Float)
    type = Column(String)

    # Новое поле для хранения ID изображения
    product_images_id = Column(Integer)

    _image_urls = []  # Это поле хранит временные данные, которые не сохраняются в БД

    @property
    def images(self):
        return self._image_urls  # Возвращаем сохранённый список изображений

    @images.setter
    def images(self, value):
        if isinstance(value, list):  # Проверяем, что значение — это список
            self._image_urls = value
        else:
            raise ValueError("The images must be a list of URLs.")  # Если это не список, выбрасываем ошибку

    def _get_image_urls(self, db_session):
        # Пример: извлекаем изображения из таблицы ProductImage на основе product_images_id
        product_images = db_session.query(ProductImage).filter(ProductImage.product_id == self.id).all()
        # Возвращаем список URL-ов изображений
        return [image.image_path for image in product_images]  # Возвращаем список UR


class Category(Base):
    __tablename__ = "categories"

    id = Column(Integer, primary_key=True)
    display_name = Column(String, nullable=False)
    type = Column(String, nullable=False, unique=True)
    display_order = Column(Integer, default=0)

    products = relationship("Product", primaryjoin="foreign(Product.type) == Category.type", viewonly=True)

class ProductImage(Base):
    __tablename__ = "product_images"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer)
    image_path = Column(String, nullable=False)  # Храним путь к файлу


class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    product_id = Column(Integer, ForeignKey("products.id"))
    quantity = Column(Integer)
    total_price = Column(Float)
    created_at = Column(DateTime, default=datetime.utcnow)

    owner = relationship("User", back_populates="orders")
    product = relationship("Product")

class CartItem(Base):
    __tablename__ = "cart_items"

    id = Column(Integer, primary_key=True)
    session_id = Column(String)  # Изменили user_id на session_id
    product_id = Column(Integer)
    quantity = Column(Integer, default=1)
    added_at = Column(DateTime, default=datetime.utcnow)