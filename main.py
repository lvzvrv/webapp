from fastapi import FastAPI, Request, Depends, Form, status, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from sqlalchemy import text, insert
from app.database import engine, SessionLocal, init_db
from app import models, auth
from app.models import Base
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from app.auth import get_auth_token, check_cookies
from fastapi.security import HTTPBasic, HTTPBasicCredentials
import secrets
from typing import Optional
import uvicorn
import uuid
from fastapi import BackgroundTasks, Form
from fastapi_mail import FastMail, MessageSchema, ConnectionConfig
from pydantic import EmailStr
from datetime import datetime
from typing import Optional

from app.database import SessionLocal, engine
from app import models

Base.metadata.create_all(bind=engine)

limiter = Limiter(key_func=get_remote_address)
app = FastAPI()
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

templates = Jinja2Templates(directory="app/templates")

# Конфигурация админ-панели
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "secure_admin_password_123"  # В реальном проекте используйте переменные окружения
security = HTTPBasic()

# Настройки почты (замените на свои)
conf = ConnectionConfig(
    MAIL_USERNAME="teahighshop@mail.ru",
    MAIL_PASSWORD="X1Gu9XWVvbhFBBKs0cKF",
    MAIL_FROM="teahighshop@mail.ru",
    MAIL_PORT=465,
    MAIL_SERVER="smtp.mail.ru",
    MAIL_STARTTLS=False,
    MAIL_SSL_TLS=True,
    USE_CREDENTIALS=True
)

def verify_admin(credentials: HTTPBasicCredentials = Depends(security)):
    correct_username = secrets.compare_digest(credentials.username, ADMIN_USERNAME)
    correct_password = secrets.compare_digest(credentials.password, ADMIN_PASSWORD)
    if not (correct_username and correct_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.get("/", response_class=HTMLResponse)
def index(request: Request, db: Session = Depends(get_db)):
    categories = db.query(models.Category).all()
    products = db.query(models.Product).all()

    for product in products:
        product.images = product._get_image_urls(db)

    session_id = request.cookies.get("session_id", "")
    items_count = db.query(models.CartItem) \
        .filter(models.CartItem.session_id == session_id) \
        .all()
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "categories": categories,
            "products": products,
            "cart_items_count": sum(item.quantity for item in items_count)
        }
    )


# Админ-панель
@app.get("/admin", response_class=HTMLResponse)
def admin_panel(
        request: Request,
        db: Session = Depends(get_db),
        username: str = Depends(verify_admin)
):
    products = db.query(models.Product).all()
    for product in products:
        product.images = product._get_image_urls(db)

    session_id = request.cookies.get("session_id", "")

    return templates.TemplateResponse(
        "admin/admin_panel.html",
        {
            "request": request,
            "products": products
        }
    )


@app.get("/admin/add-product", response_class=HTMLResponse)
def add_product_form(
        request: Request,
        db: Session = Depends(get_db),
        username: str = Depends(verify_admin)
):

    return templates.TemplateResponse(
        "admin/add_product.html",
        {
            "request": request
        }
    )


@app.post("/admin/add-product")
async def add_product(
        request: Request,
        product_id: int = Form(...),
        name: str = Form(...),
        small_description: str = Form(...),
        description: str = Form(...),
        price: float = Form(...),
        product_type: str = Form(...),  # Добавлен параметр типа
        image_urls: str = Form(...),
        db: Session = Depends(get_db),
        username: str = Depends(verify_admin)
):
    try:
        product = models.Product(
            id=product_id,
            name=name,
            small_description=small_description,
            description=description,
            price=price,
            type=product_type  # Сохраняем тип товара
        )

        db.add(product)
        db.commit()

        # Добавляем изображения
        urls = [url.strip() for url in image_urls.split(',') if url.strip()]
        for url in urls:
            product_image = models.ProductImage(
                product_id=product.id,
                image_path=url
            )
            db.add(product_image)
        db.commit()

        return RedirectResponse(url="/admin", status_code=status.HTTP_303_SEE_OTHER)

    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=400,
            detail=f"Ошибка при добавлении товара: {str(e)}"
        )


@app.post("/admin/delete-product/{product_id}")
def delete_product(
        request: Request,
        product_id: int,
        db: Session = Depends(get_db),
        username: str = Depends(verify_admin)
):
    product = db.query(models.Product).filter(models.Product.id == product_id).first()
    if not product:
        return templates.TemplateResponse(
            "admin/admin_panel.html",
            {
                "request": request,
                "error": f"Товар с ID {product_id} не найден"
            }
        )

    try:
        # Удаляем связанные изображения
        db.query(models.ProductImage).filter(models.ProductImage.product_id == product_id).delete()
        # Удаляем сам продукт
        db.delete(product)
        db.commit()
        return RedirectResponse(url="/admin", status_code=status.HTTP_303_SEE_OTHER)

    except Exception as e:
        db.rollback()
        return templates.TemplateResponse(
            "admin/admin_panel.html",
            {
                "request": request,
                "error": f"Ошибка при удалении товара: {str(e)}"
            }
        )



# Остальные маршруты (логин, регистрация, профиль и т.д.)



@app.get("/login")
def login_form(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@app.post("/login")
def login(request: Request, username: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    user = auth.authenticate_user(db, username, password)
    if user:
        response = RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)
        response.set_cookie(key="Authorization", value=get_auth_token(username))
        return response
    else:
        return templates.TemplateResponse("login.html", {"request": request, "error": "Неверные учетные данные"})


@app.get("/register")
def register_form(request: Request):
    return templates.TemplateResponse("register.html", {"request": request})


@app.post("/register")
def register(request: Request, username: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    hashed_password = auth.get_password_hash(password)
    user = models.User(username=username, password_hash=hashed_password)
    if auth.check_user(username, db):
        return templates.TemplateResponse("register.html", {"request": request, "error": "Пользователь уже существует"})
    db.add(user)
    db.commit()
    return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)


@app.get("/product/{product_id}", response_class=HTMLResponse)
def product_details(product_id: int, request: Request, db: Session = Depends(get_db)):
    product = db.query(models.Product).filter(models.Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Товар не найден")

    product.images = product._get_image_urls(db)
    session_id = request.cookies.get("session_id", "")
    items_count = db.query(models.CartItem) \
        .filter(models.CartItem.session_id == session_id) \
        .all()

    return templates.TemplateResponse(
        "product_details.html",
        {
            "request": request,
            "product": product,
            "cart_items_count": sum(item.quantity for item in items_count)
        }
    )




@app.get("/admin/edit-product/{product_id}", response_class=HTMLResponse)
def edit_product_form(
        product_id: int,
        request: Request,
        db: Session = Depends(get_db),
        username: str = Depends(verify_admin)
):
    product = db.query(models.Product).filter(models.Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Товар не найден")

    # Получаем изображения товара
    product.images = product._get_image_urls(db)
    image_urls = ", ".join(product.images) if product.images else ""

    return templates.TemplateResponse(
        "admin/edit_product.html",
        {
            "request": request,
            "product": product,
            "image_urls": image_urls
        }
    )


@app.post("/admin/update-product/{product_id}")
async def update_product(
        product_id: int,
        request: Request,
        name: str = Form(...),
        small_description: str = Form(...),
        description: str = Form(...),
        price: float = Form(...),
        image_urls: str = Form(...),
        db: Session = Depends(get_db),
        username: str = Depends(verify_admin)
):
    try:
        product = db.query(models.Product).filter(models.Product.id == product_id).first()
        if not product:
            raise HTTPException(status_code=404, detail="Товар не найден")

        # Обновляем данные товара
        product.name = name
        product.small_description = small_description
        product.description = description
        product.price = price

        # Удаляем старые изображения
        db.query(models.ProductImage).filter(models.ProductImage.product_id == product_id).delete()

        # Добавляем новые изображения
        urls = [url.strip() for url in image_urls.split(',') if url.strip()]
        for url in urls:
            product_image = models.ProductImage(
                product_id=product.id,
                image_path=url
            )
            db.add(product_image)

        db.commit()

        return RedirectResponse(url="/admin", status_code=status.HTTP_303_SEE_OTHER)

    except Exception as e:
        db.rollback()
        product.images = product._get_image_urls(db)
        return templates.TemplateResponse(
            "admin/edit_product.html",
            {
                "request": request,
                "product": product,
                "image_urls": image_urls,
                "error": f"Ошибка при обновлении товара: {str(e)}"
            }
        )


@app.post("/add-to-cart")
async def add_to_cart(
        request: Request,
        product_id: int = Form(...),
        quantity: int = Form(1),
        db: Session = Depends(get_db)
):
    session_id = request.cookies.get("session_id")
    if not session_id:
        session_id = str(uuid.uuid4())

    response = JSONResponse(content={
        "status": "success",
        "added_count": quantity,
        "message": "Товар добавлен в корзину"
    })

    # Устанавливаем cookie с правильными атрибутами
    response.set_cookie(
        key="session_id",
        value=session_id,
        max_age=30 * 24 * 60 * 60,  # 30 дней
        httponly=True,
        secure=True,  # Для HTTPS
        samesite='Lax'  # Разрешает передачу между страницами
    )

    # Проверка существования товара
    product = db.query(models.Product).filter(models.Product.id == product_id).first()
    if not product:
        return JSONResponse(
            content={"status": "error", "message": "Товар не найден"},
            status_code=404
        )

    cart_item = db.query(models.CartItem).filter(
        models.CartItem.session_id == session_id,
        models.CartItem.product_id == product_id
    ).first()

    if cart_item:
        cart_item.quantity += quantity
    else:
        cart_item = models.CartItem(
            session_id=session_id,
            product_id=product_id,
            quantity=quantity
        )
        db.add(cart_item)

    db.commit()

    return response


# Просмотр корзины
@app.get("/cart", response_class=HTMLResponse)
async def view_cart(
    request: Request,
    db: Session = Depends(get_db)
):
    session_id = request.cookies.get("session_id")
    if not session_id:
        return templates.TemplateResponse("cart.html", {
            "request": request,
            "cart_items": [],
            "total": 0,
            "cart_items_count": 0
        })

    # Получаем элементы корзины с информацией о товарах
    cart_items = db.query(
        models.CartItem,
        models.Product
    ).join(
        models.Product,
        models.CartItem.product_id == models.Product.id
    ).filter(
        models.CartItem.session_id == session_id
    ).all()

    # Преобразуем результат в удобный формат
    items_with_details = []
    total = 0
    for cart_item, product in cart_items:
        cart_item.product = product  # Добавляем информацию о товаре
        items_with_details.append(cart_item)
        total += product.price * cart_item.quantity

    return templates.TemplateResponse("cart.html", {
        "request": request,
        "cart_items": items_with_details,  # Передаем items вместо item
        "total": total,
        "cart_items_count": len(items_with_details)
    })


@app.post("/update-cart-item/{item_id}")
async def update_cart_item(
        item_id: int,
        request: Request,
        quantity: int = Form(...),
        db: Session = Depends(get_db)
):
    session_id = request.cookies.get("session_id")


    cart_item = db.query(models.CartItem).filter(
        models.CartItem.id == item_id,
        models.CartItem.session_id == session_id
    ).first()

    if cart_item:
        if quantity <= 0:
            db.delete(cart_item)
        else:
            cart_item.quantity = quantity
        db.commit()

    return RedirectResponse(url="/cart", status_code=status.HTTP_303_SEE_OTHER)

# Удаление товара из корзины
@app.post("/remove-from-cart/{item_id}")
async def remove_from_cart(
        item_id: int,
        request: Request,
        db: Session = Depends(get_db)
):
    session_id = request.cookies.get("session_id")
    if session_id:
        db.query(models.CartItem).filter(
            models.CartItem.id == item_id,
            models.CartItem.session_id == session_id
        ).delete()
        db.commit()

    return RedirectResponse(url="/cart", status_code=status.HTTP_303_SEE_OTHER)


# Оформление заказа
@app.post("/checkout")
async def checkout(
        request: Request,
        db: Session = Depends(get_db)
):
    session_id = request.cookies.get("session_id")


    cart_items = db.query(models.CartItem).filter(
        models.CartItem.session_id == session_id
    ).all()

    if not cart_items:
        return RedirectResponse(url="/cart", status_code=status.HTTP_303_SEE_OTHER)

    # Здесь должна быть логика оформления заказа
    # Пока просто очищаем корзину
    db.query(models.CartItem).filter(
        models.CartItem.session_id == session_id
    ).delete()
    db.commit()

    return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)


@app.get("/admin/categories", response_class=HTMLResponse)
def list_categories(
        request: Request,
        db: Session = Depends(get_db),
        username: str = Depends(verify_admin)
):
    # Получаем уникальные типы товаров для создания категорий
    existing_types = db.query(models.Product.type).distinct().all()
    existing_types = [t[0] for t in existing_types if t[0]]

    # Получаем существующие категории
    categories = db.query(models.Category).all()

    # Находим типы товаров, для которых нет категорий
    missing_types = set(existing_types) - {c.type for c in categories}

    return templates.TemplateResponse(
        "admin/categories.html",
        {
            "request": request,
            "categories": categories,
            "missing_types": missing_types
        }
    )


@app.get("/admin/add-category", response_class=HTMLResponse)
def add_category_form(
        request: Request,
        db: Session = Depends(get_db),
        username: str = Depends(verify_admin)
):
    # Получаем уникальные типы товаров для выпадающего списка
    existing_types = db.query(models.Product.type).distinct().all()
    existing_types = [t[0] for t in existing_types if t[0]]

    # Получаем существующие категории, чтобы исключить уже использованные типы
    existing_categories = db.query(models.Category.type).all()
    existing_categories = [c[0] for c in existing_categories]

    # Фильтруем типы, оставляя только те, что еще не использованы в категориях
    available_types = [t for t in existing_types if t not in existing_categories]

    return templates.TemplateResponse(
        "admin/add_category.html",
        {
            "request": request,
            "existing_types": available_types
        }
    )


@app.post("/admin/add-category")
async def add_category(
        request: Request,
        display_name: str = Form(...),
        type: str = Form(...),
        display_order: int = Form(0),
        db: Session = Depends(get_db),
        username: str = Depends(verify_admin)
):
    # Проверяем, что тип товара существует
    if not db.query(models.Product).filter(models.Product.type == type).first():
        raise HTTPException(
            status_code=400,
            detail=f"Тип товара '{type}' не существует. Сначала добавьте товары с таким типом."
        )

    # Проверяем, что категория с таким type еще не существует
    if db.query(models.Category).filter(models.Category.type == type).first():
        raise HTTPException(
            status_code=400,
            detail=f"Категория для типа '{type}' уже существует"
        )

    category = models.Category(
        display_name=display_name,
        type=type,
        display_order=display_order
    )

    db.add(category)
    db.commit()

    return RedirectResponse(url="/admin/categories", status_code=303)

@app.get("/admin/categories", response_class=HTMLResponse)
def list_categories(
        request: Request,
        db: Session = Depends(get_db),
        username: str = Depends(verify_admin)):
    existing_types = db.query(models.Product.type).distinct().all()
    existing_types = [t[0] for t in existing_types if t[0]]
    categories = db.query(models.Category).all()
    missing_types = set(existing_types) - {c.type for c in categories}

    return templates.TemplateResponse(
        "admin/categories.html",  # путь правильный
        {
            "request": request,
            "categories": categories,
            "missing_types": missing_types
        }
    )

@app.get("/category/{category_type}", response_class=HTMLResponse)
def category_products(
        category_type: str,
        request: Request,
        db: Session = Depends(get_db)
):
    category = db.query(models.Category).filter(models.Category.type == category_type).first()
    if not category:
        raise HTTPException(status_code=404, detail="Категория не найдена")

    products = db.query(models.Product).filter(models.Product.type == category_type).all()

    for product in products:
        product.images = product._get_image_urls(db)

    session_id = request.cookies.get("session_id", "")
    items_count = db.query(models.CartItem) \
        .filter(models.CartItem.session_id == session_id) \
        .all()

    return templates.TemplateResponse(
        "category.html",  # Убедитесь, что имя файла совпадает
        {
            "request": request,
            "category": category,
            "products": products,
            "cart_items_count": sum(item.quantity for item in items_count)
        }
    )

@app.post("/admin/delete-category/{category_id}")
def delete_category(
        category_id: int,
        request: Request,
        db: Session = Depends(get_db),
        username: str = Depends(verify_admin)
):
    category = db.query(models.Category).filter(models.Category.id == category_id).first()
    if not category:
        raise HTTPException(status_code=404, detail="Категория не найдена")

    try:
        db.delete(category)
        db.commit()
        return RedirectResponse(url="/admin/categories", status_code=303)
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=400,
            detail=f"Ошибка при удалении категории: {str(e)}"
        )

@app.get("/admin/edit-category/{category_id}", response_class=HTMLResponse)
def edit_category_form(
        category_id: int,
        request: Request,
        db: Session = Depends(get_db),
        username: str = Depends(verify_admin)
):
    category = db.query(models.Category).filter(models.Category.id == category_id).first()
    if not category:
        raise HTTPException(status_code=404, detail="Категория не найдена")

    return templates.TemplateResponse(
        "admin/edit_category.html",
        {
            "request": request,
            "category": category
        }
    )

@app.post("/admin/update-category/{category_id}")
async def update_category(
        category_id: int,
        request: Request,
        display_name: str = Form(...),
        display_order: int = Form(...),
        db: Session = Depends(get_db),
        username: str = Depends(verify_admin)
):
    category = db.query(models.Category).filter(models.Category.id == category_id).first()
    if not category:
        raise HTTPException(status_code=404, detail="Категория не найдена")

    try:
        category.display_name = display_name
        category.display_order = display_order
        db.commit()
        return RedirectResponse(url="/admin/categories", status_code=303)
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=400,
            detail=f"Ошибка при обновлении категории: {str(e)}"
        )






# Форма оформления заказа
@app.get("/checkout", response_class=HTMLResponse)
def checkout_form(request: Request):
    return templates.TemplateResponse(
        "checkout.html",
        {
            "request": request
        }
    )


# Функция отправки почты
async def send_order_email(email_to: EmailStr, order_data: dict):
    message = MessageSchema(
        subject=f"Новый заказ №{order_data['order_id']}",
        recipients=[email_to],
        body=f"""
        Новый заказ на сайте Tea High!

        Детали заказа:
        - Номер: {order_data['order_id']}
        - Телефон: {order_data['phone']}
        - Telegram: {order_data['telegram']}
        - Комментарий: {order_data['comment'] or 'Нет комментария'}
        - Сумма: {order_data['total_price']} ₽
        - Дата: {order_data['created_at']}

        Товары:
        {order_data['products']}
        """,
        subtype="plain"
    )

    fm = FastMail(conf)
    await fm.send_message(message)


# Обработка оформления заказа
@app.post("/process-checkout")
async def process_checkout(
        background_tasks: BackgroundTasks,
        request: Request,
        phone: str = Form(...),
        telegram: str = Form(...),
        comment: Optional[str] = Form(None),
        db: Session = Depends(get_db)
):

    # Получаем товары из корзины
    session_id = request.cookies.get("session_id")
    if not session_id:
        return RedirectResponse(url="/cart", status_code=303)

    cart_items = db.query(models.CartItem).filter(
        models.CartItem.session_id == session_id
    ).all()

    if not cart_items:
        return RedirectResponse(url="/cart", status_code=303)

    # Создаем заказы для каждого товара
    products_info = []
    total = 0
    last_order = None

    for item in cart_items:
        product = db.query(models.Product).filter(models.Product.id == item.product_id).first()
        if not product:
            continue

        order = models.Order(
            product_id=product.id,
            quantity=item.quantity,
            total_price=product.price * item.quantity,
            phone=phone,
            telegram=telegram,
            comment=comment
        )
        db.add(order)
        products_info.append(f"- {product.name} x{item.quantity} = {product.price * item.quantity} ₽")
        total += product.price * item.quantity
        last_order = order

    db.commit()

    # Очищаем корзину
    db.query(models.CartItem).filter(models.CartItem.session_id == session_id).delete()
    db.commit()

    if not last_order:
        raise HTTPException(status_code=400, detail="Не удалось создать заказ")

    # Подготовка данных для письма
    order_data = {
        "order_id": last_order.id,
        "phone": phone,
        "telegram": telegram,
        "comment": comment,
        "total_price": total,
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "products": "\n".join(products_info)
    }

    # Отправка письма в фоне
    background_tasks.add_task(
        send_order_email,
        email_to="teahighshop@mail.ru",
        order_data=order_data
    )

    return RedirectResponse(url=f"/order-success/{last_order.id}", status_code=303)


# Страница успешного оформления
@app.get("/order-success/{order_id}", response_class=HTMLResponse)
def order_success(
        order_id: int,
        request: Request,
        db: Session = Depends(get_db)
):



    order = db.query(models.Order).filter(models.Order.id == order_id).first()

    if not order:
        raise HTTPException(status_code=404, detail="Заказ не найден")

    return templates.TemplateResponse(
        "order_success.html",
        {
            "request": request,
            "order": order
        }
    )

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )