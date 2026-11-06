# Estado de Cuenta Promoción 2026 — V2

Proyecto nuevo e independiente. El sistema anterior no se modifica.

## Diseño

- Streamlit: consulta familiar y panel administrativo.
- Supabase/PostgreSQL: alumnos, conceptos y movimientos.
- Excel: solo importación inicial y descarga de respaldos.
- Una cuota, rifa o actividad nueva se registra como un concepto; nunca como una columna.

## Puesta en marcha

1. Crear un proyecto en Supabase.
2. Ejecutar `schema.sql` en el editor SQL de Supabase.
3. Crear el primer usuario en Authentication > Users.
4. Insertar su perfil administrativo usando el UUID del usuario:

```sql
insert into public.profiles (id, full_name, role)
values ('UUID-DEL-USUARIO', 'Administrador', 'admin');
```

5. Copiar `.streamlit/secrets.toml.example` como `.streamlit/secrets.toml` y colocar la URL y la clave pública `anon`.
6. Instalar dependencias y ejecutar:

```bash
python -m pip install -r requirements.txt
streamlit run app.py
```

Las claves privadas nunca deben guardarse en GitHub.

## Modelo mínimo

- `students`: un registro por alumno.
- `concepts`: un registro por ahorro, actividad, compromiso o reembolso.
- `student_concepts`: indica quiénes participan en cada compromiso; quien no está asignado no genera deuda.
- `movements`: un registro por operación.
- `profiles`: administradores autorizados.

Los totales y saldos se calculan desde los movimientos; no se almacenan en columnas repetidas.

