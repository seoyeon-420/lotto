
import json
import sys
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

from ollama import chat
import json

POSITIONS = ["입당"]
MODEL_NAME = "qwen3:4b"

# 1. 검색엔진의 상위 3곡을 그대로 확정
selected = {}
llm_input = []

date = (
    sys.argv[1]
    if len(sys.argv) > 1
    else datetime.now(
        ZoneInfo("Asia/Seoul")
    ).strftime("%Y%m%d")
)

folder = Path("data") / date

def load_json(path):
    return json.loads(
        Path(path).read_text(encoding="utf-8")
    )

# 기존 검색 결과와 원문 불러오기
missa = load_json(folder / "raw.json")
retrieved = load_json(
    folder / "retrieved_hymns.json"
)
hymns = load_json(
    "embeddings/hymn_metadata.json"
)

hymn_lookup = {
    h["hymn_id"]: h for h in hymns
}


for position in POSITIONS:
    result = retrieved.get(position, {})
    songs = result.get("recommendations", [])[:3]

    selected[position] = []

    # 검색에 활용한 매일미사 항목
    source_sections = {
        name: missa.get("sections", {}).get(name, "")
        for name in result.get("used_sections", [])
        if name in missa.get("sections", {})
    }

    for song in songs:
        hymn = hymn_lookup.get(song["hymn_id"])

        if hymn is None:
            continue

        selected[position].append({
            "hymn_id": song["hymn_id"],
            "number": hymn["number"],
            "title": hymn["title"],
            "category": hymn.get("category", ""),
            "retrieval_score": song.get("final_score", 0),
            "reason": ""
        })

    llm_input.append({
        "position": position,
        "celebration": missa.get("celebration", ""),
        "missa_sections": source_sections,
        "hymns": [
            {
                "hymn_id": item["hymn_id"],
                "title": item["title"],
                "lyrics": hymn_lookup[
                    item["hymn_id"]
                ].get("lyrics", "")
            }
            for item in selected[position]
        ]
    })


from pydantic import BaseModel
from ollama import chat

# LLM 출력 형식
class ReasonResponse(BaseModel):
    reasons: list[str]

PROMPT = """
당신은 가톨릭 미사 성가 추천 근거 작성 시스템입니다.

이미 성가 추천과 순위는 확정되어 있습니다.
성가를 다시 선정하거나 순서를 변경하지 마세요.

규칙:
1. 입력된 성가의 순서대로 추천 이유를 작성하세요.
2. 각 성가마다 한국어로 1~2문장만 작성하세요.
3. 매일미사 원문과 성가 가사의 의미를 연결하세요.
4. 실제 원문과 가사에서 확인할 수 있는 내용만 사용하세요.
5. 관련성이 약하면 관련성이 약하다고 설명하세요.
6. 입력 성가 개수와 같은 개수의 이유를 반환하세요.
7. reasons 배열에 문자열만 넣으세요.

반드시 JSON 형식으로 응답하세요.
"""

print("LLM 추천 근거 생성 시작", flush=True)

response = chat(
    model=MODEL_NAME,
    messages=[
        {
            "role": "system",
            "content": PROMPT
        },
        {
            "role": "user",
            "content": json.dumps(
                llm_input,
                ensure_ascii=False
            )
        }
    ],
    format=ReasonResponse.model_json_schema(),
    think=False,
    options={
        "temperature": 0,
        "num_ctx": 8192,
        "num_predict": 1200
    }
)

# 실제 응답 확인
print("\n===== Ollama 응답 =====")
print(response.message.content)
print("======================\n")

parsed = ReasonResponse.model_validate_json(
    response.message.content
)

# LLM에 전달한 성가와 같은 순서로 연결
all_songs = [
    song
    for position in POSITIONS
    for song in selected[position]
]

if len(parsed.reasons) != len(all_songs):
    print(
        f"[경고] 성가 {len(all_songs)}곡에 대해 "
        f"추천 이유 {len(parsed.reasons)}개 생성"
    )

for i, song in enumerate(all_songs):
    if i < len(parsed.reasons):
        song["reason"] = parsed.reasons[i].strip()
    else:
        song["reason"] = "추천 근거 생성 누락"

print("추천 근거 연결 완료", flush=True)

# 4. 결과 저장
output = {
    "date": date,
    "celebration": missa.get("celebration", ""),
    "model": MODEL_NAME,
    "recommendations": selected
}

output_path = folder / "final_recommendations.json"

output_path.write_text(
    json.dumps(output, ensure_ascii=False, indent=2),
    encoding="utf-8"
)

print("추천 근거 생성 완료", flush=True)