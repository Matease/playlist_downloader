import os
import yt_dlp
import requests
import threading
import sys
import argparse
from dotenv import load_dotenv
from googleapiclient.discovery import build
from rapidfuzz import fuzz
from mutagen.mp4 import MP4

load_dotenv()

API_KEY = os.getenv("YOUTUBE_API_KEY")
YOUTUBE_API_SERVICE_NAME = "youtube"
YOUTUBE_API_VERSION = "v3"


# --------------------------
# Utils
# --------------------------
def input_with_timeout(prompt):
    result = [None]
    result[0] = input(prompt).strip().lower()
    return result[0] in ["y", "yes"]


# --------------------------
# Deezer API
# --------------------------
def search_deezer(song_query):
    params = {"q": song_query, "limit": 1}
    response = requests.get("https://api.deezer.com/search", params=params)
    data = response.json()
    if "data" in data and len(data["data"]) > 0:
        track = data["data"][0]
        artist = track["artist"]["name"].strip()
        title = track["title"].strip()
        album = track["album"]["title"].strip()
        print(f"🎵 Deezer: Artist: {artist} | Title: {title} | Album: {album}")
        return artist, title, album
    print("❌ Rien trouvé sur Deezer")
    return "", "", ""

def is_similar_title(original_title, deezer_title, threshold=80):
    similarity = fuzz.token_set_ratio(original_title.lower(), deezer_title.lower())
    return similarity >= threshold, similarity

# --------------------------
# YouTube API
# --------------------------
def search_youtube_link(song_title):
    youtube = build(YOUTUBE_API_SERVICE_NAME, YOUTUBE_API_VERSION, developerKey=API_KEY)
    request = youtube.search().list(
        q=song_title,
        part="snippet",
        maxResults=1,
        type="video"
    )
    response = request.execute()
    if "items" in response and len(response["items"]) > 0:
        video_id = response["items"][0]["id"]["videoId"]
        video_url = f"https://www.youtube.com/watch?v={video_id}"
        print(f"📺 YouTube: {video_url}")
        return video_url
    print("❌ Pas trouvé sur YouTube")
    return None

def download_audio_m4a(youtube_url, output_dir="results"):
    os.makedirs(output_dir, exist_ok=True)
    ydl_opts = {
        'format': 'bestaudio[ext=m4a]',
        'outtmpl': f'{output_dir}/%(title)s.%(ext)s',
        'quiet': True
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([youtube_url])

# --------------------------
# Metadata
# --------------------------
def set_proposed_metadata(file_path, artist=None, title=None, album=None, label=None):
    print("\n--- Validation métadonnées ---")
    print(f"Fichier : {file_path}")
    print("\n--- Métadonnées proposées ---")
    if artist:
        print(f"Artiste : {artist}")
    if title:
        print(f"Titre   : {title}")
    if album:
        print(f"Album   : {album}")
    if label:
        print(f"Label   : {label}")
    print("-----------------------------")

    if input_with_timeout("Voulez-vous appliquer ces métadonnées ? (y/n): "):
        try:
            save_metadata(file_path, title=title, artist=artist, album=album, label=label)
            print("✅ Métadonnées appliquées avec succès.")
        except Exception as e:
            print(f"❌ Erreur lors de l'application des métadonnées : {e}")
    else:
        print("❌ Métadonnées proposées ignorées.")
        if input_with_timeout("Voulez-vous ajouter les métadonnées à la main ? (y/n): "):
            manual_metadata_input(file_path)
        else: 
            print("❌ Métadonnées ignorées.")

def manual_metadata_input(file_path):
    """
    Demande à l'utilisateur de saisir manuellement artiste, titre, album,
    puis applique les métadonnées dans le fichier .m4a
    """
    print("\n✏️ Saisie manuelle des métadonnées")
    artist = input("Artiste : ").strip()
    title = input("Titre : ").strip()
    album = input("Album : ").strip()
    label = input("Label : ").strip()

    try:
        save_metadata(file_path=file_path, title=title, artist=artist, album=album, label=label)
        print("✅ Métadonnées appliquées avec succès (saisie manuelle).")
    except Exception as e:
        print(f"❌ Erreur lors de l'application des métadonnées : {e}")


def save_metadata(file_path, title=None, artist=None, album=None, label=None):
    audio = MP4(file_path)
    if title:
        audio["\xa9nam"] = title
    if artist:
        audio["\xa9ART"] = artist
    if album:
        audio["\xa9alb"] = album
    if label:
        audio["\xa9pub"] = label
    audio.save()


# --------------------------
# Workflow complet batch
# --------------------------
def batch_process(input_file="songs.txt", results_dir="results"):
    os.makedirs(results_dir, exist_ok=True)
    with open(input_file, 'r', encoding='utf-8') as f:
        song_titles = [line.strip() for line in f.readlines() if line.strip()]

    for original_title in song_titles:
        print(f"\n🔎 Processing: {original_title}")

        artist, title, album = search_deezer(original_title)
        if not title:
            continue

        valid, score = is_similar_title(original_title, title)
        if not valid:
            print(f"⚠️ Titre Deezer pas sûr ({score}%), confirmation demandée")
            if not input_with_timeout("Voulez-vous continuer avec ces métadonnées ? (y/n) [timeout 5s]: "):
                continue

        link = search_youtube_link(f"{artist} {title}")
        if not link:
            continue

        download_audio_m4a(link, output_dir=results_dir)
        file_path = os.path.join(results_dir, f"{title}.m4a")

        if os.path.exists(file_path):
            set_proposed_metadata(file_path, artist=artist, title=title, album=album)

def filename_to_title(filepath, remove_extension=True):
    filename = os.path.basename(filepath)
    if remove_extension:
        filename = os.path.splitext(filename)[0]
    return filename

def process_metadata_folder(filepath):
    if not os.path.exists(filepath):
        print(f"❌ Dossier {filepath} introuvable")
        return

    for file in os.listdir(filepath):
        if not file.lower().endswith(".m4a"):
            continue

        file_path = os.path.join(filepath, file)
        raw_title = filename_to_title(file)

        print(f"\n🔎 Traitement de : {raw_title}")
        artist, title, album = search_deezer(raw_title)
        valid, score = is_similar_title(raw_title, title)
        if not title:
            print("❌ Aucune correspondance Deezer trouvée.")
            if input_with_timeout("Voulez-vous ajouter les métadonnées à la main ? (y/n): "):
                manual_metadata_input(file_path)
            continue

        valid, score = is_similar_title(raw_title, title)
        if valid:
            print(f"✅ Correspondance Deezer ({score}%): {artist} - {title} [{album}]")
            set_proposed_metadata(file_path, artist, title, album)
        else:
            print(f"⚠️ Correspondance incertaine ({score}%) : {artist} - {title} [{album}]")
            set_proposed_metadata(file_path, artist, title, album)

# --------------------------
# CLI avec argparse
# --------------------------
def main():
    parser = argparse.ArgumentParser(description="Outil musique (Deezer + YouTube + metadata)")
    parser.add_argument("--deezer", help="Rechercher des infos sur Deezer pour un titre")
    parser.add_argument("--youtube", help="Télécharger une vidéo YouTube (titre ou lien)")
    parser.add_argument("--metadata", help="Appliquer des métadonnées à un fichier")
    parser.add_argument("--metadatafolder", help="Appliquer des métadonnées aux fichiers d'un dossier")
    parser.add_argument("--sbatch", action="store_true", help="Traiter automatiquement songs.txt")
    parser.add_argument("--ybatch", help="Télécharge les liens youtube dans un fichier .txt")
    args = parser.parse_args()

    if len(sys.argv) == 1:
        parser.print_help(sys.stderr)
        sys.exit(1)

    if not args.sbatch:
        if args.deezer and not args.metadata:
            search_deezer(args.deezer)

        if args.youtube:
            query = args.youtube
            if "youtube.com" not in query:
                query = search_youtube_link(query)
            if query:
                download_audio_m4a(query)

        if args.metadata and not args.deezer:
            title_to_search = filename_to_title(args.metadata)
            artist, title, album = search_deezer(title_to_search)
            if artist and title:
                set_proposed_metadata(args.metadata, artist=artist, title=title, album=album)

        if args.metadatafolder and not args.deezer:
            process_metadata_folder(args.metadatafolder)
 
    if args.sbatch:
        batch_process()

    if args.ybatch:
        # TODO : télécharger uniquement les liens youtubes
        pass

if __name__ == "__main__":
    main()

