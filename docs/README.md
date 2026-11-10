# MRP — Ruta de Proceso

> Planeación de producción para una planta acerera: convierte pedidos dispersos en un plan realista, considerando la capacidad, la disponibilidad y la merma de cada equipo de la ruta.

El sistema responde una pregunta: **¿cuándo puede entregar la planta cada pedido?** Modela la ruta de producción completa (de la materia prima al producto terminado), descuenta los festivos, mantenimientos e interrupciones de cada equipo, y asigna la capacidad semana por semana.

📘 **Manual de usuario (en español):** [`docs/MANUAL.txt`](docs/MANUAL.txt). Explica cada pestaña, un ejemplo completo, la demostración de septiembre y la solución de problemas.

---

## Funcionalidades

- **Equipos y ruta de producción:** capacidad mensual, semanas disponibles, rendimiento, festivos, capacidad real de la planta y cuello de botella.
- **Pedidos:** alta, edición y baja, con filtros, orden por columnas y paginación.
- **Disponibilidad:** mapa del año por equipo y semana, excepciones manuales, festivos de México, interrupciones aleatorias reproducibles y aviso cuando un plan guardado ya no cabe en la disponibilidad.
- **Calendario:** disponibilidad semana por semana de un equipo durante todo el año.
- **Requerimientos de material:** materia prima, merma y rendimiento por pedido o por mes, con la carga de cada equipo frente a su capacidad.
- **Planeación mensual:**
  - Tres criterios para comparar antes de guardar: **PEPS**, **Prioritario** y **Heurística**.
  - Secuencia manual con bloques Expedite, Estándar y Hold, vista previa sin guardar y replaneación que respeta el orden.
  - Resultados en **tabla** o en **Gantt** (una fila por pedido, una barra por equipo, la fecha de entrega coloreada según el atraso).
  - Los meses se planean en orden cronológico y los posteriores se replanean solos.
- **Ocupación:** mapa de calor de equipos por semana, con el detalle de los pedidos que ocupan cada semana.
- **Dashboard:** cinco indicadores del mes con su variación frente al mes anterior, y cuatro gráficas.

Los límites actuales están en la sección 9 del manual.

---

## Instalación

Desde la carpeta del proyecto, en una terminal de Windows con Python 3.10 o más reciente:

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

Para cargar los datos de demostración y correr las pruebas, instala también:

```bash
pip install -r requirements-dev.txt
```

---

## Iniciar el sistema

Se necesitan dos ventanas abiertas al mismo tiempo:

| Ventana | Cómo abrirla | Qué debe decir |
|---|---|---|
| **Servidor** (cálculos) | Doble clic en `run.bat` | `Uvicorn running on http://127.0.0.1:8000` |
| **Páginas** | Doble clic en `run_frontend.bat` | `Serving HTTP on … port 5500` |

Después abre **http://localhost:5500** en el navegador.

Para comprobar el servidor, **http://localhost:8000/health** debe mostrar `{"status":"ok"}`.

Sin los `.bat`, con el entorno activo y dentro de la carpeta del proyecto:

```bash
uvicorn main:app --app-dir backend --reload
```

y en otra terminal, dentro de la carpeta `frontend`:

```bash
python -m http.server 5500
```

La base de datos `mrp.db` se crea sola en la carpeta del proyecto la primera vez que arranca el servidor.

---

## Datos de demostración

Con el servidor corriendo y una base de datos nueva (borra `mrp.db` si ya existe):

```bash
python scripts/seed_data.py
```

Crea una planta de cuatro equipos, 168 pedidos de 2026 y los planes de casi todo el año. Septiembre queda sin planear a propósito, para compararlo en vivo (ver la sección 6 del manual).

---

## Pruebas

```bash
pip install -r requirements-dev.txt
pytest
```

Las pruebas usan una base de datos temporal y nunca tocan `mrp.db`. Cubren el planificador (capacidad, disponibilidad, semanas 52 y 53, orden de meses), la secuencia manual, los requerimientos, la validación de datos, el resumen de la ruta, las sobrecargas de disponibilidad, el dashboard y la historia de demostración.

---

## Estructura del proyecto

```text
mrp-system/
├── backend/                  # Servidor FastAPI
│   ├── main.py               # Endpoints
│   ├── models.py             # Tablas (SQLAlchemy)
│   ├── database.py           # Conexión a SQLite
│   ├── planning.py           # Planeación mensual y replaneación
│   ├── manual_planning.py    # Secuencia manual: vista previa y guardado
│   ├── heuristics.py         # Criterios PEPS, Prioritario y Heurística
│   ├── calculations.py       # Requerimientos de material y resumen de la ruta
│   ├── capacity.py           # Capacidad semanal y sobrecargas
│   ├── dashboard.py          # Indicadores del dashboard
│   ├── lateness.py           # Clasificación de atrasos
│   ├── validation.py         # Validación de datos
│   ├── disruptions.py        # Interrupciones aleatorias reproducibles
│   └── mexican_holidays.py   # Festivos federales de México
├── frontend/                 # Páginas (HTML, CSS y JavaScript sin frameworks)
│   ├── index.html
│   ├── css/                  # Un archivo por área de la interfaz
│   └── js/                   # Un archivo por pestaña, más api.js y main.js
├── scripts/
│   └── seed_data.py          # Datos de demostración
├── tests/                    # Pruebas con pytest
├── docs/
│   └── MANUAL.txt            # Manual de usuario
├── run.bat                   # Inicia el servidor
├── run_frontend.bat          # Sirve las páginas
├── pytest.ini
├── requirements.txt          # Dependencias del servidor
└── requirements-dev.txt      # Pruebas y datos de demostración
```

---

## Tecnologías

- **Backend:** Python, FastAPI, SQLAlchemy, Pydantic
- **Base de datos:** SQLite
- **Frontend:** HTML, CSS y JavaScript sin frameworks
- **Pruebas:** pytest

---

## Estado del proyecto

Proyecto académico en desarrollo. Demuestra planeación con capacidad, comparación de criterios, secuencia manual, requerimientos de material y disponibilidad a lo largo de una ruta de varios equipos.

Pendiente, entre otros: edición y baja de equipos desde la pantalla, exportación a Excel, inicio de sesión y festivos estatales. La lista completa está en la sección 9 del manual.

## Licencia

Sin licencia por ahora.
