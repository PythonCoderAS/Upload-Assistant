# -*- coding: utf-8 -*-
import os
import re
from xml.etree import ElementTree

import requests
from src.exceptions import UploadException
from src.console import console
from src.languages import has_english_language, has_language, has_language_other_than, process_desc_language
from src.rehostimages import check_hosts
from .COMMON import COMMON
from torf import Torrent
from aiohttp import ClientSession, FormData


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
        self.signature = ""

    async def edit_torrent(self, meta, tracker, source_flag, torrent_filename="BASE"):
        if os.path.exists(f"{meta['base_dir']}/tmp/{meta['uuid']}/{torrent_filename}.torrent"):
            new_torrent = Torrent.read(f"{meta['base_dir']}/tmp/{meta['uuid']}/{torrent_filename}.torrent")
            for each in list(new_torrent.metainfo):
                if each not in ('announce', 'comment', 'creation date', 'created by', 'encoding', 'info'):
                    new_torrent.metainfo.pop(each, None)
            new_torrent.metainfo['announce'] = self.announce_url

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
                screenshots_block += f"[![Screenshot]({img_url})]({web_url}) "
            desc_parts.append(screenshots_block)

        # BDInfo
        tech_info = ""
        if meta.get('is_disc') == 'BDMV':
            bd_summary_file = f"{meta['base_dir']}/tmp/{meta['uuid']}/BD_SUMMARY_00.txt"
            if os.path.exists(bd_summary_file):
                with open(bd_summary_file, 'r', encoding='utf-8') as f:
                    tech_info = f.read()

        if not meta.get('audio_languages') or not meta.get('subtitle_languages'):
            await process_desc_language(meta, desc=None, tracker=self.tracker)

        if meta.get("subtitle_languages", []):
            sub_languages = '\n'.join(f"- {lang}" for lang in meta["subtitle_languages"])
            desc_parts.append(f"## Subtitles\n{sub_languages}\n")

        if tech_info:
            desc_parts.append(f"## BD Info\n```\n{tech_info}\n```\n")

        mediainfo_file = f"{meta['base_dir']}/tmp/{meta['uuid']}/MEDIAINFO.txt"
        if os.path.exists(mediainfo_file):
            with open(mediainfo_file, 'r', encoding='utf-8') as f:
                mediainfo_content = f.read()
            mediainfo_pieces = mediainfo_content.split('\n\n')
            kept_pieces = []
            for mediainfo_piece, mediainfo_piece_json in zip(mediainfo_pieces, meta["mediainfo"]["media"]["track"]):
                if mediainfo_piece_json["@type"] in ["General", "Video", "Audio"]:
                    kept_pieces.append(mediainfo_piece)
            desc_parts.append(f"## MediaInfo\n```\n{"\n\n".join(kept_pieces)}\n```\n")

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

        if not meta.get('audio_languages') or not meta.get('subtitle_languages'):
            await process_desc_language(meta, desc=None, tracker=self.tracker)

        has_english_audio_or_sub = await has_english_language(meta.get('audio_languages')) or await has_english_language(meta.get('subtitle_languages'))
        has_non_japanese = await has_language_other_than(meta.get('audio_languages'), 'japanese') or await has_language_other_than(meta.get('subtitle_languages'), 'japanese')

        if has_english_audio_or_sub:
            return "1_2"
        elif has_non_japanese:
            return "1_3"
        else:
            return "1_4"

    async def validate_credentials(self, meta):
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

        search_url = f"{self.base_url}/"
        search_params = {'q': meta["name"], "page": "rss"}

        try:
            async with self.session.get(search_url, params=search_params, timeout=15) as response:
                response.raise_for_status()

                if text := await response.text():
                    root = ElementTree.fromstring(text)

                    # 3. Find all items, accommodating both RSS (<item>) and Atom (<entry>)
                    # The './/' prefix searches the entire tree for the tag.
                    items = root.findall('.//item') + root.findall('.//entry')

                    titles = []
                    for item in items:
                        # Find the 'title' tag within each item/entry
                        title_element = item.find('title')
                        if title_element is not None and title_element.text:
                            titles.append(title_element.text.strip())

                    return titles

        except Exception as e:
            console.print(f"[bold red]Error searching for '{search_params["q"]}' on {self.tracker}: {e}[/bold red]")

        return []

    async def add_tracker_torrent(self, meta, tracker, source_flag, new_tracker, comment):
        if os.path.exists(f"{meta['base_dir']}/tmp/{meta['uuid']}/[{tracker}].torrent"):
            new_torrent = Torrent.read(f"{meta['base_dir']}/tmp/{meta['uuid']}/[{tracker}].torrent")
            new_torrent.metainfo['announce'] = new_tracker
            new_torrent.metainfo['comment'] = comment
            Torrent.copy(new_torrent).write(f"{meta['base_dir']}/tmp/{meta['uuid']}/[{tracker}].torrent", overwrite=True)

    async def upload(self, meta, disctype):
        await self.edit_torrent(meta, self.tracker, self.source_flag)

        cat_id = await self.get_category_id(meta)

        approved_image_hosts = ['imgbox', 'imgbb', "bhd", "imgur", "postimg"]
        url_host_mapping = {
            "ibb.co": "imgbb",
            "imgbox.com": "imgbox",
            "beyondhd.co": "bhd",
            "imgur.com": "imgur",
            "postimg.cc": "postimg"
        }

        await check_hosts(meta, self.tracker, url_host_mapping=url_host_mapping, img_host_index=1, approved_image_hosts=approved_image_hosts)

        await self.generate_description(meta)

        description_path = f"{meta['base_dir']}/tmp/{meta['uuid']}/[{self.tracker}]DESCRIPTION.txt"
        with open(description_path, 'r', encoding='utf-8') as f:
            description = f.read()

        is_anonymous = meta['anon'] != 0 or self.config['TRACKERS'][self.tracker].get('anon', False)
        is_pack = bool(meta.get('tv_pack', 0))
        is_remake = bool(meta.get("repack", ""))

        display_name = meta['name']
        if tag == "-SubsPlease" and is_pack:
            display_name = f'{meta["uuid"]} [Unofficial Batch]'

        data = {
            'display_name': display_name,
            'category': cat_id,
            'information': f"https://myanimelist.net/anime/{meta['mal']}" if meta.get('mal') else '',
            "description": description,
        }

        if is_anonymous:
            data['is_anonymous'] = 'y'
        if is_pack:
            data['is_complete'] = 'y'
        if is_remake:
            data['is_remake'] = 'y'

        torrent_path = f"{meta['base_dir']}/tmp/{meta['uuid']}/[{self.tracker}].torrent"

        upload_filename = f"{meta['name']}.torrent"
        try:
            with open(torrent_path, 'rb') as torrent_file:
                form_data = FormData()
                for key, value in data.items():
                    form_data.add_field(key, value)
                # files = {'torrent_file': (upload_filename, torrent_file, "application/x-bittorrent")}
                form_data.add_field("torrent_file", torrent_file, filename=upload_filename)
                upload_url = f"{self.base_url}/upload"

                if meta['debug'] is False:
                    async with self.session.post(upload_url, data=form_data, timeout=90, allow_redirects=True) as response:
                        with open(f"{meta['base_dir']}/tmp/{meta['uuid']}/upload_response.html", 'w', encoding='utf-8') as f:
                            f.write(await response.text())
                        response.raise_for_status()
                        details_url = str(response.url)
                        torrent_id = int(re.search(r'/view/(\d+)', str(details_url)).group(1))
                        meta['tracker_status'][self.tracker]['torrent_id'] = torrent_id
                        announce_url = self.announce_url
                        await self.add_tracker_torrent(meta, self.tracker, self.source_flag, announce_url, details_url)
                else:
                    console.print(f"[bold blue]Debug Mode: Upload to {self.tracker} was not sent.[/bold blue]")
                    console.print("Headers:", self.session.headers)
                    console.print("Payload (data):", data)
        except Exception as e:
            raise UploadException(f"An unexpected error occurred during upload to {self.tracker}: {e}")
        finally:
            await self.session.close()
