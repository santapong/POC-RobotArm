"""Run the FastAPI server with ``python -m server``."""

import uvicorn


def main() -> None:
    uvicorn.run(
        "server.main:create_app",
        factory=True,
        host="127.0.0.1",
        port=8000,
        reload=False,
    )


if __name__ == "__main__":
    main()
