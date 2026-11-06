from __future__ import annotations

from io import BytesIO
from typing import Any

import pandas as pd
import streamlit as st
from supabase import Client, create_client


@st.cache_resource
def get_client() -> Client:
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_ANON_KEY"])


def configured() -> bool:
    return "SUPABASE_URL" in st.secrets and "SUPABASE_ANON_KEY" in st.secrets


def public_statement(access_code: str) -> dict[str, Any] | None:
    result = get_client().rpc(
        "get_student_statement", {"p_access_code": access_code.strip()}
    ).execute()
    return result.data or None


def sign_in(email: str, password: str) -> Any:
    return get_client().auth.sign_in_with_password({"email": email, "password": password})


def sign_out() -> None:
    get_client().auth.sign_out()


def is_admin() -> bool:
    user = get_client().auth.get_user().user
    if not user:
        return False
    rows = (
        get_client()
        .table("profiles")
        .select("role,active")
        .eq("id", user.id)
        .limit(1)
        .execute()
        .data
    )
    return bool(rows and rows[0]["active"] and rows[0]["role"] == "admin")


def list_students(search: str = "") -> list[dict[str, Any]]:
    query = get_client().table("students").select("id,access_code,full_name,classroom,active")
    if search.strip():
        query = query.ilike("full_name", f"%{search.strip()}%")
    return query.order("full_name").execute().data


def list_concepts(active_only: bool = True) -> list[dict[str, Any]]:
    query = get_client().table("concepts").select("*")
    if active_only:
        query = query.eq("active", True)
    return query.order("category").order("name").execute().data


def create_concept(data: dict[str, Any]) -> None:
    get_client().table("concepts").insert(data).execute()


def assigned_student_ids(concept_id: str) -> list[str]:
    rows = (
        get_client().table("student_concepts").select("student_id")
        .eq("concept_id", concept_id).eq("active", True).execute().data
    )
    return [row["student_id"] for row in rows]


def save_participants(concept_id: str, student_ids: list[str]) -> None:
    client = get_client()
    client.table("student_concepts").update({"active": False}).eq(
        "concept_id", concept_id
    ).execute()
    if student_ids:
        client.table("student_concepts").upsert(
            [{"concept_id": concept_id, "student_id": student_id, "active": True}
             for student_id in student_ids],
            on_conflict="student_id,concept_id",
        ).execute()


def create_movement(data: dict[str, Any]) -> None:
    get_client().table("movements").insert(data).execute()


def list_movements(student_id: str | None = None) -> list[dict[str, Any]]:
    query = get_client().table("movement_detail").select("*")
    if student_id:
        query = query.eq("student_id", student_id)
    return query.order("movement_date", desc=True).order("created_at", desc=True).execute().data


def void_movement(movement_id: str, reason: str) -> None:
    get_client().rpc(
        "void_movement", {"p_movement_id": movement_id, "p_reason": reason.strip()}
    ).execute()


def export_excel() -> bytes:
    students = pd.DataFrame(list_students())
    concepts = pd.DataFrame(list_concepts(active_only=False))
    movements = pd.DataFrame(list_movements())
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        students.to_excel(writer, sheet_name="Alumnos", index=False)
        concepts.to_excel(writer, sheet_name="Conceptos", index=False)
        movements.to_excel(writer, sheet_name="Movimientos", index=False)
    return output.getvalue()

