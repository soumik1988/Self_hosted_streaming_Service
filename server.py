
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
import urllib.parse
import uvicorn

app = FastAPI(title="DIY Streaming API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

MEDIA_REPO = Path("C:/Users/soumi/Videos/movie/1_Final")

@app.get("/")
def serve_frontend():
    return FileResponse("C:/Users/soumi/OneDrive/Documents/Workspace/index1.html")

# NEW: Dynamic browsing endpoint
@app.get("/api/browse")
def browse_media(path: str = ""):
    """Returns the contents of a specific folder, identifying movies vs sub-folders."""
    
    # Safely resolve the requested path to prevent users from breaking out of the media folder
    target_dir = (MEDIA_REPO / path).resolve()
    
    # Security check: Ensure the target directory is still inside MEDIA_REPO
    if not str(target_dir).startswith(str(MEDIA_REPO)):
        return {"error": "Invalid path"}

    if not target_dir.exists() or not target_dir.is_dir():
        return {"error": "Directory not found"}

    items = []
    
    # Scan only the current target directory
    for item in target_dir.iterdir():
        if item.is_dir():
            item_id = item.name
            # Get the relative path (e.g., "Action/Die_Hard" instead of "C:/.../Action/Die_Hard")
            rel_path = item.relative_to(MEDIA_REPO).as_posix()
            safe_rel_path = urllib.parse.quote(rel_path)

            # Check if this folder is an actual playable movie
            if (item / "master.m3u8").exists() or (item / "playlist.m3u8").exists():
                items.append({
                    "type": "movie",
                    "id": item_id,
                    "title": item_id.replace("_", " ").title(),
                    "path": rel_path,
                    "playlist_url": f"/media/{safe_rel_path}/master.m3u8",
                    "poster_url": f"/media/{safe_rel_path}/poster.jpg"
                })
            else:
                # If it has no playlist, it is just a container folder (like "Action Movies")
                items.append({
                    "type": "folder",
                    "id": item_id,
                    "title": item_id.replace("_", " ").title(),
                    "path": rel_path,
                    "poster_url": f"/media/{safe_rel_path}/poster.jpg"
                })

    return {"current_path": path, "items": items}

app.mount("/media", StaticFiles(directory=MEDIA_REPO), name="media")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8080)