import os
import json
import time
from dotenv import load_dotenv
from openai import OpenAI
from app.schemas import FortuneScriptItem, FortuneScriptBatchResponse

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))

GROQ_API_KEY = os.getenv("GROQ_API_KEY")

client = OpenAI(
    base_url="https://api.groq.com/openai/v1",
    api_key=GROQ_API_KEY
)

# ---------------------------------------------------------------------------
# 콘텐츠 기획: 사용법 안내 5편 + 에피소드·스토리형 15편 (총 20편)
# 각 항목: (content_type, topic, start_id, count, character_id, app_steps)
# character_id를 그룹별로 재사용하여 20편 전체에서 제한된 인물군 일관성을 유지
# ---------------------------------------------------------------------------
CONTENT_PLAN = [
    # --- 사용법 안내 5편 (video_id 1~5) : 실제 앱 화면 + 비식별화 전제 ---
    ("사용법 안내", "회원가입 및 서비스 소개", 1, 1, "char_A_상담사", "앱 실행 → 회원가입 → 서비스 메인 화면"),
    ("사용법 안내", "사주/생년월일 정보 입력", 2, 1, "char_A_상담사", "정보 입력 화면 → 생년월일시 입력 → 확인"),
    ("사용법 안내", "결과 확인 및 리포트 열람", 3, 1, "char_A_상담사", "결과 리포트 화면 → 항목별 풀이 확인"),
    ("사용법 안내", "결제/구독 절차 안내", 4, 1, "char_A_상담사", "결제 화면 → 상품 선택 → 결제 완료"),
    ("사용법 안내", "재이용 및 알림 설정", 5, 1, "char_A_상담사", "마이페이지 → 알림 설정 → 재이용 안내"),

    # --- 에피소드·스토리형 15편 (video_id 6~20) : 주제별 3편 묶음, 연속 구성 가능 ---
    ("에피소드·스토리형", "연애운, 재회운, 결혼운", 6, 3, "char_B_역술가", None),
    ("에피소드·스토리형", "재물운, 직업운", 9, 3, "char_B_역술가", None),
    ("에피소드·스토리형", "자녀운, 종합운세", 12, 3, "char_C_타로마스터", None),
    ("에피소드·스토리형", "궁합, 타로", 15, 3, "char_C_타로마스터", None),
    ("에피소드·스토리형", "자미두수", 18, 3, "char_B_역술가", None),
]

FORTUNE_JSON_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "fortune_scripts",
        "schema": {
            "type": "object",
            "properties": {
                "scripts": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "video_id": {"type": "integer"},
                            "content_type": {"type": "string"},
                            "topic": {"type": "string"},
                            "character_id": {"type": "string"},
                            "persona": {"type": "string"},
                            "series_group": {"type": ["string", "null"]},
                            "episode_order": {"type": ["string", "null"]},
                            "title": {"type": "string"},
                            "hook": {"type": "string"},
                            "body_narration": {"type": "string"},
                            "closing_line": {"type": "string"},
                            "screen_guide": {"type": "string"},
                            "app_screen_reference": {"type": ["string", "null"]},
                            "estimated_duration": {"type": "string"},
                            "aspect_ratio": {"type": "string"},
                            "disclaimer_note": {"type": "string"},
                            "music_license_note": {"type": "string"}
                        },
                        "required": [
                            "video_id", "content_type", "topic", "character_id", "persona",
                            "title", "hook", "body_narration", "closing_line", "screen_guide",
                            "estimated_duration", "disclaimer_note"
                        ]
                    }
                }
            },
            "required": ["scripts"]
        }
    }
}


def build_system_prompt():
    return (
        "당신은 사주·운세·타로·자미두수 서비스의 숏폼(유튜브 쇼츠/인스타그램 릴스) 기획·대본 전문가입니다.\n"
        "성인 시청자를 대상으로, 정보성을 유지하면서 흥미롭게 전달되는 최소 20초 분량의 대본을 작성하세요.\n"
        "결과물은 실제 AI 영상 제작(사람 중심 AI 생성 인물·음성, 9:16 세로형, 유튜브 쇼츠·인스타 릴스 공통 게시용)에 "
        "바로 투입 가능한 수준으로 구체적이어야 합니다.\n\n"

        "[제작 전제 조건]\n"
        "- 전편 AI 기반 제작이며, 특정 실제 인물을 재현하지 않는 AI 생성 인물·음성을 사용합니다.\n"
        "- 3D 캐릭터가 아닌 '사람 중심'의 자연스러운 실사풍 AI 영상 표현을 전제로 화면 가이드를 작성하세요.\n"
        "- 같은 character_id를 사용하는 영상들은 성별·연령대·말투·목소리 분위기가 서로 일관되어야 합니다 "
        "(20편 전체에서 동일 인물 또는 제한된 인물군 유지).\n"
        "- 최종 영상은 9:16 세로형 MP4로 납품되므로, 화면 가이드는 세로 프레임 기준(인물 클로즈업, "
        "세로 자막 배치 등)으로 작성하세요.\n\n"

        "[반드시 지켜야 할 정보성 표현 기준 - 위반 시 콘텐츠 전체 무효]\n"
        "1. 운세·타로·자미두수 내용을 사실로 단정하거나 미래 결과를 보장하는 표현 금지 "
        "(예: '반드시 ~된다', '100% ~할 것이다' 금지 / '~일 수 있어요', '~를 참고해보세요' 등 완곡 표현 사용)\n"
        "2. 불안이나 공포를 과도하게 자극하는 표현 금지 (예: '지금 안 하면 큰일 난다', '이걸 놓치면 큰 화를 입는다' 등 금지)\n"
        "3. 특정 선택이나 결제를 '직접 강요'하는 명령형/압박형 문구는 금지하되, 자연스러운 관심 유도와 결제 전환으로 "
        "이어지는 CTA는 반드시 closing_line에 포함할 것 "
        "(금지 예: '지금 결제하세요', '망설이지 말고 구매하세요' / "
        "사용 가능 예: '궁금하다면 프로필 링크에서 자세히 확인해보세요', '전체 풀이는 앱에서 확인할 수 있어요')\n"
        "4. 사례를 활용하는 경우에도 실제 결과를 보장하는 것처럼 보이지 않게 구성하고, "
        "'개인마다 다를 수 있다'는 전제를 body_narration 또는 disclaimer_note에 포함할 것\n"
        "5. 서비스명을 반복적으로 강조하지 말되, closing_line 마무리에는 '프로필 링크' 또는 '앱에서 확인'으로 "
        "자연스럽게 연결되는 유도 멘트를 반드시 포함할 것\n"
        "6. disclaimer_note에는 '본 콘텐츠는 정보 제공 목적이며 개인차가 있을 수 있습니다' 수준의 "
        "정보성 고지 문구와 그 노출 위치(예: 하단 자막 고정)를 명시할 것\n\n"

        "[사용법 안내 영상 전용 지침 (content_type이 '사용법 안내'인 경우)]\n"
        "- 실제 앱 화면 캡처를 활용한다는 전제로 screen_guide를 작성하고, "
        "app_screen_reference에 해당 단계의 화면 흐름을 구체적으로 기술하세요.\n"
        "- 앱 화면에 노출될 수 있는 개인정보·민감정보는 비식별화하거나 테스트 계정 사용을 전제로 안내 문구를 "
        "screen_guide에 포함하세요.\n"
        "- 자료만으로 표현하기 어려운 부분은 설명용 화면(그래픽/자막 강조)으로 보완하는 방식을 제안하세요.\n\n"

        "[에피소드·스토리형 영상 전용 지침 (content_type이 '에피소드·스토리형'인 경우)]\n"
        "- 등장인물의 페르소나(성별/연령대/말투/분위기)를 구체적으로 작성하고, "
        "같은 character_id의 다른 영상과 일관성을 유지하세요.\n"
        "- 여러 편이 이어지는 연속 구성으로 만들 경우 series_group과 episode_order를 채우고, "
        "단독 에피소드인 경우 둘 다 null로 두세요.\n"
        "- hook(0~3초)은 시청 이탈을 막을 수 있는 강한 첫 문장으로 작성하세요.\n\n"

        "반드시 JSON 형식으로만 응답하세요. 설명이나 주석, 마크다운 코드블록 없이 순수 JSON만 출력하세요."
    )


def generate_batch(content_type, topics, start_id, count, character_id, app_steps, max_retries=3):
    system_prompt = build_system_prompt()

    if content_type == "사용법 안내":
        user_prompt = (
            f"콘텐츠 유형: 사용법 안내\n"
            f"다룰 절차: {topics}\n"
            f"활용할 실제 앱 화면 흐름: {app_steps}\n"
            f"등장인물 character_id: {character_id} (전체 사용법 안내 5편에서 동일 인물 유지)\n\n"
            f"위 조건으로 숏폼 대본을 {count}편 생성하세요.\n"
            f"video_id는 {start_id}번부터 {start_id + count - 1}번까지 순서대로 부여하세요.\n"
            f"screen_guide에는 반드시 실제 앱 화면 캡처 삽입 지점, 비식별화/테스트 계정 안내, "
            f"설명용 화면 보완 지점을 구체적으로 작성하세요.\n"
            f"app_screen_reference에는 '{app_steps}' 흐름을 단계별로 기술하세요.\n"
            f"series_group과 episode_order는 null로 설정하세요 (사용법 안내는 개별 절차 안내이므로 단독 구성)."
        )
    else:
        user_prompt = (
            f"콘텐츠 유형: 에피소드·스토리형\n"
            f"다룰 주제: {topics}\n"
            f"등장인물 character_id: {character_id} (이 배치 내 및 동일 character_id를 쓰는 다른 배치와 일관성 유지)\n\n"
            f"위 조건으로 숏폼 대본을 {count}편 생성하세요.\n"
            f"video_id는 {start_id}번부터 {start_id + count - 1}번까지 순서대로 부여하세요.\n"
            f"persona는 character_id에 맞게 성별/연령대/말투/목소리 분위기를 구체적으로 작성하세요.\n"
            f"{count}편이 하나의 연속 스토리로 자연스럽게 이어질 수 있다면 series_group에 "
            f"'{topics}_시리즈'와 같은 값을, episode_order에 '1/{count}', '2/{count}' 형식을 부여하세요. "
            f"독립적인 에피소드로 구성하는 것이 더 적합하다면 둘 다 null로 두세요.\n"
            f"app_screen_reference는 null로 설정하세요 (에피소드형은 실제 앱 화면을 사용하지 않음)."
        )

    last_error = None
    for attempt in range(1, max_retries + 1):
        try:
            response = client.chat.completions.create(
                model="openai/gpt-oss-20b",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                response_format=FORTUNE_JSON_SCHEMA,
                temperature=0.6,
                max_tokens=3000
            )

            content = response.choices[0].message.content
            if not content or not content.strip():
                raise ValueError("빈 응답을 받았습니다.")

            parsed_json = json.loads(content)
            scripts = parsed_json.get("scripts", parsed_json.get("data", []))

            if not scripts:
                raise ValueError("scripts 배열이 비어있습니다.")

            return scripts

        except Exception as e:
            last_error = e
            print(f"[배치 '{content_type}/{topics}' 시도 {attempt}/{max_retries} 실패]: {e}")
            if attempt < max_retries:
                time.sleep(1.5)  # 재시도 전 잠깐 대기 (TPM 완충 목적)
                continue

    raise RuntimeError(
        f"'{content_type}/{topics}' 배치 생성에 {max_retries}회 시도 후 실패했습니다. "
        f"마지막 에러: {last_error}"
    )


def generate_fortune_scripts_logic(service_name: str = "사주운세 서비스") -> FortuneScriptBatchResponse:
    all_scripts_data = []

    for content_type, topics, start_id, count, character_id, app_steps in CONTENT_PLAN:
        batch_data = generate_batch(content_type, topics, start_id, count, character_id, app_steps)
        all_scripts_data.extend(batch_data)
        time.sleep(0.5)  # 배치 간 짧은 텀 (TPM 한도 여유 확보)

    script_items = []
    for idx, item in enumerate(all_scripts_data, 1):
        script_items.append(FortuneScriptItem(
            video_id=item.get("video_id", idx),
            content_type=item.get("content_type", "에피소드·스토리형"),
            topic=item.get("topic", ""),
            character_id=item.get("character_id", ""),
            persona=item.get("persona", ""),
            series_group=item.get("series_group"),
            episode_order=item.get("episode_order"),
            title=item.get("title", ""),
            hook=item.get("hook", ""),
            body_narration=item.get("body_narration", ""),
            closing_line=item.get("closing_line", ""),
            screen_guide=item.get("screen_guide", ""),
            app_screen_reference=item.get("app_screen_reference"),
            estimated_duration=item.get("estimated_duration", "20~50초"),
            aspect_ratio=item.get("aspect_ratio", "9:16"),
            disclaimer_note=item.get("disclaimer_note", ""),
            music_license_note=item.get(
                "music_license_note",
                "상업적 이용 가능 라이선스 음원 사용 예정 (출처 표기 조건 별도 확인)"
            ),
        ))

    how_to_use_count = sum(1 for s in script_items if s.content_type == "사용법 안내")
    episode_count = sum(1 for s in script_items if s.content_type == "에피소드·스토리형")

    return FortuneScriptBatchResponse(
        service_name=service_name,
        total_count=len(script_items),
        how_to_use_count=how_to_use_count,
        episode_count=episode_count,
        scripts=script_items
    )