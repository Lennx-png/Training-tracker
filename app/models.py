from sqlalchemy import Column, Integer, Float, String, Boolean, DateTime, ForeignKey, Date, Text
from sqlalchemy.orm import relationship
from datetime import datetime, date
from app.database import Base


class WeightEntry(Base):
    __tablename__ = "weight_entries"
    id = Column(Integer, primary_key=True, index=True)
    weight = Column(Float, nullable=False)
    date = Column(Date, nullable=False, default=date.today)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class MuscleGroup(Base):
    __tablename__ = "muscle_groups"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)
    exercises = relationship("Exercise", back_populates="muscle_group")


class Exercise(Base):
    __tablename__ = "exercises"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    muscle_group_id = Column(Integer, ForeignKey("muscle_groups.id"))
    category = Column(String, nullable=True)
    description = Column(Text, nullable=True)
    muscle_group = relationship("MuscleGroup", back_populates="exercises")
    template_exercises = relationship("TemplateExercise", back_populates="exercise")
    workout_exercises = relationship("WorkoutExercise", back_populates="exercise")


class Workout(Base):
    __tablename__ = "workouts"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    date = Column(Date, nullable=False, default=date.today)
    notes = Column(Text, nullable=True)
    is_completed = Column(Boolean, default=False)
    duration_minutes = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    exercises = relationship(
        "WorkoutExercise",
        back_populates="workout",
        cascade="all, delete-orphan",
        order_by="WorkoutExercise.sort_order",
    )


class WorkoutExercise(Base):
    __tablename__ = "workout_exercises"
    id = Column(Integer, primary_key=True, index=True)
    workout_id = Column(Integer, ForeignKey("workouts.id"))
    exercise_id = Column(Integer, ForeignKey("exercises.id"))
    sort_order = Column(Integer, default=0)
    notes = Column(Text, nullable=True)
    workout = relationship("Workout", back_populates="exercises")
    exercise = relationship("Exercise", back_populates="workout_exercises")
    sets = relationship(
        "Set",
        back_populates="workout_exercise",
        cascade="all, delete-orphan",
        order_by="Set.set_number",
    )


class Set(Base):
    __tablename__ = "sets"
    id = Column(Integer, primary_key=True, index=True)
    workout_exercise_id = Column(Integer, ForeignKey("workout_exercises.id"))
    set_number = Column(Integer, nullable=False)
    weight = Column(Float, nullable=True)
    reps = Column(Integer, nullable=True)
    rpe = Column(Integer, nullable=True)
    is_failure = Column(Boolean, default=False)
    is_warmup = Column(Boolean, default=False)
    is_completed = Column(Boolean, default=False)
    notes = Column(Text, nullable=True)
    workout_exercise = relationship("WorkoutExercise", back_populates="sets")


class TemplateWorkout(Base):
    __tablename__ = "template_workouts"
    id = Column(Integer, primary_key=True, index=True)
    day_of_week = Column(Integer, nullable=False)
    name = Column(String, nullable=False)
    sort_order = Column(Integer, default=0)
    exercises = relationship(
        "TemplateExercise",
        back_populates="template_workout",
        cascade="all, delete-orphan",
        order_by="TemplateExercise.sort_order",
    )


class TemplateExercise(Base):
    __tablename__ = "template_exercises"
    id = Column(Integer, primary_key=True, index=True)
    template_workout_id = Column(Integer, ForeignKey("template_workouts.id"))
    exercise_id = Column(Integer, ForeignKey("exercises.id"))
    target_sets = Column(Integer, default=3)
    target_reps_min = Column(Integer, default=8)
    target_reps_max = Column(Integer, default=12)
    sort_order = Column(Integer, default=0)
    notes = Column(Text, nullable=True)
    template_workout = relationship("TemplateWorkout", back_populates="exercises")
    exercise = relationship("Exercise", back_populates="template_exercises")
