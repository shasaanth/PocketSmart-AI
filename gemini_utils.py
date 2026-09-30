import os

from dotenv import load_dotenv
from google import genai
from google.genai import types


# Load environment variables
load_dotenv()


API_KEY = os.getenv("GEMINI_API_KEY")


if not API_KEY:
    raise ValueError(
        "GEMINI_API_KEY was not found in the .env file."
    )


# Gemini client
client = genai.Client(
    api_key=API_KEY
)


# Current stable model used by the project
MODEL_NAME = "gemini-3.5-flash-lite"


def generate_recommendation(
    prompt,
    image_bytes=None,
    mime_type=None
):

    contents = [prompt]

    # Add image when the user uploads one
    if image_bytes and mime_type:

        image_part = types.Part.from_bytes(
            data=image_bytes,
            mime_type=mime_type
        )

        contents = [
            image_part,
            prompt
        ]

    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=contents,
        config=types.GenerateContentConfig(
            max_output_tokens=2500
        )
    )

    return response.text