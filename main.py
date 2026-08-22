from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, PlainTextResponse, HTMLResponse
from typing import List
import io
import os
import re
import zipfile
import traceback
from datetime import datetime, timezone

from app.schemas import FortuneScriptBatchResponse
from app.services import generate_fortune_scripts_logic

app = FastAPI(
    title="Fortune-Telling Short-form Script Manager",
    description="사주·운세·타로·자미두수 서비스 홍보용 숏폼 대본 20편 생성/업로드/다운로드 API"
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

# ---------------------------------------------------------------------------
# AI 생성 결과 캐시 + 진행 상태 (POST/GET /generate-fortune-scripts 용)
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


@app.get("/")
def read_root():
    return {"status": "ok", "message": "사주운세 숏폼 대본 생성/업로드/다운로드 API 작동 중"}


# ---------------------------------------------------------------------------
# [AI 생성 시작] 백그라운드로 20편 생성 (GET으로 바로 실행 가능, 즉시 응답)
# ---------------------------------------------------------------------------
@app.get("/generate-fortune-scripts")
def generate_fortune_scripts(background_tasks: BackgroundTasks, service_name: str = "사주운세 서비스"):
    """
    AI로 20편(1~5편: 사용법 안내 / 6~20편: 에피소드·스토리형) 대본 생성을 백그라운드로 시작합니다.
    브라우저 주소창에 그냥 쳐도 실행됩니다. 완료 여부는 /generation-status 로 확인하세요.
    """
    status = _get_status(service_name)
    if status["state"] == "running":
        return {
            "status": "already_running",
            "message": "이미 생성이 진행 중입니다. /generation-status 로 확인해주세요.",
            "started_at": status["started_at"],
        }
    background_tasks.add_task(_run_generation, service_name)
    return {
        "status": "started",
        "message": "대본 생성을 백그라운드에서 시작했습니다. /generation-status 로 완료 여부를 확인해주세요.",
        "service_name": service_name,
    }


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


# ---------------------------------------------------------------------------
# [생성된 대본을 저장 폴더로 내보내기] AI 생성 결과를 개별 txt 파일로 저장
# 이후 업로드 없이도 아래 다운로드 엔드포인트들이 이 파일들을 바로 사용할 수 있음
# ---------------------------------------------------------------------------
@app.get("/save-generated-scripts-to-storage")
def save_generated_scripts_to_storage(service_name: str = "사주운세 서비스"):
    """
    캐시에 생성된 대본이 있으면, 각 편을 개별 txt 파일로 STORAGE_DIR에 저장합니다.
    파일명 형식: 01_사용법_안내_회원가입_및_서비스_소개.txt 등
    저장 후에는 /fortune-scripts, /download-fortune-vrew-zip 등에서 그대로 사용할 수 있습니다.
    """
    status = _get_status(service_name)
    if service_name not in _CACHE:
        if status["state"] == "running":
            raise HTTPException(status_code=202, detail="아직 생성 중입니다. /generation-status 로 확인 후 다시 시도해주세요.")
        raise HTTPException(status_code=404, detail="생성된 대본이 없습니다. 먼저 /generate-fortune-scripts 를 호출해주세요.")

    batch_data = _CACHE[service_name]
    saved = []
    for s in batch_data.scripts:
        text = f"{s.hook}\n{s.body_narration}\n{s.closing_line}\n"
        safe_topic = _safe_filename(s.topic)
        filename = f"{s.video_id:02d}_{_safe_filename(s.content_type)}_{safe_topic}.txt"
        path = os.path.join(STORAGE_DIR, filename)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        saved.append(filename)

    return {"status": "ok", "saved_count": len(saved), "saved_files": saved}


@app.get("/upload-page", response_class=HTMLResponse)
def upload_page():
    """브라우저에서 바로 파일을 선택/드래그해서 업로드할 수 있는 간단한 페이지"""
    return """
<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<title>대본 업로드</title>
<style>
  body { font-family: sans-serif; max-width: 600px; margin: 60px auto; padding: 0 20px; }
  #drop { border: 2px dashed #999; border-radius: 12px; padding: 40px; text-align: center; color: #666; cursor: pointer; }
  #drop.drag { background: #f0f8ff; border-color: #3b82f6; }
  #fileList { margin-top: 16px; font-size: 14px; }
  #fileList li { margin: 4px 0; }
  button { margin-top: 16px; padding: 10px 20px; font-size: 15px; cursor: pointer; }
  #result { margin-top: 20px; white-space: pre-wrap; background: #f5f5f5; padding: 12px; border-radius: 8px; font-size: 13px; }
</style>
</head>
<body>
  <h2>운세 대본 txt 파일 업로드</h2>
  <p>여러 개(예: 20개)의 .txt 파일을 한 번에 선택하거나 드래그해서 올려주세요.</p>

  <div id="drop">여기에 파일을 끌어다 놓거나 클릭해서 선택하세요</div>
  <input type="file" id="fileInput" accept=".txt" multiple style="display:none">

  <ul id="fileList"></ul>
  <button id="uploadBtn" disabled>업로드</button>
  <div id="result"></div>

<script>
const drop = document.getElementById('drop');
const fileInput = document.getElementById('fileInput');
const fileList = document.getElementById('fileList');
const uploadBtn = document.getElementById('uploadBtn');
const result = document.getElementById('result');
let selectedFiles = [];

drop.addEventListener('click', () => fileInput.click());
drop.addEventListener('dragover', e => { e.preventDefault(); drop.classList.add('drag'); });
drop.addEventListener('dragleave', () => drop.classList.remove('drag'));
drop.addEventListener('drop', e => {
  e.preventDefault();
  drop.classList.remove('drag');
  handleFiles(e.dataTransfer.files);
});
fileInput.addEventListener('change', () => handleFiles(fileInput.files));

function handleFiles(files) {
  selectedFiles = Array.from(files);
  fileList.innerHTML = selectedFiles.map(f => `<li>${f.name}</li>`).join('');
  uploadBtn.disabled = selectedFiles.length === 0;
}

uploadBtn.addEventListener('click', async () => {
  if (selectedFiles.length === 0) return;
  const formData = new FormData();
  selectedFiles.forEach(f => formData.append('files', f));

  uploadBtn.disabled = true;
  uploadBtn.textContent = '업로드 중...';
  result.textContent = '';

  try {
    const res = await fetch('/upload-fortune-scripts', { method: 'POST', body: formData });
    const data = await res.json();
    result.textContent = JSON.stringify(data, null, 2);
  } catch (err) {
    result.textContent = '업로드 실패: ' + err;
  } finally {
    uploadBtn.disabled = false;
    uploadBtn.textContent = '업로드';
  }
});
</script>
</body>
</html>
"""


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
# [업로드] 20개 개별 txt 파일 업로드 (직접 만든 대본을 올릴 때)
# ---------------------------------------------------------------------------
@app.post("/upload-fortune-scripts")
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
        raise HTTPException(status_code=404, detail="저장된 대본 파일이 없습니다. 먼저 업로드하거나 AI로 생성해주세요.")

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
        raise HTTPException(status_code=404, detail="저장된 대본 파일이 없습니다. 먼저 업로드하거나 AI로 생성해주세요.")

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
        raise HTTPException(status_code=404, detail="저장된 대본 파일이 없습니다. 먼저 업로드하거나 AI로 생성해주세요.")

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