import logging
import uuid
import tempfile
import os
import httpx
from pathlib import Path
from PIL import Image
import io
import numpy as np

logger = logging.getLogger(__name__)

# Output directory for generated videos
VIDEOS_DIR = Path(__file__).parent.parent / "generated_videos"
VIDEOS_DIR.mkdir(exist_ok=True)


class VideoService:
    """Service for generating share videos from image + audio."""

    async def create_share_video(
        self,
        image_data: bytes,
        audio_url: str,
        title: str = "Melody Snap Song",
        duration: int = 15,
    ) -> str:
        """
        Create a share video by combining an image with audio.

        The video applies a slow Ken Burns zoom effect on the image
        and overlays the audio track.

        Args:
            image_data: PNG image bytes (the card screenshot)
            audio_url: URL to the audio file
            title: Song title (for logging)
            duration: Duration in seconds

        Returns:
            str: Path to the generated MP4 file
        """
        # moviepy 2.x imports
        from moviepy import VideoClip, AudioFileClip  # pyright: ignore[reportMissingImports]

        temp_dir = tempfile.mkdtemp()
        video_id = str(uuid.uuid4())[:8]

        try:
            # 1. Prepare image
            img = Image.open(io.BytesIO(image_data))

            # Convert RGBA → RGB (PNG from ViewShot has alpha channel)
            if img.mode == 'RGBA':
                background = Image.new('RGB', img.size, (255, 255, 255))
                background.paste(img, mask=img.split()[3])
                img = background
            elif img.mode != 'RGB':
                img = img.convert('RGB')

            # Ensure image is 1080px wide (9:16 video = 1080x1920)
            target_w = 1080
            target_h = 1920
            img = img.resize((target_w, target_h), Image.LANCZOS)
            logger.info(f"Card image prepared: {target_w}x{target_h}, mode={img.mode}")

            # Pre-convert to numpy RGB array (H, W, 3) - uint8
            img_array = np.array(img, dtype=np.uint8)
            logger.info(f"Image array shape: {img_array.shape}, dtype: {img_array.dtype}")

            # 2. Download audio to temp file
            audio_path = os.path.join(temp_dir, "audio.mp3")
            async with httpx.AsyncClient(timeout=60.0, verify=False) as client:
                audio_resp = await client.get(audio_url)
                if audio_resp.status_code != 200:
                    raise Exception(f"Failed to download audio: HTTP {audio_resp.status_code}")
                with open(audio_path, "wb") as f:
                    f.write(audio_resp.content)
            logger.info(f"Audio downloaded: {len(audio_resp.content)} bytes")

            # 3. Create video with moviepy 2.x API
            output_path = str(VIDEOS_DIR / f"share_{video_id}.mp4")
            h, w = img_array.shape[:2]

            # Ken Burns zoom: use VideoClip with custom make_frame
            def make_frame(t):
                """Apply slow Ken Burns zoom: 4% zoom over duration, returns RGB uint8."""
                scale = 1 + 0.04 * (t / duration)
                new_h, new_w = int(h * scale), int(w * scale)
                # Resize with PIL for quality
                zoomed = Image.fromarray(img_array).resize((new_w, new_h), Image.LANCZOS)
                # Center crop back to original size
                left = (new_w - w) // 2
                top = (new_h - h) // 2
                cropped = zoomed.crop((left, top, left + w, top + h))
                return np.array(cropped, dtype=np.uint8)

            video_clip = VideoClip(make_frame, duration=duration)

            # Load and trim audio
            audio_clip = AudioFileClip(audio_path)
            if audio_clip.duration > duration:
                # Try to start from a musically interesting point (25% in)
                start_time = min(audio_clip.duration * 0.25, audio_clip.duration - duration)
                audio_clip = audio_clip.subclipped(start_time, start_time + duration)
            else:
                audio_clip = audio_clip.subclipped(0, min(duration, audio_clip.duration))

            # Combine
            final = video_clip.with_audio(audio_clip)
            final.write_videofile(
                output_path,
                fps=24,
                codec="libx264",
                audio_codec="aac",
                preset="fast",
                threads=2,
                logger=None,  # Suppress moviepy progress bars
            )

            logger.info(f"Video generated: {output_path}")
            return output_path

        except Exception as e:
            logger.error(f"Video generation failed: {str(e)}", exc_info=True)
            raise
        finally:
            # Clean up temp files (keep the output video)
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)
