# main.py
import os
import time
import logging
import base64
import requests
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
from ibm_cloud_sdk_core.authenticators import IAMAuthenticator
from PIL import Image
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

app = FastAPI()

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Retrieve API keys from environment variables
IBM_API_KEY = os.getenv('IBM_API_KEY')
STABILITY_KEY = os.getenv('STABILITY_KEY')

if not IBM_API_KEY or not STABILITY_KEY:
    logger.error("API keys are not set in environment variables.")
    raise Exception("API keys are missing.")

# IBM Allam Model Authentication
try:
    authenticator = IAMAuthenticator(IBM_API_KEY)
    token = authenticator.token_manager.get_token()
    logger.info("IBM Allam Model authenticated successfully.")
except Exception as e:
    logger.error(f"Failed to authenticate IBM Allam Model: {e}")
    token = None

# Allam API Headers
allam_headers = {
    "Accept": "application/json",
    "Content-Type": "application/json",
    "Authorization": f"Bearer {token}"
}
allam_url = "https://eu-de.ml.cloud.ibm.com/ml/v1/text/generation?version=2023-05-29"

# SD3 request
stability_host = "https://api.stability.ai/v2beta/stable-image/generate/sd3"

class StoryRequest(BaseModel):
    child_name: str
    value: str

class StoryResponse(BaseModel):
    story: str
    translated_story: str
    summary: str
    images: list  # List of base64-encoded images or URLs

def send_generation_request(host, params):
    headers = {
        "Accept": "image/*",
        "Authorization": f"Bearer {STABILITY_KEY}"
    }

    # Prepare multipart form-data
    files = {
        "prompt": (None, params["prompt"]),
        "aspect_ratio": (None, params["aspect_ratio"]),
        "seed": (None, str(params["seed"])),
        "output_format": (None, params["output_format"]),
        "model": (None, params["model"]),
        "mode": (None, params["mode"])
    }

    try:
        response = requests.post(
            host,
            headers=headers,
            files=files,
            timeout=30  # 30 seconds timeout
        )
        if not response.ok:
            raise Exception(f"HTTP {response.status_code}: {response.text}")
        logger.info("Image generation request successful.")
        return response
    except requests.exceptions.Timeout:
        logger.error("Request timed out.")
        raise HTTPException(status_code=504, detail="Stability AI request timed out.")
    except Exception as e:
        logger.error(f"Error in send_generation_request: {e}")
        raise HTTPException(status_code=502, detail="Failed to generate image.")

def generate_prompt(prompt_text):
    """Generate text using Allam Model."""
    body = {
        "input": f"<s> [INST] {prompt_text} [/INST]",
        "parameters": {
            "decoding_method": "greedy",
            "max_new_tokens": 1000,
            "repetition_penalty": 1.2
        },
        "model_id": "sdaia/allam-1-13b-instruct",
        "project_id": 'a63b4a9e-75df-4de5-b2d5-a2abe3d58e70'
    }
    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = requests.post(allam_url, headers=allam_headers, json=body, timeout=30)
            if response.status_code == 200:
                result = response.json()
                generated_text = result.get('results', [{}])[0].get('generated_text', '')
                return generated_text
            else:
                logger.error(f"Request failed with status {response.status_code}: {response.text}")
                time.sleep(2)
        except requests.exceptions.Timeout:
            logger.error("Request timed out. Retrying...")
            time.sleep(2)
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            break
    raise HTTPException(status_code=502, detail="Failed to generate prompt after retries.")

def translate_to_english_allam(text):
    """Translate Arabic story to English using Allam."""
    translation_prompt = f"Translate the following story into English:\n\n{text}"
    return generate_prompt(translation_prompt)

def get_story_summary_english(story_text):
    """Generate an English summary of the story using Allam."""
    summary_prompt = f"Provide a summary of this story and give a cinematic description of the story scene and character and the character outfit:\n\n{story_text}"
    return generate_prompt(summary_prompt)

def evaluate_story_safety(story_text):
    """Evaluate if the story is safe for children and aligned with Islamic values using Allam."""
    safety_prompt = (
        f"Evaluate the following story for child safety and alignment with Islamic values. "
        "Provide feedback on whether it meets these standards. If it does not, suggest changes or specify it as unsafe:\n\n{story_text}"
    )
    try:
        safety_feedback = generate_prompt(safety_prompt)
        if "unsafe" in safety_feedback.lower() or "does not meet" in safety_feedback.lower():
            logger.warning("Story did not pass safety checks.")
            return False, safety_feedback
        else:
            logger.info("Story passed safety checks.")
            return True, safety_feedback
    except Exception as e:
        logger.error(f"Error in safety evaluation: {e}")
        return False, "Error in safety evaluation."

def generate_images_for_scenes(english_story, story_summary, story_id, sentences_per_scene=4):
    """Split the story into scenes and generate images with improved context."""
    sentences = english_story.split(".")
    scenes = [".".join(sentences[i:i + sentences_per_scene]).strip() for i in range(0, len(sentences), sentences_per_scene) if sentences[i].strip()]
    image_data_list = []

    for i, scene in enumerate(scenes):
        if not scene:
            continue
        enhanced_prompt = f"{story_summary} In this scene: {scene}. Make sure the style is consistent with previous images, in an animated Arabic style."

        params = {
            "prompt": enhanced_prompt,
            "aspect_ratio": "1:1",
            "seed": 0,
            "output_format": "jpeg",
            "model": "sd3.5-large",
            "mode": "text-to-image"
        }
        try:
            response = send_generation_request(stability_host, params)
            image_data = base64.b64encode(response.content).decode('utf-8')
            image_data_list.append(image_data)
            logger.info(f"Generated image for scene {i+1}.")
        except HTTPException as he:
            logger.error(f"Failed to generate image for scene {i+1}: {he.detail}")
            image_data_list.append(None)
        except Exception as e:
            logger.error(f"Unexpected error for scene {i+1}: {e}")
            image_data_list.append(None)

    return image_data_list

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/generate-story", response_model=StoryResponse)
async def generate_story(request_data: StoryRequest):
    try:
        child_name = request_data.child_name
        value = request_data.value

        story_prompt = f"اكتب قصة قصيرة باللغة العربية عن طفل اسمه {child_name} يتعلم قيمة {value}. اجعل القصة مشوقة وتعليمية."
        story_text = generate_prompt(story_prompt)

        is_safe, feedback = evaluate_story_safety(story_text)
        if not is_safe:
            raise HTTPException(status_code=400, detail="Generated story is not safe for children.")

        english_story = translate_to_english_allam(story_text)
        story_summary = get_story_summary_english(english_story)
        story_id = f"{child_name}_{int(time.time())}"

        images = generate_images_for_scenes(english_story, story_summary, story_id)

        return StoryResponse(
            story=story_text,
            translated_story=english_story,
            summary=story_summary,
            images=images
        )

    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Error in generate_story: {e}")
        raise HTTPException(status_code=500, detail="Internal server error.")

@app.post("/generate-story")
async def generate_story(request: StoryRequest):
    child_name = request.child_name
    value = request.value

    if not child_name or not value:
        raise HTTPException(status_code=400, detail="Missing required data")

    # توليد القصة بناءً على البيانات المدخلة (الطفل والقيمة)
    paragraphs = [
        f"في يوم مشمس، كان هناك طفل صغير يدعى {child_name} يحب مساعدة الآخرين ويهتم بالقيم الأخلاقية مثل {value}.",
        "قرر محمد جمع ثمار الفواكه والخضراوات ومشاركتها مع جيرانه بمساعدة أصدقائه.",
        "استطاع محمد أن يكون رمزًا ومصدر إلهام للجميع، وكان يدعو دائما إلى العمل بروح الفريق."
    ]
    
    # توليد صور ملائمة لكل فقرة (يمكنك استخدام نموذج توليد الصور هنا)
    images = [
        "data:image/jpeg;base64,...",  # صورة الفقرة 1
        "data:image/jpeg;base64,...",  # صورة الفقرة 2
        "data:image/jpeg;base64,..."   # صورة الفقرة 3
    ]

    # التأكد من أن عدد الصور يتناسب مع عدد الفقرات
    if len(images) != len(paragraphs):
        raise HTTPException(status_code=500, detail="Mismatch between paragraphs and images")

    # الاستجابة تتضمن نص القصة والصور التوضيحية
    return {
        "story": paragraphs,
        "images": images
    }