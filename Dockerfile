FROM python:3.11-slim

# Postavi radni direktorij
WORKDIR /code

# Kopiraj requirements i instaliraj biblioteke
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade -r requirements.txt

# Kopiraj cijeli app folder u /code/app
COPY ./app ./app

# Pokreni aplikaciju (primijeti app.main:app)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]