# ── Stage 1: base image with Python + deps ──────────────────────────────
FROM public.ecr.aws/lambda/python:3.13 AS base

# Install dependencies
COPY requirements.txt ${LAMBDA_TASK_ROOT}/
RUN pip install --no-cache-dir -r ${LAMBDA_TASK_ROOT}/requirements.txt

# Copy the full project (pipelines + analytics + infra + raw data)
COPY pipelines/ ${LAMBDA_TASK_ROOT}/pipelines/
COPY analytics/ ${LAMBDA_TASK_ROOT}/analytics/
COPY infra/ ${LAMBDA_TASK_ROOT}/infra/
COPY conut_bakery_scaled_data/ ${LAMBDA_TASK_ROOT}/conut_bakery_scaled_data/


# ── Stage 2a: ETL handler image ─────────────────────────────────────────
FROM base AS etl
CMD ["infra.handlers.etl_handler.handler"]


# ── Stage 2b: Forecast handler image ────────────────────────────────────
FROM base AS forecast
CMD ["infra.handlers.forecast_handler.handler"]


# ── Stage 2c: Combo handler image ───────────────────────────────────────
FROM base AS combo
CMD ["infra.handlers.combo_handler.handler"]


# ── Stage 2d: Expansion handler image ──────────────────────────────────
FROM base AS expansion
CMD ["infra.handlers.expansion_handler.handler"]


# ── Stage 2e: Staffing handler image ───────────────────────────────────
FROM base AS staffing
CMD ["infra.handlers.staffing_handler.handler"]


# ── Stage 2f: Growth handler image ─────────────────────────────────────
FROM base AS growth
CMD ["infra.handlers.growth_handler.handler"]
