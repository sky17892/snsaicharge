from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, PlainTextResponse
import io
import zipfile

from app.schemas import FortuneScriptBatchResponse
from app.services import generate_fortune_scripts_logic

app = FastAPI(
    title="Fortune-Telling Short-form Script Generator",
    description="사주·운세·타로·자미두수 서비스 홍보용 숏폼 대본 20편 자동 생성 API"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# 생성 결과 캐시
# 매 요청마다 AI를 다시 호출하지 않도록, 한 번 생성한 결과를 메모리에 저장해두고
# 이후 다운로드/조회 요청은 이 캐시를 재사용합니다.
# 서버가 재시작되면 캐시는 초기화되며, /generate-fortune-scripts로 다시 생성해야 합니다.
# ---------------------------------------------------------------------------
_CACHE: dict[str, FortuneScriptBatchResponse] = {}


def get_or_generate(service_name: str, force_regenerate: bool = False) -> FortuneScriptBatchResponse:
    if force_regenerate or service_name not in _CACHE:
        _CACHE[service_name] = generate_fortune_scripts_logic(service_name)
    return _CACHE[service_name]


@app.get("/")
def read_root():
    return {"status": "ok", "message": "사주운세 서비스 숏폼 대본 생성 API 작동 중"}


# ---------------------------------------------------------------------------
# [명시적 생성] AI 대본을 새로 생성해서 캐시에 저장
# ---------------------------------------------------------------------------
@app.post("/generate-fortune-scripts")
def generate_fortune_scripts(service_name: str = "사주운세 서비스"):
    """
    AI로 20편(사용법 안내 5편 + 에피소드·스토리형 15편) 대본을 새로 생성하고 캐시에 저장합니다.
    이미 생성된 적이 있어도 이 엔드포인트를 호출하면 강제로 다시 생성합니다.
    이후 다운로드/조회 엔드포인트들은 여기서 생성된 결과를 재사용합니다.
    """
    try:
        batch_data = get_or_generate(service_name, force_regenerate=True)
        return {
            "status": "ok",
            "service_name": batch_data.service_name,
            "total_count": batch_data.total_count,
            "how_to_use_count": batch_data.how_to_use_count,
            "episode_count": batch_data.episode_count,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def build_single_script_text(script) -> str:
    """영상 1편을 Vrew에 바로 붙여넣기 좋은 형태로 변환 (대사만)"""
    text = f"{script.hook}\n"
    text += f"{script.body_narration}\n"
    text += f"{script.closing_line}\n"
    return text


def build_single_script_review_text(script) -> str:
    """영상 1편을 검수용으로 변환 (모든 메타정보 포함)"""
    series_info = ""
    if script.series_group:
        series_info = f"시리즈: {script.series_group} ({script.episode_order})\n"

    app_ref_info = ""
    if script.app_screen_reference:
        app_ref_info = f"📱 [앱 화면 흐름]: {script.app_screen_reference}\n"

    text = f"[영상 {script.video_id:02d}편 : {script.content_type} / {script.topic}]\n"
    text += f"제목: {script.title}\n"
    text += f"등장인물 ID: {script.character_id}\n"
    text += f"페르소나: {script.persona}\n"
    text += series_info
    text += f"예상 길이: {script.estimated_duration} | 비율: {script.aspect_ratio}\n\n"
    text += f"[대사]\n{script.hook}\n{script.body_narration}\n{script.closing_line}\n\n"
    text += f"📌 [화면 가이드]: {script.screen_guide}\n"
    text += app_ref_info
    text += f"⚠️ [정보성 문구]: {script.disclaimer_note}\n"
    text += f"🎵 [음원 라이선스]: {script.music_license_note}\n"
    return text


def build_full_text(service_name: str, scripts) -> str:
    how_to_use = [s for s in scripts if s.content_type == "사용법 안내"]
    episodes = [s for s in scripts if s.content_type == "에피소드·스토리형"]

    text = f"=== [{service_name}] 숏폼 {len(scripts)}편 대본 (검수용) ===\n"
    text += f"구성: 사용법 안내 {len(how_to_use)}편 + 에피소드·스토리형 {len(episodes)}편\n\n"

    for s in scripts:
        text += build_single_script_review_text(s)
        text += "=" * 50 + "\n\n"
    return text


# ---------------------------------------------------------------------------
# 전체 텍스트 화면 출력 (검수용, 모든 메타정보 포함)
# ---------------------------------------------------------------------------
@app.get("/export-fortune-vrew-text", response_class=PlainTextResponse)
def export_fortune_vrew_text(service_name: str = "사주운세 서비스"):
    try:
        batch_data = get_or_generate(service_name)
        return build_full_text(service_name, batch_data.scripts)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# 전체 20편 통짜 텍스트 파일 다운로드 (검수용, 모든 메타정보 포함)
# ---------------------------------------------------------------------------
@app.get("/download-fortune-vrew-file")
def download_fortune_vrew_file(service_name: str = "사주운세 서비스"):
    try:
        batch_data = get_or_generate(service_name)
        text = build_full_text(service_name, batch_data.scripts)

        headers = {
            'Content-Disposition': 'attachment; filename="fortune_scripts_review.txt"'
        }
        return Response(content=text, media_type="text/plain; charset=utf-8", headers=headers)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# 영상 1편씩 개별 다운로드 (Vrew 붙여넣기용: 대사만)
# ---------------------------------------------------------------------------
@app.get("/download-fortune-vrew-file/{video_id}")
def download_single_script(
    video_id: int,
    service_name: str = "사주운세 서비스"
):
    """
    특정 영상 1편(video_id)의 대본만 txt로 다운로드합니다.
    Vrew에 바로 붙여넣기 좋은 형태(hook + narration + closing만)로 제공됩니다.
    """
    try:
        batch_data = get_or_generate(service_name)

        target_script = next((s for s in batch_data.scripts if s.video_id == video_id), None)
        if not target_script:
            raise HTTPException(status_code=404, detail=f"video_id {video_id}를 찾을 수 없습니다.")

        text = build_single_script_text(target_script)
        filename = f"fortune_script_{video_id:02d}.txt"

        headers = {
            'Content-Disposition': f'attachment; filename="{filename}"'
        }
        return Response(content=text, media_type="text/plain; charset=utf-8", headers=headers)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# 특정 영상 1편 검수용 상세 정보 다운로드 (모든 메타정보 포함)
# ---------------------------------------------------------------------------
@app.get("/download-fortune-review-file/{video_id}")
def download_single_script_review(
    video_id: int,
    service_name: str = "사주운세 서비스"
):
    """
    특정 영상 1편(video_id)의 검수용 상세 정보를 txt로 다운로드합니다.
    페르소나, 화면 가이드, 앱 화면 흐름, 정보성 문구, 음원 라이선스 등 모든 메타정보를 포함합니다.
    """
    try:
        batch_data = get_or_generate(service_name)

        target_script = next((s for s in batch_data.scripts if s.video_id == video_id), None)
        if not target_script:
            raise HTTPException(status_code=404, detail=f"video_id {video_id}를 찾을 수 없습니다.")

        text = build_single_script_review_text(target_script)
        filename = f"fortune_script_{video_id:02d}_review.txt"

        headers = {
            'Content-Disposition': f'attachment; filename="{filename}"'
        }
        return Response(content=text, media_type="text/plain; charset=utf-8", headers=headers)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# 20편 전체를 zip으로 한번에 다운로드 (Vrew 붙여넣기용: 대사만)
# ---------------------------------------------------------------------------
@app.get("/download-fortune-vrew-zip")
def download_fortune_vrew_zip(service_name: str = "사주운세 서비스"):
    """
    전체 대본을 각각 별도의 txt 파일로 만들어 zip으로 압축해 다운로드합니다.
    파일마다 Vrew에 바로 붙여넣기 좋은 형태(대사만)로 저장됩니다.
    """
    try:
        batch_data = get_or_generate(service_name)

        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
            for s in batch_data.scripts:
                filename = f"fortune_script_{s.video_id:02d}_{s.content_type}_{s.topic}.txt"
                content = build_single_script_text(s)
                zip_file.writestr(filename, content)

        zip_buffer.seek(0)

        headers = {
            'Content-Disposition': 'attachment; filename="fortune_scripts_all.zip"'
        }
        return Response(content=zip_buffer.read(), media_type="application/zip", headers=headers)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# 20편 전체 검수용 zip 다운로드 (모든 메타정보 포함, 편별 개별 파일)
# ---------------------------------------------------------------------------
@app.get("/download-fortune-review-zip")
def download_fortune_review_zip(service_name: str = "사주운세 서비스"):
    """
    전체 대본을 편별 검수용 txt 파일로 만들어 zip으로 압축해 다운로드합니다.
    페르소나, 화면 가이드, 앱 화면 흐름, 정보성 문구, 음원 라이선스 등 모든 메타정보를 포함합니다.
    """
    try:
        batch_data = get_or_generate(service_name)

        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
            for s in batch_data.scripts:
                filename = f"fortune_script_{s.video_id:02d}_{s.content_type}_{s.topic}_review.txt"
                content = build_single_script_review_text(s)
                zip_file.writestr(filename, content)

        zip_buffer.seek(0)

        headers = {
            'Content-Disposition': 'attachment; filename="fortune_scripts_review_all.zip"'
        }
        return Response(content=zip_buffer.read(), media_type="application/zip", headers=headers)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))