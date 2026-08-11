"""Start the API in hybrid simulation mode without persisting credentials."""

from getpass import getpass
from pathlib import Path
import os
import sys
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).parents[1]))

import uvicorn


def main():
    host = os.getenv("SUPABASE_HOST", "db.szozfcqawdkfzugwrzdh.supabase.co")
    password = getpass("Supabase database password: ")
    database_url = (
        f"postgresql://postgres:{quote(password, safe='')}@{host}:5432/"
        "postgres?sslmode=require"
    )
    os.environ.update(
        {
            "STORAGE_MODE": "hybrid_sim",
            "ADJUSTMENT_PROJECT_KEY": os.getenv(
                "ADJUSTMENT_PROJECT_KEY", "limon_ldp_bmf"
            ),
            "OUTPUT_DB_URL": database_url,
            "METADATA_DB_URL": database_url,
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
