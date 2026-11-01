
import json
import numpy as np
from pathlib import Path
from sentence_transformers import SentenceTransformer

MODEL_NAME = "BAAI/bge-m3"

model = SentenceTransformer(MODEL_NAME)
hymn_dir = Path("data/hymns")
output_dir = Path("embeddings")
output_dir.mkdir(exist_ok=True)

hymns = []
texts = []

# 성가책별 JSON 파일 읽기
for file in sorted(hymn_dir.glob("*.json")):
    book_name = file.stem

    data = json.loads(
        file.read_text(encoding="utf-8")
    )

    for hymn in data:
        # ID는 성가책 이름과 번호로 구분
        hymn_id = f"{book_name}:{hymn['number']}"

        # 실제 임베딩에 사용할 텍스트
        text = (
            f"제목: {hymn['title']}\n"
            f"분류: {hymn['category']}\n"
            f"가사: {hymn['lyrics']}"
        )

        hymns.append({
            "hymn_id": hymn_id,
            "book": book_name,
            **hymn
        })

        texts.append(text)

if not hymns:
    raise ValueError("성가 JSON 파일이 비어 있습니다.")

# 긴 가사는 모델 한계로 잘릴 수 있음
embeddings = model.encode(
    texts,
    batch_size=16,
    show_progress_bar=True,
    normalize_embeddings=True
)

# 임베딩 벡터 저장
np.save(
    output_dir / "hymn_vectors.npy",
    embeddings
)

# 원본 성가 정보 및 검색 순서 저장
(output_dir / "hymn_metadata.json").write_text(
    json.dumps(
        hymns,
        ensure_ascii=False,
        indent=2
    ),
    encoding="utf-8"
)

# 모델 정보도 함께 저장
(output_dir / "model_info.json").write_text(
    json.dumps({"model": MODEL_NAME}, indent=2),
    encoding="utf-8"
)

print(f"임베딩 완료: 총 {len(hymns)}곡")
print(f"벡터 차원: {embeddings.shape[1]}")
