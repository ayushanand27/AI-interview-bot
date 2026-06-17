# 🎙️ Audio-to-Text — Speech-to-Text Transcription Module

## Table of Contents
- [Overview](#overview)
- [Feature Flow](#feature-flow)
- [Why Whisper?](#why-whisper)
- [Project Structure](#project-structure)
- [File Breakdown](#file-breakdown)
- [Dependencies](#dependencies)
- [API Reference](#api-reference)
- [Error Handling](#error-handling)
- [Whisper Model Options](#whisper-model-options)
- [System Requirements](#system-requirements)
- [Local Setup](#local-setup)
- [Testing](#testing)
- [Frontend Integration](#frontend-integration)
- [Related Modules](#related-modules)

---

## Overview

This module handles **Speech-to-Text transcription** for the AI-Assisted Mock & PI Platform.

During an interview, a candidate records their audio answer in the browser. The frontend sends that audio file to this backend module, which uses **OpenAI Whisper** to convert the audio into text. The transcribed text is then passed to the AI evaluation system for scoring.

> **Owner:** Ritesh
> **Branch:** `feature/audio-to-text`
> **Status:** ✅ Complete
> **Merged into:** `dev`

---

## Feature Flow

```
Candidate speaks into mic
        ↓
Browser records audio via MediaRecorder API (frontend)
        ↓
On submit → frontend sends audio blob to backend
        ↓
POST /api/v1/audio/transcribe
        ↓
FastAPI validates file type (wav, mp3, webm, ogg)
        ↓
audio_service.py saves file temporarily
        ↓
Whisper model transcribes audio → text
        ↓
Temp file deleted (always, even on failure)
        ↓
Transcription + language + duration returned to frontend
        ↓
Text passed to AI Evaluation Module (Shrey's task)
```

---

## Why Whisper?

| Option | Decision | Reason |
|---|---|---|
| **OpenAI Whisper** | ✅ Chosen | Already in tech stack, highly accurate, supports multiple languages, runs locally at no extra cost |
| AWS Transcribe | ❌ Rejected | Costs money, requires AWS account & setup |
| Google Speech-to-Text | ❌ Rejected | Requires Google Cloud setup and billing |

---

## Project Structure

```
app/
├── api/
│   └── v1/
│       ├── audio.py              ← NEW: HTTP endpoint (POST /transcribe)
│       └── router.py             ← MODIFIED: registered audio route
├── schemas/
│   └── audio.py                  ← NEW: Request/Response Pydantic models
├── services/
│   └── audio_service.py          ← NEW: Whisper transcription logic
│   └── README_audio_to_text.md   ← YOU ARE HERE
```

---

## File Breakdown

### `app/schemas/audio.py`
**What:** Defines the exact shape of JSON the API returns.

**Why:** Pydantic validates data automatically — if something is wrong, it catches it before sending to the frontend. Keeps API responses consistent and predictable for the frontend team. Also auto-generates Swagger docs.

**Key Models:**

```python
class TranscriptionResponse(BaseModel):
    success: bool
    transcription: Optional[str]   # The converted text
    language: Optional[str]        # Detected language e.g. "en"
    duration: Optional[float]      # Audio duration in seconds
    message: str                   # Human readable status

class TranscriptionError(BaseModel):
    success: bool = False
    message: str
    detail: Optional[str]          # Debug info
```

---

### `app/services/audio_service.py`
**What:** The core business logic — loads Whisper and handles the full transcription flow.

**Why:** Business logic is separated from routes so it's easier to test, reuse, and maintain. If we switch from Whisper to another model later, only this file changes.

**How it works:**
1. Saves uploaded audio to a temporary file (Whisper needs a file path, not a file object)
2. Runs Whisper transcription
3. Extracts text, detected language, and audio duration from result
4. Deletes temp file — always, even if transcription fails (`finally` block)
5. Returns `TranscriptionResponse`

---

### `app/api/v1/audio.py`
**What:** The HTTP endpoint that receives the audio file from the frontend.

**Why:** Routes are kept thin — they only validate input and delegate to the service layer. No business logic lives here.

**How it works:**
1. Checks that a file was provided
2. Validates file type against allowed list (`wav`, `mp3`, `webm`, `ogg`)
3. Calls `transcribe_audio()` from the service layer
4. Returns the response

---

### `app/api/v1/router.py` *(modified)*
**What:** Registers the audio route into the main API router.

**Why:** FastAPI won't know the endpoint exists unless it's mounted here. This is the single entry point for all routes.

**Change made:**
```python
from app.api.v1 import audio
api_router.include_router(audio.router)
```

---

## Dependencies

Added to `requirements.txt`:

```txt
# ── Audio Processing ──────────────────────────────────────────────
openai-whisper==20231117     # Local speech-to-text transcription model
ffmpeg-python==0.2.0         # Python wrapper for FFmpeg — audio format handling
pydub==0.25.1                # Audio file manipulation (mp3, wav, webm, ogg)

# ── File Handling ─────────────────────────────────────────────────
python-multipart==0.0.9      # Required by FastAPI to handle file uploads
aiofiles==23.2.1             # Async file read/write — non-blocking operations
```

| Package | Purpose |
|---|---|
| `openai-whisper` | Runs the Whisper model locally to convert audio to text |
| `ffmpeg-python` | Whisper internally needs FFmpeg to read different audio formats |
| `pydub` | Converts any browser audio format (webm, ogg) to wav before Whisper |
| `python-multipart` | Without this, FastAPI cannot parse uploaded audio files at all |
| `aiofiles` | FastAPI is async — blocking file I/O would slow down all requests |

> ⚠️ **FFmpeg must also be installed at the system level.**
> - Linux: `sudo apt install ffmpeg`
> - Mac: `brew install ffmpeg`
> - Windows: [Download from ffmpeg.org](https://ffmpeg.org/download.html) and add to PATH

---

## API Reference

### `POST /api/v1/audio/transcribe`

Accepts an audio file and returns the transcribed text.

**Request**
```
Content-Type: multipart/form-data
Field:        file  (required)
Formats:      audio/wav | audio/mp3 | audio/mpeg | audio/webm | audio/ogg
```

**Success Response — `200 OK`**
```json
{
  "success": true,
  "transcription": "My approach to this problem would be to first analyse...",
  "language": "en",
  "duration": 42.5,
  "message": "Audio transcribed successfully."
}
```

**Validation Error — `400 Bad Request`**
```json
{
  "detail": "Invalid file type 'video/mp4'. Allowed: wav, mp3, webm, ogg."
}
```

**Transcription Failure — `200 OK` (with success: false)**
```json
{
  "success": false,
  "transcription": null,
  "language": null,
  "duration": null,
  "message": "Transcription failed: <error detail>"
}
```

---

## Error Handling

| Scenario | Behaviour |
|---|---|
| No file provided | `400` — "No audio file provided." |
| Unsupported file type | `400` — "Invalid file type. Allowed: wav, mp3, webm, ogg." |
| Whisper model fails | Returns `success: false` with error message |
| Temp file cleanup | `finally` block ensures temp file is always deleted, even on crash |

---

## Whisper Model Options

The service currently loads the `base` model. To change it, update `audio_service.py`:

```python
model = whisper.load_model("base")  # change to: tiny | base | small | medium | large
```

| Model | Speed | Accuracy | Use Case |
|---|---|---|---|
| `tiny` | Fastest | Lowest | Quick local testing |
| `base` | Fast | Good | **Current — Production** ✅ |
| `small` | Medium | Better | If accuracy issues arise |
| `medium` | Slow | High | High accuracy requirements |
| `large` | Slowest | Highest | Maximum accuracy, heavy infrastructure |

---

## System Requirements

- Python `3.9+`
- FFmpeg installed at system level (see Dependencies)
- Minimum `2GB RAM` for `base` model (more for larger models)

---

## Local Setup

```bash
# 1. Install Python dependencies
pip install -r requirements.txt

# 2. Install FFmpeg (Linux)
sudo apt install ffmpeg

# 3. Run the server
uvicorn app.main:app --reload

# 4. Open Swagger docs
http://localhost:8000/docs
```

---

## Testing

You can test the endpoint directly from Swagger UI at `http://localhost:8000/docs` or via curl:

```bash
curl -X POST "http://localhost:8000/api/v1/audio/transcribe" \
  -H "accept: application/json" \
  -H "Content-Type: multipart/form-data" \
  -F "file=@your_audio_file.wav"
```

Expected response:
```json
{
  "success": true,
  "transcription": "your transcribed text here",
  "language": "en",
  "duration": 15.3,
  "message": "Audio transcribed successfully."
}
```

---

## Frontend Integration

This module is a **backend-only** responsibility. The frontend team is responsible for:

| Task | Detail |
|---|---|
| Mic button UI | Record button in interview screen |
| Audio recording | Using `MediaRecorder API` (WebRTC) |
| Sending audio | `POST` the audio blob to `/api/v1/audio/transcribe` |
| Displaying text | Show transcription to candidate |
| Passing to evaluation | Send transcribed text to AI evaluation module |

---

## Related Modules

| Module | Branch | Owner | Status |
|---|---|---|---|
| User Authentication | `feature/auth` | Ritesh | ✅ Done |
| Audio to Text | `feature/audio-to-text` | Ritesh | ✅ Done |