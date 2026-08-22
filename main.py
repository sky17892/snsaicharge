from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, PlainTextResponse
from typing import List
import io
import os
import re
import zipfile

app = FastAPI(
    title="Fortune-Telling Short-form Script Manager",
    description="사주·운세·타로·자미두수 서비스 홍보용 숏폼 대본 20편 업로드/다운로드 API"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# 저장 폴더 (배포 전 테스트용 - 로컬 디스크에 파일로만 저장)
# ---------------------------------------------------------------------------
STORAGE_DIR = "storage/fortune_scripts"
os.makedirs(STORAGE_DIR, exist_ok=True)


@app.get("/")
def read_root():
    return {"status": "ok", "message": "사주운세 숏폼 대본 업로드/다운로드 API 작동 중"}


def _safe_filename(filename: str) -> str:
    """경로 조작(../ 등) 방지용 파일명 정제"""
    base = os.path.basename(filename)
    base = re.sub(r'[\\/:*?"<>|]', "_", base)
    return base


def _extract_video_id(filename: str) -> int:
    """파일명에서 앞쪽 숫자를 video_id로 추출 (예: 01_사랑운.txt -> 1)"""
    match = re.match(r"^0*(\d+)", filename)
    if match:
        return int(match.group(1))
    return -1


# ---------------------------------------------------------------------------
# [업로드] 20개 개별 txt 파일 업로드
# ---------------------------------------------------------------------------
@app.get("/upload-fortune-scripts")
async def upload_fortune_scripts(files: List[UploadFile] = File(...)):
    """
    개별 txt 파일 여러 개(예: 20개)를 업로드하면 서버 로컬 폴더에 저장합니다.
    파일명 앞부분 숫자를 video_id로 인식합니다. (예: 01_연애운.txt, 02_금전운.txt ...)
    같은 이름의 파일이 이미 있으면 덮어씁니다.
    """
    if not files:
        raise HTTPException(status_code=400, detail="업로드할 파일이 없습니다.")

    saved = []
    skipped = []

    for f in files:
        if not f.filename or not f.filename.lower().endswith(".txt"):
            skipped.append(f.filename or "(이름 없음)")
            continue

        safe_name = _safe_filename(f.filename)
        content = await f.read()

        save_path = os.path.join(STORAGE_DIR, safe_name)
        with open(save_path, "wb") as out:
            out.write(content)

        saved.append({
            "filename": safe_name,
            "video_id": _extract_video_id(safe_name),
            "size_bytes": len(content),
        })

    return {
        "status": "ok",
        "saved_count": len(saved),
        "saved_files": sorted(saved, key=lambda x: x["video_id"]),
        "skipped_files": skipped,
    }


# ---------------------------------------------------------------------------
# [목록 조회] 현재 저장된 파일 목록 확인
# ---------------------------------------------------------------------------
@app.get("/fortune-scripts")
def list_fortune_scripts():
    files = sorted(os.listdir(STORAGE_DIR))
    result = [
        {"filename": name, "video_id": _extract_video_id(name)}
        for name in files if name.lower().endswith(".txt")
    ]
    result.sort(key=lambda x: x["video_id"])
    return {"count": len(result), "files": result}


# ---------------------------------------------------------------------------
# 전체 텍스트 화면 출력 (저장된 파일들을 순서대로 합쳐서 보여줌)
# ---------------------------------------------------------------------------
@app.get("/export-fortune-vrew-text", response_class=PlainTextResponse)
def export_fortune_vrew_text():
    files = sorted(
        [f for f in os.listdir(STORAGE_DIR) if f.lower().endswith(".txt")],
        key=_extract_video_id,
    )
    if not files:
        raise HTTPException(status_code=404, detail="저장된 대본 파일이 없습니다. 먼저 업로드해주세요.")

    full_text = "=== 사주운세 숏폼 대본 모음 (Vrew용) ===\n\n"
    for name in files:
        path = os.path.join(STORAGE_DIR, name)
        with open(path, "r", encoding="utf-8") as fp:
            content = fp.read()
        full_text += f"--- [{name}] ---\n{content}\n\n" + ("=" * 50) + "\n\n"

    return full_text


# ---------------------------------------------------------------------------
# 전체 통짜 텍스트 파일 다운로드
# ---------------------------------------------------------------------------
@app.get("/download-fortune-vrew-file")
def download_fortune_vrew_file():
    files = sorted(
        [f for f in os.listdir(STORAGE_DIR) if f.lower().endswith(".txt")],
        key=_extract_video_id,
    )
    if not files:
        raise HTTPException(status_code=404, detail="저장된 대본 파일이 없습니다. 먼저 업로드해주세요.")

    full_text = ""
    for name in files:
        path = os.path.join(STORAGE_DIR, name)
        with open(path, "r", encoding="utf-8") as fp:
            full_text += fp.read() + "\n\n"

    headers = {
        'Content-Disposition': 'attachment; filename="fortune_scripts.txt"'
    }
    return Response(content=full_text, media_type="text/plain; charset=utf-8", headers=headers)


# ---------------------------------------------------------------------------
# 영상 1편씩 개별 다운로드
# ---------------------------------------------------------------------------
@app.get("/download-fortune-vrew-file/{video_id}")
def download_single_script(video_id: int):
    files = [f for f in os.listdir(STORAGE_DIR) if f.lower().endswith(".txt")]
    target = next((f for f in files if _extract_video_id(f) == video_id), None)

    if not target:
        raise HTTPException(status_code=404, detail=f"video_id {video_id}에 해당하는 파일을 찾을 수 없습니다.")

    path = os.path.join(STORAGE_DIR, target)
    with open(path, "rb") as fp:
        content = fp.read()

    headers = {
        'Content-Disposition': f'attachment; filename="{target}"'
    }
    return Response(content=content, media_type="text/plain; charset=utf-8", headers=headers)


# ---------------------------------------------------------------------------
# 20편 전체를 zip으로 한번에 다운로드
# ---------------------------------------------------------------------------
@app.get("/download-fortune-vrew-zip")
def download_fortune_vrew_zip():
    files = sorted(
        [f for f in os.listdir(STORAGE_DIR) if f.lower().endswith(".txt")],
        key=_extract_video_id,
    )
    if not files:
        raise HTTPException(status_code=404, detail="저장된 대본 파일이 없습니다. 먼저 업로드해주세요.")

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for name in files:
            path = os.path.join(STORAGE_DIR, name)
            with open(path, "rb") as fp:
                zip_file.writestr(name, fp.read())

    zip_buffer.seek(0)
    headers = {
        'Content-Disposition': 'attachment; filename="fortune_scripts_all.zip"'
    }
    return Response(content=zip_buffer.read(), media_type="application/zip", headers=headers)


# ---------------------------------------------------------------------------
# [삭제] 저장된 대본 전체 초기화 (테스트 중 다시 업로드하고 싶을 때)
# ---------------------------------------------------------------------------
@app.delete("/fortune-scripts")
def clear_fortune_scripts():
    files = [f for f in os.listdir(STORAGE_DIR) if f.lower().endswith(".txt")]
    for name in files:
        os.remove(os.path.join(STORAGE_DIR, name))
    return {"status": "ok", "deleted_count": len(files)}