# Match Predictions System 🎯

Sistema de predicción de partidos deportivos con análisis de precisión de usuarios.

**Stack:** Python 3.11+ | MongoDB 7.0 | Motor (async) | Pydantic v2

---

## 📋 Contenido

- [Características](#-características)
- [Arquitectura](#-arquitectura)
- [Instalación](#-instalación)
- [Ejecución](#-ejecución)
- [Uso](#-uso)
- [Estructura del proyecto](#-estructura-del-proyecto)
- [API de modelos](#-api-de-modelos)
- [Análisis](#-análisis)
- [Migraciones](#-migraciones)
- [Pruebas](#-pruebas)

---

## 🚀 Características

- **Registro de usuarios** con validación de datos mediante Pydantic
- **Partidos** — creación, actualización de resultados, historial
- **Predicciones** — los usuarios hacen predicciones sobre resultados de partidos
- **Análisis** — cálculo de precisión de predicciones, rankings, estadísticas
- **Trabajo asíncrono** con MongoDB mediante Motor
- **Interfaz CLI** para gestión de datos
- **Docker-ready** — contenedorización completa

---

## 🏗 Arquitectura

```
┌─────────────────────────────────────────────────────────┐
│                      CLI / Scripts                       │
├─────────────────────────────────────────────────────────┤
│                       Services                           │
│  ┌─────────────┐ ┌─────────────┐ ┌───────────────────┐  │
│  │ UserService │ │MatchService │ │ PredictionService │  │
│  └─────────────┘ └─────────────┘ └───────────────────┘  │
├─────────────────────────────────────────────────────────┤
│                     Repositories                         │
│  ┌────────────────┐ ┌────────────────┐ ┌──────────────┐ │
│  │ UserRepository │ │MatchRepository │ │ PredictionRep│ │
│  └────────────────┘ └────────────────┘ └──────────────┘ │
├─────────────────────────────────────────────────────────┤
│                   Pydantic Models                        │
│  ┌──────┐ ┌───────┐ ┌────────────┐ ┌─────────────────┐  │
│  │ User │ │ Match │ │ Prediction │ │ AnalyticsResult │  │
│  └──────┘ └───────┘ └────────────┘ └─────────────────┘  │
├─────────────────────────────────────────────────────────┤
│                MongoDB (Motor async driver)              │
└─────────────────────────────────────────────────────────┘
```

---

## 📦 Instalación

### Requisitos

- Python 3.11+
- Docker & Docker Compose
- uv (recomendado) o pip

### Pasos de instalación

```bash
# Clonar el repositorio
cd Mongo-Motor

# Crear entorno virtual
python -m venv .venv
source .venv/bin/activate  # Linux/macOS
# o
.venv\Scripts\activate  # Windows

# Instalar dependencias
pip install -e ".[dev]"

# Copiar configuración
cp .env.example .env
```

---

## 🐳 Ejecución

### Con Docker (recomendado)

```bash
# Iniciar MongoDB y Mongo Express
cd docker
docker-compose up -d

# Verificar estado
docker-compose ps

# Mongo Express disponible en http://localhost:8081
```

### Ejecución local de la aplicación

```bash
# Desde la raíz del proyecto
python main.py

# O mediante CLI
predictions --help
```

---

## 💻 Uso

### Comandos CLI

```bash
# Usuarios
predictions user create --username "john_doe" --email "john@example.com"
predictions user list
predictions user stats <user_id>

# Partidos
predictions match create --home "Equipo A" --away "Equipo B" --date "2024-03-15T18:00:00"
predictions match result <match_id> --home-score 2 --away-score 1
predictions match list --status pending

# Predicciones
predictions predict create --user <user_id> --match <match_id> --home 2 --away 1
predictions predict list --user <user_id>

# Análisis
predictions analytics user <user_id>
predictions analytics leaderboard --limit 10
predictions analytics accuracy --period month
```

### API Programática

```python
import asyncio
from src.db.connection import get_database
from src.services.user_service import UserService
from src.services.prediction_service import PredictionService

async def main():
    db = await get_database()
    
    # Crear usuario
    user_service = UserService(db)
    user = await user_service.create_user(
        username="pro_predictor",
        email="pro@example.com"
    )
    
    # Obtener análisis
    prediction_service = PredictionService(db)
    stats = await prediction_service.get_user_accuracy(user.id)
    print(f"Precisión: {stats.accuracy_percent}%")

asyncio.run(main())
```

---

## 📁 Estructura del proyecto

```
Mongo-Motor/
├── docker/
│   ├── Dockerfile
│   └── docker-compose.yml
├── src/
│   ├── config/
│   │   ├── __init__.py
│   │   └── settings.py          # Pydantic Settings
│   ├── db/
│   │   ├── __init__.py
│   │   ├── connection.py        # Conexión Motor
│   │   └── indexes.py           # Definiciones de índices
│   ├── models/
│   │   ├── __init__.py
│   │   ├── base.py              # Modelo base con ObjectId
│   │   ├── user.py              # Modelo de usuario
│   │   ├── match.py             # Modelo de partido
│   │   ├── prediction.py        # Modelo de predicción
│   │   └── analytics.py         # DTOs de análisis
│   ├── repositories/
│   │   ├── __init__.py
│   │   ├── base.py              # Repositorio genérico
│   │   ├── user_repository.py
│   │   ├── match_repository.py
│   │   └── prediction_repository.py
│   ├── services/
│   │   ├── __init__.py
│   │   ├── user_service.py
│   │   ├── match_service.py
│   │   ├── prediction_service.py
│   │   └── analytics_service.py
│   ├── validators/
│   │   ├── __init__.py
│   │   └── custom_types.py      # PyObjectId, validadores personalizados
│   └── cli/
│       ├── __init__.py
│       └── commands.py          # CLI con Click
├── data/
│   └── seed/
│       ├── teams.json
│       └── sample_matches.json
├── migrations/
│   ├── __init__.py
│   └── versions/
│       └── 001_initial.py
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   ├── test_models.py
│   ├── test_repositories.py
│   └── test_services.py
├── scripts/
│   ├── seed_data.py
│   └── run_analytics.py
├── .env.example
├── .gitignore
├── pyproject.toml
├── README.md
└── main.py
```

---

## 📊 API de modelos

### User (Usuario)

| Campo | Tipo | Descripción |
|-------|------|-------------|
| id | ObjectId | Identificador único |
| username | str | Nombre de usuario (único) |
| email | str | Email (único) |
| created_at | datetime | Fecha de registro |
| is_active | bool | Si la cuenta está activa |

### Match (Partido)

| Campo | Tipo | Descripción |
|-------|------|-------------|
| id | ObjectId | Identificador único |
| home_team | str | Equipo local |
| away_team | str | Equipo visitante |
| scheduled_at | datetime | Fecha y hora del partido |
| status | MatchStatus | pending / live / finished / cancelled |
| home_score | int? | Goles del local |
| away_score | int? | Goles del visitante |

### Prediction (Predicción)

| Campo | Tipo | Descripción |
|-------|------|-------------|
| id | ObjectId | Identificador único |
| user_id | ObjectId | Referencia al usuario |
| match_id | ObjectId | Referencia al partido |
| predicted_home | int | Predicción de goles del local |
| predicted_away | int | Predicción de goles del visitante |
| created_at | datetime | Fecha de la predicción |
| points | int? | Puntos otorgados |

---

## 📈 Análisis

Sistema de puntuación:

| Resultado | Puntos | Descripción |
|-----------|--------|-------------|
| Resultado exacto | 3 | Acertó el resultado exacto |
| Resultado + diferencia | 2 | Acertó el resultado y la diferencia de goles |
| Resultado | 1 | Solo acertó el resultado (victoria/empate) |
| Fallo | 0 | La predicción no coincidió |

### Métricas de usuario

- **total_predictions** — total de predicciones
- **correct_outcomes** — resultados acertados
- **exact_scores** — resultados exactos
- **accuracy_percent** — % de precisión
- **avg_points** — promedio de puntos
- **current_streak** — racha actual
- **best_streak** — mejor racha

---

## 🔄 Migraciones

```bash
# Aplicar todas las migraciones
predictions migrate up

# Revertir la última
predictions migrate down

# Estado de las migraciones
predictions migrate status
```

---

## 🧪 Pruebas

```bash
# Ejecutar todas las pruebas
pytest

# Con cobertura
pytest --cov=src --cov-report=html

# Solo pruebas unitarias
pytest tests/test_models.py -v

# Pruebas de integración (requiere MongoDB)
pytest tests/test_repositories.py -v
```

---

## 🔧 Variables de entorno

| Variable | Por defecto | Descripción |
|----------|-------------|-------------|
| MONGO_HOST | localhost | Host de MongoDB |
| MONGO_PORT | 27017 | Puerto de MongoDB |
| MONGO_DB_NAME | predictions_db | Nombre de la base de datos |
| MONGO_ROOT_USER | admin | Usuario de MongoDB |
| MONGO_ROOT_PASSWORD | secret | Contraseña de MongoDB |
| LOG_LEVEL | INFO | Nivel de logging |

---

## 📝 Licencia

MIT License

---

## 🤝 Contribuir

1. Fork del repositorio
2. Crear rama de feature (`git checkout -b feature/amazing`)
3. Commit de cambios (`git commit -m 'Add amazing feature'`)
4. Push a la rama (`git push origin feature/amazing`)
5. Abrir Pull Request