FROM python:3.12-slim

WORKDIR /app

# Installer les dépendances système
RUN apt-get update && apt-get install -y \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copier et installer les dépendances Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Le code est monté via volumes dans docker-compose
# Pas besoin de COPY ici pour le dev

CMD ["python", "scripts/load_to_postgres.py"]
