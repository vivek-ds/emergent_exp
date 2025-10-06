import { useState, useEffect } from 'react';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import axios from 'axios';
import { Button } from './components/ui/button';
import { Input } from './components/ui/input';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from './components/ui/card';
import { Badge } from './components/ui/badge';
import { Separator } from './components/ui/separator';
import { toast, Toaster } from 'sonner';
import '@/App.css';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

const HomePage = () => {
  const [spotifyData, setSpotifyData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [sessionId, setSessionId] = useState(null);
  const [artistsText, setArtistsText] = useState('');
  const [genresText, setGenresText] = useState('');
  const [generating, setGenerating] = useState(false);
  const [result, setResult] = useState(null);

  useEffect(() => {
    // Check if we're returning from Spotify auth
    const urlParams = new URLSearchParams(window.location.search);
    const spotifyConnected = urlParams.get('spotify_connected');
    const session = urlParams.get('session');
    
    if (spotifyConnected && session) {
      setSessionId(session);
      fetchSpotifyData(session);
      // Clean up URL
      window.history.replaceState({}, document.title, window.location.pathname);
    }
  }, []);

  const fetchSpotifyData = async (sessionId) => {
    try {
      const response = await axios.get(`${API}/session/${sessionId}/spotify`);
      if (response.data.spotify_data) {
        setSpotifyData(response.data.spotify_data);
        setArtistsText(response.data.spotify_data.artists_text || '');
        setGenresText(response.data.spotify_data.genres_text || '');
        toast.success('Spotify data loaded successfully!');
      }
    } catch (error) {
      console.error('Error fetching Spotify data:', error);
    }
  };

  const handleSpotifyConnect = async () => {
    setLoading(true);
    try {
      const response = await axios.get(`${API}/login/spotify`);
      window.location.href = response.data.auth_url;
    } catch (error) {
      console.error('Error connecting to Spotify:', error);
      toast.error('Failed to connect to Spotify');
      setLoading(false);
    }
  };

  // Removed photo upload functionality

  const handleGenerate = async () => {
    if (!artistsText.trim() && !genresText.trim()) {
      toast.error('Please provide artists or genres, or connect your Spotify account');
      return;
    }

    setGenerating(true);
    try {
      const formData = new FormData();
      formData.append('session_id', sessionId || '');
      formData.append('artists_text', artistsText);
      formData.append('genres_text', genresText);

      const response = await axios.post(`${API}/generate`, formData, {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
      });

      setResult(response.data);
      toast.success('DJ Persona generated successfully!');
    } catch (error) {
      console.error('Error generating persona:', error);
      toast.error('Failed to generate DJ persona');
    } finally {
      setGenerating(false);
    }
  };

  const clearSpotify = () => {
    setSpotifyData(null);
    setSessionId(null);
    setArtistsText('');
    setGenresText('');
    toast.info('Spotify data cleared');
  };

  if (result) {
    return <GalleryPage result={result} onBack={() => setResult(null)} />;
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-950 via-slate-900 to-gray-950">
      <div className="container mx-auto px-4 py-8">
        <div className="text-center mb-12">
          <h1 
            className="text-6xl font-bold mb-4 bg-gradient-to-r from-cyan-400 via-emerald-400 to-orange-400 bg-clip-text text-transparent"
            style={{fontFamily: 'Space Grotesk, sans-serif'}}
            data-testid="main-title"
          >
            AI DJ Persona
          </h1>
          <p className="text-xl text-gray-300 max-w-2xl mx-auto">
            Transform your music taste into a visual DJ identity. Connect Spotify, upload photos, and watch AI create your unique persona.
          </p>
        </div>

        <div className="max-w-4xl mx-auto">
          <div className="grid md:grid-cols-2 gap-8">
            {/* Spotify Connection Card */}
            <Card className="bg-gray-900/50 border-gray-700 backdrop-blur-sm" data-testid="spotify-card">
              <CardHeader>
                <CardTitle className="text-white flex items-center gap-2">
                  🎵 Spotify Integration
                </CardTitle>
                <CardDescription className="text-gray-400">
                  Connect your Spotify to automatically analyze your music taste
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                {spotifyData ? (
                  <div className="space-y-3">
                    <div className="flex items-center justify-between">
                      <Badge variant="outline" className="bg-green-500/20 text-green-400 border-green-500/50">
                        ✓ Connected to Spotify
                      </Badge>
                      <Button 
                        variant="ghost" 
                        size="sm" 
                        onClick={clearSpotify}
                        className="text-gray-400 hover:text-white"
                        data-testid="clear-spotify-btn"
                      >
                        Clear
                      </Button>
                    </div>
                    <div className="text-sm text-gray-300">
                      <p><strong>Artists:</strong> {spotifyData.artists?.slice(0, 3).join(', ')} {spotifyData.artists?.length > 3 && '...'}</p>
                      <p><strong>Genres:</strong> {spotifyData.genres?.slice(0, 3).join(', ')} {spotifyData.genres?.length > 3 && '...'}</p>
                    </div>
                  </div>
                ) : (
                  <Button 
                    onClick={handleSpotifyConnect}
                    disabled={loading}
                    className="w-full bg-green-600 hover:bg-green-700 text-white"
                    data-testid="connect-spotify-btn"
                  >
                    {loading ? 'Connecting...' : 'Connect with Spotify'}
                  </Button>
                )}
              </CardContent>
            </Card>

            {/* Manual Input Card */}
            <Card className="bg-gray-900/50 border-gray-700 backdrop-blur-sm" data-testid="manual-input-card">
              <CardHeader>
                <CardTitle className="text-white">Manual Input</CardTitle>
                <CardDescription className="text-gray-400">
                  Or manually enter your favorite artists and genres
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="space-y-2">
                  <label className="text-sm font-medium text-gray-300">Top Artists</label>
                  <Input
                    placeholder="e.g., Deadmau5, Charlotte de Witte, Amelie Lens"
                    value={artistsText}
                    onChange={(e) => setArtistsText(e.target.value)}
                    className="bg-gray-800 border-gray-600 text-white placeholder-gray-400 focus:border-cyan-500"
                    data-testid="artists-input"
                  />
                </div>
                <div className="space-y-2">
                  <label className="text-sm font-medium text-gray-300">Genres</label>
                  <Input
                    placeholder="e.g., techno, melodic house, progressive house"
                    value={genresText}
                    onChange={(e) => setGenresText(e.target.value)}
                    className="bg-gray-800 border-gray-600 text-white placeholder-gray-400 focus:border-cyan-500"
                    data-testid="genres-input"
                  />
                </div>
              </CardContent>
            </Card>
          </div>

          {/* Info Card */}
          <Card className="mt-8 bg-gray-900/50 border-gray-700 backdrop-blur-sm" data-testid="info-card">
            <CardHeader>
              <CardTitle className="text-white">✨ AI-Generated DJ Persona</CardTitle>
              <CardDescription className="text-gray-400">
                Our AI will create a unique DJ persona based on your music taste, complete with a custom name, bio, and 4 professional DJ photos
              </CardDescription>
            </CardHeader>
          </Card>

          {/* Generate Button */}
          <div className="mt-8 text-center">
            <Button
              onClick={handleGenerate}
              disabled={generating || (!artistsText.trim() && !genresText.trim())}
              size="lg"
              className="px-12 py-4 bg-gradient-to-r from-cyan-500 to-emerald-500 hover:from-cyan-600 hover:to-emerald-600 text-white font-semibold rounded-xl shadow-lg shadow-cyan-500/25 transform hover:scale-105 transition-all duration-200"
              data-testid="generate-btn"
            >
              {generating ? (
                <>
                  <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-white mr-2"></div>
                  Generating Your DJ Persona...
                </>
              ) : (
                'Generate DJ Persona'
              )}
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
};

const GalleryPage = ({ result, onBack }) => {
  const [regenerating, setRegenerating] = useState(false);
  const [prompts, setPrompts] = useState(result.prompts);

  const handleRegeneratePrompts = async () => {
    setRegenerating(true);
    try {
      const response = await axios.post(`${API}/regenerate-prompts/${result.session_id}`);
      setPrompts(response.data.prompts);
      toast.success('New prompts generated!');
    } catch (error) {
      console.error('Error regenerating prompts:', error);
      toast.error('Failed to regenerate prompts');
    } finally {
      setRegenerating(false);
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-950 via-slate-900 to-gray-950">
      <div className="container mx-auto px-4 py-8">
        <div className="flex justify-between items-center mb-8">
          <Button 
            onClick={onBack} 
            variant="outline" 
            className="border-gray-600 text-gray-300 hover:bg-gray-800"
            data-testid="back-btn"
          >
            ← Back to Generator
          </Button>
          <h1 
            className="text-4xl font-bold bg-gradient-to-r from-cyan-400 via-emerald-400 to-orange-400 bg-clip-text text-transparent"
            style={{fontFamily: 'Space Grotesk, sans-serif'}}
            data-testid="gallery-title"
          >
            Your DJ Persona
          </h1>
          <div className="text-sm text-gray-400">
            Session: {result.session_id}
          </div>
        </div>

        <div className="grid lg:grid-cols-3 gap-8">
          {/* Persona Card */}
          <Card className="lg:col-span-1 bg-gray-900/50 border-gray-700 backdrop-blur-sm" data-testid="persona-card">
            <CardHeader>
              <CardTitle className="text-white text-2xl">{result.persona.dj_name}</CardTitle>
              <CardDescription className="text-gray-300">
                {result.persona.bio}
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              {/* Color Palette */}
              <div>
                <h4 className="text-sm font-medium text-gray-300 mb-2">Color Palette</h4>
                <div className="flex gap-2">
                  {result.persona.palette.map((color, index) => (
                    <div
                      key={index}
                      className="w-8 h-8 rounded-full border border-gray-600"
                      style={{ backgroundColor: color }}
                      title={color}
                    />
                  ))}
                </div>
              </div>

              {/* Style Tags */}
              <div>
                <h4 className="text-sm font-medium text-gray-300 mb-2">Style Tags</h4>
                <div className="flex flex-wrap gap-2">
                  {result.persona.style_tags.map((tag, index) => (
                    <Badge key={index} variant="secondary" className="bg-gray-700 text-gray-300">
                      {tag}
                    </Badge>
                  ))}
                </div>
              </div>

              {/* Logo Shape */}
              <div>
                <h4 className="text-sm font-medium text-gray-300 mb-2">Logo Shape</h4>
                <Badge variant="outline" className="border-cyan-500/50 text-cyan-400">
                  {result.persona.logo_shape}
                </Badge>
              </div>
            </CardContent>
          </Card>

          {/* Results */}
          <div className="lg:col-span-2 space-y-6">
            {/* Uploaded Photos */}
            {result.uploaded_photos && result.uploaded_photos.length > 0 && (
              <Card className="bg-gray-900/50 border-gray-700 backdrop-blur-sm" data-testid="uploaded-photos-card">
                <CardHeader>
                  <CardTitle className="text-white">Uploaded Photos</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="grid grid-cols-3 gap-3">
                    {result.uploaded_photos.map((photo, index) => (
                      <div key={index} className="aspect-square bg-gray-800 rounded-lg overflow-hidden">
                        <img
                          src={`${BACKEND_URL}/static/uploads/${result.session_id}/${photo}`}
                          alt={`Uploaded photo ${index + 1}`}
                          className="w-full h-full object-cover"
                        />
                      </div>
                    ))}
                  </div>
                </CardContent>
              </Card>
            )}

            {/* Generated Images */}
            {result.image_urls && result.image_urls.length > 0 ? (
              <Card className="bg-gray-900/50 border-gray-700 backdrop-blur-sm" data-testid="generated-images-card">
                <CardHeader>
                  <CardTitle className="text-white">Generated DJ Persona Images</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="grid grid-cols-2 lg:grid-cols-3 gap-4">
                    {result.image_urls.map((imageUrl, index) => (
                      <div key={index} className="aspect-square bg-gray-800 rounded-lg overflow-hidden shadow-lg">
                        <img
                          src={`${BACKEND_URL}/static/generated/${result.session_id}/${imageUrl}`}
                          alt={`Generated DJ persona image ${index + 1}`}
                          className="w-full h-full object-cover hover:scale-105 transition-transform duration-200"
                        />
                      </div>
                    ))}
                  </div>
                </CardContent>
              </Card>
            ) : (
              /* Prompts Display */
              <Card className="bg-gray-900/50 border-gray-700 backdrop-blur-sm" data-testid="prompts-card">
                <CardHeader>
                  <CardTitle className="text-white flex justify-between items-center">
                    AI Prompts for Your DJ Persona
                    <Button
                      onClick={handleRegeneratePrompts}
                      disabled={regenerating}
                      size="sm"
                      variant="outline"
                      className="border-cyan-500/50 text-cyan-400 hover:bg-cyan-500/10"
                      data-testid="regenerate-prompts-btn"
                    >
                      {regenerating ? 'Regenerating...' : 'Regenerate Prompts'}
                    </Button>
                  </CardTitle>
                  <CardDescription className="text-gray-400">
                    Copy these prompts to use with any AI image generator
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <div className="space-y-4 max-h-96 overflow-y-auto">
                    {prompts.map((prompt, index) => (
                      <div key={index} className="bg-gray-800 p-4 rounded-lg border border-gray-700">
                        <div className="flex justify-between items-start mb-2">
                          <span className="text-sm font-medium text-cyan-400">Prompt {index + 1}</span>
                          <Button
                            onClick={() => navigator.clipboard.writeText(prompt)}
                            size="sm"
                            variant="ghost"
                            className="text-xs text-gray-400 hover:text-white"
                          >
                            Copy
                          </Button>
                        </div>
                        <p className="text-sm text-gray-300 font-mono leading-relaxed">
                          {prompt}
                        </p>
                      </div>
                    ))}
                  </div>
                </CardContent>
              </Card>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

function App() {
  return (
    <div className="App">
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<HomePage />} />
        </Routes>
      </BrowserRouter>
      <Toaster 
        position="top-right"
        theme="dark"
        toastOptions={{
          style: {
            background: '#1f2937',
            color: '#f3f4f6',
            border: '1px solid #374151'
          }
        }}
      />
    </div>
  );
}

export default App;