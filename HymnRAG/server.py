"""Flask adapter for the existing readmisa.py / search_hymns.py pipeline."""
import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from flask import Flask, jsonify, render_template, request

ROOT = Path(__file__).resolve().parent
app = Flask(__name__, template_folder='frontend/templates', static_folder='frontend/static')
DATE_FORMAT = re.compile(r'^\d{8}$')
POSITIONS = ('입당', '봉헌', '성체', '파견')
ALLOWED_SECTIONS = {'celebration','입당송','본기도','제1독서','제2독서','화답송','복음 환호송','복음','영성체송'}
HYMNS_DIR = ROOT / "data" / "hymns"


def load_hymn_book(book_id):
    # 허용된 성가책 JSON 파일만 조회
    books = {
        path.stem: path
        for path in HYMNS_DIR.glob("*.json")
    }

    path = books.get(book_id)

    if path is None:
        return None

    with path.open("r", encoding="utf-8") as f:
        return json.load(f)

def validate_search_config(value):
    if not isinstance(value, dict) or set(value) != set(POSITIONS):
        raise ValueError('미사 순서 네 가지의 설정이 모두 필요합니다.')
    normalized = {}
    for position in POSITIONS:
        rows = value[position]
        if not isinstance(rows, dict) or not 1 <= len(rows) <= 4:
            raise ValueError(f'{position}: 전례문을 1~4개 선택하세요.')
        if any(section not in ALLOWED_SECTIONS for section in rows):
            raise ValueError(f'{position}: 사용할 수 없는 전례문이 포함되어 있습니다.')
        if any(type(w) not in (int, float) or not 0 <= w <= 1 for w in rows.values()):
            raise ValueError(f'{position}: 비율은 0~100% 사이여야 합니다.')
        if abs(sum(rows.values())-1.0)>0.00001:
            raise ValueError(f'{position}: 반영 비율 합계는 100%여야 합니다.')
        normalized[position]=rows
    return normalized



def book_names():
    folder = ROOT / 'data' / 'hymns'
    return sorted(p.stem for p in folder.glob('*.json')) if folder.exists() else []


def load_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


@app.get('/')
def index():
    return render_template('index.html')


@app.get('/api/books')
def books():
    return jsonify({'books': book_names()})


@app.post('/api/recommend')
def recommend():
    payload = request.get_json(silent=True) or {}
    date = str(payload.get('date', '')).strip()
    book = str(payload.get('book') or '').strip()

    if not DATE_FORMAT.fullmatch(date):
        return jsonify({'error': '날짜는 YYYYMMDD 형식의 숫자 8자리로 입력해 주세요.'}), 400
    try:
        datetime.strptime(date, '%Y%m%d')
    except ValueError:
        return jsonify({'error': '존재하지 않는 날짜입니다. 날짜를 확인해 주세요.'}), 400
    try:
        search_config = validate_search_config(payload.get('search_config'))
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    names = book_names()
    if book not in names:
        return jsonify({'error': '성가책을 선택해 주세요'}), 400

    script = ROOT / 'search_hymns.py'
    if not script.is_file():
        return jsonify({'error': '프로젝트 최상위 폴더에 search_hymns.py가 없습니다.'}), 500

    # No shell=True: validated date is passed as a positional argument.
    try:
        env = os.environ.copy()
        env['HYMN_SEARCH_CONFIG'] = json.dumps(search_config, ensure_ascii=False)
        proc = subprocess.run(
            [sys.executable, str(script), date],
            cwd=str(ROOT), capture_output=True, text=True,
            encoding='utf-8', errors='replace', timeout=240, env=env,
        )
    except subprocess.TimeoutExpired:
        return jsonify({'error': '검색 시간이 초과되었습니다. 터미널에서 search_hymns.py를 먼저 확인해 주세요.'}), 504

    if proc.returncode != 0:
        # Deliberately avoid exposing arbitrary server traceback to browsers.
        print('Search subprocess failed:', proc.stdout[-3000:], proc.stderr[-3000:], flush=True)
        return jsonify({'error': '검색 코드 실행에 실패했습니다. 서버 터미널의 오류 로그를 확인해 주세요.'}), 500

    result_path = ROOT / 'data' / date / 'retrieved_hymns.json'
    raw_path = ROOT / 'data' / date / 'raw.json'
    if not result_path.exists():
        return jsonify({'error': '검색은 실행됐지만 retrieved_hymns.json 파일을 찾지 못했습니다.'}), 500

    try:
        results = load_json(result_path)
        missa = load_json(raw_path) if raw_path.exists() else {}
    except (OSError, json.JSONDecodeError):
        return jsonify({'error': '저장된 JSON 파일을 읽지 못했습니다.'}), 500

    output = {}
    for position in POSITIONS:
        group = results.get(position, {})
        songs = group.get('recommendations', [])
            # This filters the retrieved shortlist, not the entire database.
        songs = [s for s in songs if str(s.get('hymn_id', '')).startswith(book + ':')]
        output[position] = {
            'used_sections': group.get('used_sections', []),
            'songs': songs,
        }

    # The optional prompt is included in the response as a note ONLY; it has
    # no effect on ranking in this starter. Do not claim otherwise in the UI.
    return jsonify({
        'date': date,
        'celebration': missa.get('celebration', ''),
        'search_config': search_config,
        'book': book,
        'results': output,
        'book_filter_note': '선택한 성가책의 성가만 표시됩니다.'
                            '현재는 전체 검색 결과 중 상위 후보를'
                            '성가책별로 필터링하는 방식입니다.'
    })

@app.get("/api/books/<book_id>/categories")
def get_categories(book_id):
    hymns = load_hymn_book(book_id)

    if hymns is None:
        return jsonify({
            "error": "성가책을 찾을 수 없습니다."
        }), 404

    categories = sorted({
        hymn["category"].strip()
        for hymn in hymns
        if isinstance(hymn.get("category"), str)
        and hymn["category"].strip()
    })

    return jsonify({
        "book": book_id,
        "categories": categories
    })
@app.get("/api/books/<book_id>/hymns")
def get_hymns_by_category(book_id):
    hymns = load_hymn_book(book_id)

    if hymns is None:
        return jsonify({
            "error": "성가책을 찾을 수 없습니다."
        }), 404

    category = request.args.get("category", "").strip()

    if not category:
        return jsonify({
            "error": "카테고리를 선택해주세요."
        }), 400

    result = [
        {
            "number": hymn.get("number"),
            "title": hymn.get("title", "")
        }
        for hymn in hymns
        if str(hymn.get("category", "")).strip() == category
    ]

    return jsonify({
        "book": book_id,
        "category": category,
        "count": len(result),
        "hymns": result
    })


if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5000, debug=False)
