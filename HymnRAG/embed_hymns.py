import json
import numpy as np
from pathlib import Path

from fastembed import TextEmbedding
from fastembed.common.model_description import PoolingType, ModelSource


# 사용할 경량 임베딩 모델
MODEL_NAME = "intfloat/multilingual-e5-small"

# FastEmbed 사용자 정의 모델 등록
TextEmbedding.add_custom_model(
    model=MODEL_NAME,
    pooling=PoolingType.MEAN,
    normalization=True,
    sources=ModelSource(hf=MODEL_NAME),
    dim=384,
    model_file="onnx/model.onnx",
)

# 모델 불러오기
model = TextEmbedding(
    model_name=MODEL_NAME,
    threads=1
)

# 경로 설정
ROOT = Path(__file__).resolve().parent
hymn_dir = ROOT / "data" / "hymns"
output_dir = ROOT / "embeddings"
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

        # 임베딩에 사용할 텍스트
        text = (
            f"제목: {hymn['title']}\n"
            f"분류: {hymn['category']}\n"
            f"가사: {hymn['lyrics']}"
        )

        # E5 모델의 문서용 접두어
        text = "passage: " + text

        hymns.append({
            "hymn_id": hymn_id,
            "book": book_name,
            **hymn
        })

        texts.append(text)

if not hymns:
    raise ValueError("성가 JSON 파일이 비어 있습니다.")

# FastEmbed로 모든 성가 임베딩 생성
# generator 결과를 NumPy 배열로 변환
embeddings = np.stack(
    list(model.embed(texts, batch_size=8))
).astype(np.float32)

# 코사인 유사도 계산을 위한 벡터 정규화
norms = np.linalg.norm(
    embeddings,
    axis=1,
    keepdims=True
)

embeddings = embeddings / np.maximum(norms, 1e-12)

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

# 모델 정보 저장
(output_dir / "model_info.json").write_text(
    json.dumps(
        {
            "model": MODEL_NAME,
            "dimension": int(embeddings.shape[1]),
            "document_prefix": "passage: ",
            "query_prefix": "query: "
        },
        ensure_ascii=False,
        indent=2
    ),
    encoding="utf-8"
)

print(f"임베딩 완료: 총 {len(hymns)}곡")
print(f"사용 모델: {MODEL_NAME}")
print(f"벡터 차원: {embeddings.shape[1]}")
print(f"벡터 배열 크기: {embeddings.nbytes / 1024 / 1024:.2f} MB")
print("임베딩 파일 저장 완료")
