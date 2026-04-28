from datetime import datetime, date, timedelta, timezone, time
from typing import Optional
from sqlalchemy import func, and_, extract
from sqlalchemy.orm import Session
from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User, UserRole
from app.models.commit import Commit
from app.models.daily_contribution import DailyContribution
from app.models.participant import Participant
from app.models.group_user import GroupUser

router = APIRouter(prefix="/analytics", tags=["analytics"])


def _calculate_streak(commit_dates: list[date], today: date) -> int:
    """Calcula la racha activa de commits de un usuario"""
    if not commit_dates:
        return 0
    unique_dates = set(commit_dates)
    yesterday = today - timedelta(days=1)
    
    # Si no hubo commit hoy pero sí ayer, la racha sigue activa
    if today in unique_dates:
        start = today
    elif yesterday in unique_dates:
        start = yesterday
    else:
        return 0
    
    streak = 0
    expected = start
    for d in sorted(unique_dates, reverse=True):
        if d == expected:
            streak += 1
            expected -= timedelta(days=1)
        elif d < expected:
            break
    return streak


@router.get("/dashboard-stats")
def get_dashboard_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Obtiene estadísticas generales del sistema para el dashboard del admin.
    Solo accesible por admins.
    """
    if current_user.rol != UserRole.admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Solo administradores pueden acceder a estas estadísticas"
        )
    
    today = datetime.now(timezone.utc).date()
    thirty_days_ago = today - timedelta(days=30)
    ninety_days_ago = today - timedelta(days=90)
    one_year_ago = today - timedelta(days=365)
    
    # Total de commits en todo el sistema
    total_commits = db.query(func.count(Commit.id)).scalar() or 0
    
    # Commits en los últimos 30 días
    commits_30d = db.query(func.count(Commit.id)).filter(
        Commit.fecha >= datetime.combine(thirty_days_ago, time.min, tzinfo=timezone.utc)
    ).scalar() or 0
    
    # Commits en los últimos 90 días
    commits_90d = db.query(func.count(Commit.id)).filter(
        Commit.fecha >= datetime.combine(ninety_days_ago, time.min, tzinfo=timezone.utc)
    ).scalar() or 0
    
    # Commits en el último año
    commits_1y = db.query(func.count(Commit.id)).filter(
        Commit.fecha >= datetime.combine(one_year_ago, time.min, tzinfo=timezone.utc)
    ).scalar() or 0
    
    # Alumnos activos (que tienen al menos un commit)
    active_students = db.query(func.count(func.distinct(Commit.usuario_id))).filter(
        Commit.usuario_id.in_(
            db.query(User.id).filter(User.rol == UserRole.alumno)
        )
    ).scalar() or 0
    
    total_students = db.query(func.count(User.id)).filter(
        User.rol == UserRole.alumno
    ).scalar() or 0
    
    # Promedio de commits por día (últimos 30 días)
    avg_commits_per_day = commits_30d / 30 if commits_30d > 0 else 0
    
    # Alumnos con racha activa
    today_for_streak = today
    # Obtener todas las fechas de commits para los últimos 90 días para cálculo de racha
    last_90_days_start = datetime.combine(ninety_days_ago, time.min, tzinfo=timezone.utc)
    
    commits_for_streak = db.query(Commit.usuario_id, Commit.fecha).filter(
        Commit.fecha >= last_90_days_start,
        Commit.usuario_id.in_(
            db.query(User.id).filter(User.rol == UserRole.alumno)
        )
    ).all()
    
    streak_map = {}
    for usuario_id, commit_datetime in commits_for_streak:
        commit_date = commit_datetime.date() if hasattr(commit_datetime, 'date') else commit_datetime
        if usuario_id not in streak_map:
            streak_map[usuario_id] = []
        streak_map[usuario_id].append(commit_date)
    
    active_streak_users = 0
    for usuario_id, dates in streak_map.items():
        streak = _calculate_streak(dates, today_for_streak)
        if streak >= 7:  # Racha de al menos 7 días
            active_streak_users += 1
    
    # Crecimiento: comparar commits últimos 30 días vs 30 días anteriores
    sixty_days_ago = today - timedelta(days=60)
    commits_30d_previous = db.query(func.count(Commit.id)).filter(
        and_(
            Commit.fecha >= datetime.combine(sixty_days_ago, time.min, tzinfo=timezone.utc),
            Commit.fecha < datetime.combine(thirty_days_ago, time.min, tzinfo=timezone.utc)
        )
    ).scalar() or 0
    
    growth_percentage = 0
    if commits_30d_previous > 0:
        growth_percentage = ((commits_30d - commits_30d_previous) / commits_30d_previous) * 100
    elif commits_30d > 0:
        growth_percentage = 100
    
    # Día con más commits (últimos 30 días)
    peak_day_result = db.query(
        func.date(Commit.fecha).label('day'),
        func.count(Commit.id).label('count')
    ).filter(
        Commit.fecha >= datetime.combine(thirty_days_ago, time.min, tzinfo=timezone.utc)
    ).group_by(func.date(Commit.fecha)).order_by(func.count(Commit.id).desc()).first()
    
    peak_day_commits = peak_day_result.count if peak_day_result else 0
    peak_day_date = peak_day_result.day if peak_day_result else None
    
    # Top 5 alumnos más activos (por TODAS las contribuciones, no solo commits)
    top_students = db.query(
        User.id,
        User.nombre,
        func.sum(DailyContribution.count).label('total_contributions'),
        Participant.github_username
    ).join(
        DailyContribution, DailyContribution.usuario_id == User.id
    ).outerjoin(
        Participant, Participant.usuario_id == User.id
    ).filter(
        User.rol == UserRole.alumno
    ).group_by(
        User.id, User.nombre, Participant.github_username
    ).order_by(
        func.sum(DailyContribution.count).desc()
    ).limit(5).all()
    
    top_students_data = [
        {
            "nombre": student.nombre,
            "github_username": student.github_username or "N/A",
            "contributions": int(student.total_contributions or 0),
        }
        for student in top_students
    ]
    
    # Distribución de commits por hora del día (últimos 30 días)
    hour_distribution = db.query(
        extract('hour', Commit.fecha).label('hour'),
        func.count(Commit.id).label('count')
    ).filter(
        Commit.fecha >= datetime.combine(thirty_days_ago, time.min, tzinfo=timezone.utc)
    ).group_by(
        extract('hour', Commit.fecha)
    ).order_by('hour').all()
    
    hours_data = [{"hour": int(row.hour) if row.hour else 0, "count": row.count} for row in hour_distribution]
    
    # Tendencia semanal (últimos 12 semanas)
    twelve_weeks_ago = today - timedelta(weeks=12)
    weekly_data = db.query(
        func.date(Commit.fecha).label('day'),
        func.count(Commit.id).label('count')
    ).filter(
        Commit.fecha >= datetime.combine(twelve_weeks_ago, time.min, tzinfo=timezone.utc)
    ).group_by(func.date(Commit.fecha)).order_by(func.date(Commit.fecha)).all()
    
    # Datos diarios: contribuciones y alumnos activos (últimos 60 días)
    sixty_days_ago = today - timedelta(days=60)
    daily_contributions_data = db.query(
        DailyContribution.fecha,
        func.sum(DailyContribution.count).label('total_contributions')
    ).filter(
        DailyContribution.fecha >= sixty_days_ago,
        DailyContribution.usuario_id.in_(
            db.query(User.id).filter(User.rol == UserRole.alumno)
        )
    ).group_by(DailyContribution.fecha).order_by(DailyContribution.fecha).all()
    
    # Obtener commits diarios para contar alumnos activos por día
    daily_active_students_data = db.query(
        func.date(Commit.fecha).label('day'),
        func.count(func.distinct(Commit.usuario_id)).label('active_students')
    ).filter(
        Commit.fecha >= datetime.combine(sixty_days_ago, time.min, tzinfo=timezone.utc),
        Commit.usuario_id.in_(
            db.query(User.id).filter(User.rol == UserRole.alumno)
        )
    ).group_by(func.date(Commit.fecha)).order_by(func.date(Commit.fecha)).all()
    
    return {
        "overall": {
            "total_commits": total_commits,
            "active_students": active_students,
            "total_students": total_students,
            "participation_rate": (active_students / total_students * 100) if total_students > 0 else 0,
        },
        "thirty_days": {
            "commits": commits_30d,
            "avg_per_day": round(avg_commits_per_day, 2),
            "growth_percentage": round(growth_percentage, 2),
            "peak_day_commits": peak_day_commits,
            "peak_day_date": str(peak_day_date) if peak_day_date else None,
        },
        "ninety_days": {
            "commits": commits_90d,
            "active_streak_users": active_streak_users,
        },
        "one_year": {
            "commits": commits_1y,
        },
        "top_students": top_students_data,
        "hours_distribution": hours_data,
        "weekly_trend": [
            {"date": str(row.day), "commits": row.count}
            for row in weekly_data
        ],
        "daily_contributions": [
            {"date": str(row.fecha), "contributions": row.total_contributions or 0}
            for row in daily_contributions_data
        ],
        "daily_active_students": [
            {"date": str(row.day), "active_students": row.active_students}
            for row in daily_active_students_data
        ],
    }
