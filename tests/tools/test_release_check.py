import zipfile

from tools.release_check import REQUIRED_PACKAGE_FILES, check_release_artifacts


def make_release(tmp_path, *, version="9.9.9", missing_zip_entry=None):
    release_dir = tmp_path / "release"
    package_dir = release_dir / "Bemanning"
    package_dir.mkdir(parents=True)

    for relative in REQUIRED_PACKAGE_FILES:
        path = package_dir / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("x", encoding="utf-8")

    setup_path = release_dir / f"Bemanning-{version}-Setup.exe"
    setup_path.write_bytes(b"setup")

    zip_path = release_dir / f"Bemanning-{version}-win64.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
        for relative in REQUIRED_PACKAGE_FILES:
            if relative == missing_zip_entry:
                continue
            archive.write(package_dir / relative, arcname=relative)

    return release_dir


def test_release_check_accepts_complete_package(tmp_path):
    release_dir = make_release(tmp_path)

    errors = check_release_artifacts(
        release_dir=release_dir,
        version="9.9.9",
        require_setup=True,
        smoke=False,
    )

    assert errors == []


def test_release_check_reports_missing_frontend_in_zip(tmp_path):
    release_dir = make_release(
        tmp_path,
        missing_zip_entry="_internal/app/frontend/js/productivity.js",
    )

    errors = check_release_artifacts(
        release_dir=release_dir,
        version="9.9.9",
        require_setup=True,
        smoke=False,
    )

    assert "Saknar fil i zip: _internal/app/frontend/js/productivity.js" in errors

