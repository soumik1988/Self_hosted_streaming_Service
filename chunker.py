import os
import json
import subprocess
from pathlib import Path
from collections import deque

ENCODER = "h264_amf" 

def analyze_media(file_path: Path):
    try:
        cmd = [
            "ffprobe", "-v", "quiet", "-print_format", "json", 
            "-show_format", "-show_streams", str(file_path.absolute())
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        data = json.loads(result.stdout)
        
        audio_count = sum(1 for s in data.get('streams', []) if s.get('codec_type') == 'audio')
        
        valid_sub_codecs = ['subrip', 'srt', 'ass', 'ssa', 'webvtt']
        text_sub_index = None
        
        for s in data.get('streams', []):
            if s.get('codec_type') == 'subtitle' and s.get('codec_name') in valid_sub_codecs:
                if text_sub_index is None:
                    text_sub_index = s.get('index')
        
        is_h264 = any(s.get('codec_type') == 'video' and s.get('codec_name') == 'h264' for s in data.get('streams', []))
        
        bit_rate = data.get('format', {}).get('bit_rate')
        if not bit_rate:
            bit_rate = "2500000"
            
        return audio_count, text_sub_index, is_h264, int(bit_rate)
    except Exception as e:
        print(f"Error analyzing {file_path.name}: {e}")
        return 0, None, False, 2500000

def process_videos():
    folder_input = "C:\\Users\\soumi\\Videos\\movie\\unprocessed"
    source_dir = Path(folder_input.strip('\"\'')) 

    if not source_dir.exists():
        print(f"Folder not found: {source_dir}")
        return

    media_files = [f for f in source_dir.iterdir() if f.suffix.lower() in ['.mp4', '.mkv', '.avi']]

    for file_path in media_files:
        movie_name = file_path.stem
        output_dir = source_dir / movie_name
        output_dir.mkdir(exist_ok=True)
        
        print(f"\nProcessing: {file_path.name}")

        audio_count, text_sub_index, is_h264, source_bitrate = analyze_media(file_path)
        sub_display = 1 if text_sub_index is not None else 0
        print(f"  -> Found: 1 Video, {audio_count} Audio, {sub_display} Text-Subtitle(s).")
        
        video_codec = "copy" if is_h264 else ENCODER
        if is_h264:
            print("  -> Video is H.264. Using Smart Copy.")
        else:
            print(f"  -> Converting video with {ENCODER} (Constraining bitrate).")

        command = [
            "ffmpeg", "-y", "-i", str(file_path.absolute()),
            "-map", "0:v:0",          
            "-c:v", video_codec
        ]
        
        if not is_h264:
            target_kbps = source_bitrate // 1000
            max_kbps = int(target_kbps * 1.2) 
            buf_kbps = target_kbps * 2        
            
            command.extend([
                "-pix_fmt", "yuv420p",
                "-b:v", f"{target_kbps}k",
                "-maxrate", f"{max_kbps}k",
                "-bufsize", f"{buf_kbps}k"
            ])
            
        var_stream_map = "v:0,agroup:aud" 

        if audio_count > 0:
            command.extend(["-map", "0:a:0"])
            var_stream_map += " a:0,agroup:aud,language:ENG"
            
        if audio_count > 1:
            command.extend(["-map", "0:a:1"])
            var_stream_map += " a:1,agroup:aud,language:ALT"

        command.extend([
            "-c:a", "aac", 
            "-ac", "2",     
            "-b:a", "128k",
            "-f", "hls", "-hls_time", "10",
            "-hls_playlist_type", "vod",
            "-master_pl_name", "master.m3u8",
            "-var_stream_map", var_stream_map,
            "-hls_segment_filename", "chunk_%v_%03d.ts", 
            "stream_%v.m3u8"
        ])
        
        try:
            print("  -> Running FFmpeg Video/Audio encoding... Please wait.")
            process = subprocess.Popen(
                command, 
                cwd=str(output_dir), 
                stdout=subprocess.PIPE, 
                stderr=subprocess.STDOUT, 
                universal_newlines=True,
                encoding='utf-8',
                errors='replace' 
            )

            error_log = deque(maxlen=20) 
            for line in process.stdout:
                error_log.append(line.strip()) 
                            
            process.wait() 
            
            if process.returncode == 0:
                print(f"  -> [SUCCESS] Video and Audio HLS generated.")
                
                if text_sub_index is not None:
                    print("  -> Extracting sidecar subtitles...")
                    sub_cmd = [
                        "ffmpeg", "-y", "-i", str(file_path.absolute()),
                        "-map", f"0:{text_sub_index}", 
                        "-c:s", "webvtt", 
                        "subtitles.vtt" 
                    ]
                    subprocess.run(sub_cmd, cwd=str(output_dir), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    
                    # --- NEW: Generate a compliant subtitle playlist ---
                    print("  -> Creating Subtitle Playlist...")
                    sub_m3u8_path = output_dir / "subtitles.m3u8"
                    with open(sub_m3u8_path, 'w') as f:
                        f.write("#EXTM3U\n")
                        f.write("#EXT-X-TARGETDURATION:86400\n") # Tell the player it's a massive, single file
                        f.write("#EXT-X-VERSION:3\n")
                        f.write("#EXT-X-PLAYLIST-TYPE:VOD\n")
                        f.write("#EXTINF:86400.0,\n")
                        f.write("subtitles.vtt\n")
                        f.write("#EXT-X-ENDLIST\n")
                    
                    print("  -> Injecting subtitles into Master Playlist...")
                    master_file = output_dir / "master.m3u8"
                    
                    with open(master_file, 'r') as f:
                        lines = f.readlines()
                        
                    with open(master_file, 'w') as f:
                        for line in lines:
                            if line.startswith("#EXT-X-STREAM-INF"):
                                line = line.strip() + ',SUBTITLES="sub"\n'
                            
                            f.write(line)
                            
                            if line.startswith("#EXT-X-VERSION"):
                                # FIXED: Now pointing to the valid .m3u8 playlist instead of the raw .vtt
                                f.write('#EXT-X-MEDIA:TYPE=SUBTITLES,GROUP-ID="sub",NAME="English",DEFAULT=YES,URI="subtitles.m3u8"\n')

                print(f"\n[COMPLETE] Successfully processed '{movie_name}'.")

            else:
                print(f"\n[ERROR] FFmpeg failed on '{movie_name}'.")
                print("-" * 40)
                print("FFMPEG ERROR LOG (Last 20 lines):")
                for err_line in error_log:
                    print(err_line)
                print("-" * 40 + "\n")
                
        except Exception as e:
            print(f"[ERROR] An unexpected error occurred: {e}")
            
if __name__ == "__main__":
    process_videos()