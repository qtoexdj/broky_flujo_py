import logging

from fastapi import FastAPI

from app.api.routes import health, webhook


def create_app() -> FastAPI:
    logging.basicConfig(level=logging.INFO)

    application = FastAPI(title="Broky WhatsApp Bot", version="0.2.0")
    application.include_router(health.router)
    application.include_router(webhook.router)

    return application


app = create_app()
