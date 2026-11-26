"""Preview NCNU Information Management courses for semester 115-1."""

import argparse
import csv
import sys
from pathlib import Path
from xml.etree import ElementTree


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("xml_path", nargs="?", type=Path, default=Path("D:/software/.ncnu-1151.xml"))
    args = parser.parse_args()

    try:
        root = ElementTree.parse(args.xml_path).getroot()
    except (OSError, ElementTree.ParseError) as error:
        parser.exit(1, f"無法讀取 XML：{error}\n")
    if root.tag != "course_ncnu":
        parser.exit(1, f"XML 根元素應為 course_ncnu，實際為 {root.tag}\n")

    writer = csv.writer(sys.stdout, delimiter="\t", lineterminator="\n")
    writer.writerow(("課號", "班別", "課名", "老師", "原始時間代碼", "原始教室", "缺少欄位"))
    total = missing_time = missing_location = 0
    for item in root.findall("item"):
        if (item.findtext("year"), item.findtext("semester"), item.findtext("department")) != (
            "115", "1", "資管系"
        ):
            continue

        total += 1
        time = item.findtext("time", "")
        location = item.findtext("location", "")
        missing = []
        if not time.strip():
            missing_time += 1
            missing.append("時間")
        if not location.strip():
            missing_location += 1
            missing.append("教室")
        writer.writerow((
            item.findtext("course_id", ""),
            item.findtext("class", ""),
            item.findtext("course_cname", ""),
            item.findtext("teacher", ""),
            time,
            location,
            "、".join(missing) or "無",
        ))

    print(f"總筆數：{total}；缺時間：{missing_time}；缺教室：{missing_location}")


if __name__ == "__main__":
    main()
