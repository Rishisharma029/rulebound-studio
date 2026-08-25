FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

ENV REQUIRE_ENTRA_AUTH="false"
ENV AZURE_TENANT_ID="common"
ENV AZURE_CLIENT_ID="rulebound-api"

CMD ["uvicorn", "rulebound.api:app", "--host", "0.0.0.0", "--port", "8000"]
