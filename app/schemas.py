from typing import List, Optional
from pydantic import BaseModel, Field


class FortuneScriptItem(BaseModel):
    video_id: int = Field(description="영상 번호 (1~20, 고유 식별자). 1~5번=사용법 안내, 6~20번=에피소드·스토리형")
    content_type: str = Field(description="콘텐츠 유형 ('사용법 안내' 또는 '에피소드·스토리형')")
    topic: str = Field(
        description="주제 (연애운/재회운/결혼운/재물운/직업운/자녀운/종합운세/궁합/타로/자미두수 중 하나, "
                     "사용법 안내 영상의 경우 '회원가입', '결제/구독', '결과 확인', '재이용/알림 설정' 등 절차명)"
    )

    character_id: str = Field(
        description="등장인물 고유 ID (예: 'char_A_역술가', 'char_B_상담사'). "
                     "20편 전체에서 동일 인물 또는 제한된 인물군을 유지하기 위해 재사용되는 식별자."
    )
    persona: str = Field(
        description="등장인물 페르소나 상세 (성별, 연령대, 말투, 목소리 분위기, 복장/톤 등). "
                     "같은 character_id를 쓰는 영상들은 이 설명이 서로 일관되어야 함."
    )

    series_group: Optional[str] = Field(
        default=None,
        description="연속 구성일 경우 시리즈 묶음명 (예: '연애운_1부작'). 단독 에피소드면 null."
    )
    episode_order: Optional[str] = Field(
        default=None,
        description="연속 구성일 경우 '1/3', '2/3'처럼 회차 표기. 단독 에피소드면 null."
    )

    title: str = Field(description="영상 제목")
    hook: str = Field(description="0~3초 후킹 대사 (시청 이탈 방지용 강한 첫 문장)")
    body_narration: str = Field(
        description="본편 내레이션/대사. 정보성 표현 기준(단정·보장 표현 금지, "
                     "공포·불안 과도 자극 금지, 개인차 전제 포함)을 반드시 준수. "
                     "영상마다 서로 다른 구체적인 내용으로 작성해야 함 (템플릿 반복 금지)"
    )
    closing_line: str = Field(
        description="마무리 멘트. 서비스명을 직접적으로 반복 강조하지 않되, "
                     "'프로필 링크' 또는 '앱에서 확인'으로 자연스럽게 연결되는 유도형 CTA 포함 "
                     "(강요형 문구 금지)"
    )

    screen_guide: str = Field(
        description="화면 연출 가이드: 배경, 등장인물 동작, 화면 전환, 자막 강조 포인트. "
                     "사람 중심 AI 생성 영상 전제 (3D 캐릭터 사용 금지). "
                     "content_type이 '사용법 안내'인 경우, 실제 앱 화면(비식별화/테스트 계정 전제) "
                     "캡처 삽입 지점과 설명용 화면 보완 지점을 구체적으로 명시"
    )
    app_screen_reference: Optional[str] = Field(
        default=None,
        description="사용법 안내 영상 전용. 활용할 실제 앱 화면 단계명 (예: '앱 실행 → 로그인 → 사주 입력 화면'). "
                     "에피소드·스토리형 영상은 null."
    )

    estimated_duration: str = Field(description="예상 길이 (최소 20초 이상, 예: '20~50초')")
    aspect_ratio: str = Field(
        default="9:16",
        description="영상 비율. 유튜브 쇼츠/인스타 릴스 공통 활용을 위한 세로형 (기본 9:16 고정)"
    )
    disclaimer_note: str = Field(
        description="정보성 콘텐츠임을 알리는 문구의 삽입 여부와 위치 "
                     "(예: '영상 하단 자막 고정 노출: 본 콘텐츠는 정보 제공 목적이며 개인차가 있을 수 있습니다')"
    )
    music_license_note: str = Field(
        default="상업적 이용 가능 라이선스 음원 사용 예정 (출처 표기 조건 별도 확인)",
        description="배경음악/효과음의 라이선스 조건 메모 (상업적 이용 허용 음원 사용 전제)"
    )


class FortuneScriptBatchResponse(BaseModel):
    service_name: str
    total_count: int = Field(description="총 영상 편수 (기본 20편: 1~5편 사용법 안내 + 6~20편 에피소드·스토리형)")
    how_to_use_count: int = Field(default=5, description="사용법 안내 영상 편수 (1~5편)")
    episode_count: int = Field(default=15, description="에피소드·스토리형 영상 편수 (6~20편)")
    scripts: List[FortuneScriptItem]