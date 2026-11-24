"""Import NCNU Information Management courses for semester 115-1 into local se1151."""

import argparse
import os
from pathlib import Path
from xml.etree import ElementTree

from psycopg import ProgrammingError
from psycopg.conninfo import conninfo_to_dict

from db import connect

COURSE_SCOPE = (115, 1, "資管系")
UPSERT_COURSE = """
    INSERT INTO official_courses (
        academic_year, semester, department, course_code, section, title,
        raw_teachers, raw_time_code, raw_classrooms
    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT (academic_year, semester, department, course_code, section)
    DO UPDATE SET title = EXCLUDED.title,
        raw_teachers = EXCLUDED.raw_teachers,
        raw_time_code = EXCLUDED.raw_time_code,
        raw_classrooms = EXCLUDED.raw_classrooms
"""


def read_courses(xml_path):
    root = ElementTree.parse(xml_path).getroot()
    if root.tag != "course_ncnu":
        raise ValueError(f"XML 根元素應為 course_ncnu，實際為 {root.tag}")

    expected = tuple(map(str, COURSE_SCOPE))
    fields = ("course_id", "class", "course_cname", "teacher", "time", "location")
    return [
        COURSE_SCOPE + tuple(item.findtext(field, "") for field in fields)
        for item in root.findall("item")
        if (item.findtext("year"), item.findtext("semester"), item.findtext("department")) == expected
    ]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("xml_path", nargs="?", type=Path, default=Path("D:/software/.ncnu-1151.xml"))
    args = parser.parse_args()

    try:
        target = conninfo_to_dict(os.environ.get("DATABASE_URL", ""))
    except ProgrammingError:
        parser.exit(1, "DATABASE_URL 格式無效。\n")
    hostaddr = target.get("hostaddr", os.environ.get("PGHOSTADDR", ""))
    if (
        target.get("host") not in {"localhost", "127.0.0.1"}
        or target.get("dbname") != "se1151"
        or hostaddr not in {"", "127.0.0.1", "::1"}
        or target.get("service", os.environ.get("PGSERVICE"))
    ):
        parser.exit(1, "請將 DATABASE_URL 設為本機 localhost 或 127.0.0.1 的 se1151。\n")

    try:
        rows = read_courses(args.xml_path)
    except (OSError, ElementTree.ParseError, ValueError) as error:
        parser.exit(1, f"無法讀取 XML：{error}\n")
    if not rows:
        parser.exit(1, "XML 中沒有 115 學年度第 1 學期的資管系課程。\n")

    with connect() as db, db.cursor() as cursor:
        cursor.executemany(UPSERT_COURSE, rows)
        cursor.execute(
            "SELECT count(*) AS total FROM official_courses "
            "WHERE academic_year = %s AND semester = %s AND department = %s",
            COURSE_SCOPE,
        )
        total = cursor.fetchone()["total"]

    print(f"本次處理 {len(rows)} 筆；資料庫中同學期、同系所共 {total} 筆。")


if __name__ == "__main__":
    main()
