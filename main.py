import os
import uuid
import logging
from typing import Optional
from datetime import datetime

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import cv_parser

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = FastAPI(title="CV Parser NLP Service", version="1.0.0")


class ParseCVRequest(BaseModel):
    url: str
    jobSeekerId: str


class ParseCVResponse(BaseModel):
    jobSeekerId: str
    parsedAt: str
    data: dict


@app.get("/")
def root():
    return {"message": "CV Parser NLP Service", "version": "1.0.0"}


@app.get("/health")
def health_check():
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}


def download_cv_from_url(url: str) -> bytes:
    """Download CV file from presigned URL"""
    try:
        with httpx.Client(timeout=60.0) as client:
            response = client.get(url)
            response.raise_for_status()
            return response.content
    except httpx.HTTPError as e:
        logger.error(f"Failed to download CV from URL: {e}")
        raise HTTPException(status_code=400, detail=f"Failed to download CV: {str(e)}")
    except Exception as e:
        logger.error(f"Error downloading CV: {e}")
        raise HTTPException(status_code=500, detail=f"Error downloading CV: {str(e)}")


def save_temp_file(content: bytes, job_seeker_id: str) -> str:
    """Save downloaded content to a temporary file"""
    temp_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "temp")
    os.makedirs(temp_dir, exist_ok=True)
    
    file_ext = ".pdf"
    if b"PK" in content[:4]:
        file_ext = ".docx"
    
    file_path = os.path.join(temp_dir, f"{job_seeker_id}_{uuid.uuid4()}{file_ext}")
    
    with open(file_path, "wb") as f:
        f.write(content)
    
    return file_path


def cleanup_temp_file(file_path: str):
    """Remove temporary file after processing"""
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
            logger.info(f"Cleaned up temporary file: {file_path}")
    except Exception as e:
        logger.warning(f"Failed to cleanup temp file: {e}")


@app.post("/parse-cv", response_model=ParseCVResponse)
def parse_cv(request: ParseCVRequest):
    """
    Parse CV from a presigned URL.
    
    - **url**: Presigned S3/MinIO URL for the CV file
    - **jobSeekerId**: UUID of the job seeker to associate with
    """
    logger.info(f"Received parse request for jobSeekerId: {request.jobSeekerId}")
    logger.info(f"CV URL: {request.url[:100]}...")
    temp_file_path = None
    
    try:
        cv_content = download_cv_from_url(request.url)
        logger.info(f"Downloaded CV ({len(cv_content)} bytes)")
        
        temp_file_path = save_temp_file(cv_content, request.jobSeekerId)
        
        result = cv_parser.parse_cv_file(temp_file_path)
        
        if result is None:
            raise HTTPException(status_code=422, detail="Failed to parse CV file")
        
        logger.info(f"Successfully parsed CV for jobSeekerId: {request.jobSeekerId}")
        
        return ParseCVResponse(
            jobSeekerId=request.jobSeekerId,
            parsedAt=datetime.now().isoformat(),
            data=result
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing CV: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")
    finally:
        if temp_file_path and os.path.exists(temp_file_path):
            try:
                os.remove(temp_file_path)
                logger.info(f"Cleaned up temp file: {temp_file_path}")
            except Exception as e:
                logger.warning(f"Failed to cleanup temp file: {e}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
