import google.genai as genai
import sys
import os
from PIL import Image
from dotenv import load_dotenv

load_dotenv()
api_key = os.environ.get('GEMINI_API_KEY')

client = genai.Client(api_key=api_key)
img = Image.open(r'C:\Users\mohdl\.gemini\antigravity\brain\cbd7da7b-7b09-41b5-b9cb-df3496d668a2\.user_uploaded\media_1788361157985.jpg')
prompt = 'Extract all text from this image exactly as you read it, preserving layout as much as possible.'
response = client.models.generate_content(model='gemini-2.5-flash', contents=[img, prompt])
print(response.text)
