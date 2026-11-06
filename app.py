from __future__ import annotations

from datetime import date
from decimal import Decimal

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

import database as db


st.set_page_config(page_title="Gaudium Vitae 2026", page_icon="🎓", layout="wide")


def money(value: object) -> str:
    return f"S/ {float(value or 0):,.2f}"


def header() -> None:
    st.title("GAUDIUM VITAE")
    st.caption("Sistema de Estado de Cuenta · Promoción 2026 – Sor Querubina")


def password_recovery() -> None:
    """La contraseña y el token viajan directo del navegador a Supabase."""
    header()
    st.subheader("Crear nueva contraseña")
    st.caption("La contraseña no se guarda en esta aplicación.")
    components.html(
        f"""
        <style>
          body {{ font-family: Arial, sans-serif; color: #f2f2f2; background: transparent; }}
          label {{ display:block; margin:14px 0 6px; }}
          input {{ width:100%; box-sizing:border-box; padding:12px; border-radius:8px;
                   border:1px solid #666; background:#262626; color:white; }}
          button {{ margin-top:18px; padding:12px 18px; border:0; border-radius:8px;
                    background:#b55b58; color:white; font-weight:bold; cursor:pointer; }}
          #message {{ margin-top:16px; line-height:1.4; }}
        </style>
        <label>Nueva contraseña</label>
        <input id="password" type="password" minlength="8" autocomplete="new-password">
        <label>Repetir contraseña</label>
        <input id="confirm" type="password" minlength="8" autocomplete="new-password">
        <button onclick="updatePassword()">Guardar contraseña</button>
        <div id="message"></div>
        <script>
          async function updatePassword() {{
            const message = document.getElementById('message');
            const password = document.getElementById('password').value;
            const confirm = document.getElementById('confirm').value;
            const params = new URLSearchParams(window.parent.location.hash.substring(1));
            const token = params.get('access_token');
            const type = params.get('type');
            if (!token || type !== 'recovery') {{
              message.textContent = 'El enlace no es válido o ya venció. Solicita uno nuevo.';
              return;
            }}
            if (password.length < 8) {{
              message.textContent = 'La contraseña debe tener al menos 8 caracteres.';
              return;
            }}
            if (password !== confirm) {{
              message.textContent = 'Las contraseñas no coinciden.';
              return;
            }}
            message.textContent = 'Guardando...';
            const response = await fetch('{st.secrets["SUPABASE_URL"]}/auth/v1/user', {{
              method: 'PUT',
              headers: {{
                'apikey': '{st.secrets["SUPABASE_ANON_KEY"]}',
                'Authorization': 'Bearer ' + token,
                'Content-Type': 'application/json'
              }},
              body: JSON.stringify({{password}})
            }});
            if (response.ok) {{
              window.parent.history.replaceState(null, '', '/');
              message.innerHTML = '<b>Contraseña actualizada.</b><br>Ya puedes entrar al área de Administración.';
              document.getElementById('password').value = '';
              document.getElementById('confirm').value = '';
            }} else {{
              const result = await response.json();
              message.textContent = result.message || 'No se pudo actualizar. Solicita un enlace nuevo.';
            }}
          }}
        </script>
        """,
        height=370,
    )


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
    a, b, c = st.columns(3)
    a.metric("Fondos acumulados", money(statement["summary"]["total_income"]))
    b.metric("Pagos aplicados", money(statement["summary"]["total_applied"]))
    c.metric("Reembolsos", money(statement["summary"]["total_refunds"]))
    d, e = st.columns(2)
    d.metric("Otros egresos", money(statement["summary"]["total_outflows"]))
    e.metric("Fondos disponibles", money(statement["summary"]["available_funds"]))

    st.subheader("Compromisos")
    commitments = pd.DataFrame(statement["commitments"])
    if commitments.empty:
        st.info("No hay compromisos registrados.")
    else:
        commitments = commitments.rename(columns={
            "name": "Concepto", "target_amount": "Costo",
            "paid_amount": "Abonado", "pending_amount": "Pendiente"
        })
        st.dataframe(
            commitments, hide_index=True, use_container_width=True,
            column_config={
                "Costo": st.column_config.NumberColumn(format="S/ %.2f"),
                "Abonado": st.column_config.NumberColumn(format="S/ %.2f"),
                "Pendiente": st.column_config.NumberColumn(format="S/ %.2f"),
            },
        )

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


def movement_form(students: list[dict]) -> None:
    st.subheader("Registrar movimiento")
    if not students:
        st.warning("Primero debe existir al menos un alumno.")
        return
    student_options = {f'{s["full_name"]} · {s["access_code"]}': s["id"] for s in students}
    student_label = st.selectbox("Alumno", student_options, key="movement_student")
    concepts = db.list_concepts_for_student(student_options[student_label])
    if not concepts:
        st.warning("El alumno no tiene conceptos disponibles.")
        return
    totals = db.concept_totals(student_options[student_label])
    concept_options = {
        f'{c["name"]} · registrado {money(totals.get(c["id"], 0))}': c
        for c in concepts
    }
    concept_label = st.selectbox("Concepto", concept_options, key="movement_concept")
    selected_concept = concept_options[concept_label]
    registered = totals.get(selected_concept["id"], 0.0)
    if selected_concept["category"] == "compromiso":
        target = db.commitment_target(student_options[student_label], selected_concept)
        st.info(
            f"Ya registrado: {money(registered)} · Costo: {money(target)} · "
            f"Pendiente: {money(max(target - registered, 0))}"
        )
    else:
        st.info(f"Ya registrado en este concepto: {money(registered)}")
    with st.form("movement", clear_on_submit=True):
        expected_type = {
            "ahorro": "ingreso", "actividad": "ingreso",
            "compromiso": "aplicacion", "reembolso": "reembolso", "egreso": "egreso"
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


def student_form() -> None:
    st.subheader("Registrar alumno")
    with st.form("student", clear_on_submit=True):
        code = st.text_input("Código personal")
        name = st.text_input("Apellidos y nombres")
        classroom = st.text_input("Aula")
        submitted = st.form_submit_button("Guardar alumno", type="primary")
    if submitted:
        if not code.strip() or not name.strip():
            st.warning("El código y el nombre son obligatorios.")
            return
        db.save_student({
            "access_code": code.strip(), "full_name": name.strip(),
            "classroom": classroom.strip() or None, "active": True,
        })
        st.success("Alumno guardado.")
        st.rerun()


def void_form(movements: list[dict]) -> None:
    active = [m for m in movements if m["status"] == "activo"]
    if not active:
        return
    labels = {
        f'{m["movement_date"]} · {m["student"]} · {m["concept"]} · {money(m["amount"])} · {m["id"][:8]}': m["id"]
        for m in active
    }
    with st.expander("Anular un movimiento"):
        with st.form("void"):
            selected = st.selectbox("Movimiento", labels)
            reason = st.text_input("Motivo de la anulación")
            submitted = st.form_submit_button("Anular movimiento")
        if submitted:
            if not reason.strip():
                st.warning("Indique el motivo.")
            else:
                db.void_movement(labels[selected], reason)
                st.success("Movimiento anulado; el historial se conservó.")
                st.rerun()


def concept_form() -> None:
    st.subheader("Crear concepto")
    with st.form("concept", clear_on_submit=True):
        name = st.text_input("Nombre", placeholder="Ejemplo: 7ma cuota de fiesta")
        category = st.selectbox(
            "Categoría", ["ahorro", "actividad", "compromiso", "reembolso", "egreso"]
        )
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


def participation_form(students: list[dict], concepts: list[dict]) -> None:
    st.subheader("Participantes por compromiso")
    commitments = [c for c in concepts if c["category"] == "compromiso"]
    if not commitments:
        st.info("Aún no hay compromisos creados.")
        return
    concept_by_label = {c["name"]: c for c in commitments}
    selected_label = st.selectbox("Compromiso", concept_by_label, key="participant_concept")
    selected = concept_by_label[selected_label]
    current = set(db.assigned_student_ids(selected["id"]))
    student_by_label = {f'{s["full_name"]} · {s["access_code"]}': s["id"] for s in students}
    defaults = [label for label, student_id in student_by_label.items() if student_id in current]
    with st.form("participants"):
        chosen = st.multiselect(
            "Alumnos que sí participan", student_by_label, default=defaults,
            help="Quienes no estén seleccionados no tendrán deuda por este compromiso.",
        )
        submitted = st.form_submit_button("Guardar participantes", type="primary")
    if submitted:
        db.save_participants(selected["id"], [student_by_label[label] for label in chosen])
        st.success("Participación actualizada.")
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
    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(
        ["Registrar", "Movimientos", "Alumnos", "Conceptos", "Participantes", "Descargar"]
    )
    with tab1:
        movement_form(students)
    with tab2:
        movement_rows = db.list_movements()
        movements = pd.DataFrame(movement_rows)
        if not movement_rows:
            st.info("No hay movimientos registrados.")
        else:
            st.dataframe(movements, hide_index=True, use_container_width=True)
            void_form(movement_rows)
        st.caption("Las correcciones se harán por anulación; nunca se borrará el historial.")
    with tab3:
        student_form()
        st.dataframe(pd.DataFrame(students), hide_index=True, use_container_width=True)
    with tab4:
        concept_form()
        st.dataframe(pd.DataFrame(db.list_concepts(False)), hide_index=True, use_container_width=True)
    with tab5:
        participation_form(students, concepts)
    with tab6:
        st.download_button(
            "Descargar respaldo completo en Excel", db.export_excel(),
            file_name=f"estado_cuenta_2026_{date.today().isoformat()}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary",
        )


if not db.configured():
    st.error("Falta conectar la nueva base de datos. Copie secrets.toml.example como secrets.toml y agregue las credenciales de Supabase.")
    st.stop()

if st.query_params.get("recovery") == "1":
    password_recovery()
    st.stop()

area = st.sidebar.radio("Área", ["Consulta familiar", "Administración"])
if area == "Consulta familiar":
    consultation()
elif st.session_state.get("admin") and db.is_admin():
    admin()
else:
    login()

