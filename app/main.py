from fastapi import FastAPI, Request, Depends, HTTPException, Form, Query
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import os
from datetime import date, timedelta, datetime
from sqlalchemy.orm import Session
from typing import Optional

from app.database import engine, get_db, run_migrations
from app import models
from app.auth import (
    register_user,
    authenticate_user,
    create_session,
    get_session_user_id,
    COOKIE_NAME,
    COOKIE_MAX_AGE,
)
from app.algorithm import get_weight_recommendation, calculate_1rm_trend
from app.seed import seed_data

app = FastAPI(title="Training Tracker")
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")


@app.on_event("startup")
def startup():
    run_migrations()
    db = next(get_db())
    seed_data(db)
    db.close()


FREE_PATHS = {"/login", "/register", "/api/"}
@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    path = request.url.path
    if path.startswith("/static") or path in FREE_PATHS or path.startswith("/api/"):
        return await call_next(request)

    user_id = get_session_user_id(request)
    if user_id is None:
        if path == "/":
            return RedirectResponse(url="/login", status_code=302)
        return JSONResponse(status_code=401, content={"error": "Unauthorized"})

    db = next(get_db())
    user = db.query(models.User).filter(models.User.id == user_id).first()
    db.close()
    if user is None:
        response = RedirectResponse(url="/login", status_code=302)
        response.delete_cookie(COOKIE_NAME)
        return response

    request.state.user = user
    return await call_next(request)


def get_user(request: Request) -> models.User:
    user = getattr(request.state, "user", None)
    if user is None:
        raise HTTPException(status_code=401)
    return user


# ===== AUTH =====
@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@app.post("/login")
def login_submit(
    request: Request,
    name: str = Form(...),
    pin: str = Form(...),
    db: Session = Depends(get_db),
):
    user = authenticate_user(db, name, pin)
    if not user:
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "Falscher Name oder PIN"},
        )
    response = RedirectResponse(url="/", status_code=302)
    response.set_cookie(
        key=COOKIE_NAME,
        value=create_session(user.id),
        max_age=COOKIE_MAX_AGE,
        httponly=True,
        samesite="lax",
    )
    return response


@app.get("/register", response_class=HTMLResponse)
def register_page(request: Request):
    return templates.TemplateResponse("register.html", {"request": request})


@app.post("/register")
def register_submit(
    request: Request,
    name: str = Form(...),
    pin: str = Form(...),
    db: Session = Depends(get_db),
):
    if len(name.strip()) < 1:
        return templates.TemplateResponse(
            "register.html",
            {"request": request, "error": "Name darf nicht leer sein"},
        )
    if len(pin) < 3:
        return templates.TemplateResponse(
            "register.html",
            {"request": request, "error": "PIN muss mindestens 3 Zeichen lang sein"},
        )
    user = register_user(db, name.strip(), pin)
    if not user:
        return templates.TemplateResponse(
            "register.html",
            {"request": request, "error": "Name bereits vergeben"},
        )
    return RedirectResponse(url="/login", status_code=302)


@app.post("/logout")
def logout():
    response = RedirectResponse(url="/login", status_code=302)
    response.delete_cookie(COOKIE_NAME)
    return response


# ===== DASHBOARD =====
@app.get("/", response_class=HTMLResponse)
def dashboard(
    request: Request,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_user),
):
    today = date.today()
    today_workout = (
        db.query(models.Workout)
        .filter(models.Workout.user_id == user.id, models.Workout.date == today)
        .order_by(models.Workout.id.desc())
        .first()
    )
    last_workout = (
        db.query(models.Workout)
        .filter(
            models.Workout.user_id == user.id,
            models.Workout.is_completed == True,
        )
        .order_by(models.Workout.date.desc())
        .first()
    )
    weight_entries = (
        db.query(models.WeightEntry)
        .filter(models.WeightEntry.user_id == user.id)
        .order_by(models.WeightEntry.date.desc())
        .limit(30)
        .all()
    )
    latest_weight = weight_entries[0] if weight_entries else None

    week_start = today - timedelta(days=today.weekday())
    week_workouts = (
        db.query(models.Workout)
        .filter(
            models.Workout.user_id == user.id,
            models.Workout.date >= week_start,
            models.Workout.date <= today,
            models.Workout.is_completed == True,
        )
        .count()
    )

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "user": user,
            "today_workout": today_workout,
            "last_workout": last_workout,
            "weight_entries": weight_entries[::-1] if weight_entries else [],
            "latest_weight": latest_weight,
            "today": today,
            "week_workouts": week_workouts,
        },
    )


# ===== WORKOUTS =====
@app.get("/workouts", response_class=HTMLResponse)
def workout_list(
    request: Request,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_user),
):
    workouts = (
        db.query(models.Workout)
        .filter(models.Workout.user_id == user.id)
        .order_by(models.Workout.date.desc())
        .limit(50)
        .all()
    )
    return templates.TemplateResponse(
        "workout.html", {"request": request, "user": user, "workouts": workouts}
    )


@app.get("/workout/new", response_class=HTMLResponse)
def new_workout(
    request: Request,
    template_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    user: models.User = Depends(get_user),
):
    templates_list = (
        db.query(models.TemplateWorkout)
        .order_by(models.TemplateWorkout.day_of_week)
        .all()
    )
    all_exercises = (
        db.query(models.Exercise).order_by(models.Exercise.name).all()
    )
    selected = None
    if template_id:
        selected = (
            db.query(models.TemplateWorkout)
            .filter(models.TemplateWorkout.id == template_id)
            .first()
        )
    return templates.TemplateResponse(
        "workout_detail.html",
        {
            "request": request,
            "user": user,
            "templates": templates_list,
            "all_exercises": all_exercises,
            "selected_template": selected,
        },
    )


@app.post("/workout/new")
def create_workout(
    request: Request,
    name: str = Form(...),
    template_id: Optional[int] = Form(None),
    db: Session = Depends(get_db),
    user: models.User = Depends(get_user),
):
    workout = models.Workout(name=name, date=date.today(), user_id=user.id)
    db.add(workout)
    db.flush()

    if template_id:
        tmpl = (
            db.query(models.TemplateWorkout)
            .filter(models.TemplateWorkout.id == template_id)
            .first()
        )
        if tmpl:
            for te in tmpl.exercises:
                we = models.WorkoutExercise(
                    workout_id=workout.id,
                    exercise_id=te.exercise_id,
                    sort_order=te.sort_order,
                    notes=te.notes,
                )
                db.add(we)
                db.flush()
                for i in range(te.target_sets):
                    s = models.Set(
                        workout_exercise_id=we.id,
                        set_number=i + 1,
                        is_warmup=(i == 0),
                    )
                    db.add(s)

    db.commit()
    return RedirectResponse(url=f"/workout/{workout.id}", status_code=302)


@app.get("/workout/{workout_id}", response_class=HTMLResponse)
def workout_detail(
    request: Request,
    workout_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_user),
):
    workout = (
        db.query(models.Workout)
        .filter(models.Workout.id == workout_id, models.Workout.user_id == user.id)
        .first()
    )
    if not workout:
        raise HTTPException(status_code=404, detail="Workout not found")

    recs = {}
    for we in workout.exercises:
        te = (
            db.query(models.TemplateExercise)
            .filter(models.TemplateExercise.exercise_id == we.exercise_id)
            .first()
        )
        if te:
            target_min = te.target_reps_min
            target_max = te.target_reps_max
        elif we.exercise.category == "compound":
            target_min, target_max = 6, 10
        else:
            target_min, target_max = 10, 15

        rec = get_weight_recommendation(db, we.exercise_id, target_min, target_max)
        if rec:
            rec["target_min"] = target_min
            rec["target_max"] = target_max
            recs[we.exercise_id] = rec

    all_exercises = (
        db.query(models.Exercise).order_by(models.Exercise.name).all()
    )

    return templates.TemplateResponse(
        "workout_detail.html",
        {
            "request": request,
            "user": user,
            "workout": workout,
            "recs": recs,
            "all_exercises": all_exercises,
        },
    )


@app.post("/workout/{workout_id}/set/{set_id}")
def update_set(
    request: Request,
    workout_id: int,
    set_id: int,
    weight: Optional[float] = Form(None),
    reps: Optional[int] = Form(None),
    rpe: Optional[int] = Form(None),
    is_failure: bool = Form(False),
    is_warmup: bool = Form(False),
    is_completed: bool = Form(True),
    db: Session = Depends(get_db),
    user: models.User = Depends(get_user),
):
    s = db.query(models.Set).filter(models.Set.id == set_id).first()
    if s:
        if weight is not None:
            s.weight = weight
        if reps is not None:
            s.reps = reps
        if rpe is not None:
            s.rpe = rpe
        s.is_failure = is_failure
        s.is_completed = is_completed
        db.commit()
    return RedirectResponse(url=f"/workout/{workout_id}", status_code=302)


@app.post("/workout/{workout_id}/complete")
def complete_workout(
    request: Request,
    workout_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_user),
):
    workout = (
        db.query(models.Workout)
        .filter(models.Workout.id == workout_id, models.Workout.user_id == user.id)
        .first()
    )
    if workout:
        workout.is_completed = True
        db.commit()
    return RedirectResponse(url="/", status_code=302)


@app.post("/workout/{workout_id}/add-set/{exercise_id}")
def add_set(
    workout_id: int,
    exercise_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_user),
):
    we = (
        db.query(models.WorkoutExercise)
        .filter(
            models.WorkoutExercise.workout_id == workout_id,
            models.WorkoutExercise.exercise_id == exercise_id,
        )
        .first()
    )
    if we:
        max_num = (
            db.query(models.Set)
            .filter(models.Set.workout_exercise_id == we.id)
            .count()
        )
        s = models.Set(
            workout_exercise_id=we.id,
            set_number=max_num + 1,
            is_warmup=False,
        )
        db.add(s)
        db.commit()
    return RedirectResponse(url=f"/workout/{workout_id}", status_code=302)


@app.post("/workout/{workout_id}/add-exercise")
def add_exercise_to_workout(
    request: Request,
    workout_id: int,
    exercise_id: int = Form(...),
    target_sets: int = Form(3),
    db: Session = Depends(get_db),
    user: models.User = Depends(get_user),
):
    max_order = (
        db.query(models.WorkoutExercise)
        .filter(models.WorkoutExercise.workout_id == workout_id)
        .count()
    )
    we = models.WorkoutExercise(
        workout_id=workout_id,
        exercise_id=exercise_id,
        sort_order=max_order + 1,
    )
    db.add(we)
    db.flush()
    for i in range(target_sets):
        s = models.Set(
            workout_exercise_id=we.id,
            set_number=i + 1,
            is_warmup=(i == 0),
        )
        db.add(s)
    db.commit()
    return RedirectResponse(url=f"/workout/{workout_id}", status_code=302)


@app.post("/workout/{workout_id}/delete")
def delete_workout(
    request: Request,
    workout_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_user),
):
    w = (
        db.query(models.Workout)
        .filter(models.Workout.id == workout_id, models.Workout.user_id == user.id)
        .first()
    )
    if w:
        db.delete(w)
        db.commit()
    return RedirectResponse(url="/workouts", status_code=302)


# ===== API: Weight Recommendations =====
@app.get("/api/recommendation/{exercise_id}")
def api_recommendation(
    exercise_id: int,
    target_reps_min: int = Query(8),
    target_reps_max: int = Query(12),
    bodyweight: float = Query(75),
    db: Session = Depends(get_db),
):
    rec = get_weight_recommendation(
        db, exercise_id, target_reps_min, target_reps_max, bodyweight
    )
    if not rec:
        return {"error": "Keine Empfehlung verfügbar"}
    return rec


@app.get("/api/1rm-trend/{exercise_id}")
def api_1rm_trend(exercise_id: int, db: Session = Depends(get_db)):
    return calculate_1rm_trend(db, exercise_id)


# ===== CALENDAR =====
@app.get("/calendar", response_class=HTMLResponse)
def calendar_page(
    request: Request,
    month: Optional[int] = Query(None),
    year: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    user: models.User = Depends(get_user),
):
    today = date.today()
    if month is None:
        month = today.month
    if year is None:
        year = today.year

    first_day = date(year, month, 1)
    if month == 12:
        last_day = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        last_day = date(year, month + 1, 1) - timedelta(days=1)

    workouts = (
        db.query(models.Workout)
        .filter(
            models.Workout.user_id == user.id,
            models.Workout.date >= first_day,
            models.Workout.date <= last_day,
        )
        .order_by(models.Workout.date)
        .all()
    )
    workout_dates = {w.date: w for w in workouts}

    first_weekday = first_day.weekday()
    days_in_month = last_day.day

    prev_m = 12 if month == 1 else month - 1
    prev_y = year - 1 if month == 1 else year
    next_m = 1 if month == 12 else month + 1
    next_y = year + 1 if month == 12 else year

    return templates.TemplateResponse(
        "calendar.html",
        {
            "request": request,
            "user": user,
            "workout_dates": workout_dates,
            "month": month,
            "year": year,
            "today": today,
            "first_day": first_day,
            "last_day": last_day,
            "first_weekday": first_weekday,
            "days_in_month": days_in_month,
            "prev_m": prev_m,
            "prev_y": prev_y,
            "next_m": next_m,
            "next_y": next_y,
            "date": date,
        },
    )


# ===== PLAN =====
@app.get("/plan", response_class=HTMLResponse)
def view_plan(
    request: Request,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_user),
):
    templates_list = (
        db.query(models.TemplateWorkout)
        .order_by(models.TemplateWorkout.day_of_week)
        .all()
    )
    all_exercises = (
        db.query(models.Exercise).order_by(models.Exercise.name).all()
    )
    return templates.TemplateResponse(
        "plan.html",
        {
            "request": request,
            "user": user,
            "templates": templates_list,
            "all_exercises": all_exercises,
        },
    )


@app.post("/plan/exercise/add")
def add_exercise_to_plan(
    request: Request,
    template_workout_id: int = Form(...),
    exercise_id: int = Form(...),
    target_sets: int = Form(3),
    target_reps_min: int = Form(8),
    target_reps_max: int = Form(12),
    db: Session = Depends(get_db),
    user: models.User = Depends(get_user),
):
    tmpl = (
        db.query(models.TemplateWorkout)
        .filter(models.TemplateWorkout.id == template_workout_id)
        .first()
    )
    if tmpl:
        max_order = (
            db.query(models.TemplateExercise)
            .filter(
                models.TemplateExercise.template_workout_id == template_workout_id
            )
            .count()
        )
        te = models.TemplateExercise(
            template_workout_id=template_workout_id,
            exercise_id=exercise_id,
            target_sets=target_sets,
            target_reps_min=target_reps_min,
            target_reps_max=target_reps_max,
            sort_order=max_order + 1,
        )
        db.add(te)
        db.commit()
    return RedirectResponse(url="/plan", status_code=302)


@app.post("/plan/exercise/{template_exercise_id}/delete")
def delete_exercise_from_plan(
    request: Request,
    template_exercise_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_user),
):
    te = (
        db.query(models.TemplateExercise)
        .filter(models.TemplateExercise.id == template_exercise_id)
        .first()
    )
    if te:
        db.delete(te)
        db.commit()
    return RedirectResponse(url="/plan", status_code=302)


# ===== EXERCISES =====
@app.get("/exercises", response_class=HTMLResponse)
def exercise_list(
    request: Request,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_user),
):
    groups = (
        db.query(models.MuscleGroup)
        .order_by(models.MuscleGroup.name)
        .all()
    )
    return templates.TemplateResponse(
        "exercises.html", {"request": request, "user": user, "groups": groups}
    )


@app.get("/exercise/{exercise_id}", response_class=HTMLResponse)
def exercise_detail_page(
    request: Request,
    exercise_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_user),
):
    exercise = (
        db.query(models.Exercise)
        .filter(models.Exercise.id == exercise_id)
        .first()
    )
    if not exercise:
        raise HTTPException(status_code=404)

    trend = calculate_1rm_trend(db, exercise_id)

    recent_workouts = (
        db.query(models.WorkoutExercise)
        .filter(models.WorkoutExercise.exercise_id == exercise_id)
        .order_by(models.WorkoutExercise.id.desc())
        .limit(5)
        .all()
    )

    return templates.TemplateResponse(
        "exercise_detail.html",
        {
            "request": request,
            "user": user,
            "exercise": exercise,
            "trend": trend,
            "recent_workouts": recent_workouts,
        },
    )


# ===== WEIGHT =====
@app.get("/weight", response_class=HTMLResponse)
def weight_page(
    request: Request,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_user),
):
    entries = (
        db.query(models.WeightEntry)
        .filter(models.WeightEntry.user_id == user.id)
        .order_by(models.WeightEntry.date)
        .all()
    )
    return templates.TemplateResponse(
        "weight.html", {"request": request, "user": user, "entries": entries}
    )


@app.post("/weight")
def add_weight(
    request: Request,
    weight: float = Form(...),
    notes: Optional[str] = Form(""),
    db: Session = Depends(get_db),
    user: models.User = Depends(get_user),
):
    entry = models.WeightEntry(
        weight=weight, notes=notes, date=date.today(), user_id=user.id
    )
    db.add(entry)
    db.commit()
    return RedirectResponse(url="/weight", status_code=302)


@app.post("/weight/delete/{entry_id}")
def delete_weight(
    request: Request,
    entry_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_user),
):
    entry = (
        db.query(models.WeightEntry)
        .filter(models.WeightEntry.id == entry_id, models.WeightEntry.user_id == user.id)
        .first()
    )
    if entry:
        db.delete(entry)
        db.commit()
    return RedirectResponse(url="/weight", status_code=302)


# ===== STATS =====
@app.get("/stats", response_class=HTMLResponse)
def stats_page(
    request: Request,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_user),
):
    total_workouts = (
        db.query(models.Workout)
        .filter(
            models.Workout.user_id == user.id,
            models.Workout.is_completed == True,
        )
        .count()
    )
    total_sets = (
        db.query(models.Set)
        .filter(models.Set.is_completed == True)
        .count()
    )

    twelve_weeks_ago = date.today() - timedelta(weeks=12)
    workouts = (
        db.query(models.Workout)
        .filter(
            models.Workout.user_id == user.id,
            models.Workout.date >= twelve_weeks_ago,
            models.Workout.is_completed == True,
        )
        .order_by(models.Workout.date)
        .all()
    )
    weekly_volume = {}
    for w in workouts:
        iso = w.date.isocalendar()
        key = f"{w.date.year}-W{iso[1]}"
        volume = 0
        for we in w.exercises:
            for s in we.sets:
                if s.is_completed and s.weight and s.reps:
                    volume += s.weight * s.reps
        weekly_volume[key] = weekly_volume.get(key, 0) + volume

    weekly_data = [
        {"week": k, "volume": round(v)} for k, v in sorted(weekly_volume.items())
    ]

    all_sets = (
        db.query(models.Set)
        .filter(
            models.Set.is_completed == True,
            models.Set.is_warmup == False,
            models.Set.weight.isnot(None),
        )
        .order_by(models.Set.weight.desc())
        .limit(200)
        .all()
    )
    best_lifts = {}
    for s in all_sets:
        we = (
            db.query(models.WorkoutExercise)
            .filter(models.WorkoutExercise.id == s.workout_exercise_id)
            .first()
        )
        if we and we.exercise:
            name = we.exercise.name
            if name not in best_lifts or s.weight > best_lifts[name]["weight"]:
                w = (
                    db.query(models.Workout)
                    .filter(models.Workout.id == we.workout_id)
                    .first()
                )
                best_lifts[name] = {
                    "weight": s.weight,
                    "reps": s.reps,
                    "date": str(w.date) if w else "",
                }

    best_lifts_sorted = sorted(
        best_lifts.items(), key=lambda x: x[1]["weight"], reverse=True
    )[:20]

    latest_weight_entry = (
        db.query(models.WeightEntry)
        .filter(models.WeightEntry.user_id == user.id)
        .order_by(models.WeightEntry.date.desc())
        .first()
    )

    return templates.TemplateResponse(
        "stats.html",
        {
            "request": request,
            "user": user,
            "total_workouts": total_workouts,
            "total_sets": total_sets,
            "weekly_data": weekly_data,
            "best_lifts": best_lifts_sorted,
            "latest_weight_entry": latest_weight_entry,
        },
    )


# ===== HISTORY =====
@app.get("/history", response_class=HTMLResponse)
def history_page(
    request: Request,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_user),
):
    workouts = (
        db.query(models.Workout)
        .filter(
            models.Workout.user_id == user.id,
            models.Workout.is_completed == True,
        )
        .order_by(models.Workout.date.desc())
        .all()
    )
    all_exercises = (
        db.query(models.Exercise).order_by(models.Exercise.name).all()
    )
    return templates.TemplateResponse(
        "history.html",
        {
            "request": request,
            "user": user,
            "workouts": workouts,
            "all_exercises": all_exercises,
        },
    )


# ===== LEADERBOARD =====
@app.get("/leaderboard", response_class=HTMLResponse)
def leaderboard_page(
    request: Request,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_user),
):
    exercises = (
        db.query(models.Exercise).order_by(models.Exercise.name).all()
    )
    return templates.TemplateResponse(
        "leaderboard.html",
        {
            "request": request,
            "user": user,
            "exercises": exercises,
        },
    )


@app.get("/api/leaderboard/exercise/{exercise_id}")
def leaderboard_by_exercise(
    exercise_id: int,
    db: Session = Depends(get_db),
):
    rows = (
        db.query(
            models.User.name,
            models.Set.weight,
            models.Set.reps,
            models.Workout.date,
            models.Set.id,
        )
        .select_from(models.Set)
        .join(models.WorkoutExercise, models.Set.workout_exercise_id == models.WorkoutExercise.id)
        .join(models.Workout, models.WorkoutExercise.workout_id == models.Workout.id)
        .join(models.User, models.Workout.user_id == models.User.id)
        .filter(
            models.WorkoutExercise.exercise_id == exercise_id,
            models.Set.is_completed == True,
            models.Set.is_warmup == False,
            models.Set.weight.isnot(None),
            models.Set.reps.isnot(None),
        )
        .order_by(models.Set.weight.desc())
        .limit(50)
        .all()
    )

    best_per_user = {}
    for name, weight, reps, w_date, _ in rows:
        e1rm = weight * (1 + reps / 30)
        if name not in best_per_user or weight > best_per_user[name]["weight"]:
            best_per_user[name] = {
                "name": name,
                "weight": weight,
                "reps": reps,
                "e1rm": round(e1rm, 1),
                "date": str(w_date),
            }

    return {"entries": sorted(best_per_user.values(), key=lambda x: x["weight"], reverse=True)}


@app.get("/api/leaderboard/weekly-volume")
def leaderboard_weekly_volume(
    db: Session = Depends(get_db),
):
    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    rows = (
        db.query(
            models.User.name,
            models.Workout.id,
        )
        .select_from(models.Workout)
        .join(models.User, models.Workout.user_id == models.User.id)
        .filter(
            models.Workout.date >= week_start,
            models.Workout.date <= today,
            models.Workout.is_completed == True,
        )
        .all()
    )

    counts = {}
    for name, _ in rows:
        counts[name] = counts.get(name, 0) + 1

    sorted_entries = sorted(counts.items(), key=lambda x: x[1], reverse=True)
    return {
        "entries": [
            {"name": name, "workouts": count} for name, count in sorted_entries
        ]
    }


# ===== LEADERBOARD (alle Übungen auf einmal, für Dropdown) =====
@app.get("/api/leaderboard/exercises")
def leaderboard_exercises(
    db: Session = Depends(get_db),
):
    exercises = (
        db.query(models.Exercise.id, models.Exercise.name)
        .order_by(models.Exercise.name)
        .all()
    )
    return {"exercises": [{"id": e.id, "name": e.name} for e in exercises]}
