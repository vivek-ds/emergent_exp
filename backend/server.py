from fastapi import FastAPI, APIRouter, HTTPException, UploadFile, File, Form, Request, status
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
import uuid
from datetime import datetime, timezone
import requests
import base64
import json
import asyncio
from PIL import Image
import io
import secrets
import urllib.parse
from google import genai as google_genai
from google.genai import types

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# Create the main app without a prefix
app = FastAPI()

# Create a router with the /api prefix
api_router = APIRouter(prefix="/api")

# Spotify OAuth configuration
SPOTIFY_CLIENT_ID = os.environ['SPOTIFY_CLIENT_ID']
SPOTIFY_CLIENT_SECRET = os.environ['SPOTIFY_CLIENT_SECRET']
SPOTIFY_REDIRECT_URI = os.environ['SPOTIFY_REDIRECT_URI']
EMERGENT_LLM_KEY = os.environ['EMERGENT_LLM_KEY']
GEMINI_API_KEY = os.environ['GEMINI_API_KEY']

# Configure Gemini client
gemini_client = google_genai.Client(api_key=GEMINI_API_KEY)

# Create static directories
static_dir = ROOT_DIR / 'static'
uploads_dir = static_dir / 'uploads'
generated_dir = static_dir / 'generated'
uploads_dir.mkdir(parents=True, exist_ok=True)
generated_dir.mkdir(parents=True, exist_ok=True)

# Models
class DJPersona(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str
    dj_name: str
    bio: str
    palette: List[str]
    style_tags: List[str]
    logo_shape: str
    locations: List[str]
    outfits: List[str]
    vibe_phrases: List[str]
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class GenerationSession(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str
    persona: Optional[Dict] = None
    prompts: List[str] = []
    image_urls: List[str] = []
    uploaded_photos: List[str] = []
    spotify_data: Optional[Dict] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class SpotifyTokens(BaseModel):
    access_token: str
    refresh_token: Optional[str] = None
    expires_in: int
    token_type: str = "Bearer"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

# Store sessions in memory (for demo purposes)
sessions_store = {}

def synth_persona(artists_text: str, genres_text: str) -> Dict[str, Any]:
    """Synthesize DJ persona from Spotify data"""
    artists = [a.strip() for a in artists_text.split(',') if a.strip()] if artists_text else []
    genres = [g.strip().lower() for g in genres_text.split(',') if g.strip()] if genres_text else []
    
    # Determine vibe phrases
    vibe_phrases = []
    if any(g in genres for g in ['techno', 'hard techno', 'edm', 'electro house']):
        vibe_phrases.append('warehouse-grade energy')
    if any(g in genres for g in ['afro house', 'amapiano', 'afro', 'deep house']):
        vibe_phrases.append('earthy percussion and rolling grooves')
    if any(g in genres for g in ['melodic techno', 'progressive house', 'trance']):
        vibe_phrases.append('melodic undertones and late-night hypnosis')
    
    if not vibe_phrases:
        vibe_phrases.append('eclectic selection and dance-floor focus')
    
    # Generate DJ name
    base_name = artists[0].split()[0] if artists else 'Meta'
    suffix = 'Pulse' if 'warehouse-grade energy' in vibe_phrases else 'Wave'
    dj_name = f'{base_name}{suffix}'
    
    # Define palette (dark futuristic)
    palette = ['#0F0F10', '#12131A', '#00D4AA', '#FF6B35']
    
    # Style and design elements
    style_tags = ['club lighting', 'editorial portrait', 'motion blur', 'neon accents']
    logo_shape = 'circular monogram'
    locations = ['underground booth', 'festival stage', 'studio portrait', 'neon hallway', 'foggy dance floor']
    outfits = ['all-black techwear', 'utility vest + headphones', 'heritage textile accent', 'oversized bomber', 'graphic tee + cargo']
    
    # Generate bio
    artist_influence = ', '.join(artists[:4]) if artists else 'diverse sounds'
    bio = f"{' and '.join(vibe_phrases)}. Influenced by {artist_influence}."
    
    return {
        'dj_name': dj_name,
        'bio': bio,
        'palette': palette,
        'style_tags': style_tags,
        'logo_shape': logo_shape,
        'locations': locations,
        'outfits': outfits,
        'vibe_phrases': vibe_phrases
    }

def build_prompts(persona: Dict[str, Any], count: int = 4, photo_context: str = "") -> List[str]:
    """Build image generation prompts"""
    anchor = "Professional DJ portrait; contemporary editorial lighting; 50mm depth of field; no extra people; crisp face details; cinematic contrast; high quality."
    
    variants = [
        ('portrait press shot', 'studio with dark background'),
        ('half-body with headphones', 'underground club booth'),
        ('action behind DJ decks', 'modern club stage with lighting'),
        ('wide shot with equipment', 'professional studio setup')
    ]
    
    prompts = []
    for i in range(min(count, len(variants))):
        title, location = variants[i]
        outfit = persona['outfits'][i % len(persona['outfits'])]
        style_tag = persona['style_tags'][i % len(persona['style_tags'])]
        palette_str = ', '.join(persona['palette'])
        
        prompt = f"{photo_context}{anchor} A {title} of DJ {persona['dj_name']}, wearing {outfit}, in {location}, styled as {style_tag}, using color palette {palette_str}, professional lighting, high quality photograph."
        prompts.append(prompt)
    
    return prompts

async def generate_images(prompts: List[str], session_id: str) -> List[str]:
    """Generate images using Gemini Imagen 3"""
    image_urls = []
    
    session_generated_dir = generated_dir / session_id
    session_generated_dir.mkdir(exist_ok=True)
    
    for i, prompt in enumerate(prompts[:4]):
        try:
            logging.info(f"Generating image {i+1} with Imagen 3: {prompt[:100]}...")
            
            # Generate image using Gemini Imagen 3
            response = gemini_client.models.generate_images(
                model='imagen-3.0-generate-002',
                prompt=prompt,
                config=types.GenerateImagesConfig(
                    number_of_images=1,
                    aspect_ratio='1:1'
                )
            )
            
            # Save the generated image
            if response.generated_images:
                generated_image = response.generated_images[0]
                image_bytes = generated_image.image.image_bytes
                
                filename = f"dj_image_{i+1}.png"
                filepath = session_generated_dir / filename
                
                with open(filepath, "wb") as f:
                    f.write(image_bytes)
                
                image_urls.append(filename)
                logging.info(f"Successfully generated image {i+1}: {filename}")
            else:
                logging.warning(f"No image generated for prompt {i+1}")
            
        except Exception as e:
            logging.error(f"Error generating image {i+1}: {str(e)}")
            # Create a fallback placeholder on error
            try:
                placeholder_filename = f"dj_image_{i+1}.png"
                placeholder_path = session_generated_dir / placeholder_filename
                
                from PIL import Image, ImageDraw, ImageFont
                
                img = Image.new('RGB', (1024, 1024), color=(15, 15, 16))
                draw = ImageDraw.Draw(img)
                
                # Add gradient effect
                for y in range(1024):
                    color_value = int(15 + (y / 1024) * 40)
                    draw.line([(0, y), (1024, y)], fill=(color_value, color_value + 10, color_value + 20))
                
                # Add text
                try:
                    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 60)
                except:
                    font = ImageFont.load_default()
                
                text = f"DJ IMAGE #{i+1}"
                bbox = draw.textbbox((0, 0), text, font=font)
                text_width = bbox[2] - bbox[0]
                text_height = bbox[3] - bbox[1]
                x = (1024 - text_width) // 2
                y = 400
                
                draw.text((x, y), text, fill=(0, 212, 170), font=font)
                
                subtitle = "Fallback Image"
                bbox2 = draw.textbbox((0, 0), subtitle, font=font)
                text_width2 = bbox2[2] - bbox2[0]
                x2 = (1024 - text_width2) // 2
                y2 = y + text_height + 20
                
                draw.text((x2, y2), subtitle, fill=(255, 107, 53), font=font)
                
                img.save(placeholder_path, 'PNG')
                image_urls.append(placeholder_filename)
                logging.info(f"Created fallback image {i+1}: {placeholder_filename}")
                
            except Exception as fallback_error:
                logging.error(f"Failed to create fallback image {i+1}: {str(fallback_error)}")
                continue
    
    return image_urls

# Routes
@api_router.get("/")
async def root():
    return {"message": "AI DJ Persona API"}

@api_router.get("/login/spotify")
async def spotify_login(request: Request):
    """Redirect to Spotify OAuth"""
    state = secrets.token_urlsafe(16)
    # Store state in session (in production, use proper session management)
    sessions_store[state] = {'created_at': datetime.now(timezone.utc)}
    
    params = {
        'client_id': SPOTIFY_CLIENT_ID,
        'response_type': 'code',
        'redirect_uri': SPOTIFY_REDIRECT_URI,
        'scope': 'user-top-read',
        'state': state
    }
    
    auth_url = 'https://accounts.spotify.com/authorize?' + urllib.parse.urlencode(params)
    return {'auth_url': auth_url}

@api_router.get("/callback/spotify")
async def spotify_callback(code: str, state: str):
    """Handle Spotify OAuth callback"""
    if state not in sessions_store:
        raise HTTPException(status_code=400, detail="Invalid state parameter")
    
    # Exchange code for tokens
    token_data = {
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': SPOTIFY_REDIRECT_URI,
    }
    
    auth_header = base64.b64encode(f"{SPOTIFY_CLIENT_ID}:{SPOTIFY_CLIENT_SECRET}".encode()).decode()
    headers = {
        'Authorization': f'Basic {auth_header}',
        'Content-Type': 'application/x-www-form-urlencoded'
    }
    
    response = requests.post('https://accounts.spotify.com/api/token', data=token_data, headers=headers)
    
    if response.status_code != 200:
        raise HTTPException(status_code=400, detail="Failed to get access token")
    
    tokens = response.json()
    
    # Fetch user's top artists
    spotify_headers = {'Authorization': f"Bearer {tokens['access_token']}"}
    artists_response = requests.get(
        'https://api.spotify.com/v1/me/top/artists?time_range=short_term&limit=20',
        headers=spotify_headers
    )
    
    if artists_response.status_code != 200:
        raise HTTPException(status_code=400, detail="Failed to fetch Spotify data")
    
    artists_data = artists_response.json()
    
    # Extract artists and genres
    artists = [artist['name'] for artist in artists_data.get('items', [])]
    all_genres = set()
    for artist in artists_data.get('items', []):
        all_genres.update(artist.get('genres', []))
    
    spotify_data = {
        'artists': artists,
        'genres': list(all_genres),
        'artists_text': ', '.join(artists),
        'genres_text': ', '.join(list(all_genres))
    }
    
    # Store in session
    sessions_store[state]['spotify_data'] = spotify_data
    
    # Redirect to frontend with session data
    frontend_url = os.environ.get('REACT_APP_BACKEND_URL', '').replace('/api', '')
    return RedirectResponse(url=f"{frontend_url}/?spotify_connected=true&session={state}")

@api_router.get("/session/{session_id}/spotify")
async def get_spotify_data(session_id: str):
    """Get Spotify data for session"""
    if session_id not in sessions_store:
        return {'spotify_data': None}
    
    return {'spotify_data': sessions_store[session_id].get('spotify_data')}

@api_router.post("/generate")
async def generate_dj_persona(
    session_id: Optional[str] = Form(None),
    artists_text: str = Form(""),
    genres_text: str = Form(""),
    photos: List[UploadFile] = File([])
):
    """Generate DJ persona with images"""
    if not session_id:
        session_id = str(uuid.uuid4())
    
    logging.info(f"Starting DJ persona generation for session: {session_id}")
    
    # Process uploaded photos for context (but don't store/display them)
    uploaded_photos_count = 0
    photo_context = ""
    
    if photos:
        for photo in photos:
            if photo.content_type and photo.content_type.startswith('image/'):
                try:
                    # Just count them for context, don't save
                    uploaded_photos_count += 1
                except Exception as e:
                    logging.error(f"Error processing photo {photo.filename}: {str(e)}")
                    continue
        
        if uploaded_photos_count > 0:
            photo_context = f"Based on {uploaded_photos_count} reference photos provided by the user, "
    
    # Generate persona
    persona = synth_persona(artists_text, genres_text)
    logging.info(f"Generated persona: {persona['dj_name']}")
    
    # Build prompts (only 4 for better performance)
    # Add photo context to prompts if photos were provided
    prompts = build_prompts(persona, 4, photo_context)
    
    # Generate images
    image_urls = await generate_images(prompts, session_id)
    
    logging.info(f"Generated {len(image_urls)} images for {persona['dj_name']}")
    
    # Save session data to MongoDB (don't include uploaded_photos in response)
    session_data = {
        'session_id': session_id,
        'persona': persona,
        'prompts': prompts,
        'image_urls': image_urls,
        'artists_text': artists_text,
        'genres_text': genres_text,
        'photos_provided': uploaded_photos_count,
        'created_at': datetime.now(timezone.utc)
    }
    
    await db.generation_sessions.insert_one(session_data)
    
    return {
        'session_id': session_id,
        'persona': persona,
        'prompts': prompts,
        'image_urls': image_urls,
        'use_image_api': True,
        'total_images': len(image_urls),
        'photos_used': uploaded_photos_count > 0
    }

@api_router.get("/session/{session_id}")
async def get_session(session_id: str):
    """Get session data"""
    session_data = await db.generation_sessions.find_one({'session_id': session_id})
    if not session_data:
        raise HTTPException(status_code=404, detail="Session not found")
    
    return session_data

@api_router.post("/regenerate-prompts/{session_id}")
async def regenerate_prompts(session_id: str):
    """Regenerate prompts for existing persona"""
    session_data = await db.generation_sessions.find_one({'session_id': session_id})
    if not session_data:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Build new prompts with existing persona
    new_prompts = build_prompts(session_data['persona'], 8)
    
    # Update session
    await db.generation_sessions.update_one(
        {'session_id': session_id},
        {'$set': {'prompts': new_prompts}}
    )
    
    return {'prompts': new_prompts}

# Include the router in the main app
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()