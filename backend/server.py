from fastapi import FastAPI, APIRouter, HTTPException, UploadFile, File, Form, Request, status
from fastapi.responses import RedirectResponse, JSONResponse
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
from emergentintegrations.llm.chat import LlmChat, UserMessage
import secrets
import urllib.parse

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

def build_prompts(persona: Dict[str, Any], count: int = 8) -> List[str]:
    """Build image generation prompts"""
    anchor = "Maintain the same subject across all images; contemporary editorial lighting; 50mm/85mm depth of field; no extra people; crisp face; slight motion blur on hands; cinematic contrast."
    
    variants = [
        ('portrait press shot', 'studio portrait'),
        ('half-body with headphones', 'underground booth'),
        ('action behind DJ decks', 'club stage'),
        ('wide festival banner frame', 'festival stage'),
        ('graphic flyer composition', 'neon hallway'),
        ('close-up with accessory', 'studio portrait'),
        ('crowd bokeh action', 'foggy dance floor'),
        ('side-profile moody shot', 'underground booth')
    ]
    
    prompts = []
    for i in range(count):
        title, location = variants[i % len(variants)]
        outfit = persona['outfits'][i % len(persona['outfits'])]
        style_tag = persona['style_tags'][i % len(persona['style_tags'])]
        palette_str = ', '.join(persona['palette'])
        
        prompt = f"{anchor} A {title} of the same person as DJ {persona['dj_name']}, wearing {outfit}, in {location}, styled as {style_tag}, color palette {palette_str}, energetic, cinematic lighting."
        prompts.append(prompt)
    
    return prompts

async def generate_images(prompts: List[str]) -> List[str]:
    """Generate images using Gemini Nano Banana"""
    image_urls = []
    
    for i, prompt in enumerate(prompts):
        try:
            chat = LlmChat(
                api_key=EMERGENT_LLM_KEY,
                session_id=f"dj-generation-{uuid.uuid4()}",
                system_message="You are an expert AI image generator creating professional DJ persona photos."
            )
            chat.with_model("gemini", "gemini-2.5-flash-image-preview").with_params(modalities=["image", "text"])
            
            msg = UserMessage(text=prompt)
            text, images = await chat.send_message_multimodal_response(msg)
            
            if images and len(images) > 0:
                # Save the first generated image
                image_data = images[0]['data']
                image_bytes = base64.b64decode(image_data)
                
                filename = f"dj_image_{i+1}.png"
                filepath = generated_dir / filename
                
                with open(filepath, "wb") as f:
                    f.write(image_bytes)
                
                image_urls.append(filename)
            
        except Exception as e:
            logging.error(f"Error generating image {i+1}: {str(e)}")
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
    
    # Create session directory
    session_uploads_dir = uploads_dir / session_id
    session_generated_dir = generated_dir / session_id
    session_uploads_dir.mkdir(exist_ok=True)
    session_generated_dir.mkdir(exist_ok=True)
    
    # Process uploaded photos
    uploaded_photos = []
    for photo in photos:
        if photo.content_type and photo.content_type.startswith('image/'):
            try:
                # Read and process image
                image_data = await photo.read()
                image = Image.open(io.BytesIO(image_data))
                
                # Resize if too large
                if image.width > 1280 or image.height > 1280:
                    image.thumbnail((1280, 1280), Image.Resampling.LANCZOS)
                
                # Save processed image
                filename = f"photo_{len(uploaded_photos) + 1}_{photo.filename}"
                filepath = session_uploads_dir / filename
                image.save(filepath, format='PNG')
                uploaded_photos.append(filename)
                
            except Exception as e:
                logging.error(f"Error processing photo {photo.filename}: {str(e)}")
                continue
    
    # Generate persona
    persona = synth_persona(artists_text, genres_text)
    
    # Build prompts
    prompts = build_prompts(persona, 8)
    
    # Generate images
    image_urls = await generate_images(prompts)
    
    # Save session data to MongoDB
    session_data = {
        'session_id': session_id,
        'persona': persona,
        'prompts': prompts,
        'image_urls': image_urls,
        'uploaded_photos': uploaded_photos,
        'artists_text': artists_text,
        'genres_text': genres_text,
        'created_at': datetime.now(timezone.utc)
    }
    
    await db.generation_sessions.insert_one(session_data)
    
    return {
        'session_id': session_id,
        'persona': persona,
        'prompts': prompts,
        'image_urls': image_urls,
        'uploaded_photos': uploaded_photos,
        'use_image_api': True
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