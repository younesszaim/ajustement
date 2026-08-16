"""Start the only API storage using vertica_sim and adjustment_meta."""

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
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise SystemExit(
            "Database connection is not configured. Set DATABASE_URL in the "
            "ignored root .env to the Supabase Session Pooler URI."
        )
    os.environ.update(
        {
            "ADJUSTMENT_PROJECT_KEY": os.getenv(
                "ADJUSTMENT_PROJECT_KEY", "limon_ldp_bmf"
            ),
            "DATABASE_URL": database_url,
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
