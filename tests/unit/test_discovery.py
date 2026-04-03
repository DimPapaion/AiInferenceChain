"""
Unit tests for core/network/discovery.py (PeerDiscovery).
"""

import pytest

from core.network.discovery import PeerDiscovery, MAX_FAILURES


class TestPeerDiscovery:
    def test_add_peer(self, tmp_path):
        d = PeerDiscovery(seed_file=tmp_path / "peers.txt")
        d.add("http://peer1:8000")
        assert "http://peer1:8000" in d.all_peers()

    def test_add_is_idempotent(self, tmp_path):
        d = PeerDiscovery(seed_file=tmp_path / "peers.txt")
        d.add("http://peer1:8000")
        d.add("http://peer1:8000")
        assert len(d) == 1

    def test_trailing_slash_normalised(self, tmp_path):
        d = PeerDiscovery(seed_file=tmp_path / "peers.txt")
        d.add("http://peer1:8000/")
        assert "http://peer1:8000" in d.all_peers()

    def test_remove_peer(self, tmp_path):
        d = PeerDiscovery(seed_file=tmp_path / "peers.txt")
        d.add("http://peer1:8000")
        d.remove("http://peer1:8000")
        assert len(d) == 0

    def test_mark_failure_removes_after_max(self, tmp_path):
        d = PeerDiscovery(seed_file=tmp_path / "peers.txt")
        d.add("http://flaky:8000")
        for _ in range(MAX_FAILURES):
            d.mark_failure("http://flaky:8000")
        assert "http://flaky:8000" not in d.all_peers()

    def test_mark_success_resets_failure_count(self, tmp_path):
        d = PeerDiscovery(seed_file=tmp_path / "peers.txt")
        d.add("http://peer1:8000")
        for _ in range(MAX_FAILURES - 1):
            d.mark_failure("http://peer1:8000")
        d.mark_success("http://peer1:8000")
        # One more failure should NOT remove (count was reset)
        d.mark_failure("http://peer1:8000")
        assert "http://peer1:8000" in d.all_peers()

    def test_persists_to_file(self, tmp_path):
        seed = tmp_path / "peers.txt"
        d1 = PeerDiscovery(seed_file=seed)
        d1.add("http://peer1:8000")
        d1.add("http://peer2:8001")

        # New instance should reload from file
        d2 = PeerDiscovery(seed_file=seed)
        assert "http://peer1:8000" in d2.all_peers()
        assert "http://peer2:8001" in d2.all_peers()

    def test_seed_file_comments_ignored(self, tmp_path):
        seed = tmp_path / "peers.txt"
        seed.write_text("# comment\nhttp://peer1:8000\n# another comment\n")
        d = PeerDiscovery(seed_file=seed)
        assert "http://peer1:8000" in d.all_peers()
        assert len(d) == 1

    def test_extra_peers_from_constructor(self, tmp_path):
        d = PeerDiscovery(
            seed_file   = tmp_path / "peers.txt",
            extra_peers = ["http://extra:9000"],
        )
        assert "http://extra:9000" in d.all_peers()

    def test_seed_peers_returns_all(self, tmp_path):
        d = PeerDiscovery(seed_file=tmp_path / "peers.txt")
        d.add("http://a:8000")
        d.add("http://b:8001")
        assert set(d.seed_peers()) == {"http://a:8000", "http://b:8001"}
