from typing import List, Optional
from pydantic import BaseModel, Field

class FortuneScriptItem(BaseModel):
    video_id: int = Field(description="영상 번호 (1~20)")
    content_type: str = Field(description="콘텐츠 유형 (사용법 안내 / 에피소드·스토리형)")
    topic: str = Field(description="주제 (연애운/재회운/결혼운/재물운/직업운/자녀운/종합운세/궁합/타로/자미두수)")
    persona: str = Field(description="등장인물 페르소나 (성별/연령대/말투/분위기)")
    title: str = Field(description="영상 제목")
    hook: str = Field(description="0~3초 후킹 대사")
    body_narration: str = Field(description="본편 내레이션/대사 (정보성 표현 기준 준수)")
    closing_line: str = Field(description="마무리 멘트 (직접적 서비스 강조 지양)")
    screen_guide: str = Field(description="화면 연출 가이드 (배경, 등장인물 동작, 자막 포인트)")
    estimated_duration: str = Field(description="예상 길이 (예: 10~20초)")
    disclaimer_note: str = Field(description="정보성 콘텐츠임을 알리는 문구 삽입 여부/위치")

class FortuneScriptBatchResponse(BaseModel):
    service_name: str
    total_count: int
    scripts: List[FortuneScriptItem]