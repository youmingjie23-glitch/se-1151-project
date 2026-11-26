"""Import NCNU Information Management courses for semester 115-1."""

import argparse
import os
from pathlib import Path
import re
from xml.etree import ElementTree

from psycopg import Error, ProgrammingError
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
    parser.add_argument("--allow-neon", action="store_true", help="允許明確指定的 Neon 匯入目標")
    parser.add_argument("--neon-host", help="預期的 Neon 主機名稱")
    parser.add_argument("--neon-dbname", help="預期的 Neon 資料庫名稱")
    args = parser.parse_args()

    try:
        target = conninfo_to_dict(os.environ.get("DATABASE_URL", ""))
    except ProgrammingError:
        parser.exit(1, "DATABASE_URL 格式無效。\n")
    hostaddr = target.get("hostaddr", os.environ.get("PGHOSTADDR", ""))
    service = target.get("service", os.environ.get("PGSERVICE"))
    if args.allow_neon:
        if not args.neon_host or not args.neon_dbname:
            parser.error("--allow-neon 必須同時指定 --neon-host 和 --neon-dbname。")
        expected_host = args.neon_host.lower()
        if (
            not re.fullmatch(r"[a-z0-9-]+(?:\.[a-z0-9-]+)*\.neon\.tech", expected_host)
            or target.get("host", "").lower() != expected_host
            or target.get("dbname") != args.neon_dbname
            or hostaddr
            or service
        ):
            parser.exit(1, "DATABASE_URL 與指定的 Neon 目標不符，未連線。\n")
    elif args.neon_host is not None or args.neon_dbname is not None:
        parser.error("指定 Neon 目標時必須加上 --allow-neon。")
    elif (
        target.get("host") not in {"localhost", "127.0.0.1"}
        or target.get("dbname") != "se1151"
        or hostaddr not in {"", "127.0.0.1", "::1"}
        or service
    ):
        parser.exit(1, "請將 DATABASE_URL 設為本機 localhost 或 127.0.0.1 的 se1151。\n")

    try:
        rows = read_courses(args.xml_path)
    except (OSError, ElementTree.ParseError, ValueError) as error:
        parser.exit(1, f"無法讀取 XML：{error}\n")
    if not rows:
        parser.exit(1, "XML 中沒有 115 學年度第 1 學期的資管系課程。\n")

    try:
        with connect() as db, db.cursor() as cursor:
            cursor.executemany(UPSERT_COURSE, rows)
            cursor.execute(
                "SELECT count(*) AS total FROM official_courses "
                "WHERE academic_year = %s AND semester = %s AND department = %s",
                COURSE_SCOPE,
            )
            total = cursor.fetchone()["total"]
    except Error as error:
        parser.exit(1, f"資料庫匯入未完成（{type(error).__name__}）。\n")

    print(f"本次處理 {len(rows)} 筆；資料庫中同學期、同系所共 {total} 筆。")


if __name__ == "__main__":
    main()
