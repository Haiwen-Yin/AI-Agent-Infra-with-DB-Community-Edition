import zipfile
import json

import pytest

import verify_deps


@pytest.fixture
def dependency_package(tmp_path, monkeypatch):
    (tmp_path / "build-manifest.json").write_text(json.dumps({"delivery_product": {
        "databases": ["oracle", "pg", "yashandb"]}}))
    (tmp_path / "requirements").mkdir()
    (tmp_path / "requirements.txt").write_text("httpx==0.28.1\n")
    for database, driver in (("oracle", "oracledb"), ("pg", "psycopg2-binary"), ("yashandb", "yaspy")):
        (tmp_path / "requirements" / (database + ".txt")).write_text(driver + ">=1.0\nhttpx==0.28.1\n")
    config = tmp_path / "config.json"
    config.write_text('{"database":{"type":"pg"}}')
    monkeypatch.setenv("CX_CONFIG_PATH", str(config))
    monkeypatch.delenv("CX_DATABASE_DIALECT", raising=False)
    monkeypatch.delenv("CX_REQUIREMENTS_FILE", raising=False)
    return tmp_path


def test_verifier_automatically_includes_configured_database_driver(dependency_package):
    root = dependency_package
    assert verify_deps._requirements_path(root, root / "scripts") == root / "requirements/pg.txt"


def test_verifier_cannot_override_selected_profile_with_shared_subset(dependency_package, monkeypatch):
    root = dependency_package
    monkeypatch.setenv("CX_REQUIREMENTS_FILE", str(root / "requirements.txt"))
    with pytest.raises(ValueError, match="differ"):
        verify_deps._requirements_path(root, root / "scripts")


def test_verifier_rejects_cli_config_conflict(dependency_package):
    root = dependency_package
    with pytest.raises(ValueError, match="Conflicting"):
        verify_deps._requirements_path(root, root / "scripts", database="oracle")


def test_verifier_does_not_report_success_without_backend_selection(dependency_package):
    root = dependency_package
    (root / "config.json").unlink()
    with pytest.raises(ValueError, match="Select database.type"):
        verify_deps._requirements_path(root, root / "scripts")


def test_verifier_cannot_use_another_backends_profile(dependency_package, monkeypatch):
    root = dependency_package
    monkeypatch.setenv("CX_REQUIREMENTS_FILE", str(root / "requirements/oracle.txt"))
    with pytest.raises(ValueError, match="differ"):
        verify_deps._requirements_path(root, root / "scripts")


def test_verifier_rejects_driver_that_pip_would_skip(dependency_package):
    root = dependency_package
    (root / "requirements/pg.txt").write_text("psycopg2-binary>=2.9; python_version < '3.0'\nhttpx==0.28.1\n")
    with pytest.raises(ValueError, match="must be unconditional"):
        verify_deps._requirements_path(root, root / "scripts")


def _metadata_wheel(tmp_path, package, version, requirements=()):
    filename = f"{package.replace('-', '_')}-{version}-py3-none-any.whl"
    path = tmp_path / filename
    metadata = [
        "Metadata-Version: 2.1",
        f"Name: {package}",
        f"Version: {version}",
        *(f"Requires-Dist: {requirement}" for requirement in requirements),
        "",
    ]
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(
            f"{package.replace('-', '_')}-{version}.dist-info/METADATA",
            "\n".join(metadata),
        )
    return {
        "version": version,
        "file": filename,
        "path": str(path),
        "floor": None,
    }


def test_platform_floor_understands_legacy_and_modern_manylinux_tags():
    assert verify_deps._wheel_platform_floor("pkg-1-cp314-cp314-manylinux2014_x86_64.whl") == (2, 17)
    assert verify_deps._wheel_platform_floor("pkg-1-cp314-cp314-manylinux_2_28_x86_64.whl") == (2, 28)
    assert verify_deps._wheel_platform_floor("pkg-1-py3-none-any.whl") is None


def test_full_platform_baseline_is_glibc_2_34():
    assert verify_deps.MIN_GLIBC == (2, 34)
    legacy = "cryptography-49.0.0-cp314-abi3-manylinux_2_28_x86_64.whl"
    current = "cryptography-49.0.0-cp311-abi3-manylinux_2_34_x86_64.whl"
    assert verify_deps._wheel_is_platform_compatible(current, (2, 34))
    assert not verify_deps._wheel_is_platform_compatible(current, (2, 33))
    assert verify_deps._wheel_is_platform_compatible(legacy, (2, 34))


def test_newer_host_can_use_the_upstream_cryptography_wheel():
    newer_host = (2, 35)
    upstream = "cryptography-49.0.0-cp311-abi3-manylinux_2_34_x86_64.whl"

    assert verify_deps._wheel_is_platform_compatible(upstream, newer_host)


def test_platform_check_rejects_a_native_wheel_for_another_operating_system():
    windows = "package-1.0-cp314-cp314-win_amd64.whl"
    assert not verify_deps._wheel_is_platform_compatible(windows, (2, 28), (3, 14))


def test_python_wheel_tags_follow_the_active_python_minor():
    abi3 = "cryptography-49.0.0-cp311-abi3-manylinux_2_28_x86_64.whl"
    exact_314 = "pydantic_core-2.46.4-cp314-cp314-manylinux_2_17_x86_64.whl"
    exact_315 = "pydantic_core-2.46.4-cp315-cp315-manylinux_2_17_x86_64.whl"

    assert verify_deps._wheel_is_python_compatible(abi3, (3, 15))
    assert not verify_deps._wheel_is_python_compatible(exact_314, (3, 15))
    assert verify_deps._wheel_is_python_compatible(exact_315, (3, 15))


def test_marker_evaluator_handles_platform_and_extra_markers():
    assert not verify_deps._marker_applies_to_runtime(
        "sys_platform == 'win32' and python_version >= '3.14'", (3, 14)
    )
    assert not verify_deps._marker_applies_to_runtime(
        "platform_python_implementation == 'CPython' and extra == 'cli'", (3, 14)
    )
    assert verify_deps._marker_applies_to_runtime(
        "sys_platform != 'win32' and python_version >= '3.14'", (3, 14)
    )


def test_dependency_closure_fails_for_missing_transitive_wheel(tmp_path):
    root = _metadata_wheel(
        tmp_path,
        "root-pkg",
        "1.0.0",
        ["argon2-cffi-bindings>=21.2.0"],
    )
    errors, dependencies = verify_deps._dependency_closure(
        {"root-pkg": [root]},
        {"root-pkg": root},
        (2, 28),
        (3, 14),
    )

    assert dependencies == {"argon2-cffi-bindings"}
    assert len(errors) == 1
    assert "argon2-cffi-bindings>=21.2.0" in errors[0]
    assert "no wheel in vendor/" in errors[0]


def test_dependency_closure_respects_direct_pin_and_platform_markers(tmp_path):
    root = _metadata_wheel(
        tmp_path,
        "root-pkg",
        "1.0.0",
        [
            "dep-pkg>=2.0.0",
            "windows-pkg>=1.0.0; sys_platform == 'win32'",
        ],
    )
    direct = _metadata_wheel(tmp_path, "dep-pkg", "1.0.0")
    errors, dependencies = verify_deps._dependency_closure(
        {"root-pkg": [root], "dep-pkg": [direct]},
        {"root-pkg": root, "dep-pkg": direct},
        (2, 28),
        (3, 14),
    )

    assert dependencies == {"dep-pkg"}
    assert len(errors) == 1
    assert "selected direct pin" in errors[0]


def test_yaspy_native_module_requires_matching_cpython_minor(tmp_path):
    vendor = tmp_path / "vendor" / "yaspy" / "client_lib"
    vendor.mkdir(parents=True)
    (vendor / "libyas_infra.so").write_bytes(b"native")
    (vendor.parent / "yaspy.cpython-314-x86_64-linux-gnu.so").write_bytes(b"native")

    assert verify_deps._verify_yaspy_vendor(str(tmp_path / "vendor"), (3, 14))[0]
    ok, errors = verify_deps._verify_yaspy_vendor(str(tmp_path / "vendor"), (3, 15))
    assert not ok
    assert "Python 3.15" in " ".join(errors)


def test_wheel_metadata_validation_rejects_missing_integrity_files(tmp_path):
    wheel = _metadata_wheel(tmp_path, "demo-pkg", "1.0.0")
    errors = verify_deps._validate_wheel(
        wheel["path"], wheel["file"], (3, 14)
    )
    assert "wheel is missing dist-info/WHEEL" in errors
    assert "wheel is missing dist-info/RECORD" in errors
