from __future__ import print_function

import os.path
import io
import json
import numpy as np
import datetime

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload, MediaIoBaseUpload, MediaIoBaseDownload

# If modifying these scopes, delete the file token.json.
SCOPES = ['https://www.googleapis.com/auth/drive']


def identification():
    creds = None
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except:
                os.remove("token.json")
                return identification()
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                'client_secrets.json', SCOPES)
            creds = flow.run_local_server(port=0)
        # Save the credentials for the next run
        with open('token.json', 'w') as token:
            token.write(creds.to_json())
    drive = build('drive', 'v3', credentials=creds)
    return drive

def get_owner_from_file_id(drive, file_id):
    file = drive.files().get(fileId=file_id, fields="owners").execute()
    owners = file.get('owners', [])[0]["displayName"]
    return owners

def get_file_infos_from_id(drive, id, utc_offset=0):
    file = drive.files().get(
        fileId=id,
        fields="modifiedTime, name, lastModifyingUser, mimeType, size"
    ).execute()

    # Time format
    modified_time_utc = file.get("modifiedTime")
    modified_time = datetime.datetime.strptime(modified_time_utc, '%Y-%m-%dT%H:%M:%S.%fZ')
    modified_time_local = modified_time + datetime.timedelta(hours=utc_offset)
    modified_time_formatted = modified_time_local.strftime('%H:%M:%S')
    modified_day = modified_time_local.strftime('%Y-%m-%d')
    modified_time_sec = int(modified_time_local.timestamp())

    file_info = {
        "modifiedTime": modified_time_formatted,
        "modifiedDay": modified_day,
        "modifiedTimeSec": modified_time_sec,
        "name": file.get("name"),
        "lastModifyingUser": file.get("lastModifyingUser", {}).get("displayName"),
        "mimeType": file.get("mimeType"),
        "size": file.get("size")
    }

    return file_info


def list_from_id(drive, id):
    results = drive.files().list(
        q=f"'{id}' in parents and trashed = false",
        fields="nextPageToken, files(id, name)").execute()
    items = results.get('files', [])
    title_list = [item["name"] for item in items]
    id_list = [item["id"] for item in items]
    return title_list, id_list

def get_id_from_path(drive, path):
    folders = path.split("/")  # Split into individual folder names
    id = "root"         # First folder has 'root' as ID
    for i, folder_title in enumerate(folders):
        if folder_title:
            results = drive.files().list(
                q=f"'{id}' in parents and name = '{folder_title}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false",
                fields="nextPageToken, files(id)").execute()
            items = results.get('files', [])
            if items:
                id = items[0]['id']
            else:
                return None
    return id

def get_id_from_folder_id(drive, folder_id, fname):
    results = drive.files().list(
        q=f"'{folder_id}' in parents and name = '{fname}' and trashed = false",
        fields="nextPageToken, files(id)").execute()
    items = results.get('files', [])
    if items:
        return items[0]['id']
    else:
        return None

def load_json_from_id(drive, id):
    request = drive.files().get_media(fileId=id).execute()
    content = io.BytesIO(request)
    return json.load(content)

def download_file(drive, id, local_path):
    request = drive.files().get_media(fileId=id)
    fh = io.FileIO(local_path, mode='wb')
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while not done:
        status, done = downloader.next_chunk()

def save_dic_to_drive(drive, data, fname, folder_id):
    # Recherche fichier existant
    file_exists = False
    results = drive.files().list(
        q=f"name='{fname}' and '{folder_id}' in parents",
        fields="files(id)"
    ).execute()

    # ID du fichier existant
    if 'files' in results and len(results['files']) > 0:
        file_id = results['files'][0]['id']
        file_exists = True
    else:
        file_id = None

    # Contenu à écrire
    content = io.BytesIO(json.dumps(to_json_compatible(data)).encode())
    media = MediaIoBaseUpload(content, mimetype='application/json')

    # Crée ou met à jour le fichier
    if file_exists:  # Met à jour le contenu du fichier existant
        file = drive.files().update(
            fileId=file_id,
            media_body=media,
            fields='id'
        ).execute()
        print("File updated successfully. ID:", file.get('id'))
    else:  # Crée un nouveau fichier
        file_metadata = {
            'name': fname,
            'parents': [folder_id]
        }
        file = drive.files().create(
            body=file_metadata,
            media_body=media,
            fields='id'
        ).execute()
        print("File uploaded successfully. ID:", file.get('id'))

    return file.get('id')

def to_json_compatible(data):
    if isinstance(data, np.ndarray):
        return data.tolist()
    elif isinstance(data, dict):
        return {k: to_json_compatible(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [to_json_compatible(v) for v in data]
    # elif np.isnan(data): return "NaN"
    else:
        return data

def from_json_compatible(data):
    if isinstance(data, list):
        return np.array(data)
    elif isinstance(data, dict):
        return {k: from_json_compatible(v) for k, v in data.items()}
    else:
        return data

def upload_fig(drive, folder_id, fig, fname):
    fullname = f"{fname}.pdf"
    tmp_local = f"/tmp/{fullname}"
    fig.savefig(tmp_local)
    fig.savefig(fname)  # Save figure locally

    file_metadata = {
        'name': fname,
        'parents': [folder_id]
    }
    media = MediaFileUpload(tmp_local, mimetype='application/pdf')
    file = drive.files().create(body=file_metadata, media_body=media, fields='id').execute()

    print("Figure uploaded successfully. ID:", file.get('id'))

def main():
    drive = identification()
    # folder = drive.files().get(fileId='root', fields='id').execute()
    folder_id = get_id_from_path(drive, "Stage_Bilbao_Neuroblastoma/G_Collab/backup/__Results__")
    file_id = get_id_from_folder_id(drive, folder_id, "result.json")
    print(file_id)
    data = load_json_from_id(drive, file_id)
    print(data)

if __name__ == '__main__':
    main()
