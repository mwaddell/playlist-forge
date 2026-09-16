from playlist_forge import cache


def test_getgenre_uses_dedicated_cache_file(monkeypatch, tmp_path):
    cache_dir = tmp_path / "cache"
    monkeypatch.setattr(cache, "CACHE_DIR", cache_dir)

    cache.set(cache.CacheType.RECCOBEATS, "track:one", {"tempo": 120.0})
    cache.set(cache.CacheType.GETGENRE, "track:one", {"genres": ["indie"]})

    assert (cache_dir / "enrichment.sqlite3").exists()
    assert (cache_dir / "getgenre.sqlite3").exists()
