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

@app.get("/")
def read_root():
    return {"status": "ok", "message": "사주운세 서비스 숏폼 대본 생성 API 작동 중"}


def build_single_script_text(script) -> str:
    """영상 1편을 Vrew에 바로 붙여넣기 좋은 형태로 변환"""
    text = f"{script.hook}\n"
    text += f"{script.body_narration}\n"
    text += f"{script.closing_line}\n"
    return text


def build_full_text(service_name: str, scripts) -> str:
    text = f"=== [{service_name}] 숏폼 {len(scripts)}편 Vrew 대본 ===\n\n"
    for s in scripts:
        text += f"--- [영상 {s.video_id}편 : {s.content_type} / {s.topic}] ---\n"
        text += f"제목: {s.title}\n"
        text += f"페르소나: {s.persona}\n"
        text += f"예상 길이: {s.estimated_duration}\n\n"
        text += f"{s.hook}\n{s.body_narration}\n{s.closing_line}\n\n"
        text += f"📌 [화면 가이드]: {s.screen_guide}\n"
        text += f"⚠️ [정보성 문구]: {s.disclaimer_note}\n"
        text += "=" * 50 + "\n\n"
    return text


# ---------------------------------------------------------------------------
# 전체 텍스트 화면 출력
# ---------------------------------------------------------------------------
@app.get("/export-fortune-vrew-text", response_class=PlainTextResponse)
def export_fortune_vrew_text(service_name: str = "사주운세 서비스"):
    try:
        batch_data = generate_fortune_scripts_logic(service_name)
        return build_full_text(service_name, batch_data.scripts)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# 전체 20편 통짜 텍스트 파일 다운로드
# ---------------------------------------------------------------------------
@app.get("/download-fortune-vrew-file")
def download_fortune_vrew_file(service_name: str = "사주운세 서비스"):
    try:
        batch_data = generate_fortune_scripts_logic(service_name)
        text = build_full_text(service_name, batch_data.scripts)

        headers = {
            'Content-Disposition': 'attachment; filename="fortune_scripts.txt"'
        }
        return Response(content=text, media_type="text/plain; charset=utf-8", headers=headers)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# [신규 1] 영상 1편씩 개별 다운로드 ⭐️
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
        batch_data = generate_fortune_scripts_logic(service_name)

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
# [신규 2] 20편 전체를 zip으로 한번에 다운로드 ⭐️⭐️
# ---------------------------------------------------------------------------
@app.get("/download-fortune-vrew-zip")
def download_fortune_vrew_zip(service_name: str = "사주운세 서비스"):
    """
    전체 대본을 각각 별도의 txt 파일로 만들어 zip으로 압축해 다운로드합니다.
    파일마다 Vrew에 바로 붙여넣기 좋은 형태로 저장됩니다.
    """
    try:
        batch_data = generate_fortune_scripts_logic(service_name)

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