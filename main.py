from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, PlainTextResponse
import io
import zipfile
import traceback
from datetime import datetime, timezone

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
# 생성 결과 캐시 + 진행 상태
# Cloudflare Tunnel(trycloudflare.com)은 기본 100초 타임아웃이 있어서,
# AI 생성처럼 오래 걸리는 작업을 요청-응답 안에서 바로 끝내면 524 에러가 납니다.
# 그래서 생성은 백그라운드로 돌리고, 상태는 별도로 폴링하는 구조로 분리했습니다.
# 서버가 재시작되면 캐시와 상태는 초기화됩니다.
# ---------------------------------------------------------------------------
_CACHE: dict[str, FortuneScriptBatchResponse] = {}
_STATUS: dict[str, dict] = {}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _get_status(service_name: str) -> dict:
    if service_name not in _STATUS:
        _STATUS[service_name] = {
            "state": "idle",
            "started_at": None,
            "finished_at": None,
            "error": None,
        }
    return _STATUS[service_name]


def _run_generation(service_name: str):
    """백그라운드에서 실제로 AI 대본 생성을 수행하는 함수 (1~5편: 사용법 안내 / 6~20편: 에피소드·스토리형)"""
    status = _get_status(service_name)
    status["state"] = "running"
    status["started_at"] = _now_iso()
    status["finished_at"] = None
    status["error"] = None

    try:
        batch_data = generate_fortune_scripts_logic(service_name)
        _CACHE[service_name] = batch_data
        status["state"] = "done"
        status["finished_at"] = _now_iso()
    except Exception as e:
        status["state"] = "error"
        status["finished_at"] = _now_iso()
        status["error"] = f"{e}\n{traceback.format_exc()}"


def get_cached_or_raise(service_name: str) -> FortuneScriptBatchResponse:
    """
    캐시에 저장된 생성 결과를 반환합니다.
    캐시가 없으면 즉시 AI를 호출하지 않고, 먼저 생성을 시작하라는 안내와 함께 에러를 던집니다.
    (다운로드 요청 안에서 AI를 새로 호출하면 다시 524가 날 수 있기 때문입니다.)
    """
    if service_name in _CACHE:
        return _CACHE[service_name]

    status = _get_status(service_name)
    if status["state"] == "running":
        raise HTTPException(
            status_code=202,
            detail="대본을 아직 생성 중입니다. GET /generation-status 로 완료 여부를 확인한 뒤 다시 시도해주세요."
        )

    raise HTTPException(
        status_code=404,
        detail="아직 생성된 대본이 없습니다. 먼저 POST /generate-fortune-scripts 를 호출해 생성을 시작해주세요."
    )


@app.get("/")
def read_root():
    return {"status": "ok", "message": "사주운세 서비스 숏폼 대본 생성 API 작동 중"}


# ---------------------------------------------------------------------------
# [생성 시작] 백그라운드로 AI 대본 생성을 시작 (즉시 응답, 타임아웃 없음)
# 1~5편 = 사용법 안내, 6~20편 = 에피소드·스토리형
# ---------------------------------------------------------------------------
@app.post("/generate-fortune-scripts")
def generate_fortune_scripts(background_tasks: BackgroundTasks, service_name: str = "사주운세 서비스"):
    """
    AI로 20편(1~5편: 사용법 안내 / 6~20편: 에피소드·스토리형) 대본 생성을 백그라운드로 시작합니다.
    이 요청은 생성이 끝날 때까지 기다리지 않고 즉시 응답하므로 Cloudflare 타임아웃(524)이 발생하지 않습니다.
    생성 완료 여부는 GET /generation-status 로 확인하세요.
    이미 생성 중이면 중복 실행하지 않고 현재 상태를 안내합니다.
    """
    status = _get_status(service_name)

    if status["state"] == "running":
        return {
            "status": "already_running",
            "message": "이미 생성이 진행 중입니다. GET /generation-status 로 확인해주세요.",
            "started_at": status["started_at"],
        }

    background_tasks.add_task(_run_generation, service_name)

    return {
        "status": "started",
        "message": "대본 생성을 백그라운드에서 시작했습니다. GET /generation-status 로 완료 여부를 확인해주세요.",
        "service_name": service_name,
    }


# ---------------------------------------------------------------------------
# [상태 확인] 생성이 끝났는지 폴링으로 확인
# ---------------------------------------------------------------------------
@app.get("/generation-status")
def generation_status(service_name: str = "사주운세 서비스"):
    status = _get_status(service_name)
    result = {
        "service_name": service_name,
        "state": status["state"],
        "started_at": status["started_at"],
        "finished_at": status["finished_at"],
    }

    if status["state"] == "error":
        result["error"] = status["error"]

    if status["state"] == "done" and service_name in _CACHE:
        batch_data = _CACHE[service_name]
        result["total_count"] = batch_data.total_count
        result["how_to_use_count"] = batch_data.how_to_use_count
        result["episode_count"] = batch_data.episode_count

    return result


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
    text += f"구성: 사용법 안내 {len(how_to_use)}편(1~5편) + 에피소드·스토리형 {len(episodes)}편(6~20편)\n\n"

    for s in scripts:
        text += build_single_script_review_text(s)
        text += "=" * 50 + "\n\n"
    return text


# ---------------------------------------------------------------------------
# 전체 텍스트 화면 출력 (검수용, 모든 메타정보 포함) - 캐시된 결과만 사용
# ---------------------------------------------------------------------------
@app.get("/export-fortune-vrew-text", response_class=PlainTextResponse)
def export_fortune_vrew_text(service_name: str = "사주운세 서비스"):
    batch_data = get_cached_or_raise(service_name)
    return build_full_text(service_name, batch_data.scripts)


# ---------------------------------------------------------------------------
# 전체 20편 통짜 텍스트 파일 다운로드 (검수용, 모든 메타정보 포함)
# ---------------------------------------------------------------------------
@app.get("/download-fortune-vrew-file")
def download_fortune_vrew_file(service_name: str = "사주운세 서비스"):
    batch_data = get_cached_or_raise(service_name)
    text = build_full_text(service_name, batch_data.scripts)

    headers = {
        'Content-Disposition': 'attachment; filename="fortune_scripts_review.txt"'
    }
    return Response(content=text, media_type="text/plain; charset=utf-8", headers=headers)


# ---------------------------------------------------------------------------
# 영상 1편씩 개별 다운로드 (Vrew 붙여넣기용: 대사만)
# ---------------------------------------------------------------------------
@app.get("/download-fortune-vrew-file/{video_id}")
def download_single_script(video_id: int, service_name: str = "사주운세 서비스"):
    batch_data = get_cached_or_raise(service_name)

    target_script = next((s for s in batch_data.scripts if s.video_id == video_id), None)
    if not target_script:
        raise HTTPException(status_code=404, detail=f"video_id {video_id}를 찾을 수 없습니다.")

    text = build_single_script_text(target_script)
    filename = f"fortune_script_{video_id:02d}.txt"

    headers = {
        'Content-Disposition': f'attachment; filename="{filename}"'
    }
    return Response(content=text, media_type="text/plain; charset=utf-8", headers=headers)


# ---------------------------------------------------------------------------
# 특정 영상 1편 검수용 상세 정보 다운로드 (모든 메타정보 포함)
# ---------------------------------------------------------------------------
@app.get("/download-fortune-review-file/{video_id}")
def download_single_script_review(video_id: int, service_name: str = "사주운세 서비스"):
    batch_data = get_cached_or_raise(service_name)

    target_script = next((s for s in batch_data.scripts if s.video_id == video_id), None)
    if not target_script:
        raise HTTPException(status_code=404, detail=f"video_id {video_id}를 찾을 수 없습니다.")

    text = build_single_script_review_text(target_script)
    filename = f"fortune_script_{video_id:02d}_review.txt"

    headers = {
        'Content-Disposition': f'attachment; filename="{filename}"'
    }
    return Response(content=text, media_type="text/plain; charset=utf-8", headers=headers)


# ---------------------------------------------------------------------------
# 20편 전체를 zip으로 한번에 다운로드 (Vrew 붙여넣기용: 대사만)
# ---------------------------------------------------------------------------
@app.get("/download-fortune-vrew-zip")
def download_fortune_vrew_zip(service_name: str = "사주운세 서비스"):
    batch_data = get_cached_or_raise(service_name)

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


# ---------------------------------------------------------------------------
# 20편 전체 검수용 zip 다운로드 (모든 메타정보 포함, 편별 개별 파일)
# ---------------------------------------------------------------------------
@app.get("/download-fortune-review-zip")
def download_fortune_review_zip(service_name: str = "사주운세 서비스"):
    batch_data = get_cached_or_raise(service_name)

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