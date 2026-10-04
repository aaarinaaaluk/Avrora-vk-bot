from fastapi import FastAPI
from app.core.verifier import ClaimRequest, VerificationResult, verify_claim

app = FastAPI(title="AVRORA")


@app.get("/")
def root():
    return {
        "project": "AVRORA",
        "status": "ok",
        "message": "Система проверки медицинской информации запущена",
    }


@app.post("/verify", response_model=VerificationResult)
def verify(request: ClaimRequest):
    return verify_claim(request.claim)
