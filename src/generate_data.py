"""ShopSphere synthetic source-data generator.

Creates relational CSV extracts in data/raw/ for later ETL development.
A small, configurable share of rows is intentionally dirty so a future
validation layer has realistic problems to catch.

Run from the project root:

    python src/generate_data.py
"""

from __future__ import annotations

import logging
import random
import sys
import time
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from faker import Faker

# Allow `python src/generate_data.py` and `python -m src.generate_data`.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.config import (  # noqa: E402
    AVG_ITEMS_PER_ORDER,
    DIRTY_DATA_RATE,
    HISTORICAL_END_DATE,
    HISTORICAL_START_DATE,
    LOG_DIR,
    LOG_LEVEL,
    MAX_ITEMS_PER_ORDER,
    NUM_CUSTOMERS,
    NUM_ORDERS,
    NUM_PRODUCTS,
    NUM_STORES,
    RANDOM_SEED,
    RAW_DATA_DIR,
    REJECTED_DATA_DIR,
)

# ---------------------------------------------------------------------------
# Reference data (business catalogs, not runtime configuration)
# ---------------------------------------------------------------------------

COUNTRY_PROFILES: dict[str, dict] = {
    "India": {
        "weight": 0.32,
        "currency": "INR",
        "phone_code": "91",
        "cities": [
            ("Mumbai", "Maharashtra", 19.0760, 72.8777),
            ("Delhi", "Delhi", 28.6139, 77.2090),
            ("Bengaluru", "Karnataka", 12.9716, 77.5946),
            ("Hyderabad", "Telangana", 17.3850, 78.4867),
            ("Chennai", "Tamil Nadu", 13.0827, 80.2707),
            ("Kolkata", "West Bengal", 22.5726, 88.3639),
            ("Pune", "Maharashtra", 18.5204, 73.8567),
            ("Ahmedabad", "Gujarat", 23.0225, 72.5714),
        ],
    },
    "United States": {
        "weight": 0.14,
        "currency": "USD",
        "phone_code": "1",
        "cities": [
            ("New York", "New York", 40.7128, -74.0060),
            ("Los Angeles", "California", 34.0522, -118.2437),
            ("Chicago", "Illinois", 41.8781, -87.6298),
            ("Houston", "Texas", 29.7604, -95.3698),
            ("Seattle", "Washington", 47.6062, -122.3321),
            ("Austin", "Texas", 30.2672, -97.7431),
        ],
    },
    "United Kingdom": {
        "weight": 0.08,
        "currency": "GBP",
        "phone_code": "44",
        "cities": [
            ("London", "England", 51.5074, -0.1278),
            ("Manchester", "England", 53.4808, -2.2426),
            ("Birmingham", "England", 52.4862, -1.8904),
            ("Edinburgh", "Scotland", 55.9533, -3.1883),
        ],
    },
    "United Arab Emirates": {
        "weight": 0.06,
        "currency": "AED",
        "phone_code": "971",
        "cities": [
            ("Dubai", "Dubai", 25.2048, 55.2708),
            ("Abu Dhabi", "Abu Dhabi", 24.4539, 54.3773),
            ("Sharjah", "Sharjah", 25.3463, 55.4209),
        ],
    },
    "Singapore": {
        "weight": 0.04,
        "currency": "SGD",
        "phone_code": "65",
        "cities": [
            ("Singapore", "Singapore", 1.3521, 103.8198),
        ],
    },
    "Australia": {
        "weight": 0.05,
        "currency": "AUD",
        "phone_code": "61",
        "cities": [
            ("Sydney", "New South Wales", -33.8688, 151.2093),
            ("Melbourne", "Victoria", -37.8136, 144.9631),
            ("Brisbane", "Queensland", -27.4698, 153.0251),
            ("Perth", "Western Australia", -31.9505, 115.8605),
        ],
    },
    "Canada": {
        "weight": 0.04,
        "currency": "CAD",
        "phone_code": "1",
        "cities": [
            ("Toronto", "Ontario", 43.6532, -79.3832),
            ("Vancouver", "British Columbia", 49.2827, -123.1207),
            ("Montreal", "Quebec", 45.5017, -73.5673),
            ("Calgary", "Alberta", 51.0447, -114.0719),
        ],
    },
    "Germany": {
        "weight": 0.05,
        "currency": "EUR",
        "phone_code": "49",
        "cities": [
            ("Berlin", "Berlin", 52.5200, 13.4050),
            ("Munich", "Bavaria", 48.1351, 11.5820),
            ("Hamburg", "Hamburg", 53.5511, 9.9937),
            ("Frankfurt", "Hesse", 50.1109, 8.6821),
        ],
    },
    "France": {
        "weight": 0.04,
        "currency": "EUR",
        "phone_code": "33",
        "cities": [
            ("Paris", "Ile-de-France", 48.8566, 2.3522),
            ("Lyon", "Auvergne-Rhone-Alpes", 45.7640, 4.8357),
            ("Marseille", "Provence-Alpes-Cote d'Azur", 43.2965, 5.3698),
        ],
    },
    "Japan": {
        "weight": 0.04,
        "currency": "JPY",
        "phone_code": "81",
        "cities": [
            ("Tokyo", "Tokyo", 35.6762, 139.6503),
            ("Osaka", "Osaka", 34.6937, 135.5023),
            ("Yokohama", "Kanagawa", 35.4437, 139.6380),
            ("Kyoto", "Kyoto", 35.0116, 135.7681),
        ],
    },
    "Saudi Arabia": {
        "weight": 0.03,
        "currency": "SAR",
        "phone_code": "966",
        "cities": [
            ("Riyadh", "Riyadh", 24.7136, 46.6753),
            ("Jeddah", "Makkah", 21.4858, 39.1925),
            ("Dammam", "Eastern Province", 26.4207, 50.0888),
        ],
    },
    "Malaysia": {
        "weight": 0.03,
        "currency": "MYR",
        "phone_code": "60",
        "cities": [
            ("Kuala Lumpur", "Federal Territory", 3.1390, 101.6869),
            ("Penang", "Penang", 5.4141, 100.3288),
            ("Johor Bahru", "Johor", 1.4927, 103.7414),
        ],
    },
    "New Zealand": {
        "weight": 0.02,
        "currency": "NZD",
        "phone_code": "64",
        "cities": [
            ("Auckland", "Auckland", -36.8485, 174.7633),
            ("Wellington", "Wellington", -41.2865, 174.7762),
            ("Christchurch", "Canterbury", -43.5321, 172.6362),
        ],
    },
    "Netherlands": {
        "weight": 0.03,
        "currency": "EUR",
        "phone_code": "31",
        "cities": [
            ("Amsterdam", "North Holland", 52.3676, 4.9041),
            ("Rotterdam", "South Holland", 51.9244, 4.4777),
            ("Utrecht", "Utrecht", 52.0907, 5.1214),
        ],
    },
    "Italy": {
        "weight": 0.03,
        "currency": "EUR",
        "phone_code": "39",
        "cities": [
            ("Rome", "Lazio", 41.9028, 12.4964),
            ("Milan", "Lombardy", 45.4642, 9.1900),
            ("Naples", "Campania", 40.8518, 14.2681),
            ("Florence", "Tuscany", 43.7696, 11.2558),
        ],
    },
}

COUNTRIES = list(COUNTRY_PROFILES.keys())
COUNTRY_WEIGHTS = np.array([COUNTRY_PROFILES[c]["weight"] for c in COUNTRIES], dtype=float)
COUNTRY_WEIGHTS = COUNTRY_WEIGHTS / COUNTRY_WEIGHTS.sum()

CUSTOMER_SEGMENTS = ["NEW", "REGULAR", "PREMIUM", "VIP", "WHOLESALE"]
CUSTOMER_SEGMENT_WEIGHTS = [0.22, 0.48, 0.18, 0.08, 0.04]

PRODUCT_CATALOG: dict[str, dict] = {
    "Electronics": {
        "subcategories": ["Smartphones", "Laptops", "Headphones", "Televisions", "Cameras"],
        "brands": ["Samsung", "Apple", "Sony", "Dell", "Xiaomi", "LG", "HP", "OnePlus"],
        "suppliers": ["GlobalTech Distributors", "Pacific Electronics Hub"],
        "price_range": (25.0, 1800.0),
    },
    "Groceries": {
        "subcategories": ["Staples", "Snacks", "Beverages", "Dairy", "Fresh Produce"],
        "brands": ["Nestle", "Amul", "PepsiCo", "Unilever", "ITC", "Britannia"],
        "suppliers": ["FreshBasket Wholesale", "Daily Harvest Supply"],
        "price_range": (0.80, 35.0),
    },
    "Fashion": {
        "subcategories": ["Men's Apparel", "Women's Apparel", "Footwear", "Accessories"],
        "brands": ["Nike", "Adidas", "Zara", "H&M", "Levi's", "Puma"],
        "suppliers": ["Urban Style Imports", "Apparel Alliance"],
        "price_range": (8.0, 220.0),
    },
    "Home & Kitchen": {
        "subcategories": ["Cookware", "Furniture", "Decor", "Storage", "Appliances"],
        "brands": ["IKEA", "Philips", "Prestige", "Bosch", "Hamilton Beach"],
        "suppliers": ["HomeLiving Wholesale", "KitchenPro Supply"],
        "price_range": (6.0, 450.0),
    },
    "Beauty & Personal Care": {
        "subcategories": ["Skincare", "Haircare", "Makeup", "Fragrance"],
        "brands": ["L'Oreal", "Nivea", "Dove", "Maybelline", "The Body Shop"],
        "suppliers": ["BeautyWorld Distributors", "GlowCare Supply"],
        "price_range": (3.0, 90.0),
    },
    "Sports & Fitness": {
        "subcategories": ["Gym Equipment", "Outdoor Sports", "Activewear", "Cycling"],
        "brands": ["Decathlon", "Nike", "Adidas", "Reebok", "Yonex"],
        "suppliers": ["ActiveLife Wholesale", "FitGear Supply"],
        "price_range": (10.0, 400.0),
    },
    "Books & Stationery": {
        "subcategories": ["Fiction", "Education", "Notebooks", "Office Supplies"],
        "brands": ["Penguin", "Oxford", "Classmate", "Pilot", "Staples"],
        "suppliers": ["PageTurn Distributors", "OfficeMart Supply"],
        "price_range": (2.0, 45.0),
    },
    "Toys & Games": {
        "subcategories": ["Action Figures", "Board Games", "Educational Toys", "Puzzles"],
        "brands": ["LEGO", "Hasbro", "Mattel", "Fisher-Price", "Hot Wheels"],
        "suppliers": ["PlayWorld Wholesale", "KidJoy Supply"],
        "price_range": (5.0, 150.0),
    },
    "Health & Wellness": {
        "subcategories": ["Vitamins", "Supplements", "First Aid", "Medical Devices"],
        "brands": ["Himalaya", "Nature's Bounty", "Omron", "Ensure", "Cetaphil"],
        "suppliers": ["WellnessHub Distributors", "CarePlus Supply"],
        "price_range": (4.0, 120.0),
    },
    "Pet Supplies": {
        "subcategories": ["Pet Food", "Toys", "Grooming", "Accessories"],
        "brands": ["Pedigree", "Royal Canin", "Whiskas", "Kong", "Hill's"],
        "suppliers": ["PawMart Wholesale", "PetCare Supply"],
        "price_range": (3.0, 80.0),
    },
}

STORE_TYPES = ["RETAIL_STORE", "DARK_STORE", "FULFILLMENT_CENTER"]
STORE_TYPE_WEIGHTS = [0.55, 0.30, 0.15]

SALES_CHANNELS = ["WEBSITE", "MOBILE_APP", "PHYSICAL_STORE", "QUICK_COMMERCE"]
SALES_CHANNEL_WEIGHTS = [0.34, 0.28, 0.22, 0.16]

CHANNEL_STORE_TYPE = {
    "WEBSITE": "FULFILLMENT_CENTER",
    "MOBILE_APP": "FULFILLMENT_CENTER",
    "PHYSICAL_STORE": "RETAIL_STORE",
    "QUICK_COMMERCE": "DARK_STORE",
}

ORDER_STATUSES = [
    "PENDING",
    "CONFIRMED",
    "PROCESSING",
    "SHIPPED",
    "DELIVERED",
    "CANCELLED",
    "RETURNED",
]
ORDER_STATUS_WEIGHTS = [0.04, 0.08, 0.10, 0.12, 0.52, 0.09, 0.05]

PAYMENT_METHODS = [
    "CREDIT_CARD",
    "DEBIT_CARD",
    "UPI",
    "NET_BANKING",
    "WALLET",
    "CASH",
    "PAYPAL",
]
PAYMENT_STATUSES = ["SUCCESS", "FAILED", "PENDING", "REFUNDED"]
DELIVERY_TYPES = ["STANDARD", "EXPRESS", "QUICK"]
DELIVERY_STATUSES = ["ASSIGNED", "IN_TRANSIT", "DELIVERED", "FAILED", "CANCELLED"]

# Approximate INR rates used as the midpoint of a synthetic random walk.
BASE_RATES_TO_INR = {
    "INR": 1.00,
    "USD": 83.50,
    "GBP": 106.20,
    "EUR": 90.40,
    "AED": 22.73,
    "SGD": 62.10,
    "AUD": 54.80,
    "CAD": 61.20,
    "JPY": 0.56,
    "SAR": 22.26,
    "MYR": 18.70,
    "NZD": 50.40,
}

NAME_SUFFIXES = ["Pro", "Lite", "Max", "Plus", "Essential", "Premium", "Classic", "Air", "Neo"]

logger = logging.getLogger("shopsphere.generate_data")


def setup_logging() -> None:
    """Write logs to the console and to logs/generate_data.log."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / "generate_data.log"
    formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")

    logger.handlers.clear()
    logger.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))
    logger.propagate = False

    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setFormatter(formatter)
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)


def seed_all(seed: int) -> tuple[np.random.Generator, Faker]:
    """Seed numpy, Python random, and Faker for reproducible output."""
    rng = np.random.default_rng(seed)
    random.seed(seed)
    faker = Faker()
    faker.seed_instance(seed)
    return rng, faker


def ensure_output_directories() -> None:
    """Create output folders if they do not already exist."""
    RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)
    REJECTED_DATA_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)


def choose_countries(rng: np.random.Generator, size: int) -> np.ndarray:
    """Sample countries using the configured market weights."""
    return rng.choice(COUNTRIES, size=size, p=COUNTRY_WEIGHTS)


def random_city(country: str, rng: np.random.Generator) -> tuple[str, str, float, float]:
    """Pick a city tuple (city, state, lat, lon) for a country."""
    cities = COUNTRY_PROFILES[country]["cities"]
    index = int(rng.integers(0, len(cities)))
    return cities[index]


def jitter_coordinate(value: float, rng: np.random.Generator, scale: float = 0.08) -> float:
    """Add a small offset so stores in the same city are not identical."""
    return round(float(value + rng.normal(0, scale)), 6)


def slug(text: str) -> str:
    """Lowercase identifier-safe fragment for emails."""
    return "".join(ch for ch in text.lower() if ch.isalnum())


def sample_dirty_indices(rng: np.random.Generator, n_rows: int, rate: float) -> np.ndarray:
    """Return a unique set of row positions to corrupt."""
    if n_rows == 0 or rate <= 0:
        return np.array([], dtype=int)
    n_dirty = max(1, int(round(n_rows * rate)))
    n_dirty = min(n_dirty, n_rows)
    return rng.choice(n_rows, size=n_dirty, replace=False)


def random_dates_between(
    rng: np.random.Generator,
    start: date,
    end: date,
    size: int,
    favor_recent: bool = False,
) -> list[date]:
    """Sample calendar dates in [start, end]."""
    span_days = (end - start).days
    if span_days < 0:
        raise ValueError("HISTORICAL_END_DATE must be on or after HISTORICAL_START_DATE")
    if span_days == 0:
        return [start] * size

    if favor_recent:
        weights = np.linspace(1.0, 2.2, span_days + 1)
        weights = weights / weights.sum()
        offsets = rng.choice(span_days + 1, size=size, p=weights)
    else:
        offsets = rng.integers(0, span_days + 1, size=size)
    return [start + timedelta(days=int(offset)) for offset in offsets]


# ---------------------------------------------------------------------------
# Entity generators
# ---------------------------------------------------------------------------

def generate_customers(n_customers: int, rng: np.random.Generator, faker: Faker) -> pd.DataFrame:
    """Build a customer master extract."""
    logger.info("Generating %s customers", n_customers)
    countries = choose_countries(rng, n_customers)
    signup_start = HISTORICAL_START_DATE - timedelta(days=365)
    signup_dates = random_dates_between(rng, signup_start, HISTORICAL_END_DATE, n_customers)
    segments = rng.choice(CUSTOMER_SEGMENTS, size=n_customers, p=CUSTOMER_SEGMENT_WEIGHTS)

    rows: list[dict] = []
    for i in range(n_customers):
        country = str(countries[i])
        city, state, _lat, _lon = random_city(country, rng)
        first_name = faker.first_name()
        last_name = faker.last_name()
        domain = rng.choice(
            ["gmail.com", "yahoo.com", "outlook.com", "hotmail.com", "icloud.com"]
        )
        email = f"{slug(first_name)}.{slug(last_name)}.{i:05d}@{domain}"
        phone_code = COUNTRY_PROFILES[country]["phone_code"]
        phone = f"+{phone_code}-{faker.numerify('##########')}"
        rows.append(
            {
                "customer_id": f"CUST-{i + 1:05d}",
                "first_name": first_name,
                "last_name": last_name,
                "email": email,
                "phone": phone,
                "city": city,
                "state": state,
                "country": country,
                "customer_segment": str(segments[i]),
                "signup_date": signup_dates[i].isoformat(),
            }
        )
    return pd.DataFrame(rows)


def generate_products(n_products: int, rng: np.random.Generator) -> pd.DataFrame:
    """Build a product catalog extract with valid prices and ratings."""
    logger.info("Generating %s products", n_products)
    categories = list(PRODUCT_CATALOG.keys())
    rows: list[dict] = []
    for i in range(n_products):
        category = str(rng.choice(categories))
        spec = PRODUCT_CATALOG[category]
        subcategory = str(rng.choice(spec["subcategories"]))
        brand = str(rng.choice(spec["brands"]))
        supplier = str(rng.choice(spec["suppliers"]))
        low, high = spec["price_range"]
        selling_price = round(float(rng.uniform(low, high)), 2)
        margin = float(rng.uniform(0.12, 0.45))
        unit_cost = round(max(0.01, selling_price * (1 - margin)), 2)
        if unit_cost > selling_price:
            unit_cost = selling_price
        rating = round(float(np.clip(rng.normal(4.1, 0.55), 1.0, 5.0)), 1)
        suffix = str(rng.choice(NAME_SUFFIXES))
        model_no = int(rng.integers(10, 999))
        product_name = f"{brand} {subcategory} {suffix} {model_no}"
        rows.append(
            {
                "product_id": f"PRD-{i + 1:05d}",
                "product_name": product_name,
                "category": category,
                "subcategory": subcategory,
                "brand": brand,
                "supplier": supplier,
                "unit_cost": unit_cost,
                "selling_price": selling_price,
                "product_rating": rating,
            }
        )
    return pd.DataFrame(rows)


def generate_stores(n_stores: int, rng: np.random.Generator) -> pd.DataFrame:
    """Build retail stores, dark stores, and fulfillment centers."""
    logger.info("Generating %s stores / fulfillment locations", n_stores)
    countries = choose_countries(rng, n_stores)
    # Weighted mix, but keep at least one of each type so small development
    # datasets still have online, store, and quick-commerce locations.
    n_fulfillment = max(1, int(round(n_stores * STORE_TYPE_WEIGHTS[2])))
    n_dark = max(1, int(round(n_stores * STORE_TYPE_WEIGHTS[1])))
    n_retail = n_stores - n_fulfillment - n_dark
    if n_retail < 1:
        n_retail = 1
        n_dark = max(1, n_dark - 1)
        n_fulfillment = n_stores - n_retail - n_dark
    store_types = np.array(
        ["RETAIL_STORE"] * n_retail
        + ["DARK_STORE"] * n_dark
        + ["FULFILLMENT_CENTER"] * n_fulfillment
    )
    rng.shuffle(store_types)
    opening_start = date(2016, 1, 1)
    opening_dates = random_dates_between(rng, opening_start, HISTORICAL_END_DATE, n_stores)

    type_labels = {
        "RETAIL_STORE": "Retail Store",
        "DARK_STORE": "Dark Store",
        "FULFILLMENT_CENTER": "Fulfillment Center",
    }
    rows: list[dict] = []
    for i in range(n_stores):
        country = str(countries[i])
        city, state, lat, lon = random_city(country, rng)
        store_type = str(store_types[i])
        store_name = f"ShopSphere {type_labels[store_type]} - {city} #{i + 1}"
        rows.append(
            {
                "store_id": f"STR-{i + 1:04d}",
                "store_name": store_name,
                "store_type": store_type,
                "country": country,
                "region": state,
                "city": city,
                "latitude": jitter_coordinate(lat, rng),
                "longitude": jitter_coordinate(lon, rng),
                "opening_date": opening_dates[i].isoformat(),
            }
        )
    return pd.DataFrame(rows)


def _build_store_lookup(stores: pd.DataFrame) -> dict[tuple, list[str]]:
    """Map (country, store_type) and store_type-only keys to store IDs."""
    lookup: dict[tuple, list[str]] = defaultdict(list)
    for row in stores.itertuples(index=False):
        lookup[(row.country, row.store_type)].append(row.store_id)
        lookup[(row.store_type,)].append(row.store_id)
    lookup[("ANY",)] = stores["store_id"].tolist()
    return lookup


def _pick_store_id(
    lookup: dict[tuple, list[str]],
    country: str,
    store_type: str,
    rng: np.random.Generator,
) -> str:
    pool = lookup.get((country, store_type)) or lookup.get((store_type,)) or lookup[("ANY",)]
    return str(pool[int(rng.integers(0, len(pool)))])


def generate_orders(
    n_orders: int,
    customers: pd.DataFrame,
    stores: pd.DataFrame,
    rng: np.random.Generator,
) -> pd.DataFrame:
    """Build orders linked to existing customers and stores."""
    logger.info("Generating %s orders", n_orders)
    customer_ids = customers["customer_id"].to_numpy()
    customer_countries = customers["country"].to_numpy()
    signup_dates = pd.to_datetime(customers["signup_date"]).to_numpy().astype("datetime64[D]")

    cust_idx = rng.integers(0, len(customers), size=n_orders)
    channels = rng.choice(SALES_CHANNELS, size=n_orders, p=SALES_CHANNEL_WEIGHTS)
    statuses = rng.choice(ORDER_STATUSES, size=n_orders, p=ORDER_STATUS_WEIGHTS)

    start = np.datetime64(HISTORICAL_START_DATE)
    end = np.datetime64(HISTORICAL_END_DATE)
    low = np.maximum(signup_dates[cust_idx], start)
    span = (end - low).astype(int)
    span = np.maximum(span, 0)
    offset = np.where(span > 0, rng.integers(0, np.maximum(span, 1)), 0)
    # When signup is after the window start, keep the order on/after signup.
    offset = np.minimum(offset, span)
    order_dates = (low + offset.astype("timedelta64[D]")).astype("datetime64[D]")

    store_lookup = _build_store_lookup(stores)
    store_ids: list[str] = []
    currencies: list[str] = []
    for i in range(n_orders):
        country = str(customer_countries[cust_idx[i]])
        preferred_type = CHANNEL_STORE_TYPE[str(channels[i])]
        store_ids.append(_pick_store_id(store_lookup, country, preferred_type, rng))
        currencies.append(COUNTRY_PROFILES[country]["currency"])

    return pd.DataFrame(
        {
            "order_id": [f"ORD-{i + 1:08d}" for i in range(n_orders)],
            "customer_id": customer_ids[cust_idx],
            "store_id": store_ids,
            "order_date": pd.to_datetime(order_dates).strftime("%Y-%m-%d"),
            "sales_channel": channels,
            "order_status": statuses,
            "currency": currencies,
            "order_total": 0.0,
        }
    )


def generate_order_items(
    orders: pd.DataFrame,
    products: pd.DataFrame,
    rng: np.random.Generator,
) -> pd.DataFrame:
    """Create one or more line items per order and realistic price variation."""
    n_orders = len(orders)
    lam = max(AVG_ITEMS_PER_ORDER, 1.0)
    n_items = np.clip(rng.poisson(lam, size=n_orders), 1, MAX_ITEMS_PER_ORDER)
    logger.info("Generating order items (about %.1f lines per order)", float(n_items.mean()))

    order_id_values = np.repeat(orders["order_id"].to_numpy(), n_items)
    n_rows = len(order_id_values)
    product_idx = rng.integers(0, len(products), size=n_rows)
    product_ids = products["product_id"].to_numpy()[product_idx]
    list_prices = products["selling_price"].to_numpy()[product_idx].astype(float)

    # Most lines use list price; a minority vary slightly (promo / local pricing).
    variation = rng.uniform(0.92, 1.08, size=n_rows)
    apply_variation = rng.random(n_rows) < 0.18
    unit_price = np.where(apply_variation, list_prices * variation, list_prices)
    unit_price = np.round(np.maximum(unit_price, 0.01), 2)

    quantity = rng.integers(1, 6, size=n_rows)
    # Most lines have no discount; others sit in a realistic promo band.
    discount = np.where(rng.random(n_rows) < 0.35, rng.choice([5, 8, 10, 12, 15, 20], size=n_rows), 0)

    return pd.DataFrame(
        {
            "order_item_id": [f"ITEM-{i + 1:08d}" for i in range(n_rows)],
            "order_id": order_id_values,
            "product_id": product_ids,
            "quantity": quantity,
            "unit_price": unit_price,
            "discount_percent": discount.astype(int),
        }
    )


def apply_order_totals(orders: pd.DataFrame, order_items: pd.DataFrame) -> pd.DataFrame:
    """Set order_total from line items: qty * price * (1 - discount/100)."""
    items = order_items.copy()
    items["line_amount"] = (
        items["quantity"].astype(float)
        * items["unit_price"].astype(float)
        * (1 - items["discount_percent"].astype(float) / 100.0)
    )
    totals = items.groupby("order_id", as_index=False)["line_amount"].sum()
    totals["line_amount"] = totals["line_amount"].round(2)
    updated = orders.drop(columns=["order_total"]).merge(
        totals.rename(columns={"line_amount": "order_total"}),
        on="order_id",
        how="left",
    )
    updated["order_total"] = updated["order_total"].fillna(0.0)
    return updated


def generate_payments(orders: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    """Create payments that follow order status and country payment mix."""
    logger.info("Generating payments")
    rows: list[dict] = []
    payment_seq = 1

    for row in orders.itertuples(index=False):
        country_currency = str(row.currency)
        status = str(row.order_status)
        channel = str(row.sales_channel)
        amount = float(row.order_total)
        order_date = date.fromisoformat(str(row.order_date))

        if channel == "PHYSICAL_STORE":
            method_choices, method_weights = (
                ["CASH", "DEBIT_CARD", "CREDIT_CARD", "UPI", "WALLET"],
                [0.35, 0.25, 0.20, 0.12, 0.08],
            )
        elif country_currency == "INR":
            method_choices, method_weights = (
                ["UPI", "DEBIT_CARD", "CREDIT_CARD", "NET_BANKING", "WALLET", "CASH"],
                [0.42, 0.16, 0.14, 0.12, 0.10, 0.06],
            )
        else:
            method_choices, method_weights = (
                ["CREDIT_CARD", "DEBIT_CARD", "PAYPAL", "WALLET", "NET_BANKING", "CASH"],
                [0.40, 0.22, 0.16, 0.12, 0.06, 0.04],
            )
        method = str(rng.choice(method_choices, p=method_weights))

        if status == "PENDING":
            pay_status = str(rng.choice(["PENDING", "SUCCESS"], p=[0.7, 0.3]))
        elif status == "CANCELLED":
            pay_status = str(rng.choice(["FAILED", "REFUNDED", "SUCCESS"], p=[0.55, 0.25, 0.20]))
        elif status == "RETURNED":
            pay_status = "REFUNDED"
        else:
            pay_status = str(rng.choice(["SUCCESS", "FAILED"], p=[0.94, 0.06]))

        delay_days = int(rng.integers(0, 3)) if pay_status != "PENDING" else 0
        payment_date = min(order_date + timedelta(days=delay_days), HISTORICAL_END_DATE)

        rows.append(
            {
                "payment_id": f"PAY-{payment_seq:08d}",
                "order_id": row.order_id,
                "payment_method": method,
                "payment_status": pay_status,
                "payment_amount": round(amount, 2),
                "payment_date": payment_date.isoformat(),
                "currency": country_currency,
            }
        )
        payment_seq += 1

        # Occasional retry after a failed attempt (keeps payment count near order count).
        if pay_status == "FAILED" and status not in {"CANCELLED", "PENDING"} and rng.random() < 0.55:
            retry_date = min(payment_date + timedelta(days=1), HISTORICAL_END_DATE)
            rows.append(
                {
                    "payment_id": f"PAY-{payment_seq:08d}",
                    "order_id": row.order_id,
                    "payment_method": method,
                    "payment_status": "SUCCESS",
                    "payment_amount": round(amount, 2),
                    "payment_date": retry_date.isoformat(),
                    "currency": country_currency,
                }
            )
            payment_seq += 1

    return pd.DataFrame(rows)


def generate_deliveries(orders: pd.DataFrame, stores: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    """Create deliveries for shipped/online orders; skip many in-store purchases."""
    logger.info("Generating deliveries")
    store_type_by_id = stores.set_index("store_id")["store_type"].to_dict()
    rows: list[dict] = []
    delivery_seq = 1

    for row in orders.itertuples(index=False):
        channel = str(row.sales_channel)
        status = str(row.order_status)

        # Physical-store purchases are often walk-out; no delivery record.
        if channel == "PHYSICAL_STORE" and rng.random() < 0.70:
            continue
        if status in {"PENDING", "CANCELLED"} and rng.random() < 0.65:
            continue

        if channel == "QUICK_COMMERCE":
            delivery_type = "QUICK"
            distance = round(float(rng.uniform(0.6, 7.5)), 2)
            minutes = int(rng.integers(12, 46))
            fee = round(float(rng.choice([0.0, 15.0, 25.0, 29.0])), 2)
        elif channel in {"WEBSITE", "MOBILE_APP"} and rng.random() < 0.28:
            delivery_type = "EXPRESS"
            distance = round(float(rng.uniform(8.0, 120.0)), 2)
            minutes = int(rng.integers(180, 36 * 60))
            fee = round(float(rng.uniform(49.0, 199.0)), 2)
        else:
            delivery_type = "STANDARD"
            distance = round(float(rng.uniform(15.0, 850.0)), 2)
            minutes = int(rng.integers(24 * 60, 7 * 24 * 60))
            fee = round(float(rng.uniform(0.0, 79.0)), 2)

        if status == "DELIVERED":
            delivery_status = str(rng.choice(["DELIVERED", "DELIVERED", "DELIVERED", "FAILED"]))
        elif status == "SHIPPED":
            delivery_status = str(rng.choice(["IN_TRANSIT", "ASSIGNED"], p=[0.8, 0.2]))
        elif status == "RETURNED":
            delivery_status = "DELIVERED"
        elif status == "CANCELLED":
            delivery_status = str(rng.choice(["CANCELLED", "FAILED"], p=[0.8, 0.2]))
        else:
            delivery_status = str(rng.choice(["ASSIGNED", "IN_TRANSIT"], p=[0.6, 0.4]))

        store_id = str(row.store_id)
        if store_type_by_id.get(store_id) == "RETAIL_STORE" and channel != "PHYSICAL_STORE":
            # Online orders can still ship from a store, but keep the original link.
            pass

        rows.append(
            {
                "delivery_id": f"DEL-{delivery_seq:08d}",
                "order_id": row.order_id,
                "store_id": store_id,
                "delivery_type": delivery_type,
                "delivery_status": delivery_status,
                "delivery_distance_km": distance,
                "delivery_time_minutes": minutes,
                "delivery_fee": fee,
            }
        )
        delivery_seq += 1

    return pd.DataFrame(rows)


def generate_exchange_rates(rng: np.random.Generator) -> pd.DataFrame:
    """Daily synthetic FX rates to INR across the historical window."""
    logger.info("Generating exchange rates")
    dates = pd.date_range(HISTORICAL_START_DATE, HISTORICAL_END_DATE, freq="D")
    rows: list[dict] = []
    for currency, base_rate in BASE_RATES_TO_INR.items():
        if currency == "INR":
            rates = np.ones(len(dates), dtype=float)
        else:
            shocks = rng.normal(0.0, 0.0025, size=len(dates))
            rates = base_rate * np.cumprod(1.0 + shocks)
            rates = np.clip(rates, base_rate * 0.85, base_rate * 1.15)
        for rate_date, rate in zip(dates, rates):
            rows.append(
                {
                    "rate_date": rate_date.strftime("%Y-%m-%d"),
                    "currency_code": currency,
                    "rate_to_inr": round(float(rate), 4),
                }
            )
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Intentional data-quality problems (modular, one issue family per helper)
# ---------------------------------------------------------------------------

def _corrupt_text_whitespace(series: pd.Series, indices: np.ndarray, rng: np.random.Generator) -> pd.Series:
    """Introduce messy capitalization and surrounding whitespace."""
    updated = series.copy()
    for idx in indices:
        value = str(updated.iat[int(idx)])
        style = int(rng.integers(0, 4))
        if style == 0:
            updated.iat[int(idx)] = f"  {value} "
        elif style == 1:
            updated.iat[int(idx)] = value.lower()
        elif style == 2:
            updated.iat[int(idx)] = value.upper()
        else:
            updated.iat[int(idx)] = value.replace(" ", "  ")
    return updated


def inject_dirty_customers(customers: pd.DataFrame, rng: np.random.Generator, rate: float) -> pd.DataFrame:
    """Missing contact fields, messy text, and a few duplicate rows."""
    df = customers.copy()
    n = len(df)
    if n == 0 or rate <= 0:
        return df

    missing_email_idx = sample_dirty_indices(rng, n, rate * 0.35)
    missing_phone_idx = sample_dirty_indices(rng, n, rate * 0.30)
    messy_city_idx = sample_dirty_indices(rng, n, rate * 0.25)
    messy_country_idx = sample_dirty_indices(rng, n, rate * 0.15)

    df.loc[missing_email_idx, "email"] = ""
    df.loc[missing_phone_idx, "phone"] = ""
    df["city"] = _corrupt_text_whitespace(df["city"], messy_city_idx, rng)
    df["country"] = _corrupt_text_whitespace(df["country"], messy_country_idx, rng)

    n_dupes = int(round(n * rate * 0.20))
    if n_dupes > 0:
        duplicates = df.sample(n=min(n_dupes, n), random_state=int(rng.integers(0, 10_000)))
        df = pd.concat([df, duplicates], ignore_index=True)
        logger.info("Injected customer data-quality issues (plus %s duplicate rows)", len(duplicates))
    else:
        logger.info("Injected customer data-quality issues")
    return df


def inject_dirty_products(products: pd.DataFrame, rng: np.random.Generator, rate: float) -> pd.DataFrame:
    """Inconsistent categories and a few invalid prices."""
    df = products.copy()
    n = len(df)
    if n == 0 or rate <= 0:
        return df

    messy_cat_idx = sample_dirty_indices(rng, n, rate * 0.50)
    df["category"] = _corrupt_text_whitespace(df["category"], messy_cat_idx, rng)

    bad_price_idx = sample_dirty_indices(rng, n, rate * 0.35)
    for idx in bad_price_idx:
        if rng.random() < 0.5:
            df.at[int(idx), "selling_price"] = -abs(float(df.at[int(idx), "selling_price"]))
        else:
            df.at[int(idx), "unit_cost"] = round(float(df.at[int(idx), "selling_price"]) * 1.25, 2)

    n_dupes = int(round(n * rate * 0.15))
    if n_dupes > 0:
        duplicates = df.sample(n=min(n_dupes, n), random_state=int(rng.integers(0, 10_000)))
        df = pd.concat([df, duplicates], ignore_index=True)
    logger.info("Injected product data-quality issues")
    return df


def inject_dirty_stores(stores: pd.DataFrame, rng: np.random.Generator, rate: float) -> pd.DataFrame:
    """Messy store types and a light duplicate injection."""
    df = stores.copy()
    n = len(df)
    if n == 0 or rate <= 0:
        return df
    messy_idx = sample_dirty_indices(rng, n, rate * 0.40)
    df["store_type"] = _corrupt_text_whitespace(df["store_type"], messy_idx, rng)
    invalid_idx = sample_dirty_indices(rng, n, rate * 0.20)
    df.loc[invalid_idx, "store_type"] = rng.choice(["STORE", "WAREHOUSE", "qc_hub"], size=len(invalid_idx))
    return df


def inject_dirty_orders(orders: pd.DataFrame, rng: np.random.Generator, rate: float) -> pd.DataFrame:
    """Orphan keys, invalid currency/status, and messy channel labels."""
    df = orders.copy()
    n = len(df)
    if n == 0 or rate <= 0:
        return df

    orphan_cust = sample_dirty_indices(rng, n, rate * 0.25)
    orphan_store = sample_dirty_indices(rng, n, rate * 0.20)
    bad_currency = sample_dirty_indices(rng, n, rate * 0.20)
    bad_status = sample_dirty_indices(rng, n, rate * 0.20)
    messy_channel = sample_dirty_indices(rng, n, rate * 0.20)

    df.loc[orphan_cust, "customer_id"] = [
        f"CUST-{900000 + int(i):05d}" for i in range(len(orphan_cust))
    ]
    df.loc[orphan_store, "store_id"] = [
        f"STR-{9000 + int(i):04d}" for i in range(len(orphan_store))
    ]
    df.loc[bad_currency, "currency"] = rng.choice(["XXX", "US", "INRR", "EURO"], size=len(bad_currency))
    df.loc[bad_status, "order_status"] = rng.choice(["SHIPED", "DONE", "N/A", "complete"], size=len(bad_status))
    df["sales_channel"] = _corrupt_text_whitespace(df["sales_channel"], messy_channel, rng)
    logger.info("Injected order data-quality issues")
    return df


def inject_dirty_order_items(order_items: pd.DataFrame, rng: np.random.Generator, rate: float) -> pd.DataFrame:
    """Invalid quantities/prices and orphan product/order references."""
    df = order_items.copy()
    n = len(df)
    if n == 0 or rate <= 0:
        return df

    bad_qty = sample_dirty_indices(rng, n, rate * 0.35)
    bad_price = sample_dirty_indices(rng, n, rate * 0.25)
    orphan_product = sample_dirty_indices(rng, n, rate * 0.20)
    orphan_order = sample_dirty_indices(rng, n, rate * 0.10)

    qty_values = rng.choice([0, -1, -3], size=len(bad_qty))
    df.loc[bad_qty, "quantity"] = qty_values
    df.loc[bad_price, "unit_price"] = rng.choice([0.0, -9.99, -1.0], size=len(bad_price))
    df.loc[orphan_product, "product_id"] = [
        f"PRD-{800000 + int(i):05d}" for i in range(len(orphan_product))
    ]
    df.loc[orphan_order, "order_id"] = [
        f"ORD-{80000000 + int(i):08d}" for i in range(len(orphan_order))
    ]
    logger.info("Injected order-item data-quality issues")
    return df


def inject_dirty_payments(payments: pd.DataFrame, rng: np.random.Generator, rate: float) -> pd.DataFrame:
    """Orphan orders, invalid currency, and invalid payment status."""
    df = payments.copy()
    n = len(df)
    if n == 0 or rate <= 0:
        return df
    orphan = sample_dirty_indices(rng, n, rate * 0.25)
    bad_currency = sample_dirty_indices(rng, n, rate * 0.25)
    bad_status = sample_dirty_indices(rng, n, rate * 0.25)
    df.loc[orphan, "order_id"] = [f"ORD-{81000000 + int(i):08d}" for i in range(len(orphan))]
    df.loc[bad_currency, "currency"] = rng.choice(["XXX", "inr", "USDOLLAR"], size=len(bad_currency))
    df.loc[bad_status, "payment_status"] = rng.choice(["OK", "DECLINED", "paid"], size=len(bad_status))
    return df


def inject_dirty_deliveries(deliveries: pd.DataFrame, rng: np.random.Generator, rate: float) -> pd.DataFrame:
    """Negative/unrealistic times and orphan keys."""
    df = deliveries.copy()
    n = len(df)
    if n == 0 or rate <= 0:
        return df
    bad_time = sample_dirty_indices(rng, n, rate * 0.40)
    orphan_order = sample_dirty_indices(rng, n, rate * 0.20)
    orphan_store = sample_dirty_indices(rng, n, rate * 0.20)
    df.loc[bad_time, "delivery_time_minutes"] = rng.choice([-15, -1, 0, 999999], size=len(bad_time))
    df.loc[orphan_order, "order_id"] = [f"ORD-{82000000 + int(i):08d}" for i in range(len(orphan_order))]
    df.loc[orphan_store, "store_id"] = [f"STR-{9100 + int(i):04d}" for i in range(len(orphan_store))]
    return df


def write_csv(df: pd.DataFrame, filename: str) -> Path:
    """Write a CSV extract into the raw data directory."""
    path = RAW_DATA_DIR / filename
    df.to_csv(path, index=False, encoding="utf-8")
    logger.info("Wrote %s (%s rows)", path, len(df))
    return path


def validate_config() -> None:
    """Fail fast on configuration that cannot produce a useful extract."""
    if NUM_CUSTOMERS < 1 or NUM_PRODUCTS < 1 or NUM_ORDERS < 1:
        raise ValueError("Customer, product, and order counts must be at least 1.")
    if NUM_STORES < 3:
        raise ValueError("NUM_STORES must be at least 3 so each store type can exist.")
    if HISTORICAL_END_DATE < HISTORICAL_START_DATE:
        raise ValueError("HISTORICAL_END_DATE must be on or after HISTORICAL_START_DATE.")
    if not 0 <= DIRTY_DATA_RATE <= 0.25:
        raise ValueError("DIRTY_DATA_RATE should be between 0 and 0.25 for this project.")


def generate_all() -> dict[str, pd.DataFrame]:
    """Run the full generation sequence and return in-memory frames."""
    validate_config()
    rng, faker = seed_all(RANDOM_SEED)

    customers = generate_customers(NUM_CUSTOMERS, rng, faker)
    products = generate_products(NUM_PRODUCTS, rng)
    stores = generate_stores(NUM_STORES, rng)
    orders = generate_orders(NUM_ORDERS, customers, stores, rng)
    order_items = generate_order_items(orders, products, rng)
    orders = apply_order_totals(orders, order_items)
    payments = generate_payments(orders, rng)
    deliveries = generate_deliveries(orders, stores, rng)
    exchange_rates = generate_exchange_rates(rng)

    customers = inject_dirty_customers(customers, rng, DIRTY_DATA_RATE)
    products = inject_dirty_products(products, rng, DIRTY_DATA_RATE)
    stores = inject_dirty_stores(stores, rng, DIRTY_DATA_RATE)
    orders = inject_dirty_orders(orders, rng, DIRTY_DATA_RATE)
    order_items = inject_dirty_order_items(order_items, rng, DIRTY_DATA_RATE)
    payments = inject_dirty_payments(payments, rng, DIRTY_DATA_RATE)
    deliveries = inject_dirty_deliveries(deliveries, rng, DIRTY_DATA_RATE)

    return {
        "customers": customers,
        "products": products,
        "stores": stores,
        "orders": orders,
        "order_items": order_items,
        "payments": payments,
        "deliveries": deliveries,
        "exchange_rates": exchange_rates,
    }


def main() -> None:
    """Generate ShopSphere source CSVs and print a run summary."""
    started = time.perf_counter()
    setup_logging()
    ensure_output_directories()

    logger.info("ShopSphere data generation started")
    logger.info(
        "Config: customers=%s products=%s stores=%s orders=%s seed=%s dirty_rate=%s dates=%s to %s",
        NUM_CUSTOMERS,
        NUM_PRODUCTS,
        NUM_STORES,
        NUM_ORDERS,
        RANDOM_SEED,
        DIRTY_DATA_RATE,
        HISTORICAL_START_DATE,
        HISTORICAL_END_DATE,
    )

    datasets = generate_all()
    write_csv(datasets["customers"], "customers.csv")
    write_csv(datasets["products"], "products.csv")
    write_csv(datasets["stores"], "stores.csv")
    write_csv(datasets["orders"], "orders.csv")
    write_csv(datasets["order_items"], "order_items.csv")
    write_csv(datasets["payments"], "payments.csv")
    write_csv(datasets["deliveries"], "deliveries.csv")
    write_csv(datasets["exchange_rates"], "exchange_rates.csv")

    elapsed = time.perf_counter() - started
    summary_lines = [
        "",
        "ShopSphere data generation completed.",
        "",
        f"Customers:       {len(datasets['customers']):>10,}",
        f"Products:        {len(datasets['products']):>10,}",
        f"Stores:          {len(datasets['stores']):>10,}",
        f"Orders:          {len(datasets['orders']):>10,}",
        f"Order items:     {len(datasets['order_items']):>10,}",
        f"Payments:        {len(datasets['payments']):>10,}",
        f"Deliveries:      {len(datasets['deliveries']):>10,}",
        f"Exchange rates:  {len(datasets['exchange_rates']):>10,}",
        "",
        f"Output directory: {RAW_DATA_DIR}",
        f"Generation duration: {elapsed:.2f} seconds",
        "",
    ]
    summary = "\n".join(summary_lines)
    print(summary)
    logger.info("Generation finished in %.2f seconds", elapsed)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        logging.getLogger("shopsphere.generate_data").exception("Data generation failed")
        raise
