from fastapi import FastAPI, Request, Depends, Form, status, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from app.database import engine, SessionLocal
from app import models, auth
from app.models import Base
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from app.auth import get_auth_token, check_cookies
from fastapi.security import HTTPBasic, HTTPBasicCredentials
import secrets
import uuid
import os

Base.metadata.create_all(bind=engine)

limiter = Limiter(key_func=get_remote_address)
app = FastAPI()
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

templates = Jinja2Templates(directory="app/templates")

# Конфигурация админ-панели
ADMIN_USERNAME = os.getenv('ADMIN_USERNAME')
ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD')  # В реальном проекте используйте переменные окружения
security = HTTPBasic()


def get_cart_items_count(db: Session, session_id: str) -> int:
    if not session_id:
        return 0
    try:
        return db.query(models.CartItem).filter(
            models.CartItem.session_id == session_id
        ).count()
    except Exception as e:
        print(f"Error getting cart items count: {e}")
        return 0

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


def check_session(request: Request, db: Session = Depends(get_db)):
    token = check_cookies(request.cookies.get("Authorization"))
    if not token:
        raise HTTPException(
            status_code=status.HTTP_302_FOUND,
            detail='Unauthorized',
            headers={"Location": "/login"},
        )
    user = db.query(models.User).filter(models.User.username == token).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_302_FOUND,
            detail='Unauthorized',
            headers={"Location": "/login"},
        )
    return user, token


@app.get("/", response_class=HTMLResponse)
def index(request: Request, db: Session = Depends(get_db)):
    products = db.query(models.Product).all()
    for product in products:
        product.images = product._get_image_urls(db)

    session_id = request.cookies.get("session_id", "")
    cart_items_count = get_cart_items_count(db, session_id)

    token = request.cookies.get("Authorization")
    user = None
    if token:
        user, token = check_session(request, db)
        user = db.query(models.User).filter(models.User.username == token).first()

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "products": products,
            "user": user,
            "cart_items_count": cart_items_count  # Добавлено
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
    cart_items_count = get_cart_items_count(db, session_id)

    return templates.TemplateResponse(
        "admin/admin_panel.html",
        {
            "request": request,
            "products": products,
            "cart_items_count": cart_items_count  # Добавлено
        }
    )


@app.get("/admin/add-product", response_class=HTMLResponse)
def add_product_form(
        request: Request,
        db: Session = Depends(get_db),
        username: str = Depends(verify_admin)
):
    session_id = request.cookies.get("session_id", "")
    cart_items_count = get_cart_items_count(db, session_id)

    return templates.TemplateResponse(
        "admin/add_product.html",
        {
            "request": request,
            "cart_items_count": cart_items_count  # Добавлено
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
@app.get("/profile")
def profile(request: Request, result=Depends(check_session)):
    user = result[0]
    return templates.TemplateResponse("profile.html", {"request": request, "user": user})


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


@app.get("/orders")
def list_orders(request: Request, db: Session = Depends(get_db), result=Depends(check_session)):
    user = result[0]
    orders = db.query(models.Order).filter(models.Order.user_id == user.id).all()
    for order in orders:
        product = db.query(models.Product).filter(models.Product.id == order.product_id).first()
        order.product = product

    return templates.TemplateResponse("orders.html", {"request": request, "orders": orders, "user": user})


@app.post("/buy")
def buy_product(request: Request, product_id: int = Form(...), db: Session = Depends(get_db),
                result=Depends(check_session)):
    user = result[0]
    product = db.query(models.Product).filter(models.Product.id == product_id).first()
    if not product or product_id == 0:
        return templates.TemplateResponse("error.html",
                                          {"request": request, "message": "Товар не найден", "user": user})

    if user.balance < product.price:
        return templates.TemplateResponse("error.html",
                                          {"request": request, "message": "Недостаточно средств", "user": user})

    order = models.Order(
        user_id=user.id,
        product_id=product.id,
        quantity=1,
        total_price=product.price
    )
    db.add(order)
    user.balance -= product.price
    db.commit()

    return RedirectResponse(url=f"/order/{order.id}", status_code=status.HTTP_302_FOUND)


@app.get("/product/{product_id}", response_class=HTMLResponse)
def product_details(product_id: int, request: Request, db: Session = Depends(get_db)):
    product = db.query(models.Product).filter(models.Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Товар не найден")

    product.images = product._get_image_urls(db)
    session_id = request.cookies.get("session_id", "")
    cart_items_count = get_cart_items_count(db, session_id)

    return templates.TemplateResponse(
        "product_details.html",
        {
            "request": request,
            "product": product,
            "cart_items_count": cart_items_count  # Добавлено
        }
    )

@app.get("/order/{order_id}")
@limiter.limit("2/second")
def view_order(request: Request, order_id: int, db: Session = Depends(get_db), result=Depends(check_session)):
    user = result[0]
    order = db.query(models.Order).filter(models.Order.id == order_id).first()
    if not order:
        return templates.TemplateResponse("error.html",
                                          {"request": request, "message": "Заказ не найден", "user": user})

    product = db.query(models.Product).filter(models.Product.id == order.product_id).first()
    order.product = product

    return templates.TemplateResponse("order.html", {"request": request, "order": order, "user": user})


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
        quantity: int = Form(1),  # Добавлен параметр количества
        db: Session = Depends(get_db)
):
    # Получаем или создаем идентификатор сессии
    session_id = request.cookies.get("session_id", str(uuid.uuid4()))

    # Проверяем существование товара
    product = db.query(models.Product).filter(models.Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Товар не найден")

    # Проверяем, есть ли уже такой товар в корзине
    cart_item = db.query(models.CartItem).filter(
        models.CartItem.session_id == session_id,
        models.CartItem.product_id == product_id
    ).first()

    if cart_item:
        cart_item.quantity += quantity  # Увеличиваем количество на указанное значение
    else:
        cart_item = models.CartItem(
            session_id=session_id,
            product_id=product_id,
            quantity=quantity
        )
        db.add(cart_item)

    db.commit()

    response = RedirectResponse(url="/cart", status_code=status.HTTP_303_SEE_OTHER)
    if not request.cookies.get("session_id"):
        response.set_cookie(key="session_id", value=session_id, httponly=True)
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
    if not session_id:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

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
    if not session_id:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

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

    return RedirectResponse(url="/orders", status_code=status.HTTP_303_SEE_OTHER)

@app.get("/logout")
def logout(request: Request, db: Session = Depends(get_db)):
    token = request.cookies.get("Authorization")
    if token:
        check_session(request, db)
        response = RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)
        response.delete_cookie(key="Authorization")
        return response
