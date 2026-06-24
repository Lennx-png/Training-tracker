from app import models
from app.auth import hash_pin
from sqlalchemy.orm import Session


DAY_NAMES = {
    0: "Montag: Push",
    1: "Dienstag: Pull",
    2: "Mittwoch: Pause",
    3: "Donnerstag: Legs",
    4: "Freitag: Oberkörper",
    5: "Samstag: Unterkörper & Core",
    6: "Sonntag: Pause",
}

TRAINING_PLAN = {
    0: {  # Montag: Push
        "name": "Montag: Push",
        "exercises": [
            ("Bankdrücken (Langhantel)", "Brust", "compound", 4, 6, 8),
            ("Schrägbankdrücken (Kurzhantel)", "Brust", "compound", 3, 8, 12),
            ("Cable Flies", "Brust", "isolation", 3, 12, 15),
            ("Überkopf-Schulterdrücken (Kurzhantel)", "Schulter (vorderer)", "compound", 3, 8, 10),
            ("Seitheben (Kurzhantel)", "Schulter (seitlicher)", "isolation", 4, 12, 15),
            ("Trizepsdrücken am Kabel", "Trizeps", "isolation", 3, 10, 12),
            ("Triceps Overhead Extension (Kabel)", "Trizeps", "isolation", 3, 12, 15),
        ],
    },
    1: {  # Dienstag: Pull
        "name": "Dienstag: Pull",
        "exercises": [
            ("Klimmzüge (Latissimus-Zug)", "Rücken (Latissimus)", "compound", 4, 6, 8),
            ("Langhantel-Rudern", "Rücken (oberer)", "compound", 3, 8, 10),
            ("Einarmiges Kurzhantelrudern", "Rücken (Latissimus)", "compound", 3, 10, 12),
            ("Face Pulls", "Schulter (hinterer)", "isolation", 4, 12, 15),
            ("Schrägbank-Bizepscurls", "Bizeps", "isolation", 3, 10, 12),
            ("Hammercurls (Kabelzug)", "Bizeps", "isolation", 3, 12, 15),
        ],
    },
    3: {  # Donnerstag: Legs
        "name": "Donnerstag: Legs",
        "exercises": [
            ("Kniebeugen (Langhantel)", "Beine (Quadrizeps)", "compound", 4, 6, 8),
            ("Rumänisches Kreuzheben", "Beine (Hamstrings)", "compound", 4, 8, 10),
            ("Beinpresse (45°)", "Beine (Quadrizeps)", "compound", 3, 10, 12),
            ("Beinstrecker (Maschine)", "Beine (Quadrizeps)", "isolation", 3, 12, 15),
            ("Wadenheben (stehend)", "Waden", "isolation", 4, 10, 12),
        ],
    },
    4: {  # Freitag: Oberkörper
        "name": "Freitag: Oberkörper",
        "exercises": [
            ("Incline Dumbbell Press", "Brust", "compound", 3, 8, 10),
            ("Heavy Lat Pulldown", "Rücken (Latissimus)", "compound", 3, 8, 10),
            ("Dips (mit Zusatzgewicht)", "Trizeps", "compound", 3, 8, 12),
            ("Kabelrudern (eng)", "Rücken (oberer)", "isolation", 3, 10, 12),
            ("Seitheben am Kabelzug (hinter Rücken)", "Schulter (seitlicher)", "isolation", 4, 12, 15),
            ("Preacher Curls (SZ-Stange)", "Bizeps", "isolation", 3, 10, 12),
            ("Trizeps-Pushdowns (gerade Stange)", "Trizeps", "isolation", 3, 10, 12),
        ],
    },
    5: {  # Samstag: Unterkörper & Core
        "name": "Samstag: Unterkörper & Core",
        "exercises": [
            ("Walking Lunges mit Kurzhanteln", "Beine (Quadrizeps)", "compound", 3, 10, 12),
            ("Beinbeuger (liegend)", "Beine (Hamstrings)", "isolation", 4, 10, 12),
            ("Beinstrecker (Maschine, Peak Contraction)", "Beine (Quadrizeps)", "isolation", 3, 12, 15),
            ("Wadenheben (sitzend)", "Waden", "isolation", 4, 12, 15),
            ("Beinheben (hängend)", "Core", "isolation", 3, 0, 0),
            ("Cable Crunches", "Core", "isolation", 3, 12, 15),
        ],
    },
}

ALL_MUSCLE_GROUPS = [
    "Brust",
    "Schulter (vorderer)",
    "Schulter (seitlicher)",
    "Schulter (hinterer)",
    "Rücken (Latissimus)",
    "Rücken (oberer)",
    "Bizeps",
    "Trizeps",
    "Beine (Quadrizeps)",
    "Beine (Hamstrings)",
    "Waden",
    "Core",
    "Nacken",
    "Unterarme",
]


def seed_data(db: Session):
    """Fügt Standard-Daten ein, falls die DB leer ist."""
    # Default-User anlegen, falls noch keiner existiert
    if db.query(models.User).count() == 0:
        admin = models.User(name="Admin", pin_hash=hash_pin("1234"))
        db.add(admin)
        db.commit()

    if db.query(models.MuscleGroup).count() > 0:
        return

    muscle_groups = {}
    for name in ALL_MUSCLE_GROUPS:
        mg = models.MuscleGroup(name=name)
        db.add(mg)
        db.flush()
        muscle_groups[name] = mg.id

    for day, plan in TRAINING_PLAN.items():
        tmpl = models.TemplateWorkout(
            day_of_week=day,
            name=plan["name"],
            sort_order=day,
        )
        db.add(tmpl)
        db.flush()

        for idx, (ex_name, mg_name, cat, sets, reps_min, reps_max) in enumerate(plan["exercises"]):
            existing = (
                db.query(models.Exercise)
                .filter(models.Exercise.name == ex_name)
                .first()
            )
            if not existing:
                existing = models.Exercise(
                    name=ex_name,
                    muscle_group_id=muscle_groups.get(mg_name),
                    category=cat,
                )
                db.add(existing)
                db.flush()

            te = models.TemplateExercise(
                template_workout_id=tmpl.id,
                exercise_id=existing.id,
                target_sets=sets,
                target_reps_min=reps_min,
                target_reps_max=reps_max,
                sort_order=idx,
            )
            db.add(te)

    db.commit()
