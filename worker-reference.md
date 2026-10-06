# Worker de envio — referências (do exemplo dos scrapers)
WEBHOOK_URL_BASE=https://jobs-api.thiagoil2006.workers.dev/api/v1/webhooks/receive/
WEBHOOK_ID=81fb7623-e731-49ae-8012-be7a467f74a6

# Assinatura HMAC: message = f"{timestamp}.{raw_body}"  →  HMAC-SHA256(SECRET, message)
# Headers:
#   Content-Type: application/json
#   X-Agrega-Timestamp: <unix_ts>
#   X-Agrega-Signature: sha256=<hexdigest>
#   X-Agrega-Delivery: <uuid4>
