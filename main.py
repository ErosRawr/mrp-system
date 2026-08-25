from fastapi import FastAPI

app = FastAPI(title="MRP System", version="0.1.0")


@app.get("/health")
def health_check():
    """Basic check that the API is running."""
    return {"status": "ok"}