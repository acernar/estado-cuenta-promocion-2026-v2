from __future__ import annotations

from datetime import date
from decimal import Decimal

import pandas as pd
import streamlit as st

import database as db


st.set_page_config(page_title="Gaudium Vitae 2026", page_icon="🎓", layout="wide")


def money(value: object) -> str:
    return f"S/ {float(value or 0):,.2f}"


def header() -> None:
    st.title("GAUDIUM VITAE")
    st.caption("Sistema de Estado de Cuenta · Promoción 2026 – Sor Querubina")


def consultation() -> None:
    header()
    st.subheader("Consulta familiar")
    code = st.text_input("Código personal", type="password")
    if not st.button("Ver estado de cuenta", type="primary", use_container_width=True):
        return
    if not code.strip():
        st.warning("Ingrese su código personal.")
        return
    statement = db.public_statement(code)
    if not statement:
        st.error("Código incorrecto.")
        return

    st.subheader(statement["student"]["full_name"])
    a, b, c, d = st.columns(4)
    a.metric("Fondos acumulados", money(statement["summary"]["total_income"]))
    b.metric("Pagos aplicados", money(statement["summary"]["total_applied"]))
    c.metric("Reembolsos", money(statement["summary"]["total_refunds"]))
    d.metric("Fondos disponibles", money(statement["summary"]["available_funds"]))

    st.subheader("Compromisos")
    commitments = pd.DataFrame(statement["commitments"])
    if commitments.empty:
        st.info("No hay compromisos registrados.")
    else:
        commitments = commitments.rename(columns={
            "name": "Concepto", "target_amount": "Costo",
            "paid_amount": "Abonado", "pending_amount": "Pendiente"
        })
        st.dataframe(commitments, hide_index=True, use_container_width=True)

    with st.expander("Ver movimientos"):
        movements = pd.DataFrame(statement["movements"])
        if movements.empty:
            st.info("No hay movimientos registrados.")
        else:
            st.dataframe(movements, hide_index=True, use_container_width=True)


def login() -> None:
    header()
    st.subheader("Acceso de administración")
    with st.form("login"):
        email = st.text_input("Correo")
        password = st.text_input("Contraseña", type="password")
        submitted = st.form_submit_button("Ingresar", type="primary")
    if submitted:
        try:
            db.sign_in(email, password)
            if not db.is_admin():
                db.sign_out()
                st.error("Este usuario no tiene permiso de administración.")
            else:
                st.session_state.admin = True
                st.rerun()
        except Exception:
            st.error("No se pudo iniciar sesión. Revise el correo y la contraseña.")


def movement_form(students: list[dict], concepts: list[dict]) -> None:
    st.subheader("Registrar movimiento")
    if not students or not concepts:
        st.warning("Primero deben existir alumnos y conceptos activos.")
        return
    student_options = {f'{s["full_name"]} · {s["access_code"]}': s["id"] for s in students}
    concept_options = {f'{c["name"]} · {c["category"]}': c for c in concepts}
    with st.form("movement", clear_on_submit=True):
        student_label = st.selectbox("Alumno", student_options)
        concept_label = st.selectbox("Concepto", concept_options)
        selected_concept = concept_options[concept_label]
        expected_type = {
            "ahorro": "ingreso", "actividad": "ingreso",
            "compromiso": "aplicacion", "reembolso": "reembolso"
        }[selected_concept["category"]]
        st.caption(f"Tipo calculado automáticamente: {expected_type}")
        amount = st.number_input("Monto (S/)", min_value=0.01, step=1.0, format="%.2f")
        movement_date = st.date_input("Fecha", value=date.today())
        note = st.text_input("Observación")
        submitted = st.form_submit_button("Guardar movimiento", type="primary")
    if submitted:
        db.create_movement({
            "student_id": student_options[student_label],
            "concept_id": selected_concept["id"],
            "movement_type": expected_type,
            "amount": float(Decimal(str(amount))),
            "movement_date": movement_date.isoformat(),
            "note": note.strip() or None,
        })
        st.success("Movimiento registrado.")
        st.rerun()


def concept_form() -> None:
    st.subheader("Crear concepto")
    with st.form("concept", clear_on_submit=True):
        name = st.text_input("Nombre", placeholder="Ejemplo: 7ma cuota de fiesta")
        category = st.selectbox("Categoría", ["ahorro", "actividad", "compromiso", "reembolso"])
        target = st.number_input("Costo u objetivo (S/)", min_value=0.0, step=1.0, format="%.2f")
        description = st.text_input("Descripción")
        submitted = st.form_submit_button("Crear concepto", type="primary")
    if submitted:
        if not name.strip():
            st.warning("Ingrese un nombre.")
            return
        db.create_concept({
            "name": name.strip(), "category": category,
            "target_amount": float(Decimal(str(target))),
            "description": description.strip() or None,
        })
        st.success("Concepto creado. No fue necesario agregar ninguna columna.")
        st.rerun()


def admin() -> None:
    header()
    left, right = st.columns([5, 1])
    left.subheader("Administración")
    if right.button("Cerrar sesión"):
        db.sign_out()
        st.session_state.admin = False
        st.rerun()

    students = db.list_students()
    concepts = db.list_concepts()
    tab1, tab2, tab3, tab4 = st.tabs(["Registrar", "Movimientos", "Conceptos", "Descargar"])
    with tab1:
        movement_form(students, concepts)
    with tab2:
        movements = pd.DataFrame(db.list_movements())
        if movements.empty:
            st.info("No hay movimientos registrados.")
        else:
            st.dataframe(movements, hide_index=True, use_container_width=True)
        st.caption("Las correcciones se harán por anulación; nunca se borrará el historial.")
    with tab3:
        concept_form()
        st.dataframe(pd.DataFrame(db.list_concepts(False)), hide_index=True, use_container_width=True)
    with tab4:
        st.download_button(
            "Descargar respaldo completo en Excel", db.export_excel(),
            file_name=f"estado_cuenta_2026_{date.today().isoformat()}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary",
        )


if not db.configured():
    st.error("Falta conectar la nueva base de datos. Copie secrets.toml.example como secrets.toml y agregue las credenciales de Supabase.")
    st.stop()

area = st.sidebar.radio("Área", ["Consulta familiar", "Administración"])
if area == "Consulta familiar":
    consultation()
elif st.session_state.get("admin") and db.is_admin():
    admin()
else:
    login()

