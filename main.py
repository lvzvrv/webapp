from fastapi import FastAPI, Request, Depends, Form, status, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
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

    token = request.cookies.get("Authorization")
    user = None
    if token:
        user, token = check_session(request, db)
        user = db.query(models.User).filter(models.User.username == token).first()
    return templates.TemplateResponse("index.html", {"request": request, "products": products, "user": user})


# Админ-панель
@app.get("/admin", response_class=HTMLResponse)
def admin_panel(request: Request, username: str = Depends(verify_admin), db: Session = Depends(get_db)):
    products = db.query(models.Product).all()
    for product in products:
        product.images = product._get_image_urls(db)
    return templates.TemplateResponse("admin/admin_panel.html", {"request": request, "products": products})


@app.get("/admin/add-product", response_class=HTMLResponse)
def add_product_form(request: Request, username: str = Depends(verify_admin)):
    return templates.TemplateResponse("admin/add_product.html", {"request": request})


@app.post("/admin/add-product")
async def add_product(
        request: Request,
        product_id: int = Form(...),
        name: str = Form(...),
        small_description: str = Form(...),
        description: str = Form(...),
        price: float = Form(...),
        image_urls: str = Form(...),
        db: Session = Depends(get_db),
        username: str = Depends(verify_admin)
):
    try:
        # Проверяем существование товара с таким ID
        if db.query(models.Product).filter(models.Product.id == product_id).first():
            return templates.TemplateResponse(
                "admin/add_product.html",
                {
                    "request": request,
                    "error": f"Товар с ID {product_id} уже существует"
                }
            )

        # Создаем новый продукт
        product = models.Product(
            id=product_id,
            name=name,
            small_description=small_description,
            description=description,
            price=price,
            type="tea"  # Указываем тип по умолчанию
        )

        db.add(product)
        db.commit()
        db.refresh(product)

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
        return templates.TemplateResponse(
            "admin/add_product.html",
            {
                "request": request,
                "error": f"Ошибка при добавлении товара: {str(e)}"
            }
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
def product_details(
        product_id: int,
        request: Request,
        db: Session = Depends(get_db)
):
    product = db.query(models.Product).filter(models.Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Товар не найден")

    # Получаем изображения для товара
    product.images = product._get_image_urls(db)

    return templates.TemplateResponse(
        "product_details.html",
        {
            "request": request,
            "product": product
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

@app.get("/logout")
def logout(request: Request, db: Session = Depends(get_db)):
    token = request.cookies.get("Authorization")
    if token:
        check_session(request, db)
        response = RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)
        response.delete_cookie(key="Authorization")
        return response


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )