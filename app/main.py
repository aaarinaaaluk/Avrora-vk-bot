from fastapi import FastAPI

from app.core.analyzer import AnalysisResult, analyze_query
from app.core.fact_checker import check_claim
from app.core.verifier import ClaimRequest, VerificationResult
from app.vk.handler import router as vk_router

app = FastAPI(title="AVRORA", version="2.0.0")
app.include_router(vk_router)


@app.get("/")
def root():
    return {
        "project": "AVRORA",
        "version": "2.0.0",
        "status": "ok",
        "message": "Предварительная проверка медицинской информации по разрешённым источникам",
    }


@app.post("/analyze", response_model=AnalysisResult)
def analyze(request: ClaimRequest):
    return analyze_query(request.claim)


@app.post("/verify", response_model=VerificationResult)
def verify(request: ClaimRequest):
    return check_claim(request.claim)
