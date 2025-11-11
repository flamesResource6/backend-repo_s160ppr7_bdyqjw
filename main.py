import os
import uuid
from typing import List, Optional

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.staticfiles import StaticFiles

from pydantic import BaseModel

# Database helpers
from database import db, create_document, get_documents
from schemas import TranslationJob, TranslationOutput

# Text extraction
from PyPDF2 import PdfReader
from docx import Document as DocxDocument

# Translation & TTS
from deep_translator import GoogleTranslator
from gtts import gTTS

app = FastAPI(title="Translator + TTS API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Ensure output directories exist
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(BASE_DIR, "outputs")
AUDIO_DIR = os.path.join(OUTPUT_DIR, "audio")
TEXT_DIR = os.path.join(OUTPUT_DIR, "texts")
for d in [OUTPUT_DIR, AUDIO_DIR, TEXT_DIR]:
    os.makedirs(d, exist_ok=True)

# Serve static outputs
app.mount("/outputs", StaticFiles(directory=OUTPUT_DIR), name="outputs")


class HealthResponse(BaseModel):
    message: str


@app.get("/", response_model=HealthResponse)
async def read_root():
    return {"message": "Hello from FastAPI Backend!"}


@app.get("/api/hello")
async def hello():
    return {"message": "Hello from the backend API!"}


@app.get("/test")
async def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }

    try:
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Configured"
            response["database_name"] = db.name if hasattr(db, 'name') else "✅ Connected"
            response["connection_status"] = "Connected"
            try:
                collections = db.list_collection_names()
                response["collections"] = collections[:10]
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️  Connected but Error: {str(e)[:50]}"
        else:
            response["database"] = "⚠️  Available but not initialized"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:50]}"

    response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
    response["database_name"] = "✅ Set" if os.getenv("DATABASE_NAME") else "❌ Not Set"
    return response


SUPPORTED_LANGS = {
    "Hindi": "hi",
    "Telugu": "te",
    "Kannada": "kn",
}


def extract_text_from_file(file_path: str) -> str:
    ext = os.path.splitext(file_path)[1].lower()
    if ext == ".pdf":
        reader = PdfReader(file_path)
        texts: List[str] = []
        for page in reader.pages:
            try:
                texts.append(page.extract_text() or "")
            except Exception:
                texts.append("")
        return "\n".join(texts).strip()
    elif ext == ".docx":
        doc = DocxDocument(file_path)
        return "\n".join([p.text for p in doc.paragraphs]).strip()
    elif ext in [".txt", ".md"]:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()
    else:
        raise HTTPException(status_code=400, detail="Unsupported file type. Please upload PDF, DOCX, or TXT.")


def chunk_text(text: str, max_len: int = 4500) -> List[str]:
    if len(text) <= max_len:
        return [text]
    chunks: List[str] = []
    current = []
    current_len = 0
    for para in text.split("\n"):
        if current_len + len(para) + 1 > max_len:
            chunks.append("\n".join(current))
            current = [para]
            current_len = len(para) + 1
        else:
            current.append(para)
            current_len += len(para) + 1
    if current:
        chunks.append("\n".join(current))
    return chunks


def translate_text(text: str, dest_lang: str) -> str:
    translator = GoogleTranslator(source="en", target=dest_lang)
    chunks = chunk_text(text)
    translated_chunks: List[str] = []
    for ch in chunks:
        translated_chunks.append(translator.translate(ch))
    return "\n".join(translated_chunks)


def synthesize_speech(text: str, lang_code: str, out_path: str):
    tts = gTTS(text=text, lang=lang_code)
    tts.save(out_path)


@app.post("/api/translate-upload")
async def translate_upload(
    file: UploadFile = File(...),
    job_name: Optional[str] = Form(default=None)
):
    # Save uploaded file temporarily
    filename = file.filename
    ext = os.path.splitext(filename)[1].lower()
    if ext not in [".pdf", ".docx", ".txt", ".md"]:
        raise HTTPException(status_code=400, detail="Please upload a PDF, DOCX, or TXT file.")

    temp_id = str(uuid.uuid4())
    temp_path = os.path.join(OUTPUT_DIR, f"upload_{temp_id}{ext}")
    with open(temp_path, "wb") as f:
        f.write(await file.read())

    try:
        source_text = extract_text_from_file(temp_path)
        if not source_text:
            raise HTTPException(status_code=400, detail="Could not extract text from the file.")

        outputs: List[TranslationOutput] = []
        for lang_name, lang_code in SUPPORTED_LANGS.items():
            translated = translate_text(source_text, lang_code)

            # Save translated text
            text_fname = f"{temp_id}_{lang_code}.txt"
            text_rel = f"texts/{text_fname}"
            text_path = os.path.join(TEXT_DIR, text_fname)
            with open(text_path, "w", encoding="utf-8") as tf:
                tf.write(translated)

            # Generate audio
            audio_fname = f"{temp_id}_{lang_code}.mp3"
            audio_rel = f"audio/{audio_fname}"
            audio_path = os.path.join(AUDIO_DIR, audio_fname)
            synthesize_speech(translated, lang_code, audio_path)

            outputs.append(TranslationOutput(
                language=lang_name,
                translated_text=translated[:5000],
                audio_path=f"/outputs/{audio_rel}",
                text_path=f"/outputs/{text_rel}",
            ))

        job = TranslationJob(
            job_name=job_name,
            source_filename=filename,
            source_language="en",
            status="completed",
            outputs=outputs,
        )
        job_id = create_document("translationjob", job)

        return JSONResponse({
            "job_id": job_id,
            "job": job.model_dump(),
        })
    except HTTPException:
        raise
    except Exception as e:
        # Save error job
        job = TranslationJob(
            job_name=job_name,
            source_filename=filename,
            source_language="en",
            status="error",
            outputs=[],
            error=str(e)
        )
        _ = create_document("translationjob", job)
        raise HTTPException(status_code=500, detail=f"Processing failed: {str(e)}")
    finally:
        try:
            if os.path.exists(temp_path):
                os.remove(temp_path)
        except Exception:
            pass


@app.get("/api/jobs")
async def list_jobs(limit: int = 10):
    try:
        docs = get_documents("translationjob", {}, limit)
        # Convert ObjectId to str
        for d in docs:
            if "_id" in d:
                d["_id"] = str(d["_id"])
        return {"items": docs}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
