"""Exercise the real shell entry point without creating Docker resources."""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]


def bash_path(path):
    value = path.resolve().as_posix()
    if os.name == "nt":
        return "/" + value[0].lower() + value[2:]
    return value


def invoke_runner(
    tmp_path,
    *,
    run_status=0,
    build_status=0,
    up_status=0,
    cleanup_status=0,
    endpoint="unix:///var/run/docker.sock",
    docker_host=None,
    docker_context=None,
):
    bash = shutil.which("bash")
    if os.name == "nt":
        git_bash = Path("C:/Program Files/Git/bin/bash.exe")
        if git_bash.is_file():
            bash = str(git_bash)
    if not bash:
        pytest.skip("Bash is required for runner-boundary regressions")
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    log = tmp_path / "calls.bin"
    shim = """#!/usr/bin/env bash
printf '\\036' >> "$FAKE_DOCKER_LOG"
printf '%s\\0' "$@" >> "$FAKE_DOCKER_LOG"
if [[ "$1" == "context" ]]; then printf '%s\\n' "$FAKE_DOCKER_ENDPOINT"; exit 0; fi
if [[ "$*" == *"ps"* ]]; then printf 'Up\\n'; fi
if [[ " $* " == *" build "* ]]; then exit "$FAKE_BUILD_STATUS"; fi
if [[ " $* " == *" up "* ]]; then exit "$FAKE_UP_STATUS"; fi
if [[ " $* " == *" run "* ]]; then exit "$FAKE_RUN_STATUS"; fi
if [[ " $* " == *" down "* ]]; then exit "$FAKE_CLEANUP_STATUS"; fi
exit 0
"""
    for name in ("docker", "docker-compose"):
        executable = fake_bin / name
        executable.write_text(shim, encoding="utf-8", newline="\n")
        executable.chmod(0o755)
    environment = os.environ.copy()
    for key in ("DOCKER_HOST", "DOCKER_CONTEXT"):
        environment.pop(key, None)
    if docker_host is not None:
        environment["DOCKER_HOST"] = docker_host
    if docker_context is not None:
        environment["DOCKER_CONTEXT"] = docker_context
    environment.update(
        FAKE_BIN=bash_path(fake_bin),
        FAKE_DOCKER_LOG=bash_path(log),
        FAKE_RUN_STATUS=str(run_status),
        FAKE_BUILD_STATUS=str(build_status),
        FAKE_UP_STATUS=str(up_status),
        FAKE_CLEANUP_STATUS=str(cleanup_status),
        FAKE_DOCKER_ENDPOINT=endpoint,
        RUNNER=bash_path(REPO / "scripts/test.sh"),
    )
    result = subprocess.run(
        [
            bash,
            "--noprofile",
            "--norc",
            "-c",
            'export PATH="$FAKE_BIN:$PATH"; bash "$RUNNER"',
        ],
        cwd=REPO,
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
    )
    calls = [
        [argument.decode() for argument in entry.split(b"\0") if argument]
        for entry in log.read_bytes().split(b"\x1e")
        if entry
    ]
    return result, calls


@pytest.mark.parametrize(
    "run_status,build_status,up_status,cleanup_status",
    [
        (0, 0, 0, 0),
        (17, 0, 0, 0),
        (0, 13, 0, 0),
        (0, 0, 19, 0),
        (0, 0, 0, 23),
        (17, 0, 0, 23),
    ],
)
def test_runner_uses_only_its_disposable_project(
    tmp_path, run_status, build_status, up_status, cleanup_status
):
    """Application exec/start or unscoped cleanup must fail this boundary test."""
    result, calls = invoke_runner(
        tmp_path,
        run_status=run_status,
        build_status=build_status,
        up_status=up_status,
        cleanup_status=cleanup_status,
    )
    expected_status = build_status or up_status or run_status or bool(cleanup_status)
    assert result.returncode == expected_status, result.stderr
    operations = [
        call
        for call in calls
        if call[0] != "context" and call != ["compose", "version"]
    ]
    assert operations
    projects = set()
    for call in operations:
        assert call[0] == "compose"
        assert "-f" in call and "-p" in call
        assert call[call.index("-f") + 1].endswith("docker-compose.test.yml")
        project = call[call.index("-p") + 1]
        assert project.startswith("fluxvpn-tests-")
        projects.add(project)
        assert "exec" not in call
        assert "worker-api" not in call
        assert "prune" not in call
    assert len(projects) == 1
    cleanup = operations[-1]
    assert "down" in cleanup
    assert "--volumes" in cleanup
    if not build_status and not up_status:
        assert any("run" in call and "worker-tests" in call for call in operations)


def test_runner_refuses_remote_docker_context_before_build(tmp_path):
    result, calls = invoke_runner(tmp_path, endpoint="tcp://remote.invalid:2376")
    assert result.returncode != 0
    assert "local Docker" in result.stderr
    assert not any("build" in call or "up" in call or "run" in call for call in calls)
    assert "remote.invalid" not in result.stderr


def test_fake_docker_does_not_inherit_real_host(tmp_path, monkeypatch):
    monkeypatch.delenv("DOCKER_CONTEXT", raising=False)
    monkeypatch.setenv("DOCKER_HOST", "tcp://ambient.invalid:2376")
    result, _ = invoke_runner(tmp_path)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    "docker_host,docker_context,endpoint,allowed",
    [
        ("tcp://remote.invalid:2376", None, "unix:///tmp/local.sock", False),
        ("unix:///tmp/local.sock", None, "tcp://remote.invalid:2376", True),
        ("unix:///tmp/local.sock", "selected", "tcp://remote.invalid:2376", False),
        (None, "selected", "unix:///tmp/local.sock", True),
    ],
)
def test_runner_respects_explicit_docker_selection(
    tmp_path, docker_host, docker_context, endpoint, allowed
):
    result, calls = invoke_runner(
        tmp_path,
        docker_host=docker_host,
        docker_context=docker_context,
        endpoint=endpoint,
    )
    assert (result.returncode == 0) is allowed
    if not allowed:
        assert not any(
            "build" in call or "up" in call or "run" in call for call in calls
        )
