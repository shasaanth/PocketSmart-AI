import hashlib
import hmac
import json
import os
import secrets
from datetime import datetime
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, Request, Form, File, UploadFile
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from gemini_utils import generate_recommendation


# ============================================================
# CONFIGURATION
# ============================================================

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent

DATA_DIR = BASE_DIR / "data"
UPLOAD_DIR = BASE_DIR / "static" / "uploads"

DATA_DIR.mkdir(exist_ok=True)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

USERS_FILE = DATA_DIR / "users.json"
HISTORY_FILE = DATA_DIR / "history.json"

SESSION_SECRET = os.getenv(
    "SESSION_SECRET",
    "pocketsmart-development-secret-change-this"
)


# ============================================================
# INITIALIZE DATA FILES
# ============================================================

if not USERS_FILE.exists():
    USERS_FILE.write_text("{}", encoding="utf-8")

if not HISTORY_FILE.exists():
    HISTORY_FILE.write_text("[]", encoding="utf-8")


# ============================================================
# FASTAPI APPLICATION
# ============================================================

app = FastAPI(
    title="PocketSmart AI",
    description="Smart Budget and Recommendation Assistant"
)

app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET,
    max_age=60 * 60 * 24 * 7
)

app.mount(
    "/static",
    StaticFiles(directory="static"),
    name="static"
)

templates = Jinja2Templates(
    directory="templates"
)


# ============================================================
# JSON FUNCTIONS
# ============================================================

def load_json(file_path, default):

    try:

        with open(
            file_path,
            "r",
            encoding="utf-8"
        ) as file:

            return json.load(file)

    except (
        FileNotFoundError,
        json.JSONDecodeError,
        TypeError
    ):

        return default


def save_json(file_path, data):

    with open(
        file_path,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            data,
            file,
            indent=4,
            ensure_ascii=False
        )


# ============================================================
# PASSWORD SECURITY
# ============================================================

def hash_password(password):

    salt = secrets.token_bytes(16)

    password_hash = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        120000
    )

    return (
        salt.hex(),
        password_hash.hex()
    )


def verify_password(
    password,
    salt_hex,
    hash_hex
):

    salt = bytes.fromhex(salt_hex)

    password_hash = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        120000
    )

    return hmac.compare_digest(
        password_hash.hex(),
        hash_hex
    )


# ============================================================
# SESSION FUNCTIONS
# ============================================================

def current_user(request: Request):

    return request.session.get("user")


def require_login(request: Request):

    if not current_user(request):

        return RedirectResponse(
            "/login",
            status_code=303
        )

    return None


def page_context(
    request: Request,
    **kwargs
):

    context = {
        "request": request,
        "user": current_user(request)
    }

    context.update(kwargs)

    return context


# ============================================================
# BUDGET ALLOCATION
# ============================================================

def create_budget_plan(
    planner,
    budget
):

    budget = float(budget)

    if planner == "Home Interior":

        items = [
            ("Furniture", 0.35),
            ("Lighting", 0.15),
            ("Decor & Curtains", 0.15),
            ("Painting / Wall Treatment", 0.15),
            ("Installation", 0.10),
            ("Contingency", 0.10)
        ]

    elif planner == "Party":

        items = [
            ("Food & Beverages", 0.45),
            ("Venue", 0.15),
            ("Decoration", 0.15),
            ("Entertainment", 0.10),
            ("Invitations", 0.05),
            ("Contingency", 0.10)
        ]

    else:

        items = [
            ("Jewelry", 0.75),
            ("Making / Crafting", 0.10),
            ("Packaging", 0.05),
            ("Care / Maintenance", 0.05),
            ("Contingency", 0.05)
        ]

    breakdown = []

    for name, percentage in items:

        amount = round(
            budget * percentage,
            2
        )

        breakdown.append(
            {
                "name": name,
                "percentage": int(
                    percentage * 100
                ),
                "amount": amount
            }
        )

    return {
        "breakdown": breakdown,
        "estimated_total": budget,
        "remaining": 0
    }


# ============================================================
# IMAGE HANDLING
# ============================================================

ALLOWED_IMAGE_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp"
}

MAX_IMAGE_SIZE = 5 * 1024 * 1024


async def process_image(image: Optional[UploadFile]):

    if not image or not image.filename:

        return None, None, None

    if image.content_type not in ALLOWED_IMAGE_TYPES:

        raise ValueError(
            "Only JPG, PNG and WEBP images are supported."
        )

    image_bytes = await image.read()

    if len(image_bytes) > MAX_IMAGE_SIZE:

        raise ValueError(
            "Image size must be less than 5 MB."
        )

    extension = {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp"
    }.get(
        image.content_type,
        ".jpg"
    )

    safe_name = (
        secrets.token_hex(12)
        + extension
    )

    save_path = (
        UPLOAD_DIR / safe_name
    )

    with open(
        save_path,
        "wb"
    ) as file:

        file.write(image_bytes)

    image_url = (
        "/static/uploads/"
        + safe_name
    )

    return (
        image_bytes,
        image.content_type,
        image_url
    )


# ============================================================
# SAVE HISTORY
# ============================================================

def save_history(
    email,
    planner,
    details,
    recommendation,
    budget,
    estimated_total,
    image_url=None
):

    history = load_json(
        HISTORY_FILE,
        []
    )

    # IMPORTANT:
    # Make sure history is always a LIST.
    # This prevents:
    # 'dict' object has no attribute 'insert'
    if not isinstance(history, list):

        history = []

    history.insert(
        0,
        {
            "id": secrets.token_hex(8),

            "email": email,

            "planner": planner,

            "date": datetime.now().strftime(
                "%d-%m-%Y %I:%M %p"
            ),

            "budget": budget,

            "estimated_total": estimated_total,

            "remaining": round(
                max(
                    0,
                    budget - estimated_total
                ),
                2
            ),

            "details": details,

            "recommendation": recommendation,

            "image_url": image_url
        }
    )

    # Keep latest 100 recommendations
    history = history[:100]

    save_json(
        HISTORY_FILE,
        history
    )


# ============================================================
# HOME PAGE
# ============================================================

@app.get("/")
async def home(request: Request):

    return templates.TemplateResponse(
        "index.html",
        page_context(request)
    )


# ============================================================
# REGISTER
# ============================================================

@app.get("/register")
async def register_page(request: Request):

    if current_user(request):

        return RedirectResponse(
            "/dashboard",
            status_code=303
        )

    return templates.TemplateResponse(
        "register.html",
        page_context(request)
    )


@app.post("/register")
async def register(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...)
):

    name = name.strip()

    email = email.strip().lower()

    if len(name) < 2:

        return templates.TemplateResponse(
            "register.html",
            page_context(
                request,
                error="Please enter a valid name."
            )
        )

    if len(password) < 6:

        return templates.TemplateResponse(
            "register.html",
            page_context(
                request,
                error=(
                    "Password must contain at least "
                    "6 characters."
                )
            )
        )

    if password != confirm_password:

        return templates.TemplateResponse(
            "register.html",
            page_context(
                request,
                error="Passwords do not match."
            )
        )

    users = load_json(
        USERS_FILE,
        {}
    )

    # Make sure users is a dictionary
    if not isinstance(users, dict):

        users = {}

    if email in users:

        return templates.TemplateResponse(
            "register.html",
            page_context(
                request,
                error=(
                    "An account with this email "
                    "already exists."
                )
            )
        )

    salt, password_hash = hash_password(
        password
    )

    users[email] = {
        "name": name,
        "email": email,
        "salt": salt,
        "password_hash": password_hash
    }

    save_json(
        USERS_FILE,
        users
    )

    request.session["user"] = {
        "name": name,
        "email": email
    }

    return RedirectResponse(
        "/dashboard",
        status_code=303
    )


# ============================================================
# LOGIN
# ============================================================

@app.get("/login")
async def login_page(request: Request):

    if current_user(request):

        return RedirectResponse(
            "/dashboard",
            status_code=303
        )

    return templates.TemplateResponse(
        "login.html",
        page_context(request)
    )


@app.post("/login")
async def login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...)
):

    email = email.strip().lower()

    users = load_json(
        USERS_FILE,
        {}
    )

    if not isinstance(users, dict):

        users = {}

    user = users.get(email)

    if not user:

        return templates.TemplateResponse(
            "login.html",
            page_context(
                request,
                error="Invalid email or password."
            )
        )

    try:

        valid = verify_password(
            password,
            user["salt"],
            user["password_hash"]
        )

    except (
        KeyError,
        ValueError,
        TypeError
    ):

        valid = False

    if not valid:

        return templates.TemplateResponse(
            "login.html",
            page_context(
                request,
                error="Invalid email or password."
            )
        )

    request.session["user"] = {
        "name": user["name"],
        "email": user["email"]
    }

    return RedirectResponse(
        "/dashboard",
        status_code=303
    )


# ============================================================
# LOGOUT
# ============================================================

@app.get("/logout")
async def logout(request: Request):

    request.session.clear()

    return RedirectResponse(
        "/",
        status_code=303
    )


# ============================================================
# DASHBOARD
# ============================================================

@app.get("/dashboard")
async def dashboard(request: Request):

    redirect = require_login(request)

    if redirect:

        return redirect

    return templates.TemplateResponse(
        "dashboard.html",
        page_context(request)
    )


# ============================================================
# PLANNER PAGES
# ============================================================

@app.get("/home-planner")
async def home_planner(request: Request):

    redirect = require_login(request)

    if redirect:

        return redirect

    return templates.TemplateResponse(
        "planner.html",
        page_context(
            request,
            planner="Home Interior"
        )
    )


@app.get("/party-planner")
async def party_planner(request: Request):

    redirect = require_login(request)

    if redirect:

        return redirect

    return templates.TemplateResponse(
        "planner.html",
        page_context(
            request,
            planner="Party"
        )
    )


@app.get("/jewelry-planner")
async def jewelry_planner(request: Request):

    redirect = require_login(request)

    if redirect:

        return redirect

    return templates.TemplateResponse(
        "planner.html",
        page_context(
            request,
            planner="Jewelry"
        )
    )


# ============================================================
# HOME GENERATION
# ============================================================

@app.post("/generate-home")
async def generate_home(
    request: Request,
    budget: float = Form(...),
    room: str = Form(...),
    lights: int = Form(0),
    fans: int = Form(0),
    furniture: str = Form(""),
    style: str = Form("Modern"),
    requirements: str = Form(""),
    image: Optional[UploadFile] = File(None)
):

    return await generate_plan(
        request=request,
        planner="Home Interior",
        budget=budget,
        fields={
            "room": room,
            "lights": lights,
            "fans": fans,
            "furniture": furniture,
            "style": style,
            "requirements": requirements
        },
        image=image
    )


# ============================================================
# PARTY GENERATION
# ============================================================

@app.post("/generate-party")
async def generate_party(
    request: Request,
    budget: float = Form(...),
    guests: int = Form(...),
    event_type: str = Form(...),
    venue: str = Form(""),
    requirements: str = Form(""),
    image: Optional[UploadFile] = File(None)
):

    return await generate_plan(
        request=request,
        planner="Party",
        budget=budget,
        fields={
            "guests": guests,
            "event_type": event_type,
            "venue": venue,
            "requirements": requirements
        },
        image=image
    )


# ============================================================
# JEWELRY GENERATION
# ============================================================

@app.post("/generate-jewelry")
async def generate_jewelry(
    request: Request,
    budget: float = Form(...),
    occasion: str = Form(...),
    style: str = Form(...),
    requirements: str = Form(""),
    image: Optional[UploadFile] = File(None)
):

    return await generate_plan(
        request=request,
        planner="Jewelry",
        budget=budget,
        fields={
            "occasion": occasion,
            "style": style,
            "requirements": requirements
        },
        image=image
    )


# ============================================================
# MAIN AI GENERATION
# ============================================================

async def generate_plan(
    request: Request,
    planner: str,
    budget: float,
    fields: dict,
    image: Optional[UploadFile]
):

    redirect = require_login(request)

    if redirect:

        return redirect

    if budget <= 0:

        return templates.TemplateResponse(
            "planner.html",
            page_context(
                request,
                planner=planner,
                error=(
                    "Budget must be greater than zero."
                )
            )
        )

    try:

        # ----------------------------------------------------
        # IMAGE
        # ----------------------------------------------------

        (
            image_bytes,
            mime_type,
            image_url
        ) = await process_image(image)


        # ----------------------------------------------------
        # BUDGET PLAN
        # ----------------------------------------------------

        budget_plan = create_budget_plan(
            planner,
            budget
        )


        budget_text = "\n".join(
            [
                (
                    f"- {item['name']}: "
                    f"₹{item['amount']:,.0f} "
                    f"({item['percentage']}%)"
                )

                for item
                in budget_plan["breakdown"]
            ]
        )


        # ----------------------------------------------------
        # USER DETAILS
        # ----------------------------------------------------

        details_text = "\n".join(
            [
                f"{key}: {value}"

                for key, value
                in fields.items()

                if value not in ("", None)
            ]
        )


        # ----------------------------------------------------
        # GEMINI PROMPT
        # ----------------------------------------------------

        prompt = f"""
You are PocketSmart AI,
a smart budget and recommendation assistant.

Planner Type:
{planner}

USER REQUIREMENTS:
{details_text}

TOTAL USER BUDGET:
₹{budget:,.2f}

SUGGESTED BUDGET ALLOCATION:
{budget_text}

Create a personalized and practical recommendation.

IMPORTANT RULES:

1. Never recommend spending more than
   ₹{budget:,.2f}.

2. Use Indian Rupees.

3. Give realistic approximate costs.

4. Clearly separate recommendations
   from approximate prices.

5. Do not claim that a price is a live
   marketplace price.

6. If an image is attached, analyze it
   and use relevant visual observations.

7. Give practical alternatives when
   something is expensive.

8. Keep the response easy to understand.

FORMAT YOUR RESPONSE:

## 1. Personalized Plan

Give a short personalized plan.

## 2. Recommended Items

List important items and explain why
they are suitable.

## 3. Budget Breakdown

Use approximate INR amounts.

## 4. Alternatives

Give lower-cost alternatives.

## 5. Money-Saving Tips

Give practical suggestions.

## 6. Estimated Total

Give the estimated total planned spending.

## 7. Remaining Budget

Give the amount remaining from
₹{budget:,.2f}.

Do not exceed the user's budget.
"""


        # ----------------------------------------------------
        # CALL GEMINI
        # ----------------------------------------------------

        recommendation = generate_recommendation(
            prompt,
            image_bytes=image_bytes,
            mime_type=mime_type
        )


        # ----------------------------------------------------
        # BUDGET CALCULATION
        # ----------------------------------------------------

        estimated_total = (
            budget_plan["estimated_total"]
        )

        remaining_budget = round(
            max(
                0,
                budget - estimated_total
            ),
            2
        )


        # ----------------------------------------------------
        # SAVE HISTORY
        # ----------------------------------------------------

        save_history(
            email=current_user(request)["email"],
            planner=planner,
            details=fields,
            recommendation=recommendation,
            budget=budget,
            estimated_total=estimated_total,
            image_url=image_url
        )


        # ----------------------------------------------------
        # RESULTS PAGE
        # ----------------------------------------------------

        return templates.TemplateResponse(
            "results.html",
            page_context(
                request,
                planner=planner,
                budget=budget,
                fields=fields,
                recommendation=recommendation,
                budget_plan=budget_plan,
                remaining_budget=remaining_budget,
                image_url=image_url
            )
        )


    except ValueError as error:

        return templates.TemplateResponse(
            "planner.html",
            page_context(
                request,
                planner=planner,
                error=str(error)
            )
        )


    except Exception as error:

        return templates.TemplateResponse(
            "results.html",
            page_context(
                request,
                planner=planner,
                budget=budget,
                fields=fields,
                recommendation=(
                    "Gemini could not generate the "
                    "recommendation right now. "
                    "Please try again.\n\n"
                    f"Technical information: {str(error)}"
                ),
                budget_plan=create_budget_plan(
                    planner,
                    budget
                ),
                remaining_budget=0,
                image_url=None
            )
        )


# ============================================================
# HISTORY
# ============================================================

@app.get("/history")
async def history(request: Request):

    redirect = require_login(request)

    if redirect:

        return redirect

    email = current_user(request)["email"]

    all_history = load_json(
        HISTORY_FILE,
        []
    )

    # Make sure history is a list
    if not isinstance(all_history, list):

        all_history = []

    user_history = [
        item

        for item in all_history

        if item.get("email") == email
    ]

    return templates.TemplateResponse(
        "history.html",
        page_context(
            request,
            history=user_history
        )
    )


# ============================================================
# HEALTH CHECK
# ============================================================

@app.get("/health")
async def health():

    return {
        "status": "running",
        "application": "PocketSmart AI"
    }