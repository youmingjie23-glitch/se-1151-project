from datetime import date, time
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from psycopg.errors import ForeignKeyViolation
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from auth import Account, CurrentUser
from db import connect

router = APIRouter()
RecordId = Annotated[int, Field(gt=0, le=2**63 - 1)]


class ScheduleCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
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


def require_teacher(account: CurrentUser) -> Account:
    if account.role != "teacher":
        raise HTTPException(403, "需要教師權限")
    return account


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
        if error.diag.constraint_name == "course_schedules_official_course_id_fkey":
            raise HTTPException(404, "找不到官方課程") from error
        if error.diag.constraint_name == "course_schedules_preferred_room_id_fkey":
            raise HTTPException(404, "找不到教室") from error
        raise
