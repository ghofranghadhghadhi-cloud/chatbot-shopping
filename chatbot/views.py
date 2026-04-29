# views.py
import json
import os
from dotenv import load_dotenv
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from openai import OpenAI

# ── Load environment variables ─────────────────────────
load_dotenv()

# ── Secure Groq AI client ─────────────────────────────
client = OpenAI(
    api_key=os.getenv("GROQ_API_KEY"),
    base_url="https://api.groq.com/openai/v1"
)

# ── Products ─────────────────────────────────────────
PRODUCTS = [
    {"id": 1, "name": "iPhone 15 Pro",      "price": 999,  "category": "phones",     "stock": 10},
    {"id": 2, "name": "Samsung Galaxy S24", "price": 849,  "category": "phones",     "stock": 5},
    {"id": 3, "name": "MacBook Air M3",     "price": 1299, "category": "laptops",    "stock": 3},
    {"id": 4, "name": "Dell XPS 15",        "price": 1099, "category": "laptops",    "stock": 7},
    {"id": 5, "name": "Sony WH-1000XM5",    "price": 349,  "category": "headphones", "stock": 15},
    {"id": 6, "name": "AirPods Pro",        "price": 249,  "category": "headphones", "stock": 20},
    {"id": 7, "name": "iPad Pro 12.9",      "price": 1099, "category": "tablets",    "stock": 8},
    {"id": 8, "name": "Nike Air Max 270",   "price": 150,  "category": "shoes",      "stock": 25},
    {"id": 9, "name": "Apple Watch Series 9", "price": 399, "category": "wearables", "stock": 12},
    {"id": 10, "name": "HP Pavilion 14", "price": 750, "category": "laptops", "stock": 6},
    {"id": 11, "name": "Logitech MX Master 3S", "price": 120, "category": "accessories", "stock": 20},
    {"id": 12, "name": "Samsung Galaxy Tab S9", "price": 899, "category": "tablets", "stock": 9},
]

cart = {}


# ── CORS helper ───────────────────────────────────────
def cors(response):
    response["Access-Control-Allow-Origin"] = "*"
    response["Access-Control-Allow-Headers"] = "Content-Type"
    response["Access-Control-Allow-Credentials"] = "true"
    return response


def options_response():
    r = JsonResponse({})
    return cors(r)


# ── Auth views ────────────────────────────────────────
@csrf_exempt
@require_http_methods(["POST", "OPTIONS"])
def register(request):
    if request.method == "OPTIONS":
        return options_response()
    try:
        data = json.loads(request.body)
        username = data.get("username", "").strip()
        password = data.get("password", "").strip()
        email = data.get("email", "").strip()

        if not username or not password:
            return cors(JsonResponse({"error": "Username and password are required."}, status=400))

        if len(username) < 3:
            return cors(JsonResponse({"error": "Username must be at least 3 characters."}, status=400))

        if len(password) < 6:
            return cors(JsonResponse({"error": "Password must be at least 6 characters."}, status=400))

        if User.objects.filter(username=username).exists():
            return cors(JsonResponse({"error": "Username already taken."}, status=400))

        user = User.objects.create_user(username=username, password=password, email=email)
        return cors(JsonResponse({
            "success": True,
            "message": f"Account created! Welcome, {username} 🎉",
            "username": username
        }))
    except Exception as e:
        return cors(JsonResponse({"error": str(e)}, status=500))


@csrf_exempt
@require_http_methods(["POST", "OPTIONS"])
def login_view(request):
    if request.method == "OPTIONS":
        return options_response()
    try:
        data = json.loads(request.body)
        username = data.get("username", "").strip()
        password = data.get("password", "").strip()

        if not username or not password:
            return cors(JsonResponse({"error": "Username and password are required."}, status=400))

        user = authenticate(request, username=username, password=password)
        if user is not None:
            return cors(JsonResponse({
                "success": True,
                "message": f"Welcome back, {username}! 👋",
                "username": username
            }))
        else:
            return cors(JsonResponse({"error": "Invalid username or password."}, status=401))
    except Exception as e:
        return cors(JsonResponse({"error": str(e)}, status=500))


@csrf_exempt
@require_http_methods(["POST", "OPTIONS"])
def logout_view(request):
    if request.method == "OPTIONS":
        return options_response()
    logout(request)
    return cors(JsonResponse({"success": True, "message": "Logged out."}))


# ── AI helper ────────────────────────────────────────
def ask_ai(user_message, cart_contents):
    products_info = "\n".join([
        f"ID:{p['id']} | {p['name']} | ${p['price']} | {p['category']} | stock:{p['stock']}"
        for p in PRODUCTS
    ])
    cart_info = (
        "Empty"
        if not cart_contents
        else ", ".join([f"{PRODUCTS[int(pid)-1]['name']} x{qty}" for pid, qty in cart_contents.items()])
    )

    system_prompt = f"""You are ShopBot, an AI shopping assistant. 
Available products:
{products_info}
Current cart: {cart_info}
Respond ONLY with JSON:
{{
  "intent": "greeting|search|add_to_cart|remove_from_cart|view_cart|checkout|price_query|help|farewell|unknown",
  "message": "response",
  "category": "phones|laptops|headphones|tablets|shoes|null",
  "product_id": null or number,
  "show_products": true or false
}}"""

    response = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message}
        ],
        temperature=0.7,
        max_tokens=500
    )

    raw = response.choices[0].message.content.strip()
    if "```" in raw:
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return json.loads(raw.strip())


# ── Generate response ─────────────────────────────────
def generate_response(message, session_cart):
    try:
        ai = ask_ai(message, session_cart)
    except Exception:
        return {"message": "🤔 Try: 'show phones' or 'help'", "intent": "unknown", "products": []}

    intent = ai.get("intent", "unknown")
    bot_message = ai.get("message", "")
    category = ai.get("category")
    product_id = ai.get("product_id")
    show_products = ai.get("show_products", False)

    products = (
        PRODUCTS if show_products and (category is None or category == "null")
        else [p for p in PRODUCTS if p["category"] == category] if show_products
        else []
    )

    if intent == "add_to_cart" and product_id:
        pid = str(product_id)
        session_cart[pid] = session_cart.get(pid, 0) + 1

    if intent == "remove_from_cart" and product_id:
        pid = str(product_id)
        if pid in session_cart:
            del session_cart[pid]

    if intent == "checkout":
        session_cart.clear()

    return {
        "message": bot_message,
        "intent": intent,
        "products": products,
        "cart_count": sum(session_cart.values())
    }


# ── Django Chat API ───────────────────────────────────
@csrf_exempt
@require_http_methods(["POST", "OPTIONS"])
def chat(request):
    if request.method == "OPTIONS":
        return options_response()
    data = json.loads(request.body)
    message = data.get("message", "").strip()
    session_id = data.get("session_id", "default")
    if session_id not in cart:
        cart[session_id] = {}
    response_data = generate_response(message, cart[session_id])
    response_data["session_id"] = session_id
    return cors(JsonResponse(response_data))


@require_http_methods(["GET"])
def products_view(request):
    category = request.GET.get("category", None)
    result = PRODUCTS if not category else [p for p in PRODUCTS if p["category"] == category]
    return cors(JsonResponse({"products": result}))
