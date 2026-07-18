"""Shared helpers for the classification-v2 taxonomy pipeline. READ-ONLY DB access."""
import os
from pathlib import Path

from dotenv import load_dotenv
from pymongo import MongoClient

ROOT = Path(__file__).resolve().parents[1]
OUTPUTS = ROOT / "outputs"
WORK = ROOT / "outputs" / "work"

load_dotenv(ROOT / ".env")

_CREDS = "admin:JhXqC1OUPWlLm2zFUPBYDIlkDiyYOQK4"


def get_db():
    """A native Windows MongoDB service shadows the Docker container on 127.0.0.1,
    so fall back to the machine's LAN IP which reaches Docker's 0.0.0.0 proxy."""
    import socket

    hosts = ["localhost", socket.gethostbyname(socket.gethostname())]
    last_err = None
    for host in hosts:
        uri = f"mongodb://{_CREDS}@{host}:27017/research_ambit?authSource=admin"
        client = MongoClient(uri, serverSelectionTimeoutMS=5000)
        try:
            db = client["research_ambit"]
            if db.researchmetadatascopus.estimated_document_count() > 0:
                return db
        except Exception as e:
            last_err = e
    raise RuntimeError(f"could not reach the research_ambit MongoDB: {last_err}")


def ensure_dirs():
    OUTPUTS.mkdir(exist_ok=True)
    WORK.mkdir(parents=True, exist_ok=True)
