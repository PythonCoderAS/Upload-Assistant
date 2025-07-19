# -*- coding: utf-8 -*-
import os
import re
import requests
from src.exceptions import UploadException
from src.console import console
from .COMMON import COMMON
from torf import Torrent
from aiohttp import ClientSession


class NYAA(COMMON):
    def __init__(self, config):
        super().__init__(config)
        self.tracker = 'NYAA'
        self.source_flag = 'Nyaa.si'
        self.base_url = "https://nyaa.si"
        self.torrent_url = f"{self.base_url}/view/"
        self.announce_url = "http://nyaa.tracker.wf:7777/announce"
        self.banned_groups = [""]

        self.session_cookie = self.config['TRACKERS'][self.tracker].get('session_cookie')
        self.session = ClientSession(headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36'}, cookies={'session': self.session_cookie} if self.session_cookie else None)
        self.signature = "----\n[Created by Audionut's Upload Assistant](https://github.com/Audionut/Upload-Assistant)"

    async def edit_torrent(self, meta, tracker, source_flag, torrent_filename="BASE"):
        if os.path.exists(f"{meta['base_dir']}/tmp/{meta['uuid']}/{torrent_filename}.torrent"):
            new_torrent = Torrent.read(f"{meta['base_dir']}/tmp/{meta['uuid']}/{torrent_filename}.torrent")
            for each in list(new_torrent.metainfo):
                if each not in ('announce', 'comment', 'creation date', 'created by', 'encoding', 'info'):
                    new_torrent.metainfo.pop(each, None)
            new_torrent.metainfo['announce'] = self.announce_url
            if 'created by' in new_torrent.metainfo and isinstance(new_torrent.metainfo['created by'], str):
                created_by = new_torrent.metainfo['created by']
                if "mkbrr" in created_by.lower():
                    new_torrent.metainfo['created by'] = f"{created_by} using Audionut's Upload Assistant"

            new_torrent.metainfo['comment'] = ''
            new_torrent.private = False

            Torrent.copy(new_torrent).write(f"{meta['base_dir']}/tmp/{meta['uuid']}/[{tracker}].torrent", overwrite=True)

    async def generate_description(self, meta):
        nyaa_desc = f"{meta['base_dir']}/tmp/{meta['uuid']}/[{self.tracker}]DESCRIPTION.txt"

        desc_parts = []

        # Screenshots
        images = meta.get('image_list', [])
        if images:
            screenshots_block = "## Screenshots\n\n"
            for image_number, image in enumerate(images, start=1):
                img_url = image['img_url']
                web_url = image['web_url']
                screenshots_block += f"[![Screenshot ]({img_url})]({web_url}) "
            desc_parts.append(screenshots_block)

        # BDInfo
        tech_info = ""
        if meta.get('is_disc') == 'BDMV':
            bd_summary_file = f"{meta['base_dir']}/tmp/{meta['uuid']}/BD_SUMMARY_00.txt"
            if os.path.exists(bd_summary_file):
                with open(bd_summary_file, 'r', encoding='utf-8') as f:
                    tech_info = f.read()

        if tech_info:
            desc_parts.append(f"## BD Info\n```\n{tech_info}\n```\n")

        mediainfo_file = f"{meta['base_dir']}/tmp/{meta['uuid']}/MEDIAINFO.txt"
        if os.path.exists(mediainfo_file):
            with open(mediainfo_file, 'r', encoding='utf-8') as f:
                mediainfo_content = f.read()
            desc_parts.append(f"## MediaInfo\n```\n{mediainfo_content}\n```\n")

        if self.signature:
            desc_parts.append(self.signature)

        final_description = "\n".join(filter(None, desc_parts))

        with open(nyaa_desc, 'w', encoding='utf-8') as f:
            f.write(final_description)

    async def get_category_id(self, meta):
        # resolution = meta.get('resolution')
        # category = meta.get('category')
        # is_disc = meta.get('is_disc')
        # tv_pack = meta.get('tv_pack')
        # sd = meta.get('sd')

        mediainfo = meta.get("mediainfo", {})
        print(meta)
        raise Exception

        if is_disc == 'BDMV':
            if resolution == '1080p' and category == 'MOVIE':
                return 3
            elif resolution == '2160p' and category == 'MOVIE':
                return 38
            elif category == 'TV':
                return 14
        if is_disc == 'DVD':
            if category == 'MOVIE':
                return 1
            elif category == 'TV':
                return 11
        if category == 'TV' and tv_pack == 1:
            return 12
        if sd == 1:
            if category == 'MOVIE':
                return 2
            elif category == 'TV':
                return 10
        category_map = {
            'MOVIE': {'2160p': 4, '1080p': 6, '1080i': 6, '720p': 5},
            'TV': {'2160p': 13, '1080p': 9, '1080i': 9, '720p': 8},
        }
        if category in category_map:
            return category_map[category].get(resolution)
        return None

    async def login(self):
        if self.session_cookie is None:
            console.print(f"[bold red]Login failed on {self.tracker}: No session cookie provided.[/bold red]")
            return False
        async with self.session.get(f"{self.base_url}/profile", allow_redirects=False) as resp:
            if resp.status != 200:
                console.print(f"[bold red]Login failed on {self.tracker}: Redirected to homepage (indicates session cookie is invalid).[/bold red]")
                return False
            else:
                return True

    async def search_existing(self, meta, disctype):
        if self.session_cookie is None:
            console.print(f"[bold red]Login failed on {self.tracker}: No session cookie provided.[/bold red]")
            return []

        search_url = f"{self.api_base_url}/torrents"
        search_params = {'searchText': imdb_id}

        try:
            response = self.session.get(search_url, params=search_params, cookies=self.auth_cookies, timeout=15)
            response.raise_for_status()

            if response.text and response.text != '[]':
                results = response.json()
                if results and isinstance(results, list):
                    return results

        except Exception as e:
            console.print(f"[bold red]Error searching for IMDb ID '{imdb_id}' on {self.tracker}: {e}[/bold red]")

        return []

    async def upload(self, meta, disctype):
        await self.edit_torrent(meta, self.tracker, self.source_flag)

        cat_id = await self.get_category_id(meta)

        await self.generate_description(meta)

        description_path = f"{meta['base_dir']}/tmp/{meta['uuid']}/[{self.tracker}]DESCRIPTION.txt"
        with open(description_path, 'r', encoding='utf-8') as f:
            description = f.read()

        imdb = meta.get('imdb_info', {}).get('imdbID', '')

        mi_path = f"{meta['base_dir']}/tmp/{meta['uuid']}/{'BD_SUMMARY_00.txt' if meta.get('is_disc') == 'BDMV' else 'MEDIAINFO.txt'}"
        with open(mi_path, 'r', encoding='utf-8') as f:
            mediainfo_dump = f.read()

        is_anonymous = "1" if meta['anon'] != 0 or self.config['TRACKERS'][self.tracker].get('anon', False) else "0"

        data = {
            'category': cat_id,
            'imdbId': imdb,
            'nfo': description,
            'mediainfo': mediainfo_dump,
            'reqid': "0",
            'section': "new",
            'frileech': "1",
            'anonymousUpload': is_anonymous,
            'p2p': "0"
        }

        torrent_path = f"{meta['base_dir']}/tmp/{meta['uuid']}/[{self.tracker}].torrent"

        try:
            is_scene = bool(meta.get('scene_name'))
            base_name = meta['scene_name'] if is_scene else meta['uuid']

            existing_torrents = await self.search_existing(meta, disctype)
            needs_unrar_tag = False

            if existing_torrents:
                current_release_identifiers = {meta['uuid']}
                if is_scene:
                    current_release_identifiers.add(meta['scene_name'])

                relevant_torrents = [
                    t for t in existing_torrents
                    if t.get('name') in current_release_identifiers
                ]

                if relevant_torrents:
                    unrar_version_exists = any(t.get('unrar', 0) != 0 for t in relevant_torrents)

                    if unrar_version_exists:
                        raise UploadException("An UNRAR duplicate of this specific release already exists on site.")
                    else:
                        console.print(f"[bold yellow]Found a RAR version of this release on {self.tracker}. Appending [UNRAR] to filename.[/bold yellow]")
                        needs_unrar_tag = True

            if needs_unrar_tag:
                upload_base_name = meta['scene_name'] if is_scene else meta['uuid']
                upload_filename = f"{upload_base_name} [UNRAR].torrent"
            else:
                upload_filename = f"{base_name}.torrent"

            with open(torrent_path, 'rb') as torrent_file:
                files = {'file': (upload_filename, torrent_file, "application/x-bittorrent")}
                upload_url = f"{self.api_base_url}/torrents/upload"

                if meta['debug'] is False:
                    response = self.session.post(upload_url, data=data, files=files, cookies=self.auth_cookies, timeout=90)
                    response.raise_for_status()
                    json_response = response.json()
                    meta['tracker_status'][self.tracker]['status_message'] = response.json()

                    if response.status_code == 200 and json_response.get('id'):
                        torrent_id = json_response.get('id')
                        details_url = f"{self.base_url}/torrent/{torrent_id}/" if torrent_id else self.base_url
                        if torrent_id:
                            meta['tracker_status'][self.tracker]['torrent_id'] = torrent_id
                        announce_url = self.config['TRACKERS'][self.tracker].get('announce_url')
                        await self.add_tracker_torrent(meta, self.tracker, self.source_flag, announce_url, details_url)
                    else:
                        raise UploadException(f"{json_response.get('message', 'Unknown API error.')}")
                else:
                    console.print(f"[bold blue]Debug Mode: Upload to {self.tracker} was not sent.[/bold blue]")
                    console.print("Headers:", self.session.headers)
                    console.print("Payload (data):", data)

        except UploadException:
            raise
        except Exception as e:
            raise UploadException(f"An unexpected error occurred during upload to {self.tracker}: {e}")
