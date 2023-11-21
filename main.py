import re
from io import BytesIO

from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from urllib.parse import urlencode
from bs4 import BeautifulSoup
import os.path
import requests
from pydantic import ValidationError
from deta import Deta
from starlette.responses import RedirectResponse

app = FastAPI()
templates = Jinja2Templates(directory="templates")

app.mount("/static", StaticFiles(directory="static"), name="static")

deta = Deta('b0hkSyUBEGwk_xAoLiGaj767xpxX87W2dvmJb9Ss5uZTG')
drive = deta.Drive('Temp')

@app.get("/robots.txt")
async def get_robots_txt():
    # Path to your robots.txt file
    robots_txt_path = "robots.txt"
    return FileResponse(robots_txt_path, media_type="text/plain")

@app.get("/sitemap.xml")
async def get_sitemap_xml():
    sitemap_patch = "sitemap.xml"
    return FileResponse(sitemap_patch, media_type="text/xml")



@app.get("/")
def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.post("/download/")
async def download_extension(
    url: str = Form(...),
    downloadAsZip: bool = Form(False),
    renameByExtensionName: bool = Form(False),
):
    try:
        # Check if the input URL is a valid Chrome Web Store link
        if not is_valid_chrome_webstore_link(url):
            raise HTTPException(status_code=400, detail="Invalid Chrome Web Store link")

        ext_id = os.path.basename(url)
        data = handle_files(url, downloadAsZip)
        file_extension = "zip" if downloadAsZip else "crx"
        if renameByExtensionName:
            ext_name = get_extension_name(ext_id)
            if ext_name is not None:
                file_name = f"{ext_name}.{file_extension}"
            else:
                file_name = f"{ext_id}.{file_extension}"
        else:
            file_name = f"{ext_id}.{file_extension}"

        # Upload the file to Deta Drive
        drive.put(file_name, data)

        return RedirectResponse(url=f"http://ced.nobss.online/files/{file_name}", status_code=303)

        # Return a FileResponse with appropriate headers to initiate download
        # return FileResponse(
        #     path='http://127.0.0.1:8000/files/',
        #     filename=file_name,
        #     media_type="application/octet-stream",
        # )

    except HTTPException as e:
        # Handle specific FastAPI HTTP exceptions
        print(str(e))
        return templates.TemplateResponse(
            "index.html", {"request": Request, "error_message": str(e)}
        )
    except ValidationError as e:
        # Handle validation errors
        print(str(e))
        return templates.TemplateResponse(
            "index.html", {"request": Request, "error_message": str(e)}
        )
    except OSError as e:
        # Handle OS errors
        print(str(e))
        return templates.TemplateResponse(
            "index.html", {"request": Request, "error_message": str(e)}
        )
    except Exception as e:
        # Handle all other exceptions
        print(str(e))
        return templates.TemplateResponse(
            "index.html", {"request": Request, "error_message": str(e)}
        )


def is_valid_chrome_webstore_link(url):
    # Use a regular expression to check if the input URL matches the Chrome Web Store format
    chrome_webstore_regex = re.compile(r'https://chromewebstore\.google\.com/.*')
    return bool(chrome_webstore_regex.match(url))


@app.get("/files/{name}")
async def get_file(name: str):
    try:
        data = drive.get(name)
        data_bytes = BytesIO(data.read())
        return StreamingResponse(data_bytes, media_type="application/octet-stream")
    except Exception as e:
        return {"error": "Error retrieving file"}


def get_extension_name(extension_id):
    # Send a GET request to the Chrome Web Store page of the extension
    response = requests.get(f"https://chrome.google.com/webstore/detail/{extension_id}")

    # Parse the response content with BeautifulSoup
    soup = BeautifulSoup(response.content, 'html.parser')

    # Find the extension name in the parsed HTML
    extension_name_tag = soup.find('h1', class_='e-f-w')

    if extension_name_tag is not None:
        return extension_name_tag.text
    else:
        return None


def extract_zip_data(crx):
    magic = crx[:4].decode()
    version = int.from_bytes(crx[4:8], byteorder='little')
    pubkey_or_header_len = int.from_bytes(crx[8:12], byteorder='little')
    sign_len = int.from_bytes(crx[12:16], byteorder='little')

    if magic != "Cr24":
        print(f"Unknown magic \"{magic}\", tool may fail.")

    if version == 2:
        zip_data = crx[16 + pubkey_or_header_len + sign_len:]
    elif version == 3:
        zip_data = crx[12 + pubkey_or_header_len:]
    else:
        raise ValueError(f"Unknown CRX version {version}, ZIP file extraction not supported (yet).")

    return zip_data

def handle_files(id_or_url: str, download_as_zip: bool):
    ext_id = os.path.basename(id_or_url)

    crx_base_url = 'https://clients2.google.com/service/update2/crx'
    crx_params = {
        'response': 'redirect',
        'prodversion': '91.0',
        'acceptformat': 'crx2,crx3',
        'x': 'id=' + ext_id + '&uc'
    }
    url = crx_base_url + '?' + urlencode(crx_params)

    response = requests.get(url)
    if response.status_code != 200:
        raise ValueError("Failed to download file.")

    crx_data = response.content

    if download_as_zip:
        zip_data = extract_zip_data(crx_data)
        return zip_data
    else:
        return crx_data
