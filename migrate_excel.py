"""Migra el Excel histórico al modelo normalizado de Supabase.

Sin --apply solo analiza, reconcilia y muestra un resumen. No modifica el Excel.
"""
from __future__ import annotations

import argparse
import os
from collections import Counter
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from openpyxl import load_workbook
SOURCE_SHEET = "Hoja3"

# Cada columna histórica se convierte una sola vez en un concepto o movimiento.
ACTIVITIES = {
    "AE": "1ra actividad - Rifa",
    "AH": "2da actividad - Pollada",
    "AK": "3ra actividad - 2da rifa",
    "AL": "4ta actividad - 2da pollada",
    "AM": "5ta actividad - 3ra rifa",
    "AN": "6ta actividad",
}
COMMITMENTS = {
    "AP": ("Fiesta - 1ra y 2da cuota", Decimal("156.76")),
    "AR": ("Kit promocional - 1ra cuota", Decimal("156.00")),
    "AT": ("Fiesta - 3ra cuota", Decimal("195.00")),
    "AV": ("Kit promocional - 2da cuota", Decimal("113.00")),
    "AZ": ("Fiesta - 4ta cuota", Decimal("195.00")),
    "BD": ("Anuario", Decimal("370.50")),
    "BF": ("Fiesta - 5ta cuota", Decimal("214.62")),
    "BG": ("Fiesta - 6ta cuota", Decimal("170.32")),
    "BH": ("Anuario - 2do abono", Decimal("185.00")),
    "BI": ("Graduación", Decimal("300.00")),
}
CASH_DEPOSITS = {
    "AQ": "Abono efectivo - Fiesta 1ra y 2da cuota",
    "AS": "Abono efectivo - Kit 1ra cuota",
    "AU": "Abono efectivo - Fiesta 3ra cuota",
    "AW": "Abono efectivo - Kit 2da cuota",
    "AY": "Abono efectivo 5",
    "BA": "Abono efectivo - Fiesta 4ta cuota",
    "BC": "Abono efectivo 7",
    "BE": "Abono efectivo 8",
}
REFUNDS = {"AX": "Devolución", "BB": "Devolución junio-julio-agosto"}


def decimal_value(value: Any) -> Decimal:
    if value in (None, ""):
        return Decimal("0")
    try:
        return Decimal(str(value))
    except Exception:
        return Decimal("0")


def movement(student_code: str, concept: str, category: str, kind: str,
             amount: Decimal, movement_date: date, note: str) -> dict[str, Any]:
    return {
        "student_code": student_code,
        "concept": concept,
        "category": category,
        "movement_type": kind,
        "amount": amount.quantize(Decimal("0.01")),
        "movement_date": movement_date,
        "note": note,
    }


def extract(path: Path) -> dict[str, Any]:
    values = load_workbook(path, data_only=True, read_only=False)[SOURCE_SHEET]
    students: list[dict[str, Any]] = []
    movements: list[dict[str, Any]] = []
    participants: list[dict[str, Any]] = []
    discrepancies: list[dict[str, Any]] = []
    source_date = datetime.fromtimestamp(path.stat().st_mtime).date()

    rows = [r for r in range(2, values.max_row + 1)
            if values[f"B{r}"].value not in (None, "") and values[f"BK{r}"].value not in (None, "")]

    for row in rows:
        code = str(values[f"BK{row}"].value).strip()
        students.append({
            "access_code": code,
            "full_name": str(values[f"B{row}"].value).strip(),
            "classroom": str(values[f"C{row}"].value or "").strip() or None,
            "active": True,
        })

        # Ahorros mensuales: D:AA. La fecha proviene del encabezado.
        for col in range(4, 28):
            cell = values.cell(row, col)
            amount = decimal_value(cell.value)
            if amount > 0:
                header = values.cell(1, col).value
                month = header.date() if isinstance(header, datetime) else source_date
                movements.append(movement(
                    code, f"Ahorro {month:%Y-%m}", "ahorro", "ingreso",
                    amount, month, f"Migrado de {cell.coordinate}",
                ))

        for col, name in ACTIVITIES.items():
            amount = decimal_value(values[f"{col}{row}"].value)
            if amount > 0:
                movements.append(movement(code, name, "actividad", "ingreso", amount,
                                          source_date, f"Migrado de {col}{row}"))
            elif amount < 0:
                movements.append(movement(code, f"Ajuste: {name}", "egreso", "egreso",
                                          abs(amount), source_date, f"Migrado de {col}{row}"))

        for col, (name, target) in COMMITMENTS.items():
            raw = values[f"{col}{row}"].value
            if raw not in (None, ""):
                participants.append({
                    "student_code": code, "concept": name,
                    "target_amount": target, "active": True,
                })
                amount = decimal_value(raw)
                if amount > 0:
                    movements.append(movement(code, name, "compromiso", "aplicacion",
                                              amount, source_date, f"Migrado de {col}{row}"))

        for col, name in CASH_DEPOSITS.items():
            amount = decimal_value(values[f"{col}{row}"].value)
            if amount > 0:
                movements.append(movement(code, name, "ahorro", "ingreso", amount,
                                          source_date, f"Migrado de {col}{row}"))

        for col, name in REFUNDS.items():
            amount = decimal_value(values[f"{col}{row}"].value)
            if amount > 0:
                movements.append(movement(code, name, "reembolso", "reembolso", amount,
                                          source_date, f"Migrado de {col}{row}"))

        imported_balance = sum(
            m["amount"] if m["movement_type"] == "ingreso" else -m["amount"]
            for m in movements if m["student_code"] == code
        )
        excel_balance = decimal_value(values[f"BJ{row}"].value)
        difference = imported_balance - excel_balance
        if abs(difference) > Decimal("0.02"):
            discrepancies.append({
                "row": row, "code": code,
                "excel": excel_balance, "imported": imported_balance,
                "difference": difference,
            })

    return {
        "students": students,
        "movements": movements,
        "participants": participants,
        "discrepancies": discrepancies,
    }


def apply_to_supabase(data: dict[str, Any]) -> None:
    from supabase import create_client

    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    admin_user_id = os.environ.get("MIGRATION_ADMIN_USER_ID")
    if not url or not key or not admin_user_id:
        raise SystemExit(
            "Faltan SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY o MIGRATION_ADMIN_USER_ID."
        )
    client = create_client(url, key)
    client.table("students").upsert(data["students"], on_conflict="access_code").execute()
    student_rows = client.table("students").select("id,access_code").execute().data
    student_ids = {row["access_code"]: row["id"] for row in student_rows}

    concept_specs: dict[tuple[str, str], Decimal] = {}
    for m in data["movements"]:
        concept_specs[(m["concept"], m["category"])] = Decimal("0")
    for name, target in COMMITMENTS.values():
        concept_specs[(name, "compromiso")] = target
    concepts = [{"name": name, "category": category, "target_amount": float(target)}
                for (name, category), target in concept_specs.items()]
    client.table("concepts").upsert(concepts, on_conflict="name,category").execute()
    concept_rows = client.table("concepts").select("id,name,category").execute().data
    concept_ids = {(row["name"], row["category"]): row["id"] for row in concept_rows}

    assignments = [{
        "student_id": student_ids[p["student_code"]],
        "concept_id": concept_ids[(p["concept"], "compromiso")],
        "target_amount": float(p["target_amount"]), "active": True,
    } for p in data["participants"]]
    if assignments:
        client.table("student_concepts").upsert(
            assignments, on_conflict="student_id,concept_id"
        ).execute()

    existing_notes = {
        row["note"] for row in client.table("movements").select("note")
        .like("note", "Migrado de %").execute().data
    }
    rows = [{
        "student_id": student_ids[m["student_code"]],
        "concept_id": concept_ids[(m["concept"], m["category"])],
        "movement_type": m["movement_type"], "amount": float(m["amount"]),
        "movement_date": m["movement_date"].isoformat(), "note": m["note"],
        "created_by": admin_user_id,
    } for m in data["movements"] if m["note"] not in existing_notes]
    for start in range(0, len(rows), 500):
        client.table("movements").insert(rows[start:start + 500]).execute()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("excel", type=Path)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    data = extract(args.excel)
    categories = Counter(m["movement_type"] for m in data["movements"])
    print(f"Alumnos: {len(data['students'])}")
    print(f"Participaciones: {len(data['participants'])}")
    print(f"Movimientos: {len(data['movements'])} {dict(categories)}")
    print(f"Diferencias de conciliación: {len(data['discrepancies'])}")
    for item in data["discrepancies"][:10]:
        print("  ", item)
    if data["discrepancies"]:
        raise SystemExit("La conciliación no pasó. No se aplicó la migración.")
    if args.apply:
        apply_to_supabase(data)
        print("Migración aplicada correctamente.")
    else:
        print("Análisis completado. Use --apply únicamente después de revisar el resultado.")


if __name__ == "__main__":
    main()

