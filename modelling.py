import sys
sys.stdout.reconfigure(encoding="utf-8")

import pandas as pd
import json
import numpy as np
from datetime import datetime, timedelta
import openai
from openai import OpenAI
 
# ============================================================
#  STANDARDISED VARIABLE CONTRACT
#  All teams (Frontend, AI, API) MUST use these exact names.
#
#  PHASE 1 — FRONTEND INPUTS
#  ┌─────────────────┬────────────────────────────────────────────────────┐
#  │ user_query      │ The question/command typed by the SME owner.       │
#  │                 │ e.g. "What should I restock for next week?"        │
#  ├─────────────────┼────────────────────────────────────────────────────┤
#  │ inventory_file  │ The raw CSV/Excel spreadsheet uploaded by the user.│
#  │                 │ e.g. "Grocery_Inventory_and_Sales_Dataset.csv"     │
#  ├─────────────────┼────────────────────────────────────────────────────┤
#  │ current_date    │ Today's date (auto-set). Tells AI when "now" is.   │
#  │                 │ e.g. "2026-04-22"                                  │
#  └─────────────────┴────────────────────────────────────────────────────┘
#
#  PHASE 2 — CONTEXT VARIABLES (extracted from the uploaded file)
#  ┌─────────────────────┬──────────────────────────────────────────────────┐
#  │ item_name           │ The name of the product.                         │
#  │                     │ e.g. "Milo 1kg"                                  │
#  ├─────────────────────┼──────────────────────────────────────────────────┤
#  │ current_stock       │ Units currently on the shelf (integer/float).    │
#  │                     │ e.g. 15                                          │
#  ├─────────────────────┼──────────────────────────────────────────────────┤
#  │ reorder_threshold   │ Minimum units allowed before ordering more.      │
#  │                     │ e.g. 20                                          │
#  ├─────────────────────┼──────────────────────────────────────────────────┤
#  │ supplier_contact    │ Email/phone of the supplier for this item.       │
#  │                     │ e.g. "supplier@nestle.com.my"                    │
#  └─────────────────────┴──────────────────────────────────────────────────┘
#
#  PHASE 2B — FORECAST VARIABLES (computed from historical sales data)
#  ┌──────────────────────────┬─────────────────────────────────────────────┐
#  │ sales_history            │ List of past weekly/monthly sales figures.  │
#  │                          │ e.g. [32, 28, 35, 40, 30, 38, 42]          │
#  ├──────────────────────────┼─────────────────────────────────────────────┤
#  │ forecast_next_week       │ AI-predicted units to be sold next week.    │
#  │                          │ e.g. 38                                     │
#  ├──────────────────────────┼─────────────────────────────────────────────┤
#  │ forecast_next_month      │ AI-predicted units to be sold next month.   │
#  │                          │ e.g. 155                                    │
#  ├──────────────────────────┼─────────────────────────────────────────────┤
#  │ forecast_confidence      │ AI's confidence in the forecast (%).        │
#  │                          │ e.g. "high" | "medium" | "low"             │
#  ├──────────────────────────┼─────────────────────────────────────────────┤
#  │ forecast_trend           │ Direction of sales trend.                   │
#  │                          │ e.g. "rising" | "stable" | "declining"     │
#  ├──────────────────────────┼─────────────────────────────────────────────┤
#  │ days_until_stockout      │ Estimated days before stock hits zero.      │
#  │                          │ e.g. 4                                      │
#  └──────────────────────────┴─────────────────────────────────────────────┘
#
#  PHASE 3 — AI LAYER VARIABLES
#  ┌─────────────────┬────────────────────────────────────────────────────┐
#  │ system_prompt   │ Hidden master instructions sent to Z.ai.           │
#  ├─────────────────┼────────────────────────────────────────────────────┤
#  │ ai_raw_response │ The exact, unedited text returned by Z.ai.         │
#  └─────────────────┴────────────────────────────────────────────────────┘
#
#  PHASE 4 — AGENTIC OUTPUT VARIABLES (parsed from ai_raw_response)
#  ┌──────────────────────┬───────────────────────────────────────────────┐
#  │ recommended_action   │ "reorder" | "discount" | "none"               │
#  ├──────────────────────┼───────────────────────────────────────────────┤
#  │ draft_message        │ Ready-to-send supplier email or memo text.    │
#  └──────────────────────┴───────────────────────────────────────────────┘
# ============================================================
 
 
# ============================================================
# PHASE 1 — FRONTEND INPUTS
# ============================================================
current_date   = datetime.now().strftime("%Y-%m-%d")         # STD VAR: current_date
user_query     = "What should I restock for next week?"      # STD VAR: user_query
inventory_file = r"C:\Users\nicky\OneDrive\Desktop\UM Hackhaton\Grocery_Inventory_and_Sales_Dataset.csv"   # STD VAR: inventory_file
 
ILMU_API_KEY  = "sk-a9e9a67ca4e71312adce464ea88e956f30c69f1f7277a0a7"
ILMU_MODEL    = "ilmu-glm-5.1"
ILMU_BASE_URL = "https://api.ilmu.ai/v1"
 
print("=" * 62)
print("PHASE 1 — FRONTEND INPUTS")
print("=" * 62)
print(f"  current_date    = {current_date}")
print(f"  user_query      = '{user_query}'")
print(f"  inventory_file  = {inventory_file}")
print(f"  model           = {ILMU_MODEL}")
 
 
# ============================================================
# UNIVERSAL SCHEMA ADAPTER  (v2 — AI-assisted column detection)
# ============================================================
#
# Detection strategy (three-tier cascade):
#
#   Tier 1 — Exact alias match  (fast, zero cost)
#             normalise_columns() checks every column header
#             against FIELD_SCHEMA aliases (case-insensitive).
#
#   Tier 2 — Z.ai semantic match  (one API call, only when needed)
#             Any STD VAR that Tier 1 couldn't map is handed to
#             Z.ai along with ALL unmapped column names + 3 sample
#             values each. Z.ai returns the best column→field JSON.
#
#   Tier 3 — Graceful degradation
#             Still-unmapped required fields raise ValueError.
#             Optional fields fall back to None / estimated values.
#
# This means the adapter works on ANY inventory CSV, even if the
# column headers are in a different language, abbreviated, or
# named after internal systems (e.g. "QTY_OH", "PROD_DESC", "SKU").
# ============================================================


FIELD_SCHEMA = {
    "item_name": {
        "aliases": [
            "product_name", "item description", "item_description",
            "product id", "product_id", "category", "series",
            "name", "item_name", "product", "sku_name", "description",
        ],
        "required": True,
        "description": "The name or description of the product / inventory item.",
    },
    "current_stock": {
        "aliases": [
            "stock_quantity", "inventory level", "inventory_level",
            "volume", "volume_sa", "retail sales", "retail_sales", "sales",
            "qty_on_hand", "stock", "on_hand", "available_qty", "balance",
        ],
        "required": True,
        "cast": float,
        "description": "How many units are currently in stock / on hand.",
    },
    "reorder_threshold": {
        "aliases": [
            "reorder_level", "reorder level",
            "units ordered", "units_ordered",
            "warehouse sales", "warehouse_sales",
            "min_stock", "safety_stock", "min_qty", "reorder_point",
        ],
        "required": False,
        "cast": float,
        "description": "Minimum stock level that triggers a reorder.",
    },
    "supplier_name": {
        "aliases": [
            "supplier_name", "supplier", "store id", "store_id", "region",
            "vendor", "vendor_name", "manufacturer", "brand",
        ],
        "required": False,
        "description": "Name of the supplier or vendor for this item.",
    },
    "product_id": {
        "aliases": [
            "product_id", "product id", "item code", "item_code",
            "sku", "barcode", "upc", "part_number",
        ],
        "required": False,
        "description": "Unique identifier / SKU / barcode for the product.",
    },
    "category": {
        "aliases": [
            "catagory", "category", "item type", "item_type",
            "dept", "department", "product_type", "segment",
        ],
        "required": False,
        "description": "Product category, department, or type.",
    },
    "status": {
        "aliases": ["status", "item_status", "availability", "stock_status"],
        "required": False,
        "description": "Current status of the item (e.g. active, discontinued, out-of-stock).",
    },
    "units_sold": {
        "aliases": [
            "sales_volume", "units sold", "units_sold",
            "demand", "retail sales", "retail_sales",
            "qty_sold", "sold_qty", "sales_qty",
        ],
        "required": False,
        "cast": float,
        "description": "Number of units sold in the most recent period.",
    },
    "date": {
        "aliases": [
            "date", "last_order_date", "date_received",
            "transaction_date", "order_date", "period",
        ],
        "required": False,
        "description": "Date associated with the row (transaction, order, or period).",
    },
    "inventory_turnover": {
        "aliases": [
            "inventory_turnover_rate", "turnover", "turnover_rate",
            "turn_rate", "stock_turns",
        ],
        "required": False,
        "cast": float,
        "description": "How many times inventory is sold/replaced in a period.",
    },
}


# ── Tier 1: fast exact / alias match ────────────────────────────────────────

def normalise_columns(df: pd.DataFrame) -> dict:
    """
    Returns col_map  {std_field: original_column_name}
    for every field whose alias appears in df.columns (case-insensitive).
    """
    col_lower = {c.lower().strip(): c for c in df.columns}
    mapping   = {}
    for field, meta in FIELD_SCHEMA.items():
        for alias in meta["aliases"]:
            if alias.lower() in col_lower:
                mapping[field] = col_lower[alias.lower()]
                break
    return mapping


# ── Tier 2: Z.ai semantic column detection ───────────────────────────────────

def _build_column_profile(df: pd.DataFrame, col_name: str, n_samples: int = 3) -> str:
    """
    Returns a short human-readable profile of one column:
      column_name | dtype | sample values
    Used as evidence for Z.ai to reason about.
    """
    samples = (
        df[col_name]
        .dropna()
        .astype(str)
        .head(n_samples)
        .tolist()
    )
    return f'"{col_name}" (dtype={df[col_name].dtype}, samples={samples})'


def ai_detect_columns(
    df: pd.DataFrame,
    already_mapped: dict,          # {std_field: col_name}  — skip these
    client: OpenAI,
) -> dict:
    """
    Tier 2: asks ilmu.ai to map unmapped columns to STD VARs.

    Returns an incremental mapping  {std_field: original_column_name}
    which is MERGED into already_mapped by the caller.
    Only STD VARs that are still unmapped are asked about.
    Only columns not yet claimed are offered as candidates.
    """
    # Fields we still need to resolve
    unmapped_fields = {
        field: meta
        for field, meta in FIELD_SCHEMA.items()
        if field not in already_mapped
    }
    if not unmapped_fields:
        return {}   # everything already found by Tier 1 — skip AI call

    # Columns not yet claimed by Tier 1
    claimed_cols    = set(already_mapped.values())
    candidate_cols  = [c for c in df.columns if c not in claimed_cols]
    if not candidate_cols:
        return {}

    # Build evidence block: one line per candidate column
    col_profiles = "\n".join(
        f"  {_build_column_profile(df, c)}"
        for c in candidate_cols
    )

    # Build target block: one line per still-needed STD VAR
    field_targets = "\n".join(
        f'  "{field}": {meta["description"]}'
        for field, meta in unmapped_fields.items()
    )

    system = """You are a data-schema expert.
You will be given:
  1. A list of CSV column profiles (name, dtype, sample values).
  2. A list of target standard variable names with descriptions.

Your job is to map each target variable to the BEST matching column, if one exists.
Rules:
- Output ONLY a raw JSON object — no markdown, no ```json fences, no extra text.
- Keys   = standard variable names (from the target list).
- Values = the EXACT column name from the profile list, or null if no reasonable match.
- Only use each column once.
- If you are not confident, use null rather than guess."""

    user = f"""CANDIDATE COLUMNS (name | dtype | sample values):
{col_profiles}

TARGET STANDARD VARIABLES (name: description):
{field_targets}

Return a JSON mapping target_variable → column_name_or_null."""

    try:
        response = client.chat.completions.create(
            model=ILMU_MODEL,
            messages=[
                {"role": "system", "content": system},
                {"role": "user",   "content": user},
            ],
            temperature=0.0,     # deterministic — schema detection is not creative
            max_tokens=8000,     # GLM-5.1 is a reasoning model — needs headroom for thinking tokens
        )
        raw = response.choices[0].message.content.strip()
        raw = raw.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        ai_map = json.loads(raw)
    except Exception as e:
        print(f"  [AI column detect] ilmu.ai call failed: {e}  — falling back to alias-only mapping.")
        return {}

    # Filter: only accept non-null values that are actual column names
    valid_cols = set(df.columns)
    result = {}
    for field, col in ai_map.items():
        if field in FIELD_SCHEMA and col and col in valid_cols:
            result[field] = col
            print(f"  [AI column detect]  '{col}'  →  {field}  ✓")
        elif field in FIELD_SCHEMA and col:
            print(f"  [AI column detect]  '{col}'  →  {field}  ✗ (column not found, ignored)")

    return result


# ── Public entry-point: run both tiers and merge ─────────────────────────────

def detect_columns(df: pd.DataFrame, client: OpenAI) -> dict:
    """
    Full two-tier column detection.

    Returns col_map  {std_field: original_column_name}

    Usage:
        col_map = detect_columns(df, client)
        # then pass col_map to extract_context_variables() as before
    """
    print("  [detect_columns] Tier 1 — alias matching …")
    col_map = normalise_columns(df)
    print(f"    matched {len(col_map)}/{len(FIELD_SCHEMA)} fields via aliases: {list(col_map.keys())}")

    unmatched = [f for f in FIELD_SCHEMA if f not in col_map]
    if unmatched:
        print(f"  [detect_columns] Tier 2 — Z.ai semantic detection for: {unmatched}")
        ai_extra = ai_detect_columns(df, col_map, client)
        col_map.update(ai_extra)
        print(f"    Z.ai added {len(ai_extra)} more fields: {list(ai_extra.keys())}")
    else:
        print("  [detect_columns] Tier 2 skipped — all fields resolved by aliases.")

    # Tier 3: check required fields
    missing_required = [
        f for f, m in FIELD_SCHEMA.items()
        if m["required"] and f not in col_map
    ]
    if missing_required:
        raise ValueError(
            f"Required fields still unresolved after AI detection: {missing_required}\n"
            f"Available columns were: {list(df.columns)}"
        )

    return col_map
 
 
def normalise_columns(df: pd.DataFrame) -> dict:
    col_lower = {c.lower().strip(): c for c in df.columns}
    mapping = {}
    for field, meta in FIELD_SCHEMA.items():
        for alias in meta["aliases"]:
            if alias.lower() in col_lower:
                mapping[field] = col_lower[alias.lower()]
                break
    return mapping
 
 
def extract_context_variables(row: pd.Series, col_map: dict, df: pd.DataFrame) -> dict:
    ctx = {}
    for field, meta in FIELD_SCHEMA.items():
        col = col_map.get(field)
        raw = row[col] if col else None
        if raw is not None and "cast" in meta:
            try:
                raw = meta["cast"](str(raw).replace("$", "").replace(",", "").strip())
            except (ValueError, TypeError):
                raw = None
        ctx[field] = raw
 
    if ctx.get("reorder_threshold") is None:
        stock_col = col_map.get("current_stock")
        if stock_col:
            median_stock = df[stock_col].apply(
                lambda x: float(str(x).replace("$", "").replace(",", "").strip())
                if str(x).replace("$", "").replace(",", "").strip().replace(".", "").isdigit()
                else None
            ).dropna().median()
            ctx["reorder_threshold"] = round(median_stock * 0.6, 2)
            ctx["_threshold_estimated"] = True
        else:
            ctx["reorder_threshold"] = 0.0
            ctx["_threshold_estimated"] = True
 
    supplier = ctx.get("supplier_name") or "unknownsupplier"
    ctx["supplier_contact"] = f"{str(supplier).lower().replace(' ', '')}@supplier.com"  # STD VAR
    return ctx
 
 
def load_and_detect(filepath: str):
    try:
        df = pd.read_csv(filepath)
    except FileNotFoundError:
        raise FileNotFoundError(f"File not found: {filepath}")
 
    col_map = normalise_columns(df)
    missing = [f for f, m in FIELD_SCHEMA.items() if m["required"] and f not in col_map]
    if missing:
        raise ValueError(f"Cannot map required fields {missing} from columns: {list(df.columns)}")
 
    cols_lower = [c.lower() for c in df.columns]
    if "product_name" in cols_lower:
        schema_name = "Grocery Inventory Dataset"
    elif "inventory level" in cols_lower:
        schema_name = "Multi-Store Sales Dataset"
    elif "item description" in cols_lower or "item code" in cols_lower:
        schema_name = "Warehouse & Retail Sales Dataset"
    elif "series" in cols_lower and "volume" in cols_lower:
        schema_name = "IO/WRT Time Series Dataset"
    else:
        schema_name = "Unknown Retail Dataset"
 
    return df, col_map, schema_name
 
 
# ============================================================
# SALES HISTORY BUILDER
# Extracts a time-series of past sales for a given item,
# or synthesises a plausible history from available fields
# when the dataset does not contain temporal rows per item.
# ============================================================
 
def build_sales_history(item_name_val: str, ctx: dict, df: pd.DataFrame,
                        col_map: dict, schema_name: str) -> list:
    """
    Returns sales_history — a list of numeric sales figures ordered
    oldest-to-newest, representing weekly or monthly periods.
    Strategy depends on the dataset type.
    """
 
    # ── Strategy A: datasets with one row per date (time-series style) ──
    if col_map.get("date") and col_map.get("current_stock"):
        name_col  = col_map.get("item_name")
        stock_col = col_map["current_stock"]
        date_col  = col_map["date"]
 
        if name_col:
            item_df = df[df[name_col].astype(str).str.strip() == str(item_name_val).strip()]
        else:
            item_df = df.copy()
 
        item_df = item_df.copy()
        item_df["_date"] = pd.to_datetime(item_df[date_col], errors="coerce")
        item_df = item_df.dropna(subset=["_date"]).sort_values("_date")
 
        if len(item_df) >= 3:
            history = item_df[stock_col].apply(
                lambda x: float(str(x).replace("$","").replace(",","").strip())
                if str(x).replace("$","").replace(",","").strip().replace(".","").isdigit()
                else None
            ).dropna().tolist()
            if len(history) >= 3:
                return history[-12:]   # last 12 data points max
 
    # ── Strategy B: single-row-per-item datasets (grocery style) ──
    # Synthesise a plausible weekly sales history using:
    #   sales_volume, inventory_turnover, and cross-item variance
    units_sold        = ctx.get("units_sold") or 0
    turnover          = ctx.get("inventory_turnover") or 1
    current_stock_val = ctx.get("current_stock") or 0
 
    # Estimate average weekly sales from available signals
    if units_sold > 0:
        avg_weekly = units_sold / max(turnover, 1) * 4
    elif current_stock_val > 0:
        avg_weekly = current_stock_val * 0.3
    else:
        avg_weekly = 10.0
 
    avg_weekly = max(avg_weekly, 1.0)
 
    # Generate 8 synthetic weekly points with mild random variance
    # Seed from item name so results are reproducible for the same item
    rng = np.random.default_rng(seed=abs(hash(str(item_name_val))) % (2**31))
    noise   = rng.normal(0, avg_weekly * 0.15, 8)
    # Add a gentle upward or downward drift based on turnover rate
    trend   = np.linspace(0, avg_weekly * 0.1 * (1 if turnover > 50 else -0.05), 8)
    history = [max(0.0, round(avg_weekly + noise[i] + trend[i], 1)) for i in range(8)]
 
    return history
 
 
# ============================================================
# STATISTICAL PRE-PROCESSING FOR FORECAST
# Computes baseline stats passed to Z.ai as grounding data,
# so the AI forecast is anchored in real numbers.
# ============================================================
 
def compute_forecast_stats(sales_history: list) -> dict:
    """
    Returns a dict of statistical signals derived from sales_history.
    These are injected into the Z.ai forecast prompt as evidence.
    """
    if not sales_history or len(sales_history) < 2:
        return {
            "avg":        0,
            "std":        0,
            "trend_pct":  0,
            "recent_avg": 0,
            "older_avg":  0,
            "n_periods":  0,
        }
 
    arr = np.array(sales_history, dtype=float)
    n   = len(arr)
    mid = n // 2
 
    older_avg  = float(np.mean(arr[:mid]))   if mid > 0 else float(arr[0])
    recent_avg = float(np.mean(arr[mid:]))
    avg        = float(np.mean(arr))
    std        = float(np.std(arr))
    trend_pct  = ((recent_avg - older_avg) / older_avg * 100) if older_avg > 0 else 0
 
    return {
        "avg":        round(avg, 2),
        "std":        round(std, 2),
        "trend_pct":  round(trend_pct, 1),
        "recent_avg": round(recent_avg, 2),
        "older_avg":  round(older_avg, 2),
        "n_periods":  n,
    }
 
 
# ============================================================
# Z.AI HELPER — single reusable call
# ============================================================
 
def call_ai(client: OpenAI, system: str, user: str,
            temperature: float = 0.1, max_tokens: int = 1000) -> str:
    """
    Makes one chat completion call to ilmu.ai and returns the raw
    response text. Returns a safe fallback string on any error.
    """
    try:
        response = client.chat.completions.create(
            model=ILMU_MODEL,
            messages=[
                {"role": "system", "content": system},
                {"role": "user",   "content": user},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        choice  = response.choices[0]
        content = choice.message.content or getattr(choice.message, "reasoning_content", None)
        if not content:
            print(f"  [ilmu] Empty content. finish_reason={choice.finish_reason}  raw={choice.message}")
            return '{"error": "AI returned empty content"}'
        return content

    except openai.APIStatusError as e:
        print(f"  [ilmu] API error     : {e}")
    except openai.APITimeoutError:
        print("  [ilmu] Request timed out.")
    except Exception as e:
        print(f"  [ilmu] Unexpected    : {e}")

    return '{"error": "AI call failed"}'
 
 
# ============================================================
# PHASE 2 — CONTEXT VARIABLES
# ============================================================
print("\n" + "=" * 62)
print("PHASE 2 — CONTEXT VARIABLES")
print("=" * 62)
 
df, col_map, schema_name = load_and_detect(inventory_file)
print(f"  Schema detected   : {schema_name}")
print(f"  Rows              : {len(df):,}  |  Columns: {len(df.columns)}")
 
row = df.iloc[0]
ctx = extract_context_variables(row, col_map, df)
 
item_name         = ctx["item_name"]          # STD VAR: item_name
current_stock     = ctx["current_stock"]      # STD VAR: current_stock
reorder_threshold = ctx["reorder_threshold"]  # STD VAR: reorder_threshold
supplier_contact  = ctx["supplier_contact"]   # STD VAR: supplier_contact
 
print(f"\n  item_name          = {item_name}")
print(f"  current_stock      = {current_stock}")
print(f"  reorder_threshold  = {reorder_threshold}", end="")
print("  ⚠️  (estimated)" if ctx.get("_threshold_estimated") else "")
print(f"  supplier_contact   = {supplier_contact}")
 
 
# ============================================================
# PHASE 2B — FORECAST VARIABLES
# Build sales history → compute stats → call Z.ai for forecast
# ============================================================
print("\n" + "=" * 62)
print("PHASE 2B — FORECAST VARIABLES")
print("=" * 62)
 
# STD VAR: sales_history
sales_history = build_sales_history(item_name, ctx, df, col_map, schema_name)
stats         = compute_forecast_stats(sales_history)
 
print(f"  sales_history      = {sales_history}")
print(f"  avg / std          = {stats['avg']} / {stats['std']}")
print(f"  trend              = {stats['trend_pct']:+.1f}% "
      f"(older avg {stats['older_avg']} → recent avg {stats['recent_avg']})")
 
# ── Z.ai CALL 1 — Sales Forecast ────────────────────────────
forecast_system_prompt = f"""You are a specialist retail demand forecasting engine for Malaysian SME stores.
Today is {current_date}. You will be given historical weekly sales data and pre-computed statistics.
Your job is to forecast future demand using trend analysis and seasonality reasoning.
Return ONLY a raw JSON object — no markdown, no ```json fences, no extra text.
JSON schema:
{{
  "forecast_next_week":  <integer, predicted units sold next week>,
  "forecast_next_month": <integer, predicted units sold next month>,
  "forecast_confidence": "high" | "medium" | "low",
  "forecast_trend":      "rising" | "stable" | "declining",
  "forecast_reasoning":  "<2 sentences max explaining your logic>"
}}
"""
 
forecast_user_message = f"""Item: {item_name}
Category: {ctx.get('category', 'N/A')}
Historical weekly sales (oldest → newest): {sales_history}
Pre-computed statistics:
  - Overall average per period : {stats['avg']}
  - Standard deviation         : {stats['std']}
  - Older half average         : {stats['older_avg']}
  - Recent half average        : {stats['recent_avg']}
  - Trend change               : {stats['trend_pct']:+.1f}%
  - Number of data points      : {stats['n_periods']}
Current stock on hand : {current_stock}
Reorder threshold     : {reorder_threshold}
 
Forecast next week's and next month's unit sales for this item."""
 
print(f"\n  Calling ilmu.ai for sales forecast ({ILMU_MODEL})...")

client        = OpenAI(api_key=ILMU_API_KEY, base_url=ILMU_BASE_URL)
forecast_raw  = call_ai(client, forecast_system_prompt, forecast_user_message,
                         temperature=0.2, max_tokens=8000)
 
# Parse forecast — with safe fallback defaults
try:
    _fc = forecast_raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    _fc_parsed = json.loads(_fc)
except json.JSONDecodeError:
    print(f"  ⚠️  Forecast JSON parse failed. Raw: {forecast_raw}")
    _fc_parsed = {}
 
forecast_next_week   = int(_fc_parsed.get("forecast_next_week",  round(stats["avg"])))       # STD VAR
forecast_next_month  = int(_fc_parsed.get("forecast_next_month", round(stats["avg"] * 4)))   # STD VAR
forecast_confidence  = _fc_parsed.get("forecast_confidence", "medium")                        # STD VAR
forecast_trend       = _fc_parsed.get("forecast_trend",      "stable")                        # STD VAR
forecast_reasoning   = _fc_parsed.get("forecast_reasoning",  "Based on historical average.")
 
# STD VAR: days_until_stockout
daily_sales_rate   = max(forecast_next_week / 7, 0.01)
days_until_stockout = int((current_stock or 0) / daily_sales_rate) if daily_sales_rate > 0 else 999  # STD VAR
 
print(f"\n  forecast_next_week   = {forecast_next_week} units")
print(f"  forecast_next_month  = {forecast_next_month} units")
print(f"  forecast_confidence  = {forecast_confidence}")
print(f"  forecast_trend       = {forecast_trend}")
print(f"  days_until_stockout  = {days_until_stockout} days")
print(f"  reasoning            : {forecast_reasoning}")
 
 
# ============================================================
# PHASE 3 — AI LAYER  (Z.ai CALL 2 — Restock Decision)
# Uses forecast variables + context variables together
# ============================================================
print("\n" + "=" * 62)
print("PHASE 3 — AI LAYER  (Z.ai — Restock Decision)")
print("=" * 62)
 
# STD VAR: system_prompt
system_prompt = f"""You are an elite inventory manager for a Malaysian SME retail store.
Today's date is {current_date}.
 
Decision rules:
1. Use BOTH current stock levels AND the sales forecast to make your decision.
2. If current_stock < reorder_threshold OR days_until_stockout <= 7
   → recommended_action = "reorder"
   Draft a polite supplier email to supplier_contact.
   Order quantity = enough to cover forecast_next_month PLUS reorder_threshold as safety buffer.
3. If forecast_trend = "declining" AND current_stock > (reorder_threshold * 2)
   → recommended_action = "discount"
   Draft a short internal memo recommending a markdown promotion to clear excess stock.
4. Otherwise → recommended_action = "none", draft_message = "".
 
Return ONLY a raw JSON object — no markdown, no ```json fences, no extra text.
JSON schema:
{{
  "item_name":           "<string>",
  "recommended_action":  "reorder" | "discount" | "none",
  "reason":              "<one sentence combining stock and forecast data>",
  "draft_message":       "<ready-to-send email or memo, or empty string>"
}}
"""
 
user_message = f"""USER QUERY: {user_query}
 
ITEM DATA:
  item_name          : {item_name}
  current_stock      : {current_stock}
  reorder_threshold  : {reorder_threshold}
  supplier_contact   : {supplier_contact}
  category           : {ctx.get('category')}
  status             : {ctx.get('status')}
 
SALES FORECAST (generated by Z.ai in prior step):
  forecast_next_week   : {forecast_next_week} units
  forecast_next_month  : {forecast_next_month} units
  forecast_confidence  : {forecast_confidence}
  forecast_trend       : {forecast_trend}
  days_until_stockout  : {days_until_stockout} days
  forecast_reasoning   : {forecast_reasoning}
 
Make a restocking decision for this item, factoring in both current stock and the forecast."""
 
print(f"  Calling ilmu.ai for restock decision ({ILMU_MODEL})...")

# STD VAR: ai_raw_response
ai_raw_response = call_ai(client, system_prompt, user_message,
                           temperature=0.1, max_tokens=8000)
 
print(f"\n  ai_raw_response =\n  {ai_raw_response}\n")
 
 
# ============================================================
# PHASE 4 — AGENTIC HANDOFF
# ============================================================
print("=" * 62)
print("PHASE 4 — AGENTIC HANDOFF")
print("=" * 62)
 
recommended_action = "none"   # STD VAR: recommended_action — default if AI call/parse fails
draft_message      = ""       # STD VAR: draft_message

try:
    _clean  = ai_raw_response.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    _parsed = json.loads(_clean)

    recommended_action = _parsed.get("recommended_action", "none")
    draft_message      = _parsed.get("draft_message", "")
    _reason            = _parsed.get("reason", "")
 
    print(f"  recommended_action  = \"{recommended_action}\"")
    print(f"  reason              = {_reason}")
    print(f"\n  → Trigger API       : {recommended_action.upper()} WORKFLOW")
 
    if draft_message:
        print(f"\n  draft_message (to: {supplier_contact}):\n")
        print("  " + "\n  ".join(draft_message.splitlines()))
    else:
        print(f"\n  draft_message = \"\"  (no action needed)")
 
except json.JSONDecodeError:
    print("  ERROR: ai_raw_response is not valid JSON.")
    print("  Raw output was:", ai_raw_response)
    print("  Fix: Tighten system_prompt or lower temperature.")
 
# ── Summary table printed for easy frontend consumption ──────
print("\n" + "=" * 62)
print("FORECAST + DECISION SUMMARY")
print("=" * 62)
print(f"  Item                : {item_name}")
print(f"  Current Stock       : {current_stock} units")
print(f"  Reorder Threshold   : {reorder_threshold} units")
print(f"  ─────────────────────────────────────────────────────")
print(f"  Forecast Next Week  : {forecast_next_week} units  ({forecast_trend}, {forecast_confidence} confidence)")
print(f"  Forecast Next Month : {forecast_next_month} units")
print(f"  Days Until Stockout : {days_until_stockout} days")
print(f"  ─────────────────────────────────────────────────────")
print(f"  Decision            : {recommended_action.upper()}")
print("=" * 62)
print("PIPELINE COMPLETE")
print("=" * 62)
