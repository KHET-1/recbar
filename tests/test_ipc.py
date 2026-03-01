"""Tests for recbar.ipc — Unix socket IPC."""

import os

import pytest

from recbar.ipc import IPCServer, send_command


@pytest.fixture
def ipc_pair(tmp_path):
    """Create an IPC server/client pair using a temp socket path."""
    sock_path = str(tmp_path / "test_recbar.sock")
    server = IPCServer(path=sock_path)
    server.start()
    yield server, sock_path
    server.stop()


def test_send_and_receive(ipc_pair):
    """Commands sent via send_command are received by the server."""
    server, path = ipc_pair
    assert send_command("rec", path=path)
    cmd = server.recv()
    assert cmd == "rec"


def test_recv_empty(ipc_pair):
    """recv() returns None when no commands pending."""
    server, _ = ipc_pair
    assert server.recv() is None


def test_recv_all_drains(ipc_pair):
    """recv_all() drains all pending commands."""
    server, path = ipc_pair
    send_command("cmd1", path=path)
    send_command("cmd2", path=path)
    send_command("cmd3", path=path)
    cmds = server.recv_all()
    assert len(cmds) == 3
    assert cmds == ["cmd1", "cmd2", "cmd3"]


def test_recv_all_empty(ipc_pair):
    """recv_all() returns empty list when nothing pending."""
    server, _ = ipc_pair
    assert server.recv_all() == []


def test_send_to_nonexistent():
    """Sending to a nonexistent socket returns False."""
    assert not send_command("test", path="/tmp/nonexistent_recbar_test.sock")


def test_server_cleanup(tmp_path):
    """Server removes socket file on stop."""
    sock_path = str(tmp_path / "cleanup_test.sock")
    server = IPCServer(path=sock_path)
    server.start()
    assert os.path.exists(sock_path)
    server.stop()
    assert not os.path.exists(sock_path)


def test_no_message_loss(ipc_pair):
    """Rapid-fire commands don't lose messages (unlike file-based IPC)."""
    server, path = ipc_pair
    count = 50
    for i in range(count):
        send_command(f"cmd_{i}", path=path)
    cmds = server.recv_all()
    assert len(cmds) == count
    assert cmds == [f"cmd_{i}" for i in range(count)]
