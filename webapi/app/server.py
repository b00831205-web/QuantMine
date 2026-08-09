import os
import uvicorn

def main()-> None:
    uvicorn.run(
        'app.main:app',
        host = os.environ.get('QUANTMINE_WEB_HOST', '0.0.0.0'),
        port = int(os.environ.get('QUANTMINE_WEB_PORT', '8000'))
    )