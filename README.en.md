# Match Predictions System 🎯

A sports match prediction system with user accuracy analytics.

**Stack:** Python 3.11+ | MongoDB 7.0 | Motor (async) | Pydantic v2

---

## 📋 Table of Contents

- [Features](#-features)
- [Architecture](#-architecture)
- [Installation](#-installation)
- [Running](#-running)
- [Usage](#-usage)
- [Project Structure](#-project-structure)
- [Model API](#-model-api)
- [Analytics](#-analytics)
- [Migrations](#-migrations)
- [Testing](#-testing)

---

## 🚀 Features

- **User Registration** with data validation via Pydantic
- **Matches** — creation, result updates, history
- **Predictions** — users make predictions on match outcomes
- **Analytics** — prediction accuracy calculation, rankings, statistics
- **Asynchronous operation** with MongoDB via Motor
- **CLI interface** for data management
- **Docker-ready** — full containerization

---

## 🏗 Architecture

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

## 📦 Installation

### Requirements

- Python 3.11+
- Docker & Docker Compose
- uv (recommended) or pip

### Installation Steps

```bash
# Clone the repository
cd Mongo-Motor

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # Linux/macOS
# or
.venv\Scripts\activate  # Windows

# Install dependencies
pip install -e ".[dev]"

# Copy configuration
cp .env.example .env
```

---

## 🐳 Running

### With Docker (recommended)

```bash
# Start MongoDB and Mongo Express
cd docker
docker-compose up -d

# Check status
docker-compose ps

# Mongo Express available at http://localhost:8081
```

### Local Application Run

```bash
# From project root
python main.py

# Or via CLI
predictions --help
```

---

## 💻 Usage

### CLI Commands

```bash
# Users
predictions user create --username "john_doe" --email "john@example.com"
predictions user list
predictions user stats <user_id>

# Matches
predictions match create --home "Team A" --away "Team B" --date "2024-03-15T18:00:00"
predictions match result <match_id> --home-score 2 --away-score 1
predictions match list --status pending

# Predictions
predictions predict create --user <user_id> --match <match_id> --home 2 --away 1
predictions predict list --user <user_id>

# Analytics
predictions analytics user <user_id>
predictions analytics leaderboard --limit 10
predictions analytics accuracy --period month
```

### Programmatic API

```python
import asyncio
from src.db.connection import get_database
from src.services.user_service import UserService
from src.services.prediction_service import PredictionService

async def main():
    db = await get_database()
    
    # Create user
    user_service = UserService(db)
    user = await user_service.create_user(
        username="pro_predictor",
        email="pro@example.com"
    )
    
    # Get analytics
    prediction_service = PredictionService(db)
    stats = await prediction_service.get_user_accuracy(user.id)
    print(f"Accuracy: {stats.accuracy_percent}%")

asyncio.run(main())
```

---

## 📁 Project Structure

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
│   │   ├── connection.py        # Motor connection
│   │   └── indexes.py           # Index definitions
│   ├── models/
│   │   ├── __init__.py
│   │   ├── base.py              # Base model with ObjectId
│   │   ├── user.py              # User model
│   │   ├── match.py             # Match model
│   │   ├── prediction.py        # Prediction model
│   │   └── analytics.py         # Analytics DTOs
│   ├── repositories/
│   │   ├── __init__.py
│   │   ├── base.py              # Generic repository
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
│   │   └── custom_types.py      # PyObjectId, custom validators
│   └── cli/
│       ├── __init__.py
│       └── commands.py          # Click CLI
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

## 📊 Model API

### User

| Field | Type | Description |
|-------|------|-------------|
| id | ObjectId | Unique identifier |
| username | str | Username (unique) |
| email | str | Email (unique) |
| created_at | datetime | Registration date |
| is_active | bool | Is account active |

### Match

| Field | Type | Description |
|-------|------|-------------|
| id | ObjectId | Unique identifier |
| home_team | str | Home team |
| away_team | str | Away team |
| scheduled_at | datetime | Match date and time |
| status | MatchStatus | pending / live / finished / cancelled |
| home_score | int? | Home team goals |
| away_score | int? | Away team goals |

### Prediction

| Field | Type | Description |
|-------|------|-------------|
| id | ObjectId | Unique identifier |
| user_id | ObjectId | Reference to user |
| match_id | ObjectId | Reference to match |
| predicted_home | int | Predicted home goals |
| predicted_away | int | Predicted away goals |
| created_at | datetime | Prediction date |
| points | int? | Awarded points |

---

## 📈 Analytics

Points scoring system:

| Result | Points | Description |
|--------|--------|-------------|
| Exact score | 3 | Guessed the exact score |
| Outcome + difference | 2 | Guessed outcome and goal difference |
| Outcome | 1 | Guessed only outcome (win/draw) |
| Miss | 0 | Prediction didn't match |

### User Metrics

- **total_predictions** — total predictions
- **correct_outcomes** — correct outcomes guessed
- **exact_scores** — exact scores
- **accuracy_percent** — accuracy percentage
- **avg_points** — average points
- **current_streak** — current streak
- **best_streak** — best streak

---

## 🔄 Migrations

```bash
# Apply all migrations
predictions migrate up

# Rollback last migration
predictions migrate down

# Migration status
predictions migrate status
```

---

## 🧪 Testing

```bash
# Run all tests
pytest

# With coverage
pytest --cov=src --cov-report=html

# Unit tests only
pytest tests/test_models.py -v

# Integration tests (requires MongoDB)
pytest tests/test_repositories.py -v
```

---

## 🔧 Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| MONGO_HOST | localhost | MongoDB host |
| MONGO_PORT | 27017 | MongoDB port |
| MONGO_DB_NAME | predictions_db | Database name |
| MONGO_ROOT_USER | admin | MongoDB user |
| MONGO_ROOT_PASSWORD | secret | MongoDB password |
| LOG_LEVEL | INFO | Logging level |

---

## 📝 License

MIT License

---

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing`)
5. Open a Pull Request