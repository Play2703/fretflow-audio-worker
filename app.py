import os
import subprocess
import urllib.parse
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse

app = FastAPI(title="FretFlow Audio Extractor Service")

# Allow requests from any origin (FretFlow on Vercel, localhost, or mobile browsers)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

MAX_DURATION_SECONDS = 600  # 10 minutes maximum


def extract_video_id(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    host = parsed.hostname or ""
    host = host.lower().replace("www.", "")
    if host == "youtu.be":
        return parsed.path.strip("/").split("/")[0]
    if "youtube.com" in host:
        if parsed.path == "/watch":
            qs = urllib.parse.parse_qs(parsed.query)
            return qs.get("v", [""])[0]
        if parsed.path.startswith(("/embed/", "/shorts/", "/live/")):
            return parsed.path.split("/")[2]
    return ""


@app.get("/")
def health_check():
    return {
        "status": "online",
        "service": "FretFlow Audio Extractor",
        "endpoints": ["/extract?url=...", "/metadata?url=..."],
    }


def get_yt_dlp_base_args():
    args = [
        "--no-playlist",
        "--quiet",
        "--no-warnings",
        "--extractor-args",
        "youtube:player_skip=webpage,configs;player_client=android,visionos",
    ]
    cookies_content = os.environ.get("YOUTUBE_COOKIES", "").strip()
    if cookies_content:
        cookies_path = "/tmp/yt_cookies.txt"
        try:
            with open(cookies_path, "w", encoding="utf-8") as f:
                f.write(cookies_content)
            args.extend(["--cookies", cookies_path])
        except Exception:
            pass
    return args


@app.get("/metadata")
def get_metadata(url: str = Query(..., description="YouTube URL")):
    video_id = extract_video_id(url)
    if not video_id:
        raise HTTPException(status_code=400, detail="URL inválida do YouTube.")

    target_url = f"https://www.youtube.com/watch?v={video_id}"
    cmd = ["yt-dlp"] + get_yt_dlp_base_args() + [
        "--print",
        "%(title)s|||%(duration)s|||%(thumbnail)s|||%(uploader)s",
        target_url,
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        if res.returncode != 0:
            raise HTTPException(
                status_code=422,
                detail=f"Não foi possível obter dados do vídeo: {res.stderr.strip()}",
            )
        output = res.stdout.strip().split("|||")
        title = output[0] if len(output) > 0 else "YouTube Video"
        duration = float(output[1]) if len(output) > 1 and output[1] else 0
        thumbnail = output[2] if len(output) > 2 else ""
        artist = output[3] if len(output) > 3 else "YouTube"

        return {
            "videoId": video_id,
            "title": title,
            "artist": artist,
            "duration": duration,
            "thumbnailUrl": thumbnail,
        }
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="Tempo limite esgotado ao consultar YouTube.")


@app.get("/extract")
@app.get("/stream")
def stream_audio(url: str = Query(..., description="YouTube URL")):
    video_id = extract_video_id(url)
    if not video_id:
        raise HTTPException(status_code=400, detail="URL inválida do YouTube.")

    target_url = f"https://www.youtube.com/watch?v={video_id}"

    # 1. Verifica duração máxima
    dur_cmd = ["yt-dlp"] + get_yt_dlp_base_args() + [
        "--print",
        "%(duration)s",
        target_url,
    ]
    try:
        dur_res = subprocess.run(dur_cmd, capture_output=True, text=True, timeout=12)
        if dur_res.returncode == 0 and dur_res.stdout.strip():
            try:
                duration = float(dur_res.stdout.strip())
                if duration > MAX_DURATION_SECONDS:
                    raise HTTPException(
                        status_code=422,
                        detail=f"Vídeo muito longo ({int(duration // 60)} min). Máximo permitido: 10 minutos.",
                    )
            except ValueError:
                pass
    except subprocess.TimeoutExpired:
        pass

    # 2. Executa yt-dlp fazendo streaming direto com ffmpeg para áudio leve (m4a/aac)
    yt_cmd = ["yt-dlp"] + get_yt_dlp_base_args() + [
        "--no-progress",
        "--format",
        "140/18/bestaudio[ext=m4a]/bestaudio[acodec!=none]/bestaudio/best",
        "-o",
        "-",
        target_url,
    ]

    process = subprocess.Popen(
        yt_cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        bufsize=64 * 1024,
    )

    first_chunk = process.stdout.read(64 * 1024)
    if not first_chunk:
        stderr_err = process.stderr.read().decode("utf-8", errors="ignore").strip()
        process.kill()
        raise HTTPException(
            status_code=422,
            detail=stderr_err or "Não foi possível extrair a faixa de áudio deste vídeo.",
        )

    def iter_audio():
        try:
            yield first_chunk
            while True:
                chunk = process.stdout.read(64 * 1024)
                if not chunk:
                    break
                yield chunk
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()

    return StreamingResponse(
        iter_audio(),
        media_type="audio/mp4",
        headers={
            "Content-Disposition": f'inline; filename="{video_id}.m4a"',
            "Access-Control-Allow-Origin": "*",
            "Cache-Control": "public, max-age=3600",
        },
    )


@app.post("/extract")
@app.post("/api/songs/import/youtube")
async def post_stream_audio(payload: dict):
    target_url = payload.get("url") if isinstance(payload, dict) else ""
    if not target_url:
        raise HTTPException(status_code=400, detail="Envie um JSON com a propriedade 'url'.")
    return stream_audio(url=str(target_url))


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 7860))
    uvicorn.run("app:app", host="0.0.0.0", port=port)

