from playlist_forge.actions import merge_playlists


def test_merge_creates_empty_destination_when_no_source_playlists(monkeypatch):
    captured: dict = {}

    monkeypatch.setattr(
        merge_playlists.spotify_client,
        "create_playlist",
        lambda spotify, name, track_ids, description="", public=False, dry_run=False: captured.update(
            {
                "spotify": spotify,
                "name": name,
                "track_ids": track_ids,
                "description": description,
                "public": public,
                "dry_run": dry_run,
            }
        )
        or "new-playlist-id",
    )
    monkeypatch.setattr(
        merge_playlists.spotify_client,
        "list_playlists",
        lambda _spotify: (_ for _ in ()).throw(AssertionError("list_playlists should not be called")),
    )

    spotify = object()
    created = merge_playlists.merge(spotify, [], "Empty Playlist", dry_run=True)

    assert created == "new-playlist-id"
    assert captured == {
        "spotify": spotify,
        "name": "Empty Playlist",
        "track_ids": [],
        "description": "",
        "public": False,
        "dry_run": True,
    }
