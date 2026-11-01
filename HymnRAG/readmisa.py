
import requests
import json
import re
import sys
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
from bs4 import BeautifulSoup

# 웹페이지에서 인식할 모든 항목
HEADINGS = [
    "오늘 전례", "입당송",
    "본기도", "제1독서",
    "제2독서", "화답송",
    "복음 환호송", "복음",
    "예물 기도", "영성체송",
    "영성체 후 묵상", "영성체 후 기도",
    "오늘의 묵상"
]

# 최종 JSON에서 제외할 항목
EXCLUDED_HEADINGS = {
    "예물 기도", "영성체 후 묵상",
    "영성체 후 기도", "오늘의 묵상"
}

# 날짜를 입력하지 않으면 한국 기준 오늘 날짜
date = (
    sys.argv[1]
    if len(sys.argv) > 1
    else datetime.now(
        ZoneInfo("Asia/Seoul")
    ).strftime("%Y%m%d")
)

datetime.strptime(date, "%Y%m%d")

url = f"https://missa.cbck.or.kr/DailyMissa/{date}"

response = requests.get(
    url,
    headers={"User-Agent": "Mozilla/5.0"},
    timeout=20
)
response.raise_for_status()

soup = BeautifulSoup(response.content, "html.parser")

for tag in soup(["script", "style", "nav", "footer"]):
    tag.decompose()

lines = [
    " ".join(line.split())
    for line in soup.get_text("\n").splitlines()
    if line.strip()
]

# 본문 날짜 부분부터 추출
date_text = (
    f"{date[:4]}년 {date[4:6]}월 {date[6:]}일"
)

start = next(
    (i for i, line in enumerate(lines)
     if date_text in line),
    None
)

if start is None:
    raise ValueError("매일미사 날짜를 찾지 못했습니다.")

lines = lines[start:]

# 페이지 하단 메뉴 제거
end = next(
    (i for i, line in enumerate(lines)
     if "페이스북 공유하기" in line
     or "매일미사 ©" in line),
    len(lines)
)
lines = lines[:end]



# 전례명과 전례색 추출
celebration = ""
color = ""

for tag in soup.find_all(["h2", "h3", "h4"]):
    title = tag.get_text(" ", strip=True)

    if not re.match(r"^\s*\[[^\]]+\]", title):
        continue

    # 첫 번째 전례색
    color_match = re.match(r"^\s*\[([^\]]+)\]", title)
    color = color_match.group(1).strip()

    # 모든 전례명을 보존 (또는 이후 포함)
    # 전례색 [녹], [백], [자], [홍] 등 제거
    celebration = re.sub(r"\[[^\]]+\]", "", title)

    # 불필요한 공백 정리
    celebration = re.sub(r"\s+", " ", celebration).strip()
    break

if not celebration:
    raise ValueError("전례명을 찾지 못했습니다.")

# 항목별 추출
sections = {}
current = None

for line in lines:
    matched = None

    for heading in HEADINGS:
        if line == heading or line.startswith(heading + " "):
            # 긴 일반 문장을 제목으로 오인하지 않도록 제한
            if len(line) <= 90:
                matched = heading
                break

    if matched:
        current = matched
        sections.setdefault(current, [])
        remainder = line[len(matched):].strip()

        if remainder:
            sections[current].append(remainder)

    elif current:
        sections[current].append(line)

sections = {
    name: "\n".join(content).split("<또는>")[0].strip()
    for name, content in sections.items()
    if name not in EXCLUDED_HEADINGS
}

# 필수 항목 검증
required = ["제1독서", "복음", "영성체송"]
missing = [
    name for name in required
    if not sections.get(name)
]

if missing:
    raise ValueError(
        f"추출 실패 또는 항목 누락: {missing}"
    )

raw_data = {
    "date": date,
    "source_url": url,
    "celebration": celebration,
    "liturgical_color": color,
    "sections": sections
}

folder = Path("data") / date
folder.mkdir(parents=True, exist_ok=True)

path = folder / "raw.json"
path.write_text(
    json.dumps(
        raw_data, ensure_ascii=False, indent=2
    ),
    encoding="utf-8"
)

print(f"원문 저장 완료: {path}")
