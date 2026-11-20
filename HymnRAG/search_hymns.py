
import json
import sys
import subprocess
import numpy as np
import os

from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

from fastembed import TextEmbedding
from fastembed.common.model_description import PoolingType, ModelSource


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

ROOT = Path(__file__).resolve().parent

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

subprocess.run(
    [sys.executable, str(ROOT / "readmisa.py"), date],
    cwd=str(ROOT),
    check=True
)

raw_path = ROOT / "data" / date / "raw.json"

missa = json.loads(
    raw_path.read_text(encoding="utf-8")
)

sections = missa["sections"]


# =====================================
# 3. 경량 임베딩 모델 불러오기
# =====================================

embedding_dir = ROOT / "embeddings"

model_info = json.loads(
    (embedding_dir / "model_info.json").read_text(
        encoding="utf-8"
    )
)

MODEL_NAME = "Xenova/multilingual-e5-small"

if model_info.get("model") != MODEL_NAME:
    raise ValueError(
        "성가 임베딩 모델과 검색 모델이 일치하지 않습니다. "
        "embed_hymns.py를 다시 실행해 주세요."
    )

# FastEmbed 사용자 정의 모델 등록
TextEmbedding.add_custom_model(
    model=MODEL_NAME,
    pooling=PoolingType.MEAN,
    normalization=True,
    sources=ModelSource(hf=MODEL_NAME),
    dim=384,
    model_file="onnx/model_quantized.onnx",
)


# ONNX 기반 경량 모델 실행
model = TextEmbedding(
    model_name=MODEL_NAME,
    threads=1
)

# 사전에 생성한 성가 임베딩 불러오기
hymn_vectors = np.load(
    embedding_dir / "hymn_vectors.npy"
).astype(np.float32)

hymns = json.loads(
    (embedding_dir / "hymn_metadata.json").read_text(
        encoding="utf-8"
    )
)

if len(hymn_vectors) != len(hymns):
    raise ValueError(
        "성가 벡터와 메타데이터 개수가 다릅니다."
    )

if hymn_vectors.ndim != 2 or hymn_vectors.shape[1] != 384:
    raise ValueError(
        "성가 벡터 차원이 E5-small 모델과 일치하지 않습니다."
    )

# 코사인 유사도 계산을 위한 정규화
hymn_norms = np.linalg.norm(
    hymn_vectors,
    axis=1,
    keepdims=True
)

hymn_vectors = hymn_vectors / np.maximum(
    hymn_norms, 1e-12
)


# =====================================
# 4. 전례문 임베딩 함수
# =====================================

def encode_query(text):
    """
    E5 모델을 이용하여 전례문을 벡터로 변환한다.
    검색 문장에는 query: 접두어를 사용한다.
    """

    vectors = list(
        model.embed(
            ["query: " + text],
            batch_size=1
        )
    )

    vector = np.asarray(
        vectors[0],
        dtype=np.float32
    )

    norm = np.linalg.norm(vector)

    if norm == 0:
        raise ValueError(
            "전례문 임베딩 벡터 생성에 실패했습니다."
        )

    return vector / norm


# =====================================
# 5. 미사 순서별 성가 검색 함수
# =====================================

def search_hymns(position, config):

    CATEGORY_MAP = {
        "입당": "입당",
        "봉헌": "봉헌",
        "성체": "성체",
        "파견": "파견"
    }

    CATEGORY_BONUS = 0.04
    SEASON_BONUS = 0.08
    MARTYR_BONUS = 0.05
    BIBLE_PENALTY = 0.03
    MARY_BONUS = 0.03

    # 입력 날짜에서 월 추출
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
        not isinstance(w, (int, float))
        or not np.isfinite(w)
        or w < 0
        for w in config.values()
    ):
        raise ValueError(
            f"{position}: 가중치는 0 이상의 유한한 숫자여야 합니다."
        )

    if sum(config.values()) <= 0:
        raise ValueError(
            f"{position}: 가중치 합계가 0보다 커야 합니다."
        )

    # 1. 전례문별 임베딩
    for section, weight in config.items():

        if section == "celebration":
            text = missa.get("celebration", "").strip()
        else:
            text = sections.get(section, "").strip()

        if not text or weight <= 0:
            continue

        # E5 모델로 전례문 임베딩
        vector = encode_query(text)

        vectors.append(vector)
        weights.append(weight)
        used_sections.append(section)

    if not vectors:
        return {
            "position": position,
            "used_sections": [],
            "recommendations": []
        }

    # 2. 사용자 가중치를 반영한 평균 벡터
    query_vector = np.average(
        np.array(vectors, dtype=np.float32),
        axis=0,
        weights=weights
    ).astype(np.float32)

    norm = np.linalg.norm(query_vector)

    if norm == 0:
        raise ValueError("검색 벡터 생성 실패")

    query_vector = query_vector / norm

    # 3. 전체 성가와 코사인 유사도 계산
    similarity_scores = hymn_vectors @ query_vector

    # 4. 전례 시기 확인
    celebration = missa.get("celebration", "")

    matched_seasons = [
        season for season in SEASONS
        if season in celebration
    ]

    is_martyr = "순교" in celebration

    # 5. 성가별 가중치 적용
    target_category = CATEGORY_MAP[position]

    final_scores = similarity_scores.copy()
    bonus_details = []

    for i, hymn in enumerate(hymns):

        category = hymn.get("category", "")

        if isinstance(category, str):
            categories = [category.strip()]

        elif isinstance(category, list):
            categories = [
                str(c).strip()
                for c in category
            ]

        else:
            categories = []

        # 미사 순서별 카테고리 가점
        category_bonus = (
            CATEGORY_BONUS
            if target_category in categories
            else 0.0
        )

        # 전례 시기 가점
        season_bonus = 0.0

        if position in ("입당", "파견"):
            season_bonus = SEASON_BONUS * sum(
                season in categories
                for season in matched_seasons
            )

        # 순교자 관련 가점
        martyr_bonus = 0.0

        if is_martyr and position in ("입당", "파견"):
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

        # 5월 성모 카테고리 가점
        mary_bonus = 0.0

        if position in ("입당", "파견"):
            if is_may and "성모" in categories:
                mary_bonus = MARY_BONUS

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

    # 6. 최종 점수 정렬
    top_indices = np.argsort(
        final_scores
    )[::-1][:TOP_K]

    # 7. 추천 결과 생성
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

            "category_bonus":
                bonuses["category_bonus"],

            "season_bonus":
                bonuses["season_bonus"],

            "martyr_bonus":
                bonuses["martyr_bonus"],

            "bible_penalty":
                bonuses["bible_penalty"],

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
# 6. 모든 미사 순서별 검색
# =====================================

results = {}

for position, config in SEARCH_CONFIG.items():

    result = search_hymns(
        position,
        config
    )

    results[position] = result

    print(f"\n===== {position} 성가 =====")
    print(
        "참조 항목:",
        ", ".join(result["used_sections"])
    )

    for rank, hymn in enumerate(
        result["recommendations"], 1
    ):
        print(
            f"{rank}. {hymn['hymn_id']} "
            f"{hymn['title']} "
            f"({hymn['similarity']:.4f})"
        )


# =====================================
# 7. 결과 저장
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
