import sqlite3
import json
import uuid
import os
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

# Path to SQLite database file
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "aria.db")

def get_db():
    """Get connected SQLite database connection with WAL mode enabled."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

def init_db():
    """Initialize database tables and seed with high-tech catalog."""
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS merchants (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            slug TEXT NOT NULL UNIQUE,
            category TEXT NOT NULL,
            tagline TEXT NOT NULL,
            logo TEXT NOT NULL DEFAULT '',
            color TEXT NOT NULL DEFAULT '#71717a',
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id TEXT PRIMARY KEY,
            merchant_id TEXT NOT NULL,
            name TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            category TEXT NOT NULL,
            price INTEGER NOT NULL,
            original_price INTEGER,
            inventory INTEGER NOT NULL DEFAULT 0,
            tags TEXT NOT NULL DEFAULT '[]',
            image TEXT NOT NULL DEFAULT '',
            upsell_ids TEXT NOT NULL DEFAULT '[]',
            cross_sell_ids TEXT NOT NULL DEFAULT '[]',
            ai_specs TEXT NOT NULL DEFAULT '{}',
            negotiable INTEGER NOT NULL DEFAULT 0,
            min_quantity INTEGER NOT NULL DEFAULT 1,
            max_quantity INTEGER NOT NULL DEFAULT 10,
            FOREIGN KEY (merchant_id) REFERENCES merchants(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id TEXT PRIMARY KEY,
            merchant_id TEXT NOT NULL,
            razorpay_order_id TEXT,
            buyer_agent_id TEXT,
            amount_paise INTEGER NOT NULL,
            currency TEXT NOT NULL DEFAULT 'INR',
            receipt TEXT,
            status TEXT NOT NULL DEFAULT 'created',
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY (merchant_id) REFERENCES merchants(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS campaigns (
            id TEXT PRIMARY KEY,
            merchant_id TEXT NOT NULL,
            name TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            payment_link_id TEXT,
            payment_link_url TEXT,
            amount_paise INTEGER NOT NULL DEFAULT 0,
            target_audience TEXT NOT NULL DEFAULT '',
            discount_percent INTEGER,
            status TEXT NOT NULL DEFAULT 'ACTIVE',
            clicks INTEGER NOT NULL DEFAULT 0,
            conversions INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY (merchant_id) REFERENCES merchants(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS audit_logs (
            id TEXT PRIMARY KEY,
            merchant_id TEXT,
            agent_id TEXT NOT NULL,
            agent_type TEXT NOT NULL,
            action_type TEXT NOT NULL,
            status TEXT NOT NULL,
            bound TEXT,
            reasoning TEXT,
            razorpay_ref TEXT,
            amount_paise INTEGER,
            payload TEXT DEFAULT '{}',
            timestamp TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)

    conn.commit()
    seed_or_update(conn)
    conn.close()

def seed_or_update(conn):
    cursor = conn.cursor()

    # 5 Merchants
    merchants = [
        {"id": "merchant_byteforge", "name": "ByteForge", "slug": "byteforge", "category": "Smartphones, GPUs & Computing", "tagline": "Next-gen tech & flagship performance", "logo": "BF", "color": "#f59e0b"},
        {"id": "merchant_homechef", "name": "HomeChef Co.", "slug": "homechef", "category": "Kitchen Appliances & Cookware", "tagline": "Cook like a pro at home", "logo": "HC", "color": "#ef4444"},
        {"id": "merchant_deskcraft", "name": "DeskCraft", "slug": "deskcraft", "category": "Desk & Ergonomic Setup", "tagline": "Workspace, refined", "logo": "DC", "color": "#10b981"},
        {"id": "merchant_glowlab", "name": "GlowLab", "slug": "glowlab", "category": "Dermatologist Skincare", "tagline": "Science-backed skincare", "logo": "GL", "color": "#a78bfa"},
        {"id": "merchant_sonicwave", "name": "SonicWave", "slug": "sonicwave", "category": "Hi-Fi Speakers & Audio", "tagline": "Acoustic perfection & spatial sound", "logo": "SW", "color": "#3b82f6"},
    ]

    for m in merchants:
        cursor.execute(
            "INSERT OR REPLACE INTO merchants (id, name, slug, category, tagline, logo, color) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (m["id"], m["name"], m["slug"], m["category"], m["tagline"], m["logo"], m["color"])
        )

    # Rich Flagship Products catalog
    products = [
        # ByteForge — Smartphones & GPUs
        {
            "id": "prod_bf_phone_01",
            "merchant_id": "merchant_byteforge",
            "name": "Samsung Galaxy S24 Ultra 5G",
            "description": "Flagship smartphone powered by Snapdragon 8 Gen 3 for Galaxy, 200MP Quad Camera with 100x Space Zoom, 6.8\" QHD+ Dynamic AMOLED 120Hz display, 12GB RAM, 512GB UFS 4.0 storage, Titanium frame, and embedded S Pen.",
            "category": "Smartphones",
            "price": 12999900,
            "original_price": 13999900,
            "inventory": 25,
            "tags": ["smartphone", "samsung", "galaxy", "camera", "processor", "snapdragon", "flagship", "5g", "android"],
            "upsell_ids": ["prod_bf_gpu_01"],
            "cross_sell_ids": ["prod_sw_001"],
            "ai_specs": {
                "processor": "Qualcomm Snapdragon 8 Gen 3 for Galaxy (4nm)",
                "camera": "200MP Main + 50MP Periscope (5x optical) + 10MP Telephoto + 12MP Ultra-wide",
                "display": "6.8\" QHD+ Dynamic AMOLED 2X, 120Hz Adaptive, 2600 nits peak brightness",
                "ram": "12GB LPDDR5X",
                "storage": "512GB UFS 4.0",
                "battery": "5000mAh with 45W fast charge"
            }
        },
        {
            "id": "prod_bf_phone_02",
            "merchant_id": "merchant_byteforge",
            "name": "Apple iPhone 15 Pro Max",
            "description": "Apple flagship powered by A17 Pro 3nm chip with 6-core GPU, 48MP Pro camera system with 5x Telephoto optical zoom lens, Super Retina XDR OLED display with ProMotion 120Hz, Natural Titanium design, and USB-C 3.0.",
            "category": "Smartphones",
            "price": 15990000,
            "original_price": 16990000,
            "inventory": 18,
            "tags": ["smartphone", "apple", "iphone", "camera", "processor", "a17pro", "flagship", "ios", "5g"],
            "upsell_ids": ["prod_bf_gpu_01"],
            "cross_sell_ids": ["prod_sw_001"],
            "ai_specs": {
                "processor": "Apple A17 Pro (3nm) 6-core CPU + 6-core Neural Engine",
                "camera": "48MP Main (sensor-shift OIS) + 12MP 5x Telephoto (120mm focal) + 12MP Ultra-wide",
                "display": "6.7\" Super Retina XDR OLED, 120Hz ProMotion, Always-On Display",
                "ram": "8GB Unified Memory",
                "storage": "256GB NVMe",
                "chassis": "Grade 5 Titanium frame with Ceramic Shield"
            }
        },
        {
            "id": "prod_bf_phone_03",
            "merchant_id": "merchant_byteforge",
            "name": "OnePlus 12 5G",
            "description": "Premium flagship powered by Snapdragon 8 Gen 3, 4th Gen Hasselblad Camera for Mobile with Sony LYT-808 sensor, 64MP periscope telephoto, 2K 120Hz ProXDR display, 100W SUPERVOOC fast charge, and Dual Cryo-velocity VC cooling.",
            "category": "Smartphones",
            "price": 6999900,
            "original_price": 7499900,
            "inventory": 40,
            "tags": ["smartphone", "oneplus", "camera", "processor", "hasselblad", "snapdragon", "fast-charge", "5g"],
            "upsell_ids": ["prod_bf_phone_01"],
            "cross_sell_ids": ["prod_bf_001"],
            "ai_specs": {
                "processor": "Qualcomm Snapdragon 8 Gen 3 (4nm)",
                "camera": "50MP Sony LYT-808 OIS + 64MP 3x Periscope + 48MP Ultra-wide (Hasselblad tuned)",
                "display": "6.82\" 2K+ LTPO 4.0 AMOLED, 1-120Hz, 4500 nits peak",
                "ram": "16GB LPDDR5X",
                "storage": "512GB UFS 4.0",
                "battery": "5400mAh with 100W SUPERVOOC & 50W AIRVOOC"
            }
        },
        {
            "id": "prod_bf_gpu_01",
            "merchant_id": "merchant_byteforge",
            "name": "NVIDIA GeForce RTX 4090 24GB",
            "description": "Ultimate gaming & AI GPU powered by NVIDIA Ada Lovelace architecture, 16,384 CUDA cores, 24GB GDDR6X VRAM, 4th Gen Tensor cores, DLSS 3.5 frame generation, and 8K ray tracing rendering engine.",
            "category": "Graphics Cards",
            "price": 18999900,
            "original_price": 19999900,
            "inventory": 8,
            "tags": ["gpu", "nvidia", "rtx4090", "graphics-card", "processor", "vram", "ai", "gaming", "flagship"],
            "upsell_ids": [],
            "cross_sell_ids": ["prod_bf_001"],
            "ai_specs": {
                "chipset": "NVIDIA GeForce RTX 4090",
                "cuda_cores": "16,384",
                "vram": "24GB GDDR6X (384-bit bus)",
                "boost_clock": "2520 MHz",
                "dlss": "DLSS 3.5 with Frame Generation & Ray Reconstruction",
                "power_tdp": "450W"
            }
        },
        {
            "id": "prod_bf_gpu_02",
            "merchant_id": "merchant_byteforge",
            "name": "NVIDIA GeForce RTX 4080 Super 16GB",
            "description": "High-end 4K gaming GPU with 10,240 CUDA cores, 16GB GDDR6X memory, 23 Gbps memory speed, DLSS 3.5 AI upscaling, 3x DisplayPort 1.4a, and vapor-chamber triple fan cooling.",
            "category": "Graphics Cards",
            "price": 10499900,
            "original_price": 11499900,
            "inventory": 15,
            "tags": ["gpu", "nvidia", "rtx4080", "graphics-card", "processor", "vram", "4k-gaming"],
            "upsell_ids": ["prod_bf_gpu_01"],
            "cross_sell_ids": ["prod_bf_001"],
            "ai_specs": {
                "chipset": "NVIDIA GeForce RTX 4080 Super",
                "cuda_cores": "10,240",
                "vram": "16GB GDDR6X (256-bit bus)",
                "boost_clock": "2550 MHz",
                "dlss": "DLSS 3.5 AI Super Resolution"
            }
        },
        {
            "id": "prod_bf_001",
            "merchant_id": "merchant_byteforge",
            "name": "Vortex Mechanical Keyboard",
            "description": "Hot-swappable TKL mechanical gaming keyboard with Gateron Yellow switches, PBT doubleshot keycaps, and per-key RGB backlighting.",
            "category": "Keyboards",
            "price": 549900,
            "original_price": 699900,
            "inventory": 38,
            "tags": ["keyboard", "mechanical", "hot-swap", "gateron"],
            "upsell_ids": ["prod_bf_phone_03"],
            "cross_sell_ids": ["prod_bf_gpu_02"],
            "ai_specs": {"switches": "Gateron Yellow", "layout": "TKL 87-key"}
        },

        # SonicWave — Speakers & Audio
        {
            "id": "prod_sw_speaker_01",
            "merchant_id": "merchant_sonicwave",
            "name": "Marshall Stanmore III Wireless Speaker",
            "description": "Iconic home audio speaker with wider soundstage, 80W Class D amplification, 5.25\" woofer, two 3/4\" tweeters, Bluetooth 5.2 LE audio, RCA & 3.5mm inputs, and vintage brass controls.",
            "category": "Speakers",
            "price": 3199900,
            "original_price": 3499900,
            "inventory": 20,
            "tags": ["speaker", "marshall", "bluetooth", "hifi", "audio", "vintage", "home-audio"],
            "upsell_ids": ["prod_sw_soundbar_01"],
            "cross_sell_ids": ["prod_sw_headphones_01"],
            "ai_specs": {
                "power_output": "80W Total (1x 50W Class D Woofer + 2x 15W Tweeters)",
                "frequency_range": "45–20,000 Hz",
                "connectivity": "Bluetooth 5.2 LE Audio, 3.5mm Aux, RCA",
                "design": "Textured vinyl casing with vintage brass accents"
            }
        },
        {
            "id": "prod_sw_soundbar_01",
            "merchant_id": "merchant_sonicwave",
            "name": "Bose Smart Soundbar 900 Dolby Atmos",
            "description": "Flagship home theater soundbar featuring Dolby Atmos spatial audio, 9 custom drivers including two custom up-firing dipole transducers, PhaseGuide technology, and Voice Assistant integration.",
            "category": "Speakers",
            "price": 8490000,
            "original_price": 9490000,
            "inventory": 12,
            "tags": ["speaker", "soundbar", "bose", "dolby-atmos", "spatial-audio", "home-theater", "hifi"],
            "upsell_ids": [],
            "cross_sell_ids": ["prod_sw_speaker_01"],
            "ai_specs": {
                "audio_tech": "Dolby Atmos, Voice4Video, PhaseGuide directional sound",
                "drivers": "9 total transducers (2 up-firing dipole, 1 center tweeter, 6 full-range)",
                "connectivity": "HDMI eARC, Optical, Wi-Fi, AirPlay 2, Spotify Connect, Bluetooth"
            }
        },
        {
            "id": "prod_sw_headphones_01",
            "merchant_id": "merchant_sonicwave",
            "name": "Sony WH-1000XM5 ANC Headphones",
            "description": "Industry-leading Noise Canceling wireless over-ear headphones with Integrated Processor V1, HD Noise Canceling Processor QN1, 8 microphones, 30-hour battery, LDAC Hi-Res Audio, and Speak-to-Chat.",
            "category": "Headphones",
            "price": 2999000,
            "original_price": 3499000,
            "inventory": 45,
            "tags": ["headphones", "sony", "anc", "noise-canceling", "bluetooth", "audio", "wireless"],
            "upsell_ids": ["prod_sw_speaker_01"],
            "cross_sell_ids": ["prod_sw_speaker_02"],
            "ai_specs": {
                "noise_canceling": "Dual Processor V1 + QN1 with 8 microphones",
                "driver": "30mm precision-engineered carbon fiber driver unit",
                "battery": "30 hours (3 min charge = 3 hours playback)",
                "codecs": "LDAC, AAC, SBC, Hi-Res Audio Wireless certified"
            }
        },
        {
            "id": "prod_sw_speaker_02",
            "merchant_id": "merchant_sonicwave",
            "name": "JBL Boombox 3 Portable Bluetooth Speaker",
            "description": "Massive sound portable speaker with 3-way speaker system (heavy-duty subwoofer + 2 mid-range drivers + 2 tweeters), IP67 dust/waterproof, 24-hour battery, and built-in powerbank.",
            "category": "Speakers",
            "price": 3599900,
            "original_price": 3999900,
            "inventory": 30,
            "tags": ["speaker", "jbl", "portable", "waterproof", "bluetooth", "bass", "audio"],
            "upsell_ids": ["prod_sw_speaker_01"],
            "cross_sell_ids": ["prod_sw_headphones_01"],
            "ai_specs": {
                "speakers": "3-way (Subwoofer 80W + 2x Midrange 40W + 2x Tweeter 10W)",
                "waterproof": "IP67 dust and waterproof rating",
                "battery": "24 hours continuous playback with USB-A powerbank port"
            }
        },

        # HomeChef Co. — Kitchenware & Appliances
        {
            "id": "prod_hc_001",
            "merchant_id": "merchant_homechef",
            "name": "Breville Barista Touch Espresso Machine",
            "description": "Automated touchscreen espresso machine with integrated precision conical burr grinder, ThermoJet 3-second heat up, dual boilers, and automatic microfoam milk texturing.",
            "category": "Appliances",
            "price": 8999900,
            "original_price": 9999900,
            "inventory": 15,
            "tags": ["espresso", "coffee", "breville", "appliance", "kitchen"],
            "upsell_ids": [],
            "cross_sell_ids": ["prod_hc_003"],
            "ai_specs": {"heat_up": "3 seconds", "grinder": "Integrated Conical Burr"}
        },
        {
            "id": "prod_hc_003",
            "merchant_id": "merchant_homechef",
            "name": "QuietBlend Pro 1500W Blender",
            "description": "High-performance commercial blender with sound enclosure shield, 1500W motor, 2L Tritan jar, and 10 speed settings.",
            "category": "Appliances",
            "price": 599900,
            "original_price": 799900,
            "inventory": 20,
            "tags": ["blender", "quiet", "kitchen", "appliance"],
            "upsell_ids": ["prod_hc_001"],
            "cross_sell_ids": [],
            "ai_specs": {"power": "1500W", "capacity": "2L"}
        },

        # DeskCraft — Desk Setup
        {
            "id": "prod_dc_chair_01",
            "merchant_id": "merchant_deskcraft",
            "name": "Herman Miller Aeron Ergonomic Chair",
            "description": "Iconic ergonomic office chair with breathable 8Z Pellicle mesh suspension, PostureFit SL sacral/lumbar support, fully adjustable armrests, and smooth tilt mechanism.",
            "category": "Chairs",
            "price": 12499900,
            "original_price": 13999900,
            "inventory": 10,
            "tags": ["chair", "ergonomic", "herman-miller", "office", "desk"],
            "upsell_ids": ["prod_dc_001"],
            "cross_sell_ids": ["prod_dc_002"],
            "ai_specs": {"suspension": "8Z Pellicle mesh", "support": "PostureFit SL lumbar"}
        },
        {
            "id": "prod_dc_001",
            "merchant_id": "merchant_deskcraft",
            "name": "AeroDesk Pro Dual-Motor Standing Desk",
            "description": "Electric sit-stand standing desk with 60x30 inch solid bamboo desktop, dual electric motors, memory presets, and anti-collision sensor.",
            "category": "Desks",
            "price": 2799900,
            "original_price": 3499900,
            "inventory": 14,
            "tags": ["standing-desk", "electric", "bamboo", "dual-motor", "desk"],
            "upsell_ids": ["prod_dc_chair_01"],
            "cross_sell_ids": ["prod_dc_002"],
            "ai_specs": {"motor": "Dual electric", "desktop": "60x30 inch solid bamboo"}
        },

        # GlowLab — Skincare
        {
            "id": "prod_gl_serum_01",
            "merchant_id": "merchant_glowlab",
            "name": "SkinCeuticals C E Ferulic Vitamin C Serum",
            "description": "Dermatologist-recommended advanced antioxidant serum with 15% pure L-ascorbic acid, 1% alpha-tocopherol (Vitamin E), and 0.5% ferulic acid for maximum photo-protection & anti-aging.",
            "category": "Serums",
            "price": 1599900,
            "original_price": 1799900,
            "inventory": 50,
            "tags": ["serum", "vitamin-c", "skinceuticals", "skincare", "anti-aging", "dermatologist"],
            "upsell_ids": [],
            "cross_sell_ids": ["prod_gl_001"],
            "ai_specs": {"actives": "15% L-ascorbic acid + 1% Vitamin E + 0.5% Ferulic acid"}
        },
        {
            "id": "prod_gl_001",
            "merchant_id": "merchant_glowlab",
            "name": "ClearPore Salicylic Gel Face Wash",
            "description": "Salicylic acid 2% gel cleanser for acne prone and oily skin. Fragrance-free, dermatologist formulated at pH 5.5.",
            "category": "Cleansers",
            "price": 44900,
            "original_price": 59900,
            "inventory": 200,
            "tags": ["face-wash", "salicylic-acid", "cleanser", "acne", "skincare"],
            "upsell_ids": ["prod_gl_serum_01"],
            "cross_sell_ids": [],
            "ai_specs": {"active": "Salicylic Acid 2%", "pH": "5.5"}
        }
    ]

    for p in products:
        cursor.execute("""
            INSERT OR REPLACE INTO products (id, merchant_id, name, description, category, price, original_price, inventory, tags, upsell_ids, cross_sell_ids, ai_specs, negotiable, min_quantity, max_quantity)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            p["id"], p["merchant_id"], p["name"], p["description"], p["category"],
            p["price"], p["original_price"], p["inventory"],
            json.dumps(p["tags"]), json.dumps(p["upsell_ids"]), json.dumps(p["cross_sell_ids"]),
            json.dumps(p["ai_specs"]), 0, 1, 10
        ))

    conn.commit()

def format_price(paise: int) -> str:
    """Format paise to Indian Rupees string format (e.g. 12999900 -> ₹1,29,999)."""
    rupees = paise // 100
    return f"₹{rupees:,}"

# Helper queries
def get_merchants() -> List[Dict[str, Any]]:
    conn = get_db()
    cursor = conn.cursor()
    merchants = [dict(row) for row in cursor.execute("SELECT * FROM merchants ORDER BY name").fetchall()]
    conn.close()
    return merchants

def get_merchant_by_id(merchant_id: str) -> Optional[Dict[str, Any]]:
    conn = get_db()
    cursor = conn.cursor()
    row = cursor.execute("SELECT * FROM merchants WHERE id = ?", (merchant_id,)).fetchone()
    conn.close()
    return dict(row) if row else None

def get_products(merchant_id: Optional[str] = None) -> List[Dict[str, Any]]:
    conn = get_db()
    cursor = conn.cursor()
    if merchant_id:
        rows = cursor.execute("SELECT * FROM products WHERE merchant_id = ? ORDER BY price DESC", (merchant_id,)).fetchall()
    else:
        rows = cursor.execute("SELECT * FROM products ORDER BY merchant_id, price DESC").fetchall()
    conn.close()
    
    res = []
    for r in rows:
        item = dict(r)
        item["tags"] = json.loads(item["tags"] or "[]")
        item["upsell_ids"] = json.loads(item["upsell_ids"] or "[]")
        item["cross_sell_ids"] = json.loads(item["cross_sell_ids"] or "[]")
        item["ai_specs"] = json.loads(item["ai_specs"] or "{}")
        res.append(item)
    return res

def get_product_by_id(product_id: str) -> Optional[Dict[str, Any]]:
    conn = get_db()
    cursor = conn.cursor()
    row = cursor.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()
    conn.close()
    if not row:
        return None
    item = dict(row)
    item["tags"] = json.loads(item["tags"] or "[]")
    item["upsell_ids"] = json.loads(item["upsell_ids"] or "[]")
    item["cross_sell_ids"] = json.loads(item["cross_sell_ids"] or "[]")
    item["ai_specs"] = json.loads(item["ai_specs"] or "{}")
    return item

def insert_product(merchant_id: str, name: str, description: str, category: str, price: int, inventory: int = 50, tags: List[str] = None, original_price: Optional[int] = None) -> Dict[str, Any]:
    conn = get_db()
    cursor = conn.cursor()
    product_id = f"prod_csv_{uuid.uuid4().hex[:8]}"
    tags_json = json.dumps(tags or [])
    
    cursor.execute("""
        INSERT INTO products (id, merchant_id, name, description, category, price, original_price, inventory, tags)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (product_id, merchant_id, name, description, category, price, original_price, inventory, tags_json))
    
    conn.commit()
    prod = get_product_by_id(product_id)
    conn.close()
    return prod

def create_order(merchant_id: str, amount_paise: int, razorpay_order_id: Optional[str] = None, buyer_agent_id: Optional[str] = None, receipt: Optional[str] = None) -> Dict[str, Any]:
    conn = get_db()
    cursor = conn.cursor()
    order_id = str(uuid.uuid4())
    created_at = datetime.now(timezone.utc).isoformat()
    
    cursor.execute("""
        INSERT INTO orders (id, merchant_id, razorpay_order_id, buyer_agent_id, amount_paise, receipt, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?, 'created', ?)
    """, (order_id, merchant_id, razorpay_order_id, buyer_agent_id, amount_paise, receipt, created_at))
    
    conn.commit()
    row = cursor.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
    conn.close()
    return dict(row)

def get_orders_by_merchant(merchant_id: str) -> List[Dict[str, Any]]:
    conn = get_db()
    cursor = conn.cursor()
    rows = cursor.execute("SELECT * FROM orders WHERE merchant_id = ? ORDER BY created_at DESC", (merchant_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def create_campaign(merchant_id: str, name: str, description: str, amount_paise: int, target_audience: str, discount_percent: Optional[int] = None, payment_link_id: Optional[str] = None, payment_link_url: Optional[str] = None) -> Dict[str, Any]:
    conn = get_db()
    cursor = conn.cursor()
    campaign_id = str(uuid.uuid4())
    created_at = datetime.now(timezone.utc).isoformat()
    
    cursor.execute("""
        INSERT INTO campaigns (id, merchant_id, name, description, amount_paise, target_audience, discount_percent, payment_link_id, payment_link_url, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (campaign_id, merchant_id, name, description, amount_paise, target_audience, discount_percent, payment_link_id, payment_link_url, created_at))
    
    conn.commit()
    row = cursor.execute("SELECT * FROM campaigns WHERE id = ?", (campaign_id,)).fetchone()
    conn.close()
    return dict(row)

def get_campaigns_by_merchant(merchant_id: str) -> List[Dict[str, Any]]:
    conn = get_db()
    cursor = conn.cursor()
    rows = cursor.execute("SELECT * FROM campaigns WHERE merchant_id = ? ORDER BY created_at DESC", (merchant_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_active_campaigns() -> List[Dict[str, Any]]:
    conn = get_db()
    cursor = conn.cursor()
    rows = cursor.execute("SELECT * FROM campaigns WHERE status = 'ACTIVE' ORDER BY created_at DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]

def log_audit(agent_id: str, agent_type: str, action_type: str, status: str, merchant_id: Optional[str] = None, bound: Optional[str] = None, reasoning: Optional[str] = None, razorpay_ref: Optional[str] = None, amount_paise: Optional[int] = None, payload: Dict[str, Any] = None) -> Dict[str, Any]:
    conn = get_db()
    cursor = conn.cursor()
    audit_id = str(uuid.uuid4())
    timestamp = datetime.now(timezone.utc).isoformat()
    payload_json = json.dumps(payload or {})
    
    cursor.execute("""
        INSERT INTO audit_logs (id, merchant_id, agent_id, agent_type, action_type, status, bound, reasoning, razorpay_ref, amount_paise, payload, timestamp)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (audit_id, merchant_id, agent_id, agent_type, action_type, status, bound, reasoning, razorpay_ref, amount_paise, payload_json, timestamp))
    
    conn.commit()
    row = cursor.execute("SELECT * FROM audit_logs WHERE id = ?", (audit_id,)).fetchone()
    conn.close()
    return dict(row)

def get_audit_logs(merchant_id: Optional[str] = None, agent_type: Optional[str] = None, status: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
    conn = get_db()
    cursor = conn.cursor()
    query = "SELECT * FROM audit_logs WHERE 1=1"
    args = []
    
    if merchant_id:
        query += " AND merchant_id = ?"
        args.append(merchant_id)
    if agent_type:
        query += " AND agent_type = ?"
        args.append(agent_type)
    if status:
        query += " AND status = ?"
        args.append(status)
        
    query += " ORDER BY timestamp DESC LIMIT ?"
    args.append(limit)
    
    rows = cursor.execute(query, tuple(args)).fetchall()
    conn.close()
    
    res = []
    for r in rows:
        item = dict(r)
        item["payload"] = json.loads(item["payload"] or "{}")
        res.append(item)
    return res

def get_audit_stats(merchant_id: Optional[str] = None) -> Dict[str, Any]:
    conn = get_db()
    cursor = conn.cursor()
    where = "WHERE merchant_id = ?" if merchant_id else ""
    args = (merchant_id,) if merchant_id else ()
    
    total = cursor.execute(f"SELECT COUNT(*) as cnt FROM audit_logs {where}", args).fetchone()["cnt"]
    
    by_status = {}
    for s in ['SUCCESS', 'FAILED', 'BLOCKED', 'PENDING', 'INFO']:
        stmt = f"SELECT COUNT(*) as cnt FROM audit_logs {where + ' AND' if where else 'WHERE'} status = ?"
        cnt = cursor.execute(stmt, args + (s,)).fetchone()["cnt"]
        by_status[s] = cnt
        
    stmt_rev = f"SELECT COALESCE(SUM(amount_paise), 0) as total FROM audit_logs {where + ' AND' if where else 'WHERE'} action_type = 'PAYMENT_CAPTURE' AND status = 'SUCCESS'"
    rev = cursor.execute(stmt_rev, args).fetchone()["total"]
    
    conn.close()
    return {
        "total": total,
        "byStatus": by_status,
        "totalRevenuePaise": rev,
        "blockedActions": by_status.get("BLOCKED", 0)
    }
