import datetime
from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse
from pydantic import BaseModel
import requests
import json
import os

app = FastAPI()

JSON_PATH = "users.json"

client_id = os.getenv("SPOTIFY_API_CLIENT_ID")
client_secret = os.getenv("SPOTIFY_API_CLIENT_SECRET")
redirect_uri = "http://localhost:8000/callback"

access_token_data = {
    "access_token": None,
    "expires_at": None,
    "refresh_token": None
}

def get_auth_url():
    scope = "user-top-read"
    return (
        f"https://accounts.spotify.com/authorize?client_id={client_id}&response_type=code"
        f"&redirect_uri={redirect_uri}&scope={scope}"
    )

class User(BaseModel):
    name: str
    email: str
    password: str

@app.post('/api/save_user')
def save_user(user: User):
    try:
        if os.path.exists(JSON_PATH):
            with open(JSON_PATH, 'r') as file:
                users = json.load(file)
        else:
            users = []
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail="Error reading user data")

    if any(u['email'] == user.email for u in users):
        raise HTTPException(status_code=400, detail="Email already exists")
    
    max_id = max([u['id'] for u in users], default=0)

    new_user = {
        "id": max_id + 1,
        "name": user.name,
        "email": user.email,
        "password": user.password,
        "favorite_artists": [],
        "favorite_tracks": [],
        "favorite_albums": []
    }
    
    users.append(new_user)
    try:
        with open(JSON_PATH, 'w') as file:
            json.dump(users, file, indent=4)
    except IOError:
        raise HTTPException(status_code=500, detail="Error saving user data")
        
    return {"message": "User created successfully", "user": new_user}

@app.get('/api/get_user/{id}')
def get_user(id: int):
    try:
        with open(JSON_PATH, 'r') as file:
            users = json.load(file)
    except FileNotFoundError:
        users = []

    for u in users:
        if u['id'] == id:
            return {"user": u}
    raise HTTPException(status_code=404, detail= "User not found")

@app.get('/api/get_all_users')
def get_all_users():
    try:
        with open(JSON_PATH, 'r') as file:
            users = json.load(file)
    except FileNotFoundError:
        users = []
    return {"usuarios": users}

@app.put('/api/update_user/{id}')
def update_user(id: int, user: User):
    try:
        with open(JSON_PATH, 'r') as file:
            users = json.load(file)
    except FileNotFoundError:
        users = []

    for u in users:
        if u['id'] == id:
            u['email'] = user.email
            u['name'] = user.name
            u['password'] = user.password

            with open(JSON_PATH, 'w') as file:
                json.dump(users, file, indent=4)
            return {"message": "User updated successfully", "user": u}
    raise HTTPException(status_code=404, detail= "User not found")

@app.delete('/api/delete_user/{id}')
def delete_user(id: int):
    try:
        with open(JSON_PATH, 'r') as file:
            users = json.load(file)
    except FileNotFoundError:
        users = []

    for u in users:
        if u['id'] == id:
            users.remove(u)
            with open(JSON_PATH, 'w') as file:
                json.dump(users, file, indent=4)
            return {"message": "User deleted successfully"}
    raise HTTPException(status_code=404, detail= "User not found")

@app.get('/')
def login():
    return RedirectResponse(url=get_auth_url())

@app.get('/callback')
def callback(request: Request):
    code = request.query_params.get("code")
    if not code:
        raise HTTPException(status_code=400, detail="Authorization code not provided")

    try:
        endpoint = "https://accounts.spotify.com/api/token"
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
        }
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": client_id,
            "client_secret": client_secret,
        }

        response = requests.post(endpoint, headers=headers, data=data)
        response.raise_for_status()
        token_info = response.json()

        access_token_data["access_token"] = token_info["access_token"]
        access_token_data["refresh_token"] = token_info["refresh_token"]
        access_token_data["expires_at"] = (
            datetime.datetime.now(datetime.timezone.utc) +
            datetime.timedelta(seconds=token_info["expires_in"])
        )

        return {"message": "Tokens saved successfully"}
    except requests.RequestException as e:
        raise HTTPException(status_code=500, detail=f"Error exchanging code for token: {e}")

def get_valid_access_token():
    if access_token_data["access_token"] is None:
        raise HTTPException(status_code=401, detail="Access token not available. Please authenticate first. Go to http://localhost:8000/")

    if datetime.datetime.now(datetime.timezone.utc) >= access_token_data["expires_at"]:

        endpoint = "https://accounts.spotify.com/api/token"
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
        }
        data = {
            "grant_type": "refresh_token",
            "refresh_token": access_token_data["refresh_token"],
            "client_id": client_id,
            "client_secret": client_secret,
        }

        response = requests.post(endpoint, headers=headers, data=data)
        response.raise_for_status()
        token_info = response.json()

        access_token_data["access_token"] = token_info["access_token"]
        access_token_data["expires_at"] = (
            datetime.datetime.now(datetime.timezone.utc) +
            datetime.timedelta(seconds=token_info["expires_in"])
        )

    return access_token_data["access_token"]


@app.get('/api/get_favorite_artists')
def get_favorite_artists():
    try:
        access_token = get_valid_access_token()
        endpoint = "https://api.spotify.com/v1/me/top/artists"
        headers = {"Authorization": f"Bearer {access_token}"}
        response = requests.get(endpoint, headers=headers)
        response.raise_for_status()
        artists = response.json()["items"]
        formatted_artists = [
            f"{index + 1}. {artist['name']}"
            for index, artist in enumerate(artists)
        ]
        return PlainTextResponse("\n".join(formatted_artists))
    except requests.RequestException as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving favorite artists: {e}")
    
@app.get('/api/get_favorite_tracks')
def get_favorite_tracks():
    try:
        access_token = get_valid_access_token()
        endpoint = "https://api.spotify.com/v1/me/top/tracks"
        headers = {"Authorization": f"Bearer {access_token}"}
        response = requests.get(endpoint, headers=headers)
        response.raise_for_status()
        tracks = response.json()["items"]
        formatted_tracks = [
            f"{index + 1}. {track['name']} - {', '.join(artist['name'] for artist in track['artists'])}"
            for index, track in enumerate(tracks)
        ]
        return PlainTextResponse("\n".join(formatted_tracks))
    except requests.RequestException as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving favorite artists: {e}")
    
@app.get('/api/{user_id}/save_favorite_artist/{name}')
def save_favourite_artist(user_id, name):
    try:

        access_token = get_valid_access_token()
        endpoint = "https://api.spotify.com/v1/search"
        headers = {"Authorization": f"Bearer {access_token}"}

        query = f"?q={name}&type=artist&limit=1"
        url = endpoint + query 
        response = requests.get(url, headers= headers)
        response.raise_for_status()

        if response.status_code == 200:
            response_json =  response.json()
        
        if not response_json['artists']['items'][0]['name']:
            return {"message": "Artist not found"}
        else:
            name_artist = response_json['artists']['items'][0]['name']

        try:
            with open(JSON_PATH, 'r') as file:
                users = json.load(file)
        except FileNotFoundError:
            users = []

        user_found = False
        
        print(name_artist)

        for u in users:
            if u['id'] == int(user_id):
                user_found = True
                if name_artist in u['favorite_artists']:
                    return {"message": "Artist already saved"}
                else:
                    u['favorite_artists'].append(name_artist)

                with open(JSON_PATH, 'w') as file:
                    json.dump(users, file, indent=4)
                return {"message": "Artist saved successfully", "favorite_artists": u['favorite_artists']}
            
            if not user_found:
                return {"message": "User not found"}
    except requests.RequestException as e:
        return{"error": str(e)}


@app.get('/api/{user_id}/save_favorite_track/{name}')
def save_favorite_track(user_id: int, name: str):
    try:
        access_token = get_valid_access_token()
        endpoint = "https://api.spotify.com/v1/search"
        headers = {"Authorization": f"Bearer {access_token}"}

        query = f"?q={name}&type=track&limit=1"
        url = endpoint + query 
        response = requests.get(url, headers=headers)
        response.raise_for_status()

        response_json = response.json()

        if not response_json['tracks']['items']:
            return {"message": "Track not found"}

        track_item = response_json['tracks']['items'][0]
        name_track = track_item['name']
        artists = ", ".join(artist['name'] for artist in track_item['artists'])
        track_with_artists = f"{name_track} - {artists}"

        try:
            with open(JSON_PATH, 'r') as file:
                users = json.load(file)
        except FileNotFoundError:
            users = []

        user_found = False

        for u in users:
            if u['id'] == user_id:
                user_found = True
                if track_with_artists in u['favorite_tracks']:
                    return {"message": "Track already saved"}
                else:
                    u['favorite_tracks'].append(track_with_artists)

                with open(JSON_PATH, 'w') as file:
                    json.dump(users, file, indent=4)
                return {"message": "Track saved successfully", "favorite_tracks": u['favorite_tracks']}

        if not user_found:
            return {"message": "User not found"}

    except requests.RequestException as e:
        return {"error": str(e)}
    except Exception as e:
        return {"error": f"Unexpected error: {str(e)}"}
    
@app.get('/api/{user_id}/save_favorite_album/{name}')
def save_favorite_album(user_id: int, name: str):
    try:
        access_token = get_valid_access_token()
        endpoint = "https://api.spotify.com/v1/search"
        headers = {"Authorization": f"Bearer {access_token}"}

        query = f"?q={name}&type=album&limit=1"
        url = endpoint + query 
        response = requests.get(url, headers=headers)
        response.raise_for_status()

        response_json = response.json()

        if not response_json['albums']['items']:
            return {"message": "Album not found"}

        album_item = response_json['albums']['items'][0]
        name_album = album_item['name']
        artists = ", ".join(artist['name'] for artist in album_item['artists'])
        album_with_artists = f"{name_album} - {artists}"

        try:
            with open(JSON_PATH, 'r') as file:
                users = json.load(file)
        except FileNotFoundError:
            users = []

        user_found = False

        for u in users:
            if u['id'] == user_id:
                user_found = True
                if album_with_artists in u['favorite_albums']:
                    return {"message": "Album already saved"}
                else:
                    u['favorite_albums'].append(album_with_artists)

                with open(JSON_PATH, 'w') as file:
                    json.dump(users, file, indent=4)
                return {"message": "Album saved successfully", "favorite_albums": u['favorite_albums']}

        if not user_found:
            return {"message": "User not found"}

    except requests.RequestException as e:
        return {"error": str(e)}
    except Exception as e:
        return {"error": f"Unexpected error: {str(e)}"}