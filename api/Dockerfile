# AI WealthPilot API image — Python quant core + FastAPI shell.
#
# The build context is the REPOSITORY ROOT (see docker-compose.yml),
# because the API imports the src/ package directly.
#
# TODO(phase-3+): slim the image by splitting streamlit/plotly-only deps
# out of requirements.txt once the Streamlit UI is retired.

FROM python:3.11-slim

WORKDIR /app

# Install dependencies first for better layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the quant core, the API shell, and the static CME fallback document.
# Runtime data (cache, profiles, reports) is NOT baked in — it comes from
# the ./data volume mount in docker-compose.yml.
COPY src/ ./src/
COPY api/ ./api/
COPY docs/ips_reference/ ./docs/ips_reference/

ENV PYTHONPATH=/app
EXPOSE 8000

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
