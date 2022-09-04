from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING, TypeVar

import asyncstdlib
from asyncstdlib import heapq
from discord.app_commands import Choice, Transformer
from discord.ext import commands
from rapidfuzz import fuzz

from pylav.types import ContextT, InteractionT
from pylav.utils import shorten_string

try:
    from redbot.core.i18n import Translator

    _ = Translator("PyLavPlayer", Path(__file__))
except ImportError:
    _ = lambda x: x

if TYPE_CHECKING:
    from pylav.sql.models import PlaylistModel

    PlaylistConverter = TypeVar("PlaylistConverter", bound=list[PlaylistModel])
else:

    class PlaylistConverter(Transformer):
        @classmethod
        async def convert(cls, ctx: ContextT, arg: str) -> list[PlaylistModel]:
            """Converts a playlist name or ID to a list of matching objects"""
            from pylav import EntryNotFoundError

            try:
                playlists = await ctx.lavalink.playlist_db_manager.get_playlist_by_name_or_id(arg)
            except EntryNotFoundError as e:
                raise commands.BadArgument(_("Playlist with name or id `{arg}` not found").format(arg=arg)) from e
            return playlists

        @classmethod
        async def transform(cls, interaction: InteractionT, argument: str) -> list[PlaylistModel]:
            if not interaction.response.is_done():
                await interaction.response.defer(ephemeral=True)
            ctx = await interaction.client.get_context(interaction)
            return await cls.convert(ctx, argument)

        @classmethod
        async def autocomplete(cls, interaction: InteractionT, current: str) -> list[Choice]:
            from pylav import EntryNotFoundError

            try:
                playlists: list[
                    PlaylistModel
                ] = await interaction.client.lavalink.playlist_db_manager.get_playlist_by_name(current, limit=50)
            except EntryNotFoundError:
                return []
            if not current:
                return [Choice(name=shorten_string(e.name, max_length=100), value=f"{e.id}") for e in playlists][:25]

            async def _filter(c: PlaylistModel):
                return await asyncio.to_thread(fuzz.token_set_ratio, current, c.name)

            extracted = await heapq.nlargest(asyncstdlib.iter(playlists), n=25, key=_filter)

            return [Choice(name=shorten_string(e.name, max_length=100), value=f"{e.id}") for e in extracted]
