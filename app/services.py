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

# 5편(사용법 안내) + 15편(에피소드형)을 작은 배치로 나눠서 호출
CONTENT_PLAN = [
    ("사용법 안내", "서비스 이용 절차 안내", 1, 3),
    ("사용법 안내", "서비스 이용 절차 안내", 4, 2),
    ("에피소드·스토리형", "연애운, 재회운, 결혼운", 6, 3),
    ("에피소드·스토리형", "재물운, 직업운", 9, 3),
    ("에피소드·스토리형", "자녀운, 종합운세", 12, 3),
    ("에피소드·스토리형", "궁합, 타로", 15, 3),
    ("에피소드·스토리형", "자미두수", 18, 3),
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
                            "persona": {"type": "string"},
                            "title": {"type": "string"},
                            "hook": {"type": "string"},
                            "body_narration": {"type": "string"},
                            "closing_line": {"type": "string"},
                            "screen_guide": {"type": "string"},
                            "estimated_duration": {"type": "string"},
                            "disclaimer_note": {"type": "string"}
                        },
                        "required": ["video_id", "content_type", "topic", "persona", "title", "hook",
                                     "body_narration", "closing_line", "screen_guide", "estimated_duration",
                                     "disclaimer_note"]
                    }
                }
            },
            "required": ["scripts"]
        }
    }
}


def build_system_prompt():
    return (
        "당신은 사주·운세·타로·자미두수 서비스의 숏폼(유튜브 쇼츠/인스타 릴스) 기획 전문가입니다.\n"
        "성인 시청자를 대상으로, 정보성을 유지하면서 흥미롭게 전달되는 20초 이상 분량의 대본을 작성하세요.\n\n"
        "[반드시 지켜야 할 표현 기준 - 위반 시 콘텐츠 전체 무효]\n"
        "1. 운세·타로·자미두수 내용을 사실로 단정하거나 미래 결과를 보장하는 표현 금지 "
        "(예: '반드시 ~된다', '100% ~할 것이다' 등 금지, 대신 '~일 수 있어요', '~를 참고해보세요' 등 완곡 표현 사용)\n"
        "2. 불안이나 공포를 과도하게 자극하는 표현 금지 (예: '지금 안 하면 큰일 난다' 등)\n"
        "3. 특정 선택이나 결제를 '직접 강요'하는 명령형/압박형 문구는 금지하되, "
        "자연스러운 관심 유도와 결제 전환으로 이어지는 CTA는 반드시 포함할 것 "
        "(예: '지금 결제하세요', '망설이지 말고 구매하세요' 등 강요형은 금지 / "
        "'궁금하다면 프로필 링크에서 자세히 확인해보세요', '더 자세한 풀이가 궁금하다면 링크를 눌러보세요', "
        "'전체 사주 풀이는 앱에서 확인할 수 있어요' 등 유도형은 사용 가능)\n"
        "4. 사례 활용 시에도 실제 결과를 보장하는 것처럼 보이지 않게 구성 (개인마다 다를 수 있다는 전제 포함)\n"
        "5. 서비스명을 반복적으로 강조하지 말되, 마무리에는 반드시 '프로필 링크' 또는 '앱에서 확인'으로 "
        "자연스럽게 연결되는 결제·구매 유도 멘트를 closing_line에 포함할 것\n"
        "6. 특정 실제 인물을 재현하지 않는 AI 생성 인물/음성을 전제로 대본 작성 (실존 인물 언급 금지)\n"
        "7. 3D 캐릭터가 아닌 사람 중심의 자연스러운 영상 표현을 전제로 화면 가이드 작성\n\n"
        "반드시 JSON 형식으로만 응답하세요. 설명이나 주석, 마크다운 코드블록 없이 순수 JSON만 출력하세요."
    )


def generate_batch(content_type, topics, start_id, count, max_retries=3):
    system_prompt = build_system_prompt()
    user_prompt = (
        f"콘텐츠 유형: {content_type}\n"
        f"다룰 주제: {topics}\n\n"
        f"위 조건으로 숏폼 대본을 {count}편 생성하세요.\n"
        f"video_id는 {start_id}번부터 {start_id + count - 1}번까지 순서대로 부여하세요.\n"
        f"{'서비스 사용법 안내 영상이므로 실제 앱 화면 캡처를 활용한다는 전제로 screen_guide를 작성하세요.' if content_type == '사용법 안내' else '등장인물의 일관성을 유지할 수 있도록 persona를 구체적으로 작성하세요.'}"
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

    # 모든 재시도 실패 시 예외 발생
    raise RuntimeError(
        f"'{content_type}/{topics}' 배치 생성에 {max_retries}회 시도 후 실패했습니다. "
        f"마지막 에러: {last_error}"
    )


def generate_fortune_scripts_logic(service_name: str = "사주운세 서비스") -> FortuneScriptBatchResponse:
    all_scripts_data = []

    for content_type, topics, start_id, count in CONTENT_PLAN:
        batch_data = generate_batch(content_type, topics, start_id, count)
        all_scripts_data.extend(batch_data)
        time.sleep(0.5)  # 배치 간 짧은 텀 (TPM 한도 여유 확보)

    script_items = []
    for idx, item in enumerate(all_scripts_data, 1):
        script_items.append(FortuneScriptItem(
            video_id=item.get("video_id", idx),
            content_type=item.get("content_type", "에피소드·스토리형"),
            topic=item.get("topic", ""),
            persona=item.get("persona", ""),
            title=item.get("title", ""),
            hook=item.get("hook", ""),
            body_narration=item.get("body_narration", ""),
            closing_line=item.get("closing_line", ""),
            screen_guide=item.get("screen_guide", ""),
            estimated_duration=item.get("estimated_duration", "20~30초"),
            disclaimer_note=item.get("disclaimer_note", "")
        ))

    return FortuneScriptBatchResponse(
        service_name=service_name,
        total_count=len(script_items),
        scripts=script_items
    )