#!/usr/bin/env python3
"""Cleanup script to purge expired job directories."""
import os
import sys
import shutil
from datetime import datetime, timedelta
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.config import get_settings

def cleanup_expired_jobs():
    """Delete job directories older than TTL."""
    settings = get_settings()
    jobs_dir = Path("./data/jobs")
    
    if not jobs_dir.exists():
        print("No jobs directory found")
        return
    
    ttl_minutes = settings.JOB_TTL_MINUTES
    cutoff_time = datetime.now() - timedelta(minutes=ttl_minutes)
    
    deleted_count = 0
    for job_dir in jobs_dir.iterdir():
        if not job_dir.is_dir():
            continue
        
        # Check directory modification time
        mtime = datetime.fromtimestamp(job_dir.stat().st_mtime)
        if mtime < cutoff_time:
            print(f"Deleting expired job: {job_dir.name}")
            shutil.rmtree(job_dir)
            deleted_count += 1
    
    print(f"Cleanup complete. Deleted {deleted_count} expired jobs.")

if __name__ == "__main__":
    cleanup_expired_jobs()
