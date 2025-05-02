import os
import uuid
import json
import time
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, Tuple
import logging
from pathlib import Path
import shutil

from fastapi import HTTPException
from celery import Celery
from redis import Redis

# Import from the main module
from ..main import (
    generate_educational_content, process_section, compose_final_video,
    get_default_voice_for_language, SUPPORTED_VOICES, LANGUAGE_CODE_MAP
)
from ..utils import ensure_dir_exists, cleanup_dir, logger
from .models import JobStatus

# --- Configuration ---
# Path configuration
PROJECT_BASE_DIR = Path(__file__).parent.parent.parent.resolve()
OUTPUT_DIR = PROJECT_BASE_DIR / os.getenv("OUTPUT_DIR", "output")
JOB_DIR = OUTPUT_DIR / "jobs"
ASSETS_DIR = PROJECT_BASE_DIR / os.getenv("ASSETS_DIR", "assets")

# Rate limiting configuration (using Redis now)
MAX_CONCURRENT_JOBS = int(os.getenv("MAX_CONCURRENT_JOBS", 5)) # Max jobs actively processed by workers
RATE_LIMIT_PERIOD = int(os.getenv("RATE_LIMIT_PERIOD", 3600))  # 1 hour in seconds
MAX_JOBS_PER_PERIOD = int(os.getenv("MAX_JOBS_PER_PERIOD", 10)) # Max jobs accepted per period

# --- Redis Initialization ---
try:
    redis_client = Redis(
        host=os.getenv("REDIS_HOST", "localhost"),
        port=int(os.getenv("REDIS_PORT", 6379)),
        db=int(os.getenv("REDIS_DB", 0)),
        password=os.getenv("REDIS_PASSWORD", "qaz000"),  # Use the password if needed
        decode_responses=True # Decode responses to strings
    )
    redis_client.ping() # Check connection
    logger.info("Successfully connected to Redis.")
except Exception as e:
    logger.error(f"Failed to connect to Redis: {e}. Job tracking and rate limiting will not work.", exc_info=True)
    redis_client = None

# --- Celery Initialization ---
# Ensure environment variables are loaded before Celery app creation if needed elsewhere
# from dotenv import load_dotenv
# dotenv_path = os.path.join(PROJECT_BASE_DIR, 'config', '.env')
# load_dotenv(dotenv_path=dotenv_path)


celery_app = Celery(
    'edu_video_generator_tasks',
    broker='redis://:qaz000@localhost:6379/1', 
    backend='redis://:qaz000@localhost:6379/2',
)

# Optional Celery configuration
celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
)

# Ensure directories exist
ensure_dir_exists(str(OUTPUT_DIR))
ensure_dir_exists(str(JOB_DIR))
ensure_dir_exists(str(ASSETS_DIR))

# --- Redis Key Prefixes ---
JOB_DATA_PREFIX = "job:"
ACTIVE_JOBS_SET = "active_jobs" # Set of job IDs currently being processed by workers
JOB_TIMESTAMPS_ZSET = "job_timestamps" # Sorted set for rate limiting (score=timestamp, value=job_id)
VIDEO_CACHE_PREFIX = "video_cache:" # Prefix for caching completed jobs
JOB_CACHE_KEY_LOOKUP = "job_cache_lookup:" # Hash: cache_key -> job_id (for active/queued check)

# --- Cache Configuration ---
CACHE_TTL_SECONDS = int(os.getenv("CACHE_TTL_SECONDS", 7 * 24 * 60 * 60)) # Default: 7 days

# --- Helper Functions ---

def _generate_cache_key(request_data: Dict[str, Any]) -> str:
    """Generates a consistent cache key based on relevant request parameters."""
    topic = request_data.get("topic", "").strip().lower()
    language = request_data.get("language", "en-US").strip().lower()
    # Use a default placeholder if voice is None or empty
    voice = request_data.get("voice", "").strip().lower() or "default"
    # Normalize boolean flags that might affect output (though less likely for caching)
    # skip_content = request_data.get("skip_content_cache", False)
    # no_anim = request_data.get("no_animation_cache", False)
    # Key based only on content-defining parameters for now
    key = f"{VIDEO_CACHE_PREFIX}{topic}:{language}:{voice}"
    # Replace potentially problematic characters for Redis keys if needed
    key = key.replace(" ", "_").replace(":", "-")
    return key

# --- Job Management Functions ---

def get_job_data(job_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve job data from Redis"""
    if not redis_client: return None
    job_key = f"{JOB_DATA_PREFIX}{job_id}"
    job_data_json = redis_client.get(job_key)
    if job_data_json:
        try:
            return json.loads(job_data_json)
        except json.JSONDecodeError:
            logger.error(f"Failed to decode JSON for job {job_id}")
            return None
    return None

def update_job_status(job_id: str, status: JobStatus, progress: Optional[float] = None,
                     error: Optional[str] = None, output_path: Optional[str] = None) -> bool:
    """Update job status and other fields in Redis"""
    if not redis_client: return False
    job_key = f"{JOB_DATA_PREFIX}{job_id}"
    try:
        # Use optimistic locking with WATCH/MULTI/EXEC for atomic updates
        with redis_client.pipeline() as pipe:
            while True:
                try:
                    pipe.watch(job_key)
                    job_data_json = pipe.get(job_key)
                    if not job_data_json:
                        logger.warning(f"Job data not found in Redis for {job_id} during update.")
                        return False

                    job_data = json.loads(job_data_json)

                    job_data["status"] = status.value # Use enum value
                    if progress is not None:
                        job_data["progress"] = round(progress, 2)
                    if error:
                        job_data["error"] = error
                    if output_path:
                        job_data["output_path"] = output_path
                    
                    # Start transaction
                    pipe.multi()
                    pipe.set(job_key, json.dumps(job_data))
                    pipe.execute()
                    logger.info(f"Updated job {job_id} status to {status.value}")
                    return True # Update successful
                except redis.WatchError:
                    # Key was modified between WATCH and EXEC, retry
                    logger.warning(f"WatchError updating job {job_id}, retrying...")
                    continue
                except json.JSONDecodeError:
                     logger.error(f"Failed to decode JSON for job {job_id} during update.")
                     return False
    except Exception as e:
        logger.error(f"Error updating job status for {job_id} in Redis: {e}", exc_info=True)
        return False


def can_start_new_job() -> bool:
    """Check if system can handle a new job based on resource constraints using Redis"""
    if not redis_client:
        logger.warning("Redis not available, cannot check resource limits. Allowing job creation.")
        return True # Or False, depending on desired behavior without Redis

    try:
        # 1. Check concurrent job limit (jobs actively being processed)
        active_job_count = redis_client.scard(ACTIVE_JOBS_SET)
        if active_job_count >= MAX_CONCURRENT_JOBS:
            logger.warning(f"Concurrent job limit reached ({active_job_count}/{MAX_CONCURRENT_JOBS}).")
            return False

        # 2. Check rate limit (jobs accepted recently)
        current_time = time.time()
        period_start = current_time - RATE_LIMIT_PERIOD

        # Remove old entries from the sorted set (score is timestamp)
        redis_client.zremrangebyscore(JOB_TIMESTAMPS_ZSET, 0, period_start)

        # Count jobs accepted within the current period
        recent_job_count = redis_client.zcount(JOB_TIMESTAMPS_ZSET, period_start, "+inf")

        if recent_job_count >= MAX_JOBS_PER_PERIOD:
            logger.warning(f"Rate limit reached ({recent_job_count}/{MAX_JOBS_PER_PERIOD} in last {RATE_LIMIT_PERIOD}s).")
            return False

        return True
    except Exception as e:
        logger.error(f"Error checking resource limits in Redis: {e}", exc_info=True)
        return False # Fail safe if Redis check fails


def create_job(request_data: Dict[str, Any]) -> Tuple[Dict[str, Any], bool]:
    """
    Check cache, check for active/queued duplicates, create a new job if none exist,
    store initial data in Redis, and queue it in Celery.
    Returns a tuple: (job_data, is_cached_or_duplicate)
    """
    if not redis_client:
        raise HTTPException(status_code=503, detail="Job tracking service (Redis) unavailable.")

    cache_key = _generate_cache_key(request_data)
    lookup_key = f"{JOB_CACHE_KEY_LOOKUP}{cache_key}" # Key for the hash lookup

    # --- Check 1: Completed Job Cache ---
    cached_job_id_completed = redis_client.get(cache_key) # Check the TTL cache first
    if cached_job_id_completed:
        logger.info(f"Potential completed cache hit for key '{cache_key}', checking job ID '{cached_job_id_completed}'")
        cached_job_data = get_job_data(cached_job_id_completed)
        if cached_job_data and cached_job_data.get("status") == JobStatus.COMPLETED.value:
            output_path = cached_job_data.get("output_path")
            if output_path and os.path.exists(output_path):
                logger.info(f"Cache hit (Completed): Returning completed job {cached_job_id_completed} for request.")
                response_data = cached_job_data.copy()
                if "request_data" in response_data: del response_data["request_data"]
                return response_data, True # Signal that this came from cache
            else:
                logger.warning(f"Cache hit for completed job {cached_job_id_completed}, but output file '{output_path}' not found. Removing stale cache entry.")
                redis_client.delete(cache_key) # Remove stale TTL cache
                redis_client.hdel(lookup_key, cache_key) # Remove from lookup hash too
        else:
             logger.info(f"Completed cache key '{cache_key}' points to job {cached_job_id_completed}, but job status is not 'completed' or data is missing. Removing stale cache entry.")
             redis_client.delete(cache_key) # Remove potentially stale TTL cache
             redis_client.hdel(lookup_key, cache_key) # Remove from lookup hash too

    # --- Check 2: Active/Queued Duplicate Job ---
    # Use a hash to map cache_key -> job_id for non-completed jobs
    existing_job_id = redis_client.hget(lookup_key, cache_key)
    if existing_job_id:
        logger.info(f"Potential active/queued duplicate found for key '{cache_key}', checking job ID '{existing_job_id}'")
        existing_job_data = get_job_data(existing_job_id)
        if existing_job_data:
            status = existing_job_data.get("status")
            if status in [JobStatus.QUEUED.value, JobStatus.PROCESSING.value]:
                logger.info(f"Duplicate request: Job {existing_job_id} is already {status}. Returning existing job details.")
                response_data = existing_job_data.copy()
                if "request_data" in response_data: del response_data["request_data"]
                return response_data, True # Signal that this is a duplicate
            elif status in [JobStatus.COMPLETED.value, JobStatus.FAILED.value, JobStatus.CANCELLED.value]:
                # Job finished/failed/cancelled but wasn't cleaned from lookup hash, clean it now
                logger.warning(f"Found job {existing_job_id} in lookup hash with status {status}. Cleaning up stale lookup entry.")
                redis_client.hdel(lookup_key, cache_key)
            else:
                 logger.warning(f"Found job {existing_job_id} in lookup hash with unknown status '{status}'. Cleaning up stale lookup entry.")
                 redis_client.hdel(lookup_key, cache_key)
        else:
            # Job ID exists in lookup hash, but no data found in Redis. Clean up.
            logger.warning(f"Found job ID {existing_job_id} in lookup hash, but no corresponding job data found. Cleaning up stale lookup entry.")
            redis_client.hdel(lookup_key, cache_key)


    # --- No Cache Hit or Duplicate Found: Proceed with New Job Creation ---
    logger.info(f"No valid cache entry or active duplicate found for key '{cache_key}'. Creating new job.")

    # Check resource limits before creating a new job
    if not can_start_new_job():
        raise HTTPException(
            status_code=429,
            detail="Resource limits exceeded. Please try again later."
        )

    # Create job ID and metadata
    job_id = str(uuid.uuid4())
    created_at = datetime.now().isoformat()

    # Estimate completion time (basic estimate)
    estimated_minutes = 15
    estimated_completion = (datetime.now() + timedelta(minutes=estimated_minutes)).isoformat()

    # Create job directory (can be done here or at the start of the task)
    job_dir = JOB_DIR / job_id
    ensure_dir_exists(str(job_dir))

    # Create initial job data
    job_data = {
        "job_id": job_id,
        "status": JobStatus.QUEUED.value, # Use enum value
        "created_at": created_at,
        "topic": request_data["topic"],
        "estimated_completion": estimated_completion,
        "progress": 0.0,
        "request_data": request_data, # Store original request
        "output_path": None,
        "error": None,
        "celery_task_id": None # Placeholder for Celery task ID
    }

    try:
        # Store initial job data in Redis (before queueing)
        job_key = f"{JOB_DATA_PREFIX}{job_id}"
        redis_client.set(job_key, json.dumps(job_data))

        # Add job to rate limiting sorted set
        redis_client.zadd(JOB_TIMESTAMPS_ZSET, {job_id: time.time()})

        # Add to the active/queued lookup hash
        redis_client.hset(lookup_key, cache_key, job_id)

        # Queue the job in Celery
        task_signature = celery_app.send_task(
            'edu_video_generator.src.api.service.generate_video_task', # Full path to task
            args=[job_id, request_data] # Pass original request data to the task
        )
        celery_task_id = task_signature.id
        logger.info(f"Queued new job {job_id} with Celery task ID: {celery_task_id}")

        # Update job data in Redis with the Celery task ID
        job_data["celery_task_id"] = celery_task_id
        redis_client.set(job_key, json.dumps(job_data)) # Update with task ID

        # Return the initial job data (without request_data for brevity)
        response_data = job_data.copy()
        del response_data["request_data"]
        return response_data, False # Signal that this is a new job

    except Exception as e:
        logger.error(f"Failed to create or queue new job {job_id}: {e}", exc_info=True)
        # Attempt cleanup in Redis if partially created
        if redis_client:
            redis_client.delete(f"{JOB_DATA_PREFIX}{job_id}")
            redis_client.zrem(JOB_TIMESTAMPS_ZSET, job_id)
            redis_client.hdel(lookup_key, cache_key) # Clean up lookup hash too
        raise HTTPException(status_code=500, detail="Failed to create and queue job.")


# --- Cancellation Function ---

def cancel_job(job_id: str) -> Dict[str, Any]:
    """Attempt to cancel a running or queued job."""
    if not redis_client:
        raise HTTPException(status_code=503, detail="Job tracking service (Redis) unavailable.")

    job_data = get_job_data(job_id)
    if not job_data:
        raise HTTPException(status_code=404, detail=f"Job with ID {job_id} not found.")

    status = job_data.get("status")
    celery_task_id = job_data.get("celery_task_id")

    if status == JobStatus.COMPLETED.value:
        raise HTTPException(status_code=409, detail=f"Job {job_id} is already completed.")
    if status == JobStatus.FAILED.value:
        raise HTTPException(status_code=409, detail=f"Job {job_id} has already failed.")
    if status == JobStatus.CANCELLED.value:
        raise HTTPException(status_code=409, detail=f"Job {job_id} is already cancelled.")

    if not celery_task_id:
         # Should not happen if job creation is atomic, but handle defensively
         logger.warning(f"Cannot cancel job {job_id}: Celery task ID not found in job data.")
         # Update status to failed as something is wrong
         update_job_status(job_id, JobStatus.FAILED, error="Internal error: Missing Celery task ID for cancellation.")
         raise HTTPException(status_code=500, detail="Internal error preventing cancellation.")

    logger.info(f"Attempting to cancel job {job_id} (Celery Task ID: {celery_task_id})")

    try:
        # Send revoke signal to Celery worker
        # terminate=True sends SIGTERM to the worker process hosting the task
        # signal='SIGTERM' is the default for terminate=True, but explicit for clarity
        celery_app.control.revoke(celery_task_id, terminate=True, signal='SIGTERM')
        logger.info(f"Revoke signal sent for Celery task {celery_task_id}")

        # Update job status in Redis immediately
        update_job_status(job_id, JobStatus.CANCELLED, progress=job_data.get("progress", 0.0)) # Keep last progress

        # Remove from active set if it was processing
        if status == JobStatus.PROCESSING.value:
            redis_client.srem(ACTIVE_JOBS_SET, job_id)
            logger.info(f"Removed cancelled job {job_id} from active set.")

        # Remove from the cache lookup hash
        cache_key = _generate_cache_key(job_data.get("request_data", {})) # Reconstruct cache key
        lookup_key = f"{JOB_CACHE_KEY_LOOKUP}{cache_key}"
        redis_client.hdel(lookup_key, cache_key)
        logger.info(f"Removed cancelled job {job_id} from lookup hash.")

        cancelled_job_data = get_job_data(job_id) # Get updated data
        response_data = cancelled_job_data.copy()
        if "request_data" in response_data: del response_data["request_data"]
        return response_data

    except Exception as e:
        logger.error(f"Error during cancellation process for job {job_id}: {e}", exc_info=True)
        # Don't necessarily mark as failed here, as revoke might eventually work,
        # but report the error during the cancellation attempt.
        raise HTTPException(status_code=500, detail=f"Error occurred while attempting to cancel job: {str(e)}")


# --- Celery Task Definition ---

@celery_app.task(bind=True, name='edu_video_generator.src.api.service.generate_video_task')
def generate_video_task(self, job_id: str, request_data: Dict[str, Any]) -> Dict[str, Any]:
    """Celery task to generate the educational video. Runs in a separate worker process."""
    if not redis_client:
        logger.error(f"Redis unavailable, cannot process job {job_id}")
        # Optionally update Celery state to FAILURE
        self.update_state(state='FAILURE', meta={'exc_type': 'RedisConnectionError', 'exc_message': 'Redis unavailable'})
        return {"job_id": job_id, "status": "failed", "error": "Redis unavailable"}

    logger.info(f"Worker started processing job {job_id}")
    output_path_str = None # Initialize

    try:
        # Add job to the set of actively processed jobs
        redis_client.sadd(ACTIVE_JOBS_SET, job_id)
        update_job_status(job_id, JobStatus.PROCESSING, progress=5.0)

        # Extract parameters
        topic = request_data["topic"]
        language = request_data.get("language", "en-US")
        voice_override = request_data.get("voice")
        skip_content_cache = request_data.get("skip_content_cache", False)
        use_animation_cache = not request_data.get("no_animation_cache", False)
        cleanup_after = request_data.get("cleanup", False)

        # Set up job-specific directories (ensure they exist)
        job_dir = JOB_DIR / job_id
        job_assets_dir = job_dir / "assets"
        job_audio_dir = job_assets_dir / "audio"
        job_diagram_dir = job_assets_dir / "diagrams"
        job_manim_dir = job_assets_dir / "manim_videos"
        job_temp_dir = job_assets_dir / "temp"

        for dir_path in [job_dir, job_assets_dir, job_audio_dir, job_diagram_dir, job_manim_dir, job_temp_dir]:
            ensure_dir_exists(str(dir_path))

        # Determine output filename
        topic_slug = "".join(c if c.isalnum() else "_" for c in topic).lower().strip('_')
        output_filename = f"{topic_slug}_{language}_{job_id}.mp4"
        output_path = job_dir / output_filename
        output_path_str = str(output_path) # Store as string for JSON

        # Update job data with the final output path early
        update_job_status(job_id, JobStatus.PROCESSING, output_path=output_path_str)

        # --- Main Processing Steps ---
        # 1. Generate Content
        logger.info(f"Job {job_id}: Generating content...")
        update_job_status(job_id, JobStatus.PROCESSING, progress=10.0)
        script_data = generate_educational_content(topic, language=language)
        script_save_path = job_dir / f"{topic_slug}_{language}_script.json"
        with open(script_save_path, "w", encoding='utf-8') as f:
            json.dump(script_data, f, indent=2, ensure_ascii=False)
        sections = script_data.get("sections", [])
        if not sections: raise ValueError("No sections found in generated script.")
        logger.info(f"Job {job_id}: Content generated ({len(sections)} sections).")

        # 2. Determine voice
        final_voice = voice_override or get_default_voice_for_language(language)
        logger.info(f"Job {job_id}: Using voice '{final_voice}' for language '{language}'.")

        # 3. Process sections (sequentially within the worker to avoid overload)
        update_job_status(job_id, JobStatus.PROCESSING, progress=20.0)
        processed_assets = [None] * len(sections)
        progress_per_section = 60.0 / len(sections) # 60% for section processing

        for i, section in enumerate(sections):
            logger.info(f"Job {job_id}: Processing section {i}...")
            # Note: process_section itself might use ThreadPoolExecutor internally,
            # but the critical part is that only ONE generate_video_task runs per worker process.
            # If process_section also causes overload, it needs internal sequential processing.
            result = process_section(
                section_index=i,
                section_data=section,
                use_animation_cache=use_animation_cache,
                language=language,
                voice=final_voice,
            )
            processed_assets[i] = result
            new_progress = 20.0 + (i + 1) * progress_per_section
            update_job_status(job_id, JobStatus.PROCESSING, progress=min(80.0, new_progress))
            logger.info(f"Job {job_id}: Finished processing section {i}.")

        # Filter valid sections
        valid_section_assets = [assets for assets in processed_assets if assets and assets.get('animation_path') and assets.get('audio_path')]
        if not valid_section_assets: raise ValueError("No sections processed successfully.")
        logger.info(f"Job {job_id}: {len(valid_section_assets)} sections processed successfully.")

        # 4. Compose Final Video
        logger.info(f"Job {job_id}: Composing final video...")
        update_job_status(job_id, JobStatus.PROCESSING, progress=90.0)
        composition_success = compose_final_video(valid_section_assets, output_path_str)
        if not composition_success: raise ValueError("Failed to compose final video.")
        logger.info(f"Job {job_id}: Final video composed.")

        # 5. Cleanup if requested
        if cleanup_after:
            logger.info(f"Job {job_id}: Cleaning up intermediate files...")
            for dir_path in [job_audio_dir, job_diagram_dir, job_manim_dir, job_temp_dir]:
                cleanup_dir(str(dir_path))
            logger.info(f"Job {job_id}: Cleanup complete.")

        # --- Completion ---
        update_job_status(job_id, JobStatus.COMPLETED, progress=100.0, output_path=output_path_str)
        logger.info(f"Job {job_id} completed successfully. Output: {output_path_str}")

        # --- Populate Cache on Success ---
        try:
            cache_key = _generate_cache_key(request_data)
            lookup_key = f"{JOB_CACHE_KEY_LOOKUP}{cache_key}"
            # Set cache key pointing to this completed job ID with TTL
            redis_client.setex(cache_key, CACHE_TTL_SECONDS, job_id)
            # Remove from the active/queued lookup hash now that it's completed and cached
            redis_client.hdel(lookup_key, cache_key)
            logger.info(f"Populated cache for key '{cache_key}' and removed from lookup hash for job ID '{job_id}' (TTL: {CACHE_TTL_SECONDS}s)")
        except Exception as cache_e:
            logger.error(f"Failed to populate cache/cleanup lookup hash for job {job_id}: {cache_e}", exc_info=True)

        return {"job_id": job_id, "status": "completed", "output_path": output_path_str}

    except Exception as e:
        # Check if the task was revoked (cancelled)
        # This requires inspecting Celery's internal state, which can be complex.
        # A simpler approach is to check the job status in Redis before marking as failed.
        current_job_data = get_job_data(job_id)
        if current_job_data and current_job_data.get("status") == JobStatus.CANCELLED.value:
            logger.info(f"Job {job_id} was cancelled during execution. Skipping failure update.")
            # Return status reflecting cancellation if possible, though Celery might override
            return {"job_id": job_id, "status": "cancelled", "error": "Job cancelled during execution."}
        else:
            error_message = f"Error processing job {job_id}: {str(e)}"
            logger.error(error_message, exc_info=True)
            update_job_status(job_id, JobStatus.FAILED, error=str(e))
            # Clean up lookup hash on failure
            try:
                cache_key = _generate_cache_key(request_data)
                lookup_key = f"{JOB_CACHE_KEY_LOOKUP}{cache_key}"
                redis_client.hdel(lookup_key, cache_key)
            except Exception as cleanup_e:
                 logger.error(f"Failed to cleanup lookup hash for failed job {job_id}: {cleanup_e}", exc_info=True)
            # Optionally raise exception to mark Celery task as failed
            # raise e
            return {"job_id": job_id, "status": "failed", "error": str(e)}
    finally:
        # Ensure job is removed from the active set regardless of outcome (unless cancelled, handled there)
        if redis_client:
            current_job_data = get_job_data(job_id) # Re-check status before removing
            if current_job_data and current_job_data.get("status") != JobStatus.CANCELLED.value:
                 if redis_client.srem(ACTIVE_JOBS_SET, job_id): # Returns 1 if removed, 0 if not present
                    logger.info(f"Removed job {job_id} from active set.")
            # Cleanup for lookup hash is handled on completion, failure, or cancellation now.
