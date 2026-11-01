
import json
import sys
import subprocess
import numpy as np
import os

from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
from sentence_transformers import SentenceTransformer

# =====================================
# 1. 미사 순서별 검색 항목 설정
# =====================================

SEARCH_CONFIG = {
    "입당": {
        "celebration": 0.6,
        "입당송": 0.2,
        "오늘 전례": 0.2
    },
    "봉헌": {
        "본기도": 0.1,
        "제1독서": 0.6,
        "제2독서": 0.3
    },
    "성체": {
        "영성체송": 0.3,
        "복음": 0.7
    },
    "파견": {
        "celebration": 0.5,
        "오늘 전례": 0.3,
        "복음": 0.2
    }
}


# 웹페이지에서 전달받은 사용자 설정
user_config = os.environ.get("HYMN_SEARCH_CONFIG")

if user_config:
    SEARCH_CONFIG = json.loads(user_config)


TOP_K = 5

# =====================================
# 2. 매일미사 가져오기
# =====================================

date = (
    sys.argv[1]
    if len(sys.argv) > 1
    else datetime.now(
        ZoneInfo("Asia/Seoul")
    ).strftime("%Y%m%d")
)

datetime.strptime(date, "%Y%m%d")

# 기존 main.py 실행
subprocess.run(
    [sys.executable, "readmisa.py", date],
    check=True
)

raw_path = Path("data") / date / "raw.json"

missa = json.loads(
    raw_path.read_text(encoding="utf-8")
)

sections = missa["sections"]

# =====================================
# 3. 성가 임베딩 불러오기
# =====================================

embedding_dir = Path("embeddings")

model_info = json.loads(
    (embedding_dir / "model_info.json").read_text(
        encoding="utf-8"
    )
)

model = SentenceTransformer(model_info["model"])

hymn_vectors = np.load(
    embedding_dir / "hymn_vectors.npy"
)

hymns = json.loads(
    (embedding_dir / "hymn_metadata.json").read_text(
        encoding="utf-8"
    )
)

if len(hymn_vectors) != len(hymns):
    raise ValueError("성가 벡터와 메타데이터 개수가 다릅니다.")

# =====================================
# 4. 미사 순서별 성가 검색 함수
# =====================================



def search_hymns(position, config):

    CATEGORY_MAP = {
        "입당": "입당",
        "봉헌": "봉헌",
        "성체": "성체",
        "파견": "파견"
    }

    CATEGORY_BONUS = 0.04 #입당, 봉헌, 성체, 파견이 맞을 때
    SEASON_BONUS = 0.08 #전례시기가 동일할 때
    MARTYR_BONUS = 0.05 #순교자 관련 시즌일때
    BIBLE_PENALTY = 0.03 #카테고리가 성서일때
    MARY_BONUS = 0.03 #성모 관련 시즌일때

    # 입력 날짜에서 월 추출 (YYYYMMDD 형식)
    is_may = date[4:6] == "05"

    SEASONS = [
        "부활", "대림", "사순",
        "위령", "성령", "성심"
    ]

    vectors = []
    weights = []
    used_sections = []

    if not config:
        raise ValueError(
            f"{position}: 참고할 전례문이 선택되지 않았습니다."
        )

    if any(
        not isinstance(w, (int, float)) or not np.isfinite(w) or w < 0
        for w in config.values()
    ):
        raise ValueError(
            f"{position}: 가중치는 0 이상의 유한한 숫자여야 합니다."
        )

    if sum(config.values()) <= 0:
        raise ValueError(
            f"{position}: 가중치 합계가 0보다 커야 합니다."
        )

    # 1. 미사 순서별 참조 항목 임베딩
    for section, weight in config.items():

        if section == "celebration":
            text = missa.get("celebration", "").strip()
        else:
            text = sections.get(section, "").strip()

        if not text or weight <= 0:
            continue

        vector = model.encode(
            text,
            normalize_embeddings=True
        )

        vectors.append(vector)
        weights.append(weight)
        used_sections.append(section)

    if not vectors:
        return {
            "position": position,
            "used_sections": [],
            "recommendations": []
        }

    # 2. 항목별 가중 평균 벡터 생성
    query_vector = np.average(
        np.array(vectors),
        axis=0,
        weights=weights
    )

    norm = np.linalg.norm(query_vector)

    if norm == 0:
        raise ValueError("검색 벡터 생성 실패")

    query_vector = query_vector / norm

    # 3. 전체 성가 임베딩 유사도 계산
    similarity_scores = hymn_vectors @ query_vector

    # 4. 매일미사 전례명 확인
    celebration = missa.get("celebration", "")

    matched_seasons = [
        season for season in SEASONS
        if season in celebration
    ]

    is_martyr = "순교" in celebration

    # 5. 각 성가에 가중치 적용
    target_category = CATEGORY_MAP[position]

    final_scores = similarity_scores.copy()
    bonus_details = []

    for i, hymn in enumerate(hymns):
        category = hymn.get("category", "")

        if isinstance(category, str):
            categories = [category.strip()]
        elif isinstance(category, list):
            categories = [
                str(c).strip() for c in category
            ]
        else:
            categories = []

        # 기본 미사 순서별 카테고리 보너스
        category_bonus = (
            CATEGORY_BONUS
            if target_category in categories
            else 0.0
        )

        # 전례명에 해당하는 카테고리 보너스
        # 입당 및 파견에만 적용
        season_bonus = 0.0

        if position in ("입당", "파견"):
            season_bonus = SEASON_BONUS * sum(
                season in categories
                for season in matched_seasons
            )

        # 순교 관련 카테고리 보너스
        martyr_bonus = 0.0

        if is_martyr in ("입당", "파견"):
            martyr_bonus = MARTYR_BONUS * sum(
                cat in categories
                for cat in ("성인", "위령")
            )

        # 성서 카테고리 감점
        bible_penalty = (
            -BIBLE_PENALTY
            if "성서" in categories
            else 0.0
        )

        # 5월 성모 카테고리 보너스
        # 입당, 파견에만 적용
        mary_bonus = 0.0

        if position in ("입당", "파견"):
            if is_may and "성모" in categories:
                mary_bonus = MARY_BONUS

        # 최종 점수 계산
        total_adjustment = (
            category_bonus
            + season_bonus
            + martyr_bonus
            + bible_penalty
            + mary_bonus
        )

        final_scores[i] += total_adjustment

        bonus_details.append({
            "category_bonus": category_bonus,
            "season_bonus": season_bonus,
            "martyr_bonus": martyr_bonus,
            "bible_penalty": bible_penalty,
            "mary_bonus": mary_bonus
        })

    # 6. 최종 점수 기준 정렬
    top_indices = np.argsort(
        final_scores
    )[::-1][:TOP_K]

    # 7. 검색 결과 생성
    recommendations = []

    for idx in top_indices:
        idx = int(idx)
        hymn = hymns[idx]
        bonuses = bonus_details[idx]

        recommendations.append({
            "hymn_id": hymn["hymn_id"],
            "title": hymn["title"],
            "category": hymn["category"],
            "similarity": round(
                float(similarity_scores[idx]), 4
            ),
            "category_bonus": bonuses["category_bonus"],
            "season_bonus": bonuses["season_bonus"],
            "martyr_bonus": bonuses["martyr_bonus"],
            "bible_penalty": bonuses["bible_penalty"],
            "final_score": round(
                float(final_scores[idx]), 4
            )
        })

    # 8. 결과 반환
    return {
        "position": position,
        "celebration": celebration,
        "matched_seasons": matched_seasons,
        "is_martyr": is_martyr,
        "used_sections": used_sections,
        "recommendations": recommendations
    }

# =====================================
# 5. 모든 미사 순서별 검색
# =====================================

results = {}

for position, config in SEARCH_CONFIG.items():

    result = search_hymns(position, config)

    results[position] = result

    print(f"\n===== {position} 성가 =====")
    print("참조 항목:", ", ".join(result["used_sections"]))

    for rank, hymn in enumerate(
        result["recommendations"], 1
    ):
        print(
            f"{rank}. {hymn['hymn_id']} "
            f"{hymn['title']} "
            f"({hymn['similarity']:.4f})"
        )

# =====================================
# 6. 결과 저장
# =====================================

output_path = (
    raw_path.parent / "retrieved_hymns.json"
)

output_path.write_text(
    json.dumps(
        results,
        ensure_ascii=False,
        indent=2
    ),
    encoding="utf-8"
)

print(f"\n검색 결과 저장: {output_path}")
