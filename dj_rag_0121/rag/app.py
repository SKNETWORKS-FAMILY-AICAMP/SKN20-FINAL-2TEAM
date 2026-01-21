"""
셀럽 코디 추천 시스템 - Gradio 웹 인터페이스
LangGraph Agent + Korean CLIP 기반
"""

import gradio as gr
from pathlib import Path
from PIL import Image

from agent import FashionRecommendationAgent

# Agent를 전역으로 한 번만 초기화 (CLIP 모델 로드 시간 절약)
print("Agent 초기화 중...")
AGENT = FashionRecommendationAgent()
print("Agent 초기화 완료!")


def create_recommendation_html(
    recommendations: list[dict],
    recommendation_text: str
) -> str:
    """추천 결과를 HTML로 포맷팅"""
    similarity_info = ""
    for i, rec in enumerate(recommendations, 1):
        similarity_info += f"<li><strong>{rec['celeb_id']}</strong> - 유사도: {rec['similarity_score']:.1%}</li>"

    html = f"""
    <div style="padding: 20px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); border-radius: 15px; margin-bottom: 20px; color: white;">
        <h3 style="margin-top: 0;">AI 스타일리스트 추천</h3>
        <p style="line-height: 1.8; white-space: pre-wrap;">{recommendation_text}</p>
    </div>

    <div style="padding: 20px; background: #f8f9fa; border-radius: 15px; border: 1px solid #e9ecef;">
        <h3 style="color: #333; margin-top: 0;">유사도 분석</h3>
        <ul style="color: #555; line-height: 1.8;">
            {similarity_info}
        </ul>
    </div>
    """
    return html


def create_error_html(error_msg: str) -> str:
    """에러 메시지 HTML"""
    return f"""
    <div style="padding: 20px; background: #f8d7da; border-radius: 15px; border: 1px solid #f5c6cb;">
        <h3 style="color: #721c24; margin-top: 0;">오류 발생</h3>
        <p style="color: #721c24;">{error_msg}</p>
    </div>
    """


def recommend_fashion(image):
    """LangGraph Agent를 사용하여 이미지 기반 패션 추천"""
    if image is None:
        return None, None, None, create_error_html("이미지를 업로드해주세요.")

    try:
        # 이미지 경로 처리
        if isinstance(image, str):
            image_path = image
        else:
            # numpy array인 경우 임시 저장
            temp_path = Path("temp_user_image.jpg")
            Image.fromarray(image).save(temp_path)
            image_path = str(temp_path)

        # 전역 Agent 사용 (매번 새로 생성하지 않음)
        result = AGENT.recommend(image_path)

        # 임시 파일 정리
        temp_file = Path("temp_user_image.jpg")
        if temp_file.exists() and image_path == str(temp_file):
            temp_file.unlink()

        # 에러 처리
        if not result["success"]:
            return None, None, None, create_error_html(result["error"])

        # 결과 이미지 추출
        recommendations = result["recommendations"]
        result_images = []

        for rec in recommendations:
            img_path = Path(rec["image_path"])
            if img_path.exists():
                result_images.append(str(img_path))

        # HTML 결과 생성
        result_html = create_recommendation_html(
            recommendations,
            result["recommendation_message"]
        )

        return (
            result_images[0] if len(result_images) > 0 else None,
            result_images[1] if len(result_images) > 1 else None,
            result_images[2] if len(result_images) > 2 else None,
            result_html
        )

    except Exception as e:
        return None, None, None, create_error_html(f"시스템 오류: {str(e)}")


# Gradio 인터페이스 구성 (Gradio 6.0 호환)
with gr.Blocks(title="셀럽 코디 추천 시스템") as demo:
    gr.Markdown(
        """
        # 셀럽 코디 추천 시스템
        ### LangGraph Agent + Korean CLIP 기반 패션 스타일 매칭

        내 옷 사진을 업로드하면, AI가 유사한 스타일의 셀럽 코디를 찾아 추천해드립니다!

        **작동 방식:**
        1. **이미지 임베딩** - Korean CLIP으로 이미지를 벡터로 변환
        2. **유사도 검색** - LangChain Chroma에서 유사한 셀럽 코디 검색
        3. **추천 생성** - GPT가 맞춤 스타일링 추천 메시지 생성
        """
    )

    with gr.Row():
        # 왼쪽: 입력 영역
        with gr.Column(scale=1):
            input_image = gr.Image(
                label="내 옷 사진",
                type="filepath",
                height=400
            )
            submit_btn = gr.Button(
                "추천받기",
                variant="primary",
                size="lg"
            )
            gr.Markdown(
                """
                **Tip:** 전신 사진이나 옷이 잘 보이는 사진을 올려주세요!
                """
            )

        # 오른쪽: 결과 영역
        with gr.Column(scale=2):
            gr.Markdown("### 추천 셀럽 코디")
            with gr.Row():
                result_img1 = gr.Image(
                    label="추천 1",
                    height=280,
                    show_label=True
                )
                result_img2 = gr.Image(
                    label="추천 2",
                    height=280,
                    show_label=True
                )
                result_img3 = gr.Image(
                    label="추천 3",
                    height=280,
                    show_label=True
                )

    # 분석 결과
    result_html = gr.HTML(label="분석 결과")

    # 버튼 클릭 이벤트
    submit_btn.click(
        fn=recommend_fashion,
        inputs=[input_image],
        outputs=[result_img1, result_img2, result_img3, result_html]
    )

    gr.Markdown(
        """
        ---
        **Tech Stack:** LangGraph + Korean CLIP + LangChain Chroma + GPT-4o-mini
        """
    )


if __name__ == "__main__":
    demo.launch(
        server_name="0.0.0.0",
        server_port=8000,
        share=False,
        # Gradio 6.0: theme, css는 launch()로 이동
        # theme=gr.themes.Soft(),  # 필요시 활성화
    )
