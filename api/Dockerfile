# AI WealthPilot API image — Python quant core + FastAPI shell.
#
# The build context is the REPOSITORY ROOT (see docker-compose.yml),
# because the API imports the src/ package directly.
#
# requirements.txt is the single runtime dependency set (Streamlit was
# retired in Phase 6; dev-only extras live in requirements-dev.txt).

FROM python:3.11-slim

WORKDIR /app

# CJK font for IPS PDF rendering. src/agents/ips_storage.py `_find_cjk_font`
# probes two fixed Linux paths (both named NotoSansCJK-Regular.ttc). Debian's
# real fonts-noto-cjk is CFF-based, which fpdf2 2.8.7 garbles — so we install
# WenQuanYi Micro Hei (TrueType outlines, ~5MB) and link it into a probed path.
RUN apt-get update \
    && apt-get install -y --no-install-recommends fonts-wqy-microhei \
    && mkdir -p /usr/share/fonts/truetype/noto \
    && ln -s /usr/share/fonts/truetype/wqy/wqy-microhei.ttc \
        /usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc \
    && rm -rf /var/lib/apt/lists/*

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
