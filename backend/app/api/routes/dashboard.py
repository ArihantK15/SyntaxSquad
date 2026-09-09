from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func, desc

from app.api.deps import get_db
from app.models import Case, DocumentAnalysis, RiskSignal
from app.schemas import DashboardStatsOut, CaseOut

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

@router.get("/stats", response_model=DashboardStatsOut)
def get_dashboard_stats(db: Session = Depends(get_db)):
    """Computes real-time metrics, risk distributions, and operational queue stats."""
    total_screened = db.query(Case).count()
    
    high_risk = db.query(Case).filter(Case.risk_level == "HIGH").count()
    critical = db.query(Case).filter(Case.risk_level == "CRITICAL").count()
    cleared = db.query(Case).filter(Case.officer_decision == "CLEARED").count()
    
    requiring_review = db.query(Case).filter(
        Case.officer_decision == "PENDING",
        Case.risk_score >= 25.0
    ).count()

    # Risk Distribution
    risk_dist = {
        "LOW": db.query(Case).filter(Case.risk_level == "LOW").count(),
        "MEDIUM": db.query(Case).filter(Case.risk_level == "MEDIUM").count(),
        "HIGH": high_risk,
        "CRITICAL": critical
    }

    # Document Types
    doc_type_counts = {}
    doc_types = db.query(Case.document_type, func.count(Case.id)).group_by(Case.document_type).all()
    for dt, count in doc_types:
        doc_type_counts[dt or "Passport"] = count

    # Average processing time
    avg_time = db.query(func.avg(DocumentAnalysis.processing_time_ms)).scalar() or 2450.0

    # Top risk reasons
    top_signals = (
        db.query(RiskSignal.signal, func.count(RiskSignal.id).label("count"))
        .group_by(RiskSignal.signal)
        .order_by(desc("count"))
        .limit(6)
        .all()
    )
    top_risk_reasons = [{"reason": s[0], "count": s[1]} for s in top_signals]

    # Recent cases
    recent_cases = db.query(Case).order_by(desc(Case.created_at)).limit(10).all()

    return {
        "documents_screened": total_screened,
        "high_risk_cases": high_risk,
        "critical_cases": critical,
        "cases_requiring_review": requiring_review,
        "cleared_cases": cleared,
        "avg_processing_time_ms": round(float(avg_time), 1),
        "risk_distribution": risk_dist,
        "document_types": doc_type_counts,
        "top_risk_reasons": top_risk_reasons,
        "recent_cases": recent_cases
    }
