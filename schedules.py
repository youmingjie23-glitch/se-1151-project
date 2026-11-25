from datetime import date, time
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path
from fastapi.exceptions import RequestValidationError
from psycopg.errors import ForeignKeyViolation
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, ValidationError, model_validator

from auth import Account, CurrentUser
from db import connect

router = APIRouter()
RecordId = Annotated[int, Field(gt=0, le=2**63 - 1)]
Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class ScheduleCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: Title
    class_date: date
    start_time: time
    end_time: time
    preferred_room_id: RecordId | None = None
    official_course_id: RecordId | None = None

    @model_validator(mode="after")
    def validate_time_range(self):
        if self.start_time.tzinfo is not None or self.end_time.tzinfo is not None:
            raise ValueError("請使用臺灣當地時間，時間欄位不含時區偏移")
        if self.end_time <= self.start_time:
            raise ValueError("結束時間必須晚於開始時間")
        return self


class Schedule(ScheduleCreate):
    id: int
    teacher_id: int


class SchedulePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: Title | None = None
    class_date: date | None = None
    start_time: time | None = None
    end_time: time | None = None
    preferred_room_id: RecordId | None = None
    official_course_id: RecordId | None = None


def schedule_reference_error(error: ForeignKeyViolation) -> HTTPException:
    if error.diag.constraint_name == "course_schedules_official_course_id_fkey":
        return HTTPException(404, "找不到官方課程")
    if error.diag.constraint_name == "course_schedules_preferred_room_id_fkey":
        return HTTPException(404, "找不到教室")
    raise error


def require_teacher(account: CurrentUser) -> Account:
    if account.role != "teacher":
        raise HTTPException(403, "需要教師權限")
    return account


@router.get("/schedules/mine", response_model=list[Schedule])
def list_my_schedules(teacher: Annotated[Account, Depends(require_teacher)]):
    with connect() as db:
        return db.execute(
            """
            SELECT id, title, teacher_id, class_date, start_time, end_time,
                   preferred_room_id, official_course_id
            FROM course_schedules
            WHERE teacher_id = %s
            ORDER BY class_date, start_time, id
            """,
            (teacher.id,),
        ).fetchall()


@router.post("/schedules", response_model=Schedule, status_code=201)
def create_schedule(schedule: ScheduleCreate, teacher: Annotated[Account, Depends(require_teacher)]):
    try:
        with connect() as db:
            return db.execute(
                """
                INSERT INTO course_schedules (
                    title, teacher_id, class_date, start_time, end_time,
                    preferred_room_id, official_course_id
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING id, title, teacher_id, class_date, start_time, end_time,
                          preferred_room_id, official_course_id
                """,
                (
                    schedule.title,
                    teacher.id,
                    schedule.class_date,
                    schedule.start_time,
                    schedule.end_time,
                    schedule.preferred_room_id,
                    schedule.official_course_id,
                ),
            ).fetchone()
    except ForeignKeyViolation as error:
        raise schedule_reference_error(error) from error


@router.patch("/schedules/{schedule_id}", response_model=Schedule)
def update_schedule(
    schedule_id: Annotated[int, Path(gt=0, le=2**63 - 1)],
    changes: SchedulePatch,
    teacher: Annotated[Account, Depends(require_teacher)],
):
    try:
        with connect() as db:
            row = db.execute(
                """
                SELECT title, class_date, start_time, end_time,
                       preferred_room_id, official_course_id
                FROM course_schedules
                WHERE id = %s AND teacher_id = %s
                FOR UPDATE
                """,
                (schedule_id, teacher.id),
            ).fetchone()
            if row is None:
                raise HTTPException(404, "找不到排課")

            try:
                updated = ScheduleCreate.model_validate(row | changes.model_dump(exclude_unset=True))
            except ValidationError as error:
                raise RequestValidationError([
                    {**item, "loc": ("body", *item["loc"])} for item in error.errors()
                ]) from error

            return db.execute(
                """
                UPDATE course_schedules
                SET title = %(title)s, class_date = %(class_date)s,
                    start_time = %(start_time)s, end_time = %(end_time)s,
                    preferred_room_id = %(preferred_room_id)s,
                    official_course_id = %(official_course_id)s
                WHERE id = %(id)s AND teacher_id = %(teacher_id)s
                RETURNING id, title, teacher_id, class_date, start_time, end_time,
                          preferred_room_id, official_course_id
                """,
                {**updated.model_dump(), "id": schedule_id, "teacher_id": teacher.id},
            ).fetchone()
    except ForeignKeyViolation as error:
        raise schedule_reference_error(error) from error


@router.delete("/schedules/{schedule_id}", status_code=204)
def delete_schedule(
    schedule_id: Annotated[int, Path(gt=0, le=2**63 - 1)],
    teacher: Annotated[Account, Depends(require_teacher)],
):
    with connect() as db:
        deleted = db.execute(
            "DELETE FROM course_schedules WHERE id = %s AND teacher_id = %s RETURNING id",
            (schedule_id, teacher.id),
        ).fetchone()
        if deleted is None:
            raise HTTPException(404, "找不到排課")
