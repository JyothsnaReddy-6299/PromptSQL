from fastapi import APIRouter
from fastapi import UploadFile
from fastapi import File

import os
import shutil


from app.services.analysis import analyze_dataset



router = APIRouter()



UPLOAD_DIR = "uploads"


os.makedirs(UPLOAD_DIR, exist_ok=True)



@router.post("/upload")
async def upload_file(
        file: UploadFile = File(...)
):


    filepath = os.path.join(
        UPLOAD_DIR,
        file.filename
    )


    with open(filepath, "wb") as buffer:

        shutil.copyfileobj(
            file.file,
            buffer
        )



    stats = analyze_dataset(filepath)



    return {


        "filename": file.filename,


        **stats

    }