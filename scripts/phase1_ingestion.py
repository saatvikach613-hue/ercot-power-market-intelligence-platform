"""
Phase 1: Data ingestion, cleaning, validation, and DuckDB load.
Executed by notebooks/01_ingestion_and_validation.ipynb (nbconvert) or directly.
"""
from __future__ import annotations

import re
import warnings
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parent

# --- EIA Texas generation (wide format) ---
PRIMARY_FUELS = {
    "coal": "coal",
    "natural gas": "natural_gas",
    "nuclear": "nuclear",
    "conventional hydroelectric": "hydro",
    "wind": "wind",
    "all solar": "solar",
}

OTHER_FUEL_KEYS = [
    "petroleum liquids",
    "petroleum coke",
    "other gases",
    "biomass",
    "wood and wood-derived fuels",
    "other biomass",
    "other",
    "all utility-scale solar",  # only if all solar missing; prefer TSN row
]

ZONE_RENAME = {
    "FAR_WEST": "FWEST",
    "NORTH_C": "NCENT",
    "SOUTHERN": "SOUTH",
    "SOUTH_C": "SCENT",
    "Hour_End": "datetime",
    "Hour Ending": "datetime",
    "ERCOT": "TOTAL",
}

CORE_START_YEAR = 2015
CORE_END_YEAR = 2024

LOAD_ZONE_COLS = [
    "COAST", "EAST", "FWEST", "FAR_WEST", "NORTH", "NCENT", "NORTH_C",
    "SOUTH", "SOUTHERN", "SCENT", "SOUTH_C", "WEST", "TOTAL", "ERCOT",
]


def _extract_year_from_load_path(path: Path) -> int:
    name = path.stem.lower()
    m = re.search(r"(\d{4})", name)
    if not m:
        raise ValueError(f"Cannot parse year from load file: {path.name}")
    return int(m.group(1))


def _parse_ercot_hour_ending(values: pd.Series) -> pd.Series:
    """Parse ERCOT hour-ending timestamps, including 24:00 and DST labels."""
    as_text = values.astype(str).str.strip().str.replace(" DST", "", regex=False)
    is_24 = as_text.str.endswith("24:00")

    parsed = pd.to_datetime(values, errors="coerce")

    if is_24.any():
        midnight_text = as_text[is_24].str.replace("24:00", "00:00", regex=False)
        parsed.loc[is_24] = pd.to_datetime(midnight_text, errors="coerce")

    still_missing = parsed.isna()
    if still_missing.any():
        parsed.loc[still_missing] = pd.to_datetime(as_text[still_missing], errors="coerce")

    return parsed.dt.round("h")


def clean_eia_generation() -> pd.DataFrame:
    path = ROOT / "data/raw/eia_texas_generation.csv"
    raw = pd.read_csv(path, skiprows=4)
    raw = raw.rename(columns={"description": "fuel_label"})
    raw["fuel_label"] = raw["fuel_label"].astype(str).str.strip('"')

    texas = raw[raw["fuel_label"].str.startswith("Texas :", na=False)].copy()
    print(f"EIA Texas rows (fuel series): {len(texas)}")
    print(texas["fuel_label"].tolist())

    month_cols = [c for c in texas.columns if re.match(r"^[A-Za-z]{3} \d{4}$", str(c).strip('"'))]
    id_vars = ["fuel_label", "units", "source key"] if "source key" in texas.columns else ["fuel_label", "units"]

    long = texas.melt(id_vars=[c for c in id_vars if c in texas.columns], value_vars=month_cols,
                        var_name="month_label", value_name="generation_thousand_mwh")
    long["month_label"] = long["month_label"].astype(str).str.strip('"')
    long["generation_thousand_mwh"] = (
        long["generation_thousand_mwh"]
        .replace(["--", "NM", ""], np.nan)
        .astype(str)
        .str.replace(",", "", regex=False)
    )
    long["generation_thousand_mwh"] = pd.to_numeric(long["generation_thousand_mwh"], errors="coerce")
    long = long.dropna(subset=["generation_thousand_mwh"])
    long = long[long["generation_thousand_mwh"] > 0]

    long["date"] = pd.to_datetime(long["month_label"], format="%b %Y")
    long["year"] = long["date"].dt.year.astype(int)
    long["month"] = long["date"].dt.month.astype(int)
    long["generation_mwh"] = long["generation_thousand_mwh"] * 1000.0

    long["fuel_key"] = (
        long["fuel_label"]
        .str.replace("Texas :", "", regex=False)
        .str.strip()
        .str.lower()
    )

    mapped = []
    for fk, g in long.groupby(["year", "month", "date"]):
        year, month, date = fk
        rows = g.set_index("fuel_key")["generation_mwh"]
        record = {"year": year, "month": month, "date": date}
        for eia_name, std in PRIMARY_FUELS.items():
            if eia_name in rows.index:
                record[std] = rows[eia_name]
        other_parts = [rows[k] for k in OTHER_FUEL_KEYS if k in rows.index and k != "all utility-scale solar"]
        if other_parts:
            record["other"] = sum(other_parts)
        mapped.append(record)

    wide = pd.DataFrame(mapped)
    for col in ["coal", "natural_gas", "nuclear", "hydro", "wind", "solar", "other"]:
        if col not in wide.columns:
            wide[col] = 0.0
        wide[col] = wide[col].fillna(0.0)

    parts = []
    for _, row in wide.iterrows():
        for fuel in ["coal", "natural_gas", "nuclear", "hydro", "wind", "solar", "other"]:
            val = row[fuel]
            if val and val > 0:
                parts.append({
                    "date": row["date"],
                    "year": int(row["year"]),
                    "month": int(row["month"]),
                    "fuel_type": fuel,
                    "generation_mwh": float(val),
                })

    gen = pd.DataFrame(parts)
    gen = gen[(gen["year"] >= 2015) & (gen["year"] <= 2024)].copy()

    monthly_totals = gen.groupby(["year", "month"])["generation_mwh"].transform("sum")
    gen["pct_of_total_monthly"] = (gen["generation_mwh"] / monthly_totals * 100).round(4)

    print(f"Generation clean shape: {gen.shape}")
    print(f"Year range: {gen['year'].min()}–{gen['year'].max()}")
    print("Fuel types:", sorted(gen["fuel_type"].unique()))
    return gen


def clean_ercot_load() -> pd.DataFrame:
    load_dir = ROOT / "data/raw/ercot_load"
    frames = []
    paths = sorted(list(load_dir.glob("*.xls")) + list(load_dir.glob("*.xlsx")))
    paths = [p for p in paths if not p.name.startswith(".")]

    for filepath in paths:
        year = _extract_year_from_load_path(filepath)
        if year < CORE_START_YEAR or year > CORE_END_YEAR:
            print(f"  Skipping {filepath.name}: outside core analysis window {CORE_START_YEAR}-{CORE_END_YEAR}")
            continue
        engine = "xlrd" if filepath.suffix.lower() == ".xls" else "openpyxl"
        xls = pd.ExcelFile(filepath, engine=engine)
        sheet = xls.sheet_names[0]
        df = xls.parse(sheet)
        df.columns = [str(c).strip() for c in df.columns]

        dt_col = None
        for c in df.columns:
            if c.lower().replace(" ", "_") in ("hour_end", "hour_ending"):
                dt_col = c
                break
        if dt_col is None:
            dt_col = df.columns[0]

        df = df.rename(columns={dt_col: "datetime"})
        for old, new in ZONE_RENAME.items():
            if old in df.columns and new not in df.columns:
                df = df.rename(columns={old: new})

        zone_cols = [c for c in df.columns if c != "datetime"]

        df["datetime"] = _parse_ercot_hour_ending(df["datetime"])
        df = df.dropna(subset=["datetime"])
        df["year"] = df["datetime"].dt.year.astype(int)
        df["month"] = df["datetime"].dt.month.astype(int)
        df["day"] = df["datetime"].dt.day.astype(int)
        df["hour"] = df["datetime"].dt.hour.astype(int)

        long = df.melt(id_vars=["datetime", "year", "month", "day", "hour"], value_vars=zone_cols,
                       var_name="zone", value_name="load_mw")
        long["load_mw"] = pd.to_numeric(long["load_mw"], errors="coerce")
        long = long.dropna(subset=["load_mw"])
        long["zone"] = long["zone"].replace({"ERCOT": "TOTAL", "FAR_WEST": "FWEST", "NORTH_C": "NCENT",
                                            "SOUTHERN": "SOUTH", "SOUTH_C": "SCENT"})
        frames.append(long)
        print(f"  Year {year}: {len(long):,} rows, zones: {sorted(long['zone'].unique())}")

    load = pd.concat(frames, ignore_index=True)
    load = load.sort_values("datetime").reset_index(drop=True)

    print(f"\nCombined load: {load.shape}")
    print(f"Date range: {load['datetime'].min()} to {load['datetime'].max()}")
    print(f"Unique zones: {sorted(load['zone'].unique())}")
    print(f"Load MW min/max: {load['load_mw'].min():,.0f} / {load['load_mw'].max():,.0f}")
    neg = (load["load_mw"] < 0).sum()
    extreme = (load["load_mw"] > 90000).sum()
    print(f"Negative values: {neg}, >90,000 MW: {extreme}")

    return load


def clean_gas_prices() -> pd.DataFrame:
    path = ROOT / "data/raw/Henry_Hub_Natural_Gas_Spot_Price.csv"
    raw = pd.read_csv(path, skiprows=4)
    raw.columns = [c.strip() for c in raw.columns]
    day_col = raw.columns[0]
    price_col = raw.columns[1]
    raw = raw.rename(columns={day_col: "date", price_col: "price"})
    raw["date"] = pd.to_datetime(raw["date"], errors="coerce")
    raw["price"] = pd.to_numeric(raw["price"].replace("NA", np.nan), errors="coerce")
    raw = raw.dropna(subset=["date", "price"])
    raw["year"] = raw["date"].dt.year.astype(int)
    raw["month"] = raw["date"].dt.month.astype(int)

    monthly = (
        raw.groupby(["year", "month"], as_index=False)
        .agg(
            date=("date", "max"),
            monthly_avg=("price", "mean"),
            monthly_min=("price", "min"),
            monthly_max=("price", "max"),
        )
    )
    monthly = monthly[(monthly["year"] >= 2015) & (monthly["year"] <= 2024)]
    print(f"Gas prices monthly rows: {len(monthly)}")
    print(f"Date range: {monthly['date'].min().date()} to {monthly['date'].max().date()}")
    print(f"Price range: ${monthly['monthly_avg'].min():.2f} – ${monthly['monthly_avg'].max():.2f}/MMBtu")
    return monthly


def build_uri_tables(load_clean: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    uri = load_clean[(load_clean["year"] == 2021) & (load_clean["month"] == 2)].copy()
    baseline = load_clean[(load_clean["month"] == 2) & (load_clean["year"].isin([2019, 2020]))].copy()
    print(f"Uri period rows: {len(uri)}")
    print(f"Baseline Feb rows: {len(baseline)}")
    total_uri = uri[uri["zone"] == "TOTAL"]
    if len(total_uri) > 0:
        print(f"Uri peak load (TOTAL): {total_uri['load_mw'].max():,.0f} MW")
        print(f"Uri min load (TOTAL): {total_uri['load_mw'].min():,.0f} MW")
    base_total = baseline[baseline["zone"] == "TOTAL"]
    if len(base_total) > 0:
        print(f"Baseline Feb avg load (TOTAL): {base_total['load_mw'].mean():,.0f} MW")
    return uri, baseline


def load_duckdb(gen: pd.DataFrame, load: pd.DataFrame, gas: pd.DataFrame, uri: pd.DataFrame) -> duckdb.DuckDBPyConnection:
    db_path = ROOT / "ercot_intelligence.db"
    if db_path.exists():
        db_path.unlink()
    conn = duckdb.connect(str(db_path))

    conn.register("gen_clean", gen)
    conn.register("load_clean", load)
    conn.register("gas_clean", gas)
    conn.register("uri_load", uri)

    for stmt in [
        "DROP TABLE IF EXISTS ercot_generation",
        "DROP TABLE IF EXISTS ercot_load",
        "DROP TABLE IF EXISTS gas_prices",
        "DROP TABLE IF EXISTS storm_uri_load",
        "CREATE TABLE ercot_generation AS SELECT * FROM gen_clean",
        "CREATE TABLE ercot_load AS SELECT * FROM load_clean",
        "CREATE TABLE gas_prices AS SELECT * FROM gas_clean",
        "CREATE TABLE storm_uri_load AS SELECT * FROM uri_load",
    ]:
        conn.execute(stmt)

    print("\nDuckDB tables created:")
    for table in ["ercot_generation", "ercot_load", "gas_prices", "storm_uri_load"]:
        n = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        print(f"  {table}: {n:,} rows")
    return conn


def run_validation(conn: duckdb.DuckDBPyConnection) -> list[tuple[str, pd.DataFrame | str]]:
    validation_results: list[tuple[str, pd.DataFrame | str]] = []

    for table, date_col in [
        ("ercot_generation", "date"),
        ("ercot_load", "datetime"),
        ("gas_prices", "date"),
    ]:
        result = conn.execute(f"""
            SELECT '{table}' AS table_name,
                   MIN({date_col}) AS earliest,
                   MAX({date_col}) AS latest,
                   COUNT(*) AS total_rows,
                   COUNT(DISTINCT EXTRACT(YEAR FROM CAST({date_col} AS TIMESTAMP))) AS years_covered
            FROM {table}
        """).df()
        print(result.to_string(index=False))
        validation_results.append((f"Date range - {table}", result))

    null_check = conn.execute("""
        SELECT
            SUM(CASE WHEN generation_mwh IS NULL THEN 1 ELSE 0 END) AS null_generation,
            SUM(CASE WHEN fuel_type IS NULL THEN 1 ELSE 0 END) AS null_fuel_type,
            SUM(CASE WHEN year IS NULL THEN 1 ELSE 0 END) AS null_year,
            SUM(CASE WHEN pct_of_total_monthly IS NULL THEN 1 ELSE 0 END) AS null_pct
        FROM ercot_generation
    """).df()
    print("\nNull check — ercot_generation:")
    print(null_check.to_string(index=False))
    validation_results.append(("Null check - ercot_generation", null_check))

    fuel_dist = conn.execute("""
        SELECT fuel_type,
               COUNT(*) AS months,
               ROUND(SUM(generation_mwh) / 1e6, 2) AS total_twh,
               ROUND(AVG(pct_of_total_monthly), 2) AS avg_monthly_share_pct
        FROM ercot_generation
        GROUP BY fuel_type
        ORDER BY total_twh DESC
    """).df()
    print("\nFuel type distribution:")
    print(fuel_dist.to_string(index=False))
    validation_results.append(("Fuel type distribution", fuel_dist))

    pct_check = conn.execute("""
        SELECT year, month,
               ROUND(SUM(pct_of_total_monthly), 1) AS total_pct
        FROM ercot_generation
        GROUP BY year, month
        HAVING ABS(SUM(pct_of_total_monthly) - 100) > 2
        ORDER BY year, month
    """).df()
    if len(pct_check) > 0:
        print("\nWARNING: months where pct does not sum to ~100%:")
        print(pct_check.to_string(index=False))
        validation_results.append(("Monthly percentage warnings", pct_check))
    else:
        pct_pass = "PASS: All monthly percentages sum to approximately 100%"
        print(f"\n{pct_pass}")
        validation_results.append(("Monthly percentage check", pct_pass))

    load_check = conn.execute("""
        SELECT
            MIN(load_mw) AS min_load,
            MAX(load_mw) AS max_load,
            AVG(load_mw) AS avg_load,
            SUM(CASE WHEN load_mw < 0 THEN 1 ELSE 0 END) AS negative_values,
            SUM(CASE WHEN load_mw > 90000 THEN 1 ELSE 0 END) AS extreme_values
        FROM ercot_load
        WHERE zone = 'TOTAL'
    """).df()
    print("\nLoad sanity (zone=TOTAL):")
    print(load_check.to_string(index=False))
    validation_results.append(("Load sanity - zone TOTAL", load_check))

    year_coverage = conn.execute("""
        SELECT year,
               COUNT(DISTINCT month) AS months_present,
               COUNT(DISTINCT fuel_type) AS fuel_types_present
        FROM ercot_generation
        GROUP BY year
        ORDER BY year
    """).df()
    print("\nGeneration year coverage:")
    print(year_coverage.to_string(index=False))
    validation_results.append(("Generation year coverage", year_coverage))

    return validation_results


def run_gate_check(conn: duckdb.DuckDBPyConnection) -> bool:
    print("=" * 60)
    print("PHASE 1 GATE CHECK")
    print("=" * 60)

    checks = {}
    tables = conn.execute("""
        SELECT table_name FROM information_schema.tables
        WHERE table_schema = 'main'
    """).df()["table_name"].tolist()
    checks["all_tables_exist"] = all(
        t in tables for t in ["ercot_generation", "ercot_load", "gas_prices", "storm_uri_load"]
    )

    year_range = conn.execute("SELECT MIN(year), MAX(year) FROM ercot_generation").fetchone()
    checks["generation_year_range"] = year_range == (2015, 2024)

    fuel_types = conn.execute(
        "SELECT DISTINCT fuel_type FROM ercot_generation ORDER BY fuel_type"
    ).df()["fuel_type"].tolist()
    expected_fuels = ["coal", "hydro", "natural_gas", "nuclear", "other", "solar", "wind"]
    checks["all_fuel_types"] = sorted(fuel_types) == expected_fuels
    checks["no_null_generation"] = conn.execute(
        "SELECT COUNT(*) FROM ercot_generation WHERE generation_mwh IS NULL"
    ).fetchone()[0] == 0

    load_years = conn.execute("SELECT COUNT(DISTINCT year) FROM ercot_load").fetchone()[0]
    load_range = conn.execute("SELECT MIN(year), MAX(year) FROM ercot_load").fetchone()
    checks["load_year_coverage"] = load_years == 10 and load_range == (2015, 2024)

    gas_rows = conn.execute("SELECT COUNT(*) FROM gas_prices").fetchone()[0]
    checks["gas_prices_loaded"] = gas_rows > 100

    uri_rows = conn.execute("SELECT COUNT(*) FROM storm_uri_load").fetchone()[0]
    checks["uri_data_loaded"] = uri_rows > 600

    processed_files = [
        "data/processed/generation_clean.csv",
        "data/processed/load_clean.csv",
        "data/processed/gas_prices_clean.csv",
        "data/processed/storm_uri_clean.csv",
    ]
    checks["processed_files_saved"] = all((ROOT / f).exists() for f in processed_files)
    checks["quality_report_saved"] = (ROOT / "outputs/data_quality_report.txt").exists()

    print("\nGate check results:")
    all_passed = True
    for name, passed in checks.items():
        status = "PASS" if passed else "FAIL"
        print(f"  [{status}] {name}")
        if not passed:
            all_passed = False

    print("\n" + "=" * 60)
    if all_passed:
        print("ALL PHASE 1 CHECKS PASSED")
        gen_rows = conn.execute("SELECT COUNT(*) FROM ercot_generation").fetchone()[0]
        load_rows = conn.execute("SELECT COUNT(*) FROM ercot_load").fetchone()[0]
        print(f"  ercot_generation: {gen_rows:,} rows")
        print(f"  ercot_load: {load_rows:,} rows")
        print(f"  gas_prices: {gas_rows:,} rows")
        print(f"  storm_uri_load: {uri_rows:,} rows")
        print(f"  Fuel types: {fuel_types}")
        print(f"  Generation year range: {year_range[0]}–{year_range[1]}")
        print(f"  Load year range: {load_range[0]}–{load_range[1]}")
    else:
        print("PHASE 1 HAS FAILING CHECKS — DO NOT PROCEED")
    print("=" * 60)
    return all_passed


def main() -> None:
    print("PHASE 1 — Data ingestion and validation\n")
    print("Environment versions:")
    print(f"  duckdb: {duckdb.__version__}")
    print(f"  pandas: {pd.__version__}")
    print(f"  numpy: {np.__version__}")

    required_files = [
        ROOT / "data/raw/eia_texas_generation.csv",
        ROOT / "data/raw/Henry_Hub_Natural_Gas_Spot_Price.csv",
    ]
    print("\nRequired raw files:")
    for required_file in required_files:
        exists = required_file.exists()
        size_kb = required_file.stat().st_size / 1024 if exists else 0
        print(f"  {required_file.relative_to(ROOT)}: {'OK' if exists else 'MISSING'} ({size_kb:.1f} KB)")

    load_files = sorted((ROOT / "data/raw/ercot_load").glob("*.xls*"))
    print(f"  data/raw/ercot_load/*.xls*: {len(load_files)} files found")
    core_load_years = sorted({_extract_year_from_load_path(path) for path in load_files if 2015 <= _extract_year_from_load_path(path) <= 2024})
    print(f"  Core load years present: {core_load_years}\n")

    gen = clean_eia_generation()
    gen.to_csv(ROOT / "data/processed/generation_clean.csv", index=False)
    print(f"Saved generation_clean.csv: {len(gen)} rows\n")

    print("Loading ERCOT hourly load files...")
    load = clean_ercot_load()
    load.to_csv(ROOT / "data/processed/load_clean.csv", index=False)
    print(f"Saved load_clean.csv: {len(load)} rows\n")

    gas = clean_gas_prices()
    gas.to_csv(ROOT / "data/processed/gas_prices_clean.csv", index=False)
    print(f"Saved gas_prices_clean.csv: {len(gas)} rows\n")

    uri, _ = build_uri_tables(load)
    uri.to_csv(ROOT / "data/processed/storm_uri_clean.csv", index=False)
    print(f"Saved storm_uri_clean.csv: {len(uri)} rows\n")

    conn = load_duckdb(gen, load, gas, uri)
    validation_results = run_validation(conn)

    report_path = ROOT / "outputs/data_quality_report.txt"
    with open(report_path, "w") as f:
        f.write("ERCOT Power Market Intelligence — Data Quality Report\n")
        f.write("=" * 60 + "\n\n")
        for title, result in validation_results:
            f.write(title + "\n")
            f.write("-" * len(title) + "\n")
            if isinstance(result, pd.DataFrame):
                f.write(result.to_string(index=False) + "\n\n")
            else:
                f.write(result + "\n\n")
        f.write("Report generated successfully\n")
    print(f"\nData quality report saved to {report_path}")

    run_gate_check(conn)
    conn.close()


if __name__ == "__main__":
    main()
