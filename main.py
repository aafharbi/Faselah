# main.py
import os
import time
import logging
import base64
import requests
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
from ibm_cloud_sdk_core.authenticators import IAMAuthenticator
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
    files = {key: (None, str(value)) for key, value in params.items()}

    try:
        response = requests.post(host, headers=headers, files=files, timeout=30)
        if response.ok:
            logger.info("Image generation request successful.")
            return response
        else:
            logger.error(f"Image generation failed: {response.status_code}")
            raise HTTPException(status_code=response.status_code, detail=response.text)
    except requests.exceptions.RequestException as e:
        logger.error(f"Error in send_generation_request: {e}")
        raise HTTPException(status_code=502, detail="Image generation request failed")

def generate_prompt(prompt_text):
    """Generate text using Allam Model."""
    body = {
        "input": f"<s> [INST] {prompt_text} [/INST]",
        "parameters": {"decoding_method": "greedy", "max_new_tokens": 1000, "repetition_penalty": 1.2},
        "model_id": "sdaia/allam-1-13b-instruct",
        "project_id": 'a63b4a9e-75df-4de5-b2d5-a2abe3d58e70'
    }

    try:
        response = requests.post(allam_url, headers=allam_headers, json=body, timeout=30)
        response.raise_for_status()
        result = response.json()
        return result.get('results', [{}])[0].get('generated_text', '')
    except requests.exceptions.RequestException as e:
        logger.error(f"Prompt generation failed: {e}")
        raise HTTPException(status_code=502, detail="Prompt generation failed")

@app.post("/generate-story", response_model=StoryResponse)
async def generate_story(request_data: StoryRequest):
    child_name = request_data.child_name
    value = request_data.value

    # Generate story text
    story_prompt = f"Write a short story in Arabic about a child named {child_name} who learns the value of {value}. Make the story engaging and educational."
    story_text = generate_prompt(story_prompt)

    # Evaluate safety
    safety_prompt = (
        f"Evaluate the following story for child safety and alignment with Islamic values. "
        "Provide feedback on whether it meets these standards. If it does not, suggest changes or specify it as unsafe:\n\n{story_text}"
    )
    is_safe, feedback = generate_prompt(safety_prompt)
    if not is_safe:
        raise HTTPException(status_code=400, detail="Generated story is not safe for children.")

    # Translate story to English
    english_story = generate_prompt(f"Translate the following story into English:\n\n{story_text}")

    # Generate story summary
    summary_prompt = f"Provide a summary of this story with a description of the scenes and character outfits:\n\n{english_story}"
    story_summary = generate_prompt(summary_prompt)

    # Generate images for each scene
    sentences = english_story.split(". ")
    scenes = [".".join(sentences[i:i + 3]).strip() for i in range(0, len(sentences), 3)]
    image_data_list = []

    for i, scene in enumerate(scenes):
        params = {
            "prompt": f"{story_summary}. Scene {i + 1}: {scene}",
            "aspect_ratio": "1:1",
            "seed": 0,
            "output_format": "jpeg",
            "model": "sd3.5-large",
            "mode": "text-to-image"
        }
        response = send_generation_request(stability_host, params)
        image_data = base64.b64encode(response.content).decode('utf-8')
        image_data_list.append(image_data)

    # Return the generated story, its translation, summary, and images
    return StoryResponse(
        story=story_text,
        translated_story=english_story,
        summary=story_summary,
        images=image_data_list
    )

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})
