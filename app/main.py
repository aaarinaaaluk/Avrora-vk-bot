
from fastapi import FastAPI

from app.core.analyzer import AnalysisResult, analyze_query
from app.core.verifier import (
    ClaimRequest,
    VerificationResult,
    verify_claim,
)

app = FastAPI(title="AVRORA")


@app.get("/")
def root():
    return {
        "project": "AVRORA",
        "status": "ok",
        "message": "Система предварительного анализа медицинской информации запущена",
    }


@app.post("/analyze", response_model=AnalysisResult)
def analyze(request: ClaimRequest):
    return analyze_query(request.claim)


@app.post("/verify", response_model=VerificationResult)
def verify(request: ClaimRequest):
    return verify_claim(request.claim)
    