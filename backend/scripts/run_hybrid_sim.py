"""Start the API in hybrid simulation mode without persisting credentials."""

from pathlib import Path
import os
import sys
from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_DIR = BACKEND_DIR.parent
sys.path.insert(0, str(BACKEND_DIR))
load_dotenv(PROJECT_DIR / ".env")
load_dotenv(BACKEND_DIR / ".env")

import uvicorn


def main():
    database_url = os.getenv("SUPABASE_DB_URL")
    output_url = os.getenv("OUTPUT_DB_URL") or database_url
    metadata_url = os.getenv("METADATA_DB_URL") or database_url
    if not output_url or not metadata_url:
        raise SystemExit(
            "Database connection is not configured. Set SUPABASE_DB_URL in the "
            "ignored root .env to the Supabase Session Pooler URI."
        )
    os.environ.update(
        {
            "STORAGE_MODE": "hybrid_sim",
            "ADJUSTMENT_PROJECT_KEY": os.getenv(
                "ADJUSTMENT_PROJECT_KEY", "limon_ldp_bmf"
            ),
            "OUTPUT_DB_URL": output_url,
            "METADATA_DB_URL": metadata_url,
            "LOCAL_USER": os.getenv("LOCAL_USER", "developer@example"),
            "SIMULATED_FAILURE_POINT": os.getenv("SIMULATED_FAILURE_POINT", ""),
        }
    )
    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=int(os.getenv("API_PORT", "8000")),
        reload=False,
    )


if __name__ == "__main__":
    main()
