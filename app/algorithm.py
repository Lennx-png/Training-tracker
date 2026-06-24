"""
Gewichtsempfehlungs-Algorithmus
================================
Basierend auf Sportwissenschaft:

- Epley-Formel zur 1RM-Schätzung (Epley 1985)
  "1RM = weight × (1 + reps/30)" – Genauigkeit ±5% für reps ≤ 10

- Double Progression (Helms et al. 2016)
  Erst Wiederholungen im Zielbereich maximieren, dann Gewicht erhöhen.

- Autoregulation via RPE (Zourdos et al. 2016)
  RPE 6-7 = sicher, RPE 8-9 = hart, RPE 10 = Failure

- Progressionsrate für Erfahrene (Schoenfeld et al. 2016)
  Max +2.5kg / Woche bzw. +5% alle 2-4 Wochen

- Deload-Zyklus (Issurin 2010)
  4-6 Wochen Belastung, dann 1 Woche reduziert
"""
from datetime import date, timedelta
from sqlalchemy.orm import Session
from app import models
import math


def estimate_1rm(weight: float, reps: int) -> float:
    """Epley-Formel: 1RM = Gewicht × (1 + reps/30)"""
    if reps <= 0 or weight <= 0:
        return None
    return weight * (1 + reps / 30)


DEFAULT_STARTING_WEIGHTS = {
    "bankdrücken": 0.80,
    "schrägbankdrücken": 0.65,
    "incline dumbbell press": 0.60,
    "cable flies": 0.30,
    "cable crossovers": 0.30,
    "überkopf-schulterdrücken": 0.55,
    "schulterdrücken": 0.55,
    "seitheben": 0.15,
    "kabel seitheben": 0.15,
    "trizepsdrücken": 0.35,
    "trizeps-pushdowns": 0.35,
    "triceps overhead extension": 0.25,
    "skull crushers": 0.25,
    "dips": 0.40,
    "klimmzüge": 0.25,
    "latzug": 0.80,
    "heavy lat pulldown": 0.80,
    "langhantel-rudern": 0.70,
    "t-bar-rudern": 0.70,
    "kurzhantelrudern": 0.50,
    "kabelrudern": 0.60,
    "einarmiges kurzhantelrudern": 0.50,
    "reverse flies": 0.15,
    "face pulls": 0.15,
    "schrägbank-bizepscurls": 0.22,
    "hammercurls": 0.22,
    "preacher curls": 0.25,
    "langhantel-curl": 0.30,
    "barbell curl": 0.30,
    "kniebeugen": 1.00,
    "hack squat": 1.20,
    "frontkniebeuge": 0.80,
    "front squat": 0.80,
    "rumänisches kreuzheben": 0.90,
    "rdl": 0.90,
    "beinpresse": 1.50,
    "beinstrecker": 0.60,
    "beinbeuger": 0.40,
    "hip thrust": 0.80,
    "wadenheben": 1.20,
    "ausfallschritte": 0.40,
    "walking lunges": 0.40,
    "cable crunches": 0.40,
    "beinheben": 0.00,
    "kreuzheben": 1.20,
    "deadlift": 1.20,
    "farmer walk": 0.80,
    "neck curl": 0.10,
    "reverse hyperextension": 0.30,
    "preacher curls": 0.25,
    "ez bar curl": 0.30,
    "ez bar skull crushers": 0.30,
    "overhead tricep extension": 0.25,
    "french press": 0.25,
    "cable tricep pushdown": 0.35,
    "chest supported row": 0.60,
    "reverse fly": 0.15,
    "bulgarian split squat": 0.40,
    "goblet squat": 0.30,
    "upright row": 0.30,
    "db shrug": 0.80,
}


def get_default_starting_weight(exercise_name: str, bodyweight: float = 75) -> float:
    """Default-Empfehlung basierend auf NSCA-Standards (% des Körpergewichts)."""
    for key, ratio in DEFAULT_STARTING_WEIGHTS.items():
        if key in exercise_name.lower():
            return round(bodyweight * ratio / 1.25) * 1.25
    return round(bodyweight * 0.4 / 1.25) * 1.25


def _check_deload_due(db: Session, exercise_id: int) -> bool:
    """Prüft, ob ein Deload fällig ist (≥10 harte Sessions in 6 Wochen)."""
    six_weeks_ago = date.today() - timedelta(weeks=6)
    recent_workouts = (
        db.query(models.Workout)
        .join(models.WorkoutExercise)
        .filter(
            models.WorkoutExercise.exercise_id == exercise_id,
            models.Workout.date >= six_weeks_ago,
            models.Workout.is_completed == True,
        )
        .count()
    )
    return recent_workouts >= 10


def get_weight_recommendation(
    db: Session,
    exercise_id: int,
    target_reps_min: int = 8,
    target_reps_max: int = 12,
    bodyweight: float = 75,
):
    """
    Hauptfunktion: Berechnet empfohlenes Gewicht basierend auf
    Trainingshistorie und wissenschaftlicher Progression.
    """
    exercise = db.query(models.Exercise).filter(models.Exercise.id == exercise_id).first()
    if not exercise:
        return None

    # Letzte 10 abgeschlossene Sätze abrufen
    recent_sets = (
        db.query(models.Set)
        .join(models.WorkoutExercise)
        .filter(
            models.WorkoutExercise.exercise_id == exercise_id,
            models.Set.is_warmup == False,
            models.Set.is_completed == True,
            models.Set.weight.isnot(None),
            models.Set.reps.isnot(None),
        )
        .order_by(models.Set.id.desc())
        .limit(10)
        .all()
    )

    if not recent_sets:
        return _default_recommendation(exercise.name, target_reps_min, target_reps_max, bodyweight)

    # Sätze nach Workout-Session gruppieren
    sets_by_workout = {}
    for s in recent_sets:
        we_id = s.workout_exercise_id
        if we_id not in sets_by_workout:
            sets_by_workout[we_id] = []
        sets_by_workout[we_id].append(s)

    # Besten e1RM pro Session berechnen
    latest_weight = 0
    latest_reps = 0
    latest_rpe = None
    best_e1rm_per_session = []

    for we_id, sets in sorted(sets_by_workout.items(), reverse=True):
        best_e1rm = 0
        best_s = None
        for s in sets:
            e1rm = estimate_1rm(s.weight, s.reps)
            if e1rm and e1rm > best_e1rm:
                best_e1rm = e1rm
                best_s = s
        if best_e1rm > 0:
            best_e1rm_per_session.append(best_e1rm)
            if best_s:
                latest_weight = best_s.weight
                latest_reps = best_s.reps
                latest_rpe = best_s.rpe

    if not best_e1rm_per_session:
        return _default_recommendation(exercise.name, target_reps_min, target_reps_max, bodyweight)

    # Exponentielle Gewichtung (neuere Sessions zählen mehr)
    weighted_e1rm = 0
    total_weight = 0
    for i, e1rm in enumerate(best_e1rm_per_session[:5]):
        w = 1.0 / (i + 1)
        weighted_e1rm += e1rm * w
        total_weight += w
    weighted_e1rm /= total_weight

    target_reps_mid = (target_reps_min + target_reps_max) / 2
    recommended_weight = weighted_e1rm / (1 + target_reps_mid / 30)

    # Double Progression Logik
    all_sets_in_range = True
    reached_upper = True
    failed_last_session = False
    total_reps_last_workout = 0
    sets_in_last_workout = 0

    # Analyse der letzten Session (erste Gruppe in recent_sets)
    last_we_id = None
    if recent_sets:
        last_we_id = recent_sets[0].workout_exercise_id

    for s in recent_sets:
        if s.workout_exercise_id == last_we_id:
            if s.is_failure:
                failed_last_session = True
            if s.reps is not None:
                total_reps_last_workout += s.reps
                sets_in_last_workout += 1
                if s.reps < target_reps_min:
                    all_sets_in_range = False
                    reached_upper = False
                elif s.reps > target_reps_max:
                    pass
                else:
                    if s.reps < target_reps_max:
                        reached_upper = False

    # RPE-Korrektur
    rpe_correction = 1.0
    if latest_rpe is not None:
        if latest_rpe >= 9:
            rpe_correction = 0.975  # -2.5% bei Extrem-Härte
        elif latest_rpe >= 7:
            rpe_correction = 1.0
        else:
            rpe_correction = 1.025  # +2.5% wenn zu einfach

    recommended_weight *= rpe_correction

    # Deload-Prüfung
    deload_due = _check_deload_due(db, exercise_id)

    if deload_due:
        deload_weight = recommended_weight * 0.70
        return {
            "gewicht": round(deload_weight / 1.25) * 1.25,
            "reps": int(target_reps_mid),
            "aenderung_kg": 0,
            "deload_faellig": True,
            "progressions_art": "deload",
            "begruendung": "Deload-Woche fällig (10+ harte Sessions in 6 Wochen). ~70% Intensität empfohlen.",
            "e1RM_aktuell": round(weighted_e1rm, 1),
        }

    # Änderung bestimmen
    change_kg = 0.0
    progression_type = "wiederholungen"

    if failed_last_session:
        change_kg = -5.0
        progression_type = "reduktion"
    elif all_sets_in_range and reached_upper:
        change_kg = 2.5
        progression_type = "gewicht"
    elif all_sets_in_range:
        change_kg = 0.0
        progression_type = "wiederholungen"
    else:
        change_kg = -2.5
        progression_type = "reduktion"

    change_kg = max(-5.0, min(change_kg, 2.5))

    final_weight = recommended_weight + change_kg
    final_weight = round(final_weight / 1.25) * 1.25
    if final_weight <= 0:
        final_weight = 2.5

    reasons = {
        "gewicht": f"Alle Sätze im Zielbereich + obere Grenze erreicht. Steigere um {change_kg}kg.",
        "wiederholungen": "Zielbereich erreicht. Bleibe beim Gewicht, erhöhe Wiederholungen.",
        "reduktion": f"Sätze unvollständig oder Failure. Reduziere um {abs(change_kg)}kg.",
    }

    return {
        "gewicht": float(final_weight),
        "reps": int(target_reps_mid),
        "aenderung_kg": change_kg,
        "deload_faellig": False,
        "progressions_art": progression_type,
        "begruendung": reasons.get(progression_type, ""),
        "e1RM_aktuell": round(weighted_e1rm, 1),
        "weighted_e1rm": round(weighted_e1rm, 1),
    }


def _default_recommendation(exercise_name, target_reps_min, target_reps_max, bodyweight):
    target_reps = (target_reps_min + target_reps_max) // 2
    weight = get_default_starting_weight(exercise_name, bodyweight)
    return {
        "gewicht": weight,
        "reps": target_reps,
        "aenderung_kg": 0,
        "deload_faellig": False,
        "progressions_art": "start",
        "begruendung": "Startgewicht basierend auf Körpergewicht. Passe bei Bedarf an.",
        "e1RM_aktuell": round(estimate_1rm(weight, target_reps), 1) if weight > 0 else 0,
    }


def calculate_1rm_trend(db: Session, exercise_id: int):
    """Berechnet 1RM-Verlauf über Zeit für die Chart-Ansicht."""
    sets = (
        db.query(models.Set)
        .join(models.WorkoutExercise)
        .filter(
            models.WorkoutExercise.exercise_id == exercise_id,
            models.Set.is_completed == True,
            models.Set.is_warmup == False,
            models.Set.weight.isnot(None),
            models.Set.reps.isnot(None),
        )
        .order_by(models.Set.id)
        .all()
    )

    trend = {}
    for s in sets:
        we = (
            db.query(models.WorkoutExercise)
            .filter(models.WorkoutExercise.id == s.workout_exercise_id)
            .first()
        )
        if we:
            w = db.query(models.Workout).filter(models.Workout.id == we.workout_id).first()
            if w:
                date_str = str(w.date)
                e1rm = estimate_1rm(s.weight, s.reps)
                if e1rm and (date_str not in trend or e1rm > trend[date_str]):
                    trend[date_str] = round(e1rm, 1)

    return [{"date": d, "e1rm": v} for d, v in sorted(trend.items())]
